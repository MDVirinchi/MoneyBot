"""
rs_momentum.py — Relative Strength Momentum Strategy.

Core idea (Jegadeesh & Titman, 1993 — replicated on NSE):
  Stocks with high excess return vs market over the past 3 months continue
  to outperform for 1-3 months. Buy strength, not weakness.

Implementation:
  - Score = stock 63-day return minus Nifty 63-day return (excess return)
  - Monthly rebalance (every 21 trading days)
  - Buy top N stocks by RS score with price above 20-day high (trend gate)
  - Exit: monthly rebalance (RS rank drops) OR hard stop-loss 8%
  - Equal-weight portfolio, Rs.5,00,000 total capital

Walk-forward: Y1-Y3 in-sample (60%) | Y4-Y5 out-of-sample (40%)

Comparison benchmarks:
  RSI<30 (S3)       : OOS PF=0.876  (from s3_validation.py)
  Compression B     : OOS PF=0.996  (from compression_breakout.py)
  Buy-and-hold Nifty: benchmark return

Parameter sweep:
  RS lookback : 42, 63, 126 days  (2M, 3M, 6M)
  Top N held  : 5, 8, 10 stocks
  Trend gate  : with / without 20-day high filter
"""

import time, math, logging, warnings, statistics
from collections import defaultdict, Counter
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

# ── Cost model ────────────────────────────────────────────────────────────────
BROKERAGE    = 20.0
STT_PCT      = 0.001
EXCHANGE_PCT = 0.0000345
SLIPPAGE     = 0.002
TOTAL_CAPITAL = 500_000.0   # Rs.5 lakh total portfolio
SL_PCT        = 8.0         # momentum stop — wider than mean reversion
WF_SPLIT      = 0.60        # 60% IS, 40% OOS

SEP = '=' * 112
sep = '-' * 112

STOCKS = [
    ('RELIANCE.NS','RELIANCE'),('TCS.NS','TCS'),('INFY.NS','INFY'),
    ('HDFCBANK.NS','HDFCBANK'),('ICICIBANK.NS','ICICIBANK'),('SBIN.NS','SBIN'),
    ('HCLTECH.NS','HCLTECH'),('WIPRO.NS','WIPRO'),('AXISBANK.NS','AXISBANK'),
    ('KOTAKBANK.NS','KOTAKBANK'),('TECHM.NS','TECHM'),('MARUTI.NS','MARUTI'),
    ('TITAN.NS','TITAN'),('BAJFINANCE.NS','BAJFINANCE'),('ITC.NS','ITC'),
    ('HINDUNILVR.NS','HINDUNILVR'),('BHARTIARTL.NS','BHARTIARTL'),
    ('ASIANPAINT.NS','ASIANPAINT'),('SUNPHARMA.NS','SUNPHARMA'),
    ('DRREDDY.NS','DRREDDY'),('CIPLA.NS','CIPLA'),('POWERGRID.NS','POWERGRID'),
    ('NTPC.NS','NTPC'),('COALINDIA.NS','COALINDIA'),('ONGC.NS','ONGC'),
    ('BPCL.NS','BPCL'),('ULTRACEMCO.NS','ULTRACEMCO'),('GRASIM.NS','GRASIM'),
    ('ADANIENT.NS','ADANIENT'),('ADANIPORTS.NS','ADANIPORTS'),
    ('BAJAJFINSV.NS','BAJAJFINSV'),('EICHERMOT.NS','EICHERMOT'),
    ('TATACONSUM.NS','TATACONSUM'),('BRITANNIA.NS','BRITANNIA'),
    ('APOLLOHOSP.NS','APOLLOHOSP'),('JSWSTEEL.NS','JSWSTEEL'),
    ('TATASTEEL.NS','TATASTEEL'),('HINDALCO.NS','HINDALCO'),('LT.NS','LT'),
    ('NESTLEIND.NS','NESTLEIND'),('PIDILITIND.NS','PIDILITIND'),
    ('HAVELLS.NS','HAVELLS'),('DIVISLAB.NS','DIVISLAB'),
    ('TORNTPHARM.NS','TORNTPHARM'),('MUTHOOTFIN.NS','MUTHOOTFIN'),
    ('INDUSINDBK.NS','INDUSINDBK'),('BANDHANBNK.NS','BANDHANBNK'),
    ('FEDERALBNK.NS','FEDERALBNK'),('ESCORTS.NS','ESCORTS'),
    ('BALKRISIND.NS','BALKRISIND'),
]
SYM_LIST = [s for _, s in STOCKS]


# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch(ticker, period='5y'):
    try:
        df = yf.Ticker(ticker).history(period=period, interval='1d', auto_adjust=True)
        if df.empty:
            return {}
        return {str(ts.date()): {
            'open':  float(row['Open']),
            'high':  float(row['High']),
            'low':   float(row['Low']),
            'close': float(row['Close']),
            'vol':   float(row.get('Volume', 0) or 0),
        } for ts, row in df.iterrows()}
    except Exception:
        return {}


# ── Portfolio Backtester ──────────────────────────────────────────────────────
def run_portfolio(price_data, nifty_data, dates,
                  rs_lookback=63, top_n=10,
                  rebal_days=21, trend_gate=True,
                  capital=TOTAL_CAPITAL):
    """
    price_data : {sym: {date_str: {open,high,low,close,vol}}}
    nifty_data : {date_str: {close, ...}}
    dates      : sorted list of date strings in the simulation period
    Returns    : metrics dict + trade list + daily equity list
    """
    cash      = capital
    positions = {}    # sym -> {qty, entry_px, entry_date, entry_i, high_since}
    trades    = []
    equity    = [capital]
    daily_val = []

    def get_close(sym, date):
        d = price_data.get(sym, {}).get(date)
        return d['close'] if d else None

    def get_open(sym, date):
        d = price_data.get(sym, {}).get(date)
        return d['open'] if d else None

    def rs_score(sym, i, lookback):
        """63-day excess return of sym vs Nifty at dates[i]."""
        if i < lookback:
            return None
        date_now  = dates[i]
        date_past = dates[i - lookback]
        c_now  = get_close(sym, date_now)
        c_past = get_close(sym, date_past)
        n_now  = nifty_data.get(date_now, {}).get('close')
        n_past = nifty_data.get(date_past, {}).get('close')
        if not all([c_now, c_past, n_now, n_past]):
            return None
        stock_ret = (c_now / c_past - 1) * 100
        nifty_ret = (n_now / n_past - 1) * 100
        return stock_ret - nifty_ret

    def above_20d_high(sym, i):
        """True if today's close > max high of prior 20 bars."""
        if i < 20:
            return True
        closes = [get_close(sym, dates[j]) for j in range(i - 20, i)
                  if get_close(sym, dates[j])]
        if not closes:
            return True
        curr = get_close(sym, dates[i])
        return curr is not None and curr > max(closes)

    last_rebal = -999

    for i, date in enumerate(dates):
        if i < rs_lookback + 5:
            daily_val.append(cash + sum(
                positions[s]['qty'] * (get_close(s, date) or positions[s]['entry_px'])
                for s in positions))
            equity.append(daily_val[-1])
            continue

        # ── Check stop-losses daily ───────────────────────────────────────────
        to_close = []
        for sym, pos in list(positions.items()):
            curr_px = get_close(sym, date)
            if curr_px is None:
                continue
            pos['high_since'] = max(pos['high_since'], curr_px)
            sl_price = pos['entry_px'] * (1 - SL_PCT / 100)
            if curr_px <= sl_price:
                to_close.append((sym, curr_px, 'StopLoss'))

        for sym, px, reason in to_close:
            pos     = positions.pop(sym)
            fill_px = px * (1 - SLIPPAGE)
            exit_val = pos['qty'] * fill_px
            costs = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
            pnl   = (fill_px - pos['entry_px']) * pos['qty'] - costs
            cash += exit_val - costs
            dur   = i - pos['entry_i']
            trades.append({
                'sym': sym, 'pnl': pnl, 'winner': 1 if pnl > 0 else 0,
                'return_pct': (fill_px / pos['entry_px'] - 1) * 100,
                'exit': reason, 'duration': dur,
                'entry_date': pos['entry_date'], 'exit_date': date,
            })

        # ── Monthly rebalance ─────────────────────────────────────────────────
        if i - last_rebal >= rebal_days:
            last_rebal = i

            # Score all stocks
            scored = []
            for sym in SYM_LIST:
                sc = rs_score(sym, i, rs_lookback)
                if sc is None:
                    continue
                c = get_close(sym, date)
                if c is None or c <= 0:
                    continue
                gate_ok = (not trend_gate) or above_20d_high(sym, i)
                scored.append((sym, sc, gate_ok))

            # Select top_n with gate
            eligible = [(s, sc) for s, sc, g in scored if g]
            eligible.sort(key=lambda x: -x[1])
            target = set(s for s, _ in eligible[:top_n])

            # Sell positions not in target
            for sym in list(positions.keys()):
                if sym not in target:
                    next_date = dates[i + 1] if i + 1 < len(dates) else date
                    fill_px_d = get_open(sym, next_date) or get_close(sym, date)
                    if fill_px_d is None:
                        continue
                    fill_px = fill_px_d * (1 - SLIPPAGE)
                    pos = positions.pop(sym)
                    exit_val = pos['qty'] * fill_px
                    costs = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
                    pnl = (fill_px - pos['entry_px']) * pos['qty'] - costs
                    cash += exit_val - costs
                    trades.append({
                        'sym': sym, 'pnl': pnl, 'winner': 1 if pnl > 0 else 0,
                        'return_pct': (fill_px / pos['entry_px'] - 1) * 100,
                        'exit': 'Rebalance', 'duration': i - pos['entry_i'],
                        'entry_date': pos['entry_date'], 'exit_date': next_date,
                    })

            # Buy new positions
            new_buys = [s for s in target if s not in positions]
            if new_buys and cash > 0:
                alloc_per = cash * 0.95 / max(len(new_buys), 1)
                alloc_per = min(alloc_per, capital / top_n)  # cap per position
                for sym in new_buys:
                    next_date = dates[i + 1] if i + 1 < len(dates) else date
                    fill_px_d = get_open(sym, next_date) or get_close(sym, date)
                    if fill_px_d is None:
                        continue
                    fill_px = fill_px_d * (1 + SLIPPAGE)
                    qty = max(1, int(alloc_per / fill_px))
                    cost_in = BROKERAGE + qty * fill_px * EXCHANGE_PCT
                    if cash >= qty * fill_px + cost_in:
                        cash -= qty * fill_px + cost_in
                        positions[sym] = {
                            'qty': qty, 'entry_px': fill_px,
                            'entry_date': next_date, 'entry_i': i,
                            'high_since': fill_px,
                        }

        # ── Daily equity ──────────────────────────────────────────────────────
        port_val = cash + sum(
            pos['qty'] * (get_close(sym, date) or pos['entry_px'])
            for sym, pos in positions.items())
        daily_val.append(port_val)
        equity.append(port_val)

    # Close all remaining positions at end
    if dates:
        last_date = dates[-1]
        for sym, pos in list(positions.items()):
            curr_px = get_close(sym, last_date) or pos['entry_px']
            fill_px = curr_px * (1 - SLIPPAGE)
            exit_val = pos['qty'] * fill_px
            costs = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
            pnl = (fill_px - pos['entry_px']) * pos['qty'] - costs
            cash += exit_val - costs
            trades.append({
                'sym': sym, 'pnl': pnl, 'winner': 1 if pnl > 0 else 0,
                'return_pct': (fill_px / pos['entry_px'] - 1) * 100,
                'exit': 'EndOfPeriod', 'duration': len(dates) - pos['entry_i'],
                'entry_date': pos['entry_date'], 'exit_date': last_date,
            })
        final_val = cash
    else:
        final_val = cash

    return _portfolio_metrics(trades, daily_val, final_val, capital, len(dates)), trades


def _portfolio_metrics(trades, daily_vals, final_val, initial_val, n_days):
    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp     = sum(t['pnl'] for t in wins)
    gl     = abs(sum(t['pnl'] for t in losses))
    pf     = gp / gl if gl > 0 else (1.0 if gp > 0 else 0.0)
    wr     = len(wins) / len(trades) * 100 if trades else 0.0
    years  = max(n_days / 252, 0.1)
    cagr   = ((final_val / initial_val) ** (1 / years) - 1) * 100 if final_val > 0 and initial_val > 0 else -100.0

    peak = daily_vals[0] if daily_vals else initial_val
    max_dd = 0.0
    for v in daily_vals:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd

    dr = [(daily_vals[i] - daily_vals[i-1]) / daily_vals[i-1]
          for i in range(1, len(daily_vals)) if daily_vals[i-1] > 0]
    sharpe = (statistics.mean(dr) / statistics.stdev(dr) * math.sqrt(252)
              if len(dr) > 2 and statistics.stdev(dr) > 0 else 0.0)

    w_rets = [t['return_pct'] for t in wins]
    l_rets = [t['return_pct'] for t in losses]
    avg_w  = statistics.mean(w_rets) if w_rets  else 0.0
    avg_l  = statistics.mean(l_rets) if l_rets  else 0.0
    wl     = abs(avg_w / avg_l)      if avg_l   else 0.0
    dur    = statistics.mean([t['duration'] for t in trades]) if trades else 0.0

    return {
        'trades': len(trades), 'wins': len(wins), 'losses': len(losses),
        'wr': round(wr, 1),    'pf':   round(pf, 3),
        'sharpe': round(sharpe, 3),   'cagr':    round(cagr, 1),
        'max_dd': round(max_dd, 1),   'avg_win':  round(avg_w, 2),
        'avg_loss': round(avg_l, 2),  'wl':       round(wl, 2),
        'avg_dur':  round(dur, 1),
        'net_pnl':  round(final_val - initial_val, 0),
        'final_val': round(final_val, 0),
        'exit_reasons': dict(Counter(t['exit'] for t in trades)),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  FETCH ALL DATA
# ═════════════════════════════════════════════════════════════════════════════
print(SEP)
print('  FETCHING 5-YEAR DAILY DATA — 50 NSE STOCKS + NIFTY')
print(SEP)

price_data = {}
for ticker, sym in STOCKS:
    d = fetch(ticker, '5y')
    price_data[sym] = d
    print(f'  {sym:<14}: {len(d)} days')
    time.sleep(0.22)

nifty_data = fetch('^NSEI', '5y')
print(f'  NIFTY50        : {len(nifty_data)} days')

# Build master date list (intersection: all days where Nifty traded)
all_dates = sorted(nifty_data.keys())
print(f'  Master timeline: {len(all_dates)} trading days  '
      f'({all_dates[0]} to {all_dates[-1]})')

# Walk-forward split
split_i  = int(len(all_dates) * WF_SPLIT)
IS_DATES  = all_dates[:split_i]
OOS_DATES = all_dates[split_i:]
print(f'  IS : {IS_DATES[0]} to {IS_DATES[-1]}  ({len(IS_DATES)} days)')
print(f'  OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}  ({len(OOS_DATES)} days)')


# ═════════════════════════════════════════════════════════════════════════════
#  PARAMETER SWEEP — find best IS config
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  PARAMETER SWEEP — IN-SAMPLE (finding best config)')
print('  RS lookback: 42 / 63 / 126 days  |  Top N: 5 / 8 / 10  |  Trend gate: Y/N')
print(SEP)
print(f'  {"Config":<40}  {"Trades":>7}  {"WR%":>6}  {"IS PF":>7}  '
      f'{"IS CAGR%":>9}  {"MaxDD%":>7}  {"Sharpe":>7}  {"AvgDur":>7}')
print(sep)

CONFIGS = []
for lk in [42, 63, 126]:
    for n in [5, 8, 10]:
        for gate in [True, False]:
            label = f'RS={lk}d  N={n}  Gate={"Y" if gate else "N"}'
            m, _ = run_portfolio(price_data, nifty_data, IS_DATES,
                                 rs_lookback=lk, top_n=n, trend_gate=gate)
            CONFIGS.append({'label': label, 'lk': lk, 'n': n, 'gate': gate, 'is': m})
            flag = '  ***' if m['cagr'] > 15 else ('  **' if m['cagr'] > 10 else '')
            print(f'  {label:<40}  {m["trades"]:>7}  {m["wr"]:>5.1f}%  '
                  f'{m["pf"]:>7.3f}  {m["cagr"]:>+8.1f}%  {m["max_dd"]:>6.1f}%  '
                  f'{m["sharpe"]:>7.3f}  {m["avg_dur"]:>6.1f}d{flag}')


# ═════════════════════════════════════════════════════════════════════════════
#  BEST CONFIG — WALK-FORWARD OOS
# ═════════════════════════════════════════════════════════════════════════════
# Select best by IS Sharpe (more stable than PF for portfolio strategies)
best_cfg = max(CONFIGS, key=lambda x: x['is']['sharpe'])
print(sep)
print(f'  Best IS config: {best_cfg["label"]}  '
      f'(Sharpe={best_cfg["is"]["sharpe"]:.3f}  CAGR={best_cfg["is"]["cagr"]:+.1f}%)')

print()
print(SEP)
print(f'  WALK-FORWARD OOS — BEST CONFIG: {best_cfg["label"]}')
print(SEP)

oos_m, oos_trades = run_portfolio(
    price_data, nifty_data, OOS_DATES,
    rs_lookback=best_cfg['lk'], top_n=best_cfg['n'],
    trend_gate=best_cfg['gate'])

print(f'  OOS Period    : {OOS_DATES[0]} to {OOS_DATES[-1]}')
print(f'  Total Trades  : {oos_m["trades"]}')
print(f'  Win Rate      : {oos_m["wr"]:.1f}%')
print(f'  Profit Factor : {oos_m["pf"]:.3f}')
print(f'  CAGR          : {oos_m["cagr"]:+.1f}%')
print(f'  Sharpe        : {oos_m["sharpe"]:.3f}')
print(f'  Max Drawdown  : {oos_m["max_dd"]:.1f}%')
print(f'  Avg Win       : {oos_m["avg_win"]:+.2f}%')
print(f'  Avg Loss      : {oos_m["avg_loss"]:+.2f}%')
print(f'  Win/Loss Ratio: {oos_m["wl"]:.2f}x')
print(f'  Avg Hold Dur  : {oos_m["avg_dur"]:.0f} days')
print(f'  Net P&L       : Rs.{oos_m["net_pnl"]:+,.0f}  '
      f'(starting capital Rs.{TOTAL_CAPITAL:,.0f})')
er = oos_m['exit_reasons']
print(f'  Exit reasons  : SL={er.get("StopLoss",0)}  '
      f'Rebal={er.get("Rebalance",0)}  EoP={er.get("EndOfPeriod",0)}')


# ═════════════════════════════════════════════════════════════════════════════
#  NIFTY BENCHMARK
# ═════════════════════════════════════════════════════════════════════════════
oos_start = nifty_data.get(OOS_DATES[0],  {}).get('close', 0)
oos_end   = nifty_data.get(OOS_DATES[-1], {}).get('close', 0)
oos_years = len(OOS_DATES) / 252
nifty_cagr = ((oos_end / oos_start) ** (1 / oos_years) - 1) * 100 if oos_start > 0 else 0

is_start = nifty_data.get(IS_DATES[0],  {}).get('close', 0)
is_end   = nifty_data.get(IS_DATES[-1], {}).get('close', 0)
is_years = len(IS_DATES) / 252
nifty_is_cagr = ((is_end / is_start) ** (1 / is_years) - 1) * 100 if is_start > 0 else 0

print()
print(f'  Nifty50 CAGR (IS period) : {nifty_is_cagr:+.1f}%')
print(f'  Nifty50 CAGR (OOS period): {nifty_cagr:+.1f}%')
print(f'  Alpha over Nifty (OOS)   : {oos_m["cagr"] - nifty_cagr:+.1f}% per year')


# ═════════════════════════════════════════════════════════════════════════════
#  PER-STOCK CONTRIBUTION (OOS)
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  PER-STOCK CONTRIBUTION — OOS (which stocks drove performance?)')
print(SEP)
print(f'  {"Stock":<14}  {"Trades":>7}  {"WR%":>6}  {"Net P&L":>10}  '
      f'{"AvgRet%":>9}  {"AvgDur":>7}  {"Exits"}')
print(sep)

by_sym = defaultdict(list)
for t in oos_trades:
    by_sym[t['sym']].append(t)

sym_summary = []
for sym in sorted(by_sym.keys()):
    ts = by_sym[sym]
    wins = [t for t in ts if t['pnl'] > 0]
    net  = sum(t['pnl'] for t in ts)
    wr   = len(wins) / len(ts) * 100 if ts else 0
    avg_ret = statistics.mean([t['return_pct'] for t in ts]) if ts else 0
    avg_dur = statistics.mean([t['duration']   for t in ts]) if ts else 0
    exits = Counter(t['exit'] for t in ts)
    exit_s = ' '.join(f'{k[:3]}={v}' for k, v in exits.most_common(3))
    sym_summary.append((sym, len(ts), wr, net, avg_ret, avg_dur))
    flag = '  +' if net > 5000 else ('  -' if net < -5000 else '')
    print(f'  {sym:<14}  {len(ts):>7}  {wr:>5.1f}%  Rs.{net:>+8,.0f}  '
          f'{avg_ret:>+8.2f}%  {avg_dur:>6.0f}d  {exit_s}{flag}')

sym_summary.sort(key=lambda x: -x[3])
print(sep)
print('  Top 5 contributors:   ' +
      '  '.join(f'{s[0]}({s[3]:+,.0f})' for s in sym_summary[:5]))
print('  Bottom 5 contributors:' +
      '  '.join(f'{s[0]}({s[3]:+,.0f})' for s in sym_summary[-5:]))


# ═════════════════════════════════════════════════════════════════════════════
#  OOS ALL CONFIGS (top 10 by IS Sharpe)
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  ALL CONFIGS — IS vs OOS COMPARISON (top 10 by IS Sharpe)')
print(SEP)
print(f'  {"Config":<40}  {"IS PF":>7}  {"IS CAGR":>8}  {"IS Sh":>7}  '
      f'{"OOS PF":>7}  {"OOS CAGR":>9}  {"OOS Sh":>7}  {"Decay":>7}')
print(sep)

top10 = sorted(CONFIGS, key=lambda x: -x['is']['sharpe'])[:10]
for cfg in top10:
    oos_r, _ = run_portfolio(price_data, nifty_data, OOS_DATES,
                             rs_lookback=cfg['lk'], top_n=cfg['n'],
                             trend_gate=cfg['gate'])
    im = cfg['is']
    decay = im['cagr'] - oos_r['cagr']
    flag = ''
    if   oos_r['cagr'] > nifty_cagr + 5: flag = '  BEATS NIFTY+5%'
    elif oos_r['cagr'] > nifty_cagr:      flag = '  BEATS NIFTY'
    elif oos_r['cagr'] > 0:               flag = '  POSITIVE'
    print(f'  {cfg["label"]:<40}  {im["pf"]:>7.3f}  {im["cagr"]:>+7.1f}%  '
          f'{im["sharpe"]:>7.3f}  {oos_r["pf"]:>7.3f}  {oos_r["cagr"]:>+8.1f}%  '
          f'{oos_r["sharpe"]:>7.3f}  {decay:>+6.1f}%{flag}')


# ═════════════════════════════════════════════════════════════════════════════
#  HEAD-TO-HEAD vs BENCHMARKS
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  HEAD-TO-HEAD COMPARISON — OOS PERIOD')
print(SEP)

rs_best_oos, _ = run_portfolio(price_data, nifty_data, OOS_DATES,
                               rs_lookback=best_cfg['lk'], top_n=best_cfg['n'],
                               trend_gate=best_cfg['gate'])

benchmarks = [
    ('RS Momentum (best config)',  rs_best_oos['pf'], rs_best_oos['cagr'],
     rs_best_oos['sharpe'], rs_best_oos['max_dd'], rs_best_oos['trades']),
    ('RSI<30 S3 (from prev test)', 0.876, -3.5, -0.774, 9.7, 278),
    ('Compression Breakout B',     0.996, -1.3, -0.515, 4.4, 82),
    ('EMA 9/21 Cross',             0.792, -6.5, -0.999, 16.0, 498),
    (f'Buy & Hold Nifty50',        1.000, nifty_cagr, 0.0, 0.0, 0),
]

print(f'  {"Strategy":<35}  {"OOS PF":>7}  {"CAGR%":>8}  {"Sharpe":>7}  '
      f'{"MaxDD%":>7}  {"Trades":>7}')
print(sep)
for name, pf, cagr, sh, dd, tr in benchmarks:
    flag = ''
    if cagr > nifty_cagr: flag = '  BEATS NIFTY'
    if cagr > nifty_cagr + 5: flag = '  BEATS NIFTY BY 5%+'
    tr_s = f'{tr:>7}' if tr else '      -'
    print(f'  {name:<35}  {pf:>7.3f}  {cagr:>+7.1f}%  {sh:>7.3f}  '
          f'{dd:>6.1f}%  {tr_s}{flag}')


# ═════════════════════════════════════════════════════════════════════════════
#  VERDICT
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  VERDICT — RELATIVE STRENGTH MOMENTUM ON NSE')
print(SEP)

beats_nifty  = rs_best_oos['cagr'] > nifty_cagr
positive_abs = rs_best_oos['cagr'] > 0
alpha        = rs_best_oos['cagr'] - nifty_cagr
better_than_rsi30 = rs_best_oos['cagr'] > -3.5   # RSI<30 CAGR
better_than_cb    = rs_best_oos['cagr'] > -1.3   # Compression B CAGR

print(f'  Best config   : {best_cfg["label"]}')
print(f'  OOS CAGR      : {rs_best_oos["cagr"]:+.1f}%')
print(f'  Nifty CAGR    : {nifty_cagr:+.1f}%')
print(f'  Alpha         : {alpha:+.1f}% per year')
print(f'  Beats Nifty   : {"YES" if beats_nifty else "NO"}')
print(f'  Positive CAGR : {"YES" if positive_abs else "NO"}')
print(f'  Beats RSI<30  : {"YES" if better_than_rsi30 else "NO"}')
print(f'  Beats Comp B  : {"YES" if better_than_cb else "NO"}')
print()

if beats_nifty and rs_best_oos['sharpe'] > 0.3:
    print('  RESULT: RS MOMENTUM BEATS BUY-AND-HOLD WITH POSITIVE SHARPE.')
    print('  This is a genuinely tradeable edge on NSE large/mid caps.')
    print('  Recommended for paper-trading with full position sizing.')
elif beats_nifty:
    print('  RESULT: RS MOMENTUM BEATS NIFTY BUT SHARPE IS LOW.')
    print('  Returns are positive but volatile. Consider tighter universe or wider stops.')
elif positive_abs:
    print('  RESULT: RS MOMENTUM IS POSITIVE CAGR BUT DOES NOT BEAT NIFTY.')
    print('  Better than losing strategies but underperforms passive index investing.')
    print('  May improve with factor combination (RS + quality + volume trend).')
elif rs_best_oos['cagr'] > max(-3.5, -1.3):
    print('  RESULT: RS MOMENTUM OUTPERFORMS OTHER TESTED STRATEGIES.')
    print('  Not profitable on absolute basis, but strongest relative performance found.')
    print('  Momentum effect exists on NSE but is weaker than developed markets suggest.')
    print('  Likely causes: high slippage, thin universe (50 stocks), monthly rebalance lag.')
else:
    print('  RESULT: RS MOMENTUM DOES NOT SHOW EDGE OVER TESTED PERIOD.')
    print('  The 50-stock Nifty universe may be too concentrated for cross-sectional momentum.')
    print('  Momentum works better on broader universes (Nifty 500) with weekly rebalancing.')
    print()
    print('  RECOMMENDED NEXT TEST: Nifty 500 universe, weekly rebalance, smaller position count.')

print()
print('  RESEARCH TRAJECTORY SUMMARY:')
print(f'  1. EMA 9/21 Cross      : OOS PF=0.792  CAGR=-6.5%  ABANDONED')
print(f'  2. RSI<30 Mean Rev     : OOS PF=0.876  CAGR=-3.5%  EDGE EXISTS, COST-LIMITED')
print(f'  3. Compression Break   : OOS PF=0.996  CAGR=-1.3%  RAW EDGE POSITIVE, COSTS DOMINATE')
print(f'  4. RS Momentum         : OOS PF={rs_best_oos["pf"]:.3f}  CAGR={rs_best_oos["cagr"]:+.1f}%  ', end='')
if rs_best_oos['cagr'] > 0:
    print('BEST RESULT SO FAR')
elif rs_best_oos['cagr'] > -1.3:
    print('COMPARABLE TO BEST')
else:
    print('BELOW COMPRESSION B')
print()
print('  HIGHEST-PROBABILITY NEXT STEPS:')
print('  A. Expand to Nifty 500 universe (200-500 stocks) for true cross-sectional momentum')
print('  B. Weekly rebalancing instead of monthly (reduces signal lag)')
print('  C. Combine RS momentum score with earnings growth (dual factor)')
print('  D. Add sector filter: only buy stocks whose sector is also outperforming Nifty')
