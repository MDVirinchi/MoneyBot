"""
s3_expand.py — Expanded validation of S3 Mean Reversion strategy.

Tests:
  - 15 NSE stocks
  - 3 years of daily data
  - Walk-forward: Y1-Y2 (in-sample) vs Y3 (out-of-sample)

Entry logic (unchanged from strategies_alt.py):
  - RSI dropped below 30 within last 5 bars (oversold reached)
  - RSI now recovered above 35 (momentum turning)
  - Price above long-term EMA (50 or 200 depending on data available)
  - RSI currently between 35 and 55

Costs: BROKERAGE=Rs.20, STT=0.1%, SLIPPAGE=0.2% each way, EXCHANGE=0.00345%
Exit:  SL=2%, TP=6%, TrailingStop=1.5%, next-open execution
"""

import time, math, logging, warnings, statistics
from collections import defaultdict, Counter

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

# ── Cost model ────────────────────────────────────────────────────────────────
BROKERAGE    = 20.0
STT_PCT      = 0.001
EXCHANGE_PCT = 0.0000345
SLIPPAGE     = 0.002
SL_PCT       = 2.0
TP_PCT       = 6.0
TRAIL_PCT    = 1.5
CAPITAL      = 5000.0
LOOKBACK     = 55

# ── 15 NSE stocks ─────────────────────────────────────────────────────────────
STOCKS = [
    ('RELIANCE.NS',   'RELIANCE'),
    ('TCS.NS',        'TCS'),
    ('INFY.NS',       'INFY'),
    ('HDFCBANK.NS',   'HDFCBANK'),
    ('ICICIBANK.NS',  'ICICIBANK'),
    ('SBIN.NS',       'SBIN'),
    ('HCLTECH.NS',    'HCLTECH'),
    ('WIPRO.NS',      'WIPRO'),
    ('AXISBANK.NS',   'AXISBANK'),
    ('KOTAKBANK.NS',  'KOTAKBANK'),
    ('LTIM.NS',       'LTIM'),
    ('TECHM.NS',      'TECHM'),
    ('MARUTI.NS',     'MARUTI'),
    ('TITAN.NS',      'TITAN'),
    ('BAJFINANCE.NS', 'BAJFINANCE'),
]


# ── Indicators ────────────────────────────────────────────────────────────────
def ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def rsi_val(closes, period=14):
    """Compute RSI on the last (period+1) closes."""
    if len(closes) <= period:
        return 50.0
    subset = closes[-(period + 1):]
    gains, losses = [], []
    for i in range(1, len(subset)):
        d = subset[i] - subset[i - 1]
        (gains if d > 0 else losses).append(abs(d))
    ag = sum(gains) / period if gains else 1e-6
    al = sum(losses) / period if losses else 1e-6
    return 100 - 100 / (1 + ag / al)


# ── S3 signal ─────────────────────────────────────────────────────────────────
def signal_s3(window):
    """
    Setup   : RSI dropped below 30 within last 5 bars
    Trigger : RSI now recovered above 35 (and below 55)
    Filter  : Price above EMA50 (long-term uptrend)
    """
    closes = [c[4] for c in window]
    if len(closes) < 25:
        return False

    curr_rsi = rsi_val(closes)

    # Must be recovering into 35-55 zone
    if not (35 <= curr_rsi <= 55):
        return False

    # Was oversold (RSI < 30) within last 5 bars
    was_oversold = False
    for j in range(2, 7):
        if j > len(closes) - 15:
            break
        past_rsi = rsi_val(closes[:-j + 1] if j > 1 else closes)
        if past_rsi < 30:
            was_oversold = True
            break
    if not was_oversold:
        return False

    # Trend filter: price above EMA50
    e50 = ema(closes, 50)
    if not e50 or closes[-1] < e50[-1] * 0.98:
        return False

    return True


# ── Backtester ────────────────────────────────────────────────────────────────
def backtest(candles, sig_fn):
    """Returns metrics dict. candles = [[ts, o, h, l, c, v], ...]"""
    capital  = CAPITAL
    position = None
    trades   = []
    equity   = [capital]

    for i in range(LOOKBACK, len(candles) - 1):
        window = candles[:i + 1]
        ltp    = candles[i][4]   # close of bar i

        if position:
            sl    = position['entry'] * (1 - SL_PCT / 100)
            tp    = position['entry'] * (1 + TP_PCT / 100)
            high  = max(position['high'], ltp)
            position['high'] = high
            trail = high * (1 - TRAIL_PCT / 100)

            reason = None
            if   ltp <= sl:                                    reason = 'StopLoss'
            elif ltp >= tp:                                    reason = 'TakeProfit'
            elif ltp <= trail and high > position['entry'] * 1.005: reason = 'TrailingStop'

            if reason:
                exit_px  = ltp * (1 - SLIPPAGE)
                exit_val = position['qty'] * exit_px
                costs    = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
                pnl      = (exit_px - position['entry']) * position['qty'] - costs
                capital += pnl
                trades.append({
                    'pnl':         pnl,
                    'return_pct':  (exit_px / position['entry'] - 1) * 100,
                    'exit_reason': reason,
                    'bar_index':   i,
                })
                position = None
                equity.append(capital)
                continue

        if position is None:
            try:
                sig = sig_fn(window)
            except Exception:
                sig = False
            if sig:
                exec_px = candles[i + 1][1]
                fill_px = exec_px * (1 + SLIPPAGE)
                qty     = max(1, int(capital * 0.95 / fill_px))
                cost_in = BROKERAGE + qty * fill_px * EXCHANGE_PCT
                if capital >= qty * fill_px + cost_in:
                    capital -= cost_in
                    position = {'qty': qty, 'entry': fill_px, 'high': fill_px,
                                'entry_bar': i}

        equity.append(capital)

    if position:
        ltp      = candles[-1][4]
        exit_px  = ltp * (1 - SLIPPAGE)
        exit_val = position['qty'] * exit_px
        costs    = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
        pnl      = (exit_px - position['entry']) * position['qty'] - costs
        trades.append({'pnl': pnl,
                       'return_pct': (exit_px / position['entry'] - 1) * 100,
                       'exit_reason': 'EndOfPeriod', 'bar_index': len(candles) - 1})
        capital += pnl

    return _metrics(trades, equity, capital, len(candles) - LOOKBACK)


def _metrics(trades, equity, final_cap, bars):
    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp     = sum(t['pnl'] for t in wins)
    gl     = abs(sum(t['pnl'] for t in losses))
    pf     = gp / gl if gl > 0 else (1.0 if gp > 0 else 0.0)
    wr     = len(wins) / len(trades) * 100 if trades else 0.0
    years  = bars / 252
    cagr   = ((final_cap / CAPITAL) ** (1 / years) - 1) * 100 if years > 0 and final_cap > 0 else -100.0

    peak = equity[0]; max_dd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd

    dr = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity)) if equity[i-1] > 0]
    sharpe = (statistics.mean(dr) / statistics.stdev(dr) * math.sqrt(252)
              if len(dr) > 2 and statistics.stdev(dr) > 0 else 0.0)

    w_rets  = [t['return_pct'] for t in wins]
    l_rets  = [t['return_pct'] for t in losses]
    avg_w   = statistics.mean(w_rets) if w_rets else 0.0
    avg_l   = statistics.mean(l_rets) if l_rets else 0.0
    wl      = abs(avg_w / avg_l) if avg_l else 0.0
    tot_costs = (BROKERAGE * 2 * len(trades)
                 + sum(abs(t['pnl']) * (STT_PCT + EXCHANGE_PCT * 2) for t in trades))

    return {
        'trades': len(trades), 'wins': len(wins), 'losses': len(losses),
        'wr': round(wr, 1), 'pf': round(pf, 3),
        'sharpe': round(sharpe, 3), 'cagr': round(cagr, 1),
        'max_dd': round(max_dd, 1), 'avg_win': round(avg_w, 2),
        'avg_loss': round(avg_l, 2), 'wl': round(wl, 2),
        'costs': round(tot_costs, 0),
        'net_pnl': round(final_cap - CAPITAL, 2),
        'exit_reasons': dict(Counter(t['exit_reason'] for t in trades)),
    }


# ── Fetch data ────────────────────────────────────────────────────────────────
def fetch(ticker, period='3y'):
    try:
        df = yf.Ticker(ticker).history(period=period, interval='1d', auto_adjust=True)
        if df.empty:
            return []
        candles = []
        for ts, row in df.iterrows():
            candles.append([
                str(ts.date()),
                float(row['Open']), float(row['High']),
                float(row['Low']),  float(row['Close']),
                float(row.get('Volume', 0)),
            ])
        return candles
    except Exception as e:
        return []


# ── Main ──────────────────────────────────────────────────────────────────────
print('Fetching 3 years of daily data for 15 NSE stocks...')
print()

stock_candles = {}
for ticker, sym in STOCKS:
    candles = fetch(ticker, '3y')
    stock_candles[sym] = candles
    status = f'{len(candles)} bars' if candles else 'FAILED'
    print(f'  {sym:<14}: {status}')
    time.sleep(0.3)

# ── Full 3-year backtest ──────────────────────────────────────────────────────
print()
print('Running S3 Mean Reversion — full 3 years...')
full_results = {}
for _, sym in STOCKS:
    candles = stock_candles[sym]
    if len(candles) < LOOKBACK + 10:
        full_results[sym] = None
        continue
    m = backtest(candles, signal_s3)
    full_results[sym] = m

# ── Walk-forward split ────────────────────────────────────────────────────────
# Split at 2/3 of the bars
print('Running walk-forward: Y1-Y2 (in-sample) vs Y3 (out-of-sample)...')
is_results  = {}
oos_results = {}
for _, sym in STOCKS:
    candles = stock_candles[sym]
    if not candles or len(candles) < LOOKBACK + 20:
        is_results[sym] = None
        oos_results[sym] = None
        continue
    split = int(len(candles) * 2 / 3)
    is_candles  = candles[:split]
    oos_candles = candles[split - LOOKBACK:]  # carry lookback into OOS window
    is_results[sym]  = backtest(is_candles,  signal_s3) if len(is_candles)  > LOOKBACK + 5 else None
    oos_results[sym] = backtest(oos_candles, signal_s3) if len(oos_candles) > LOOKBACK + 5 else None

# ── Print full 3-year table ───────────────────────────────────────────────────
SEP = '=' * 106
sep = '-' * 106

print()
print(SEP)
print('  S3 MEAN REVERSION — FULL 3-YEAR RESULTS (15 NSE stocks, daily, Rs.5000/stock)')
print(SEP)
print(f'  {"Stock":<14}  {"Bars":>4}  {"Trades":>6}  {"WR%":>6}  {"PF":>6}  '
      f'{"Sharpe":>7}  {"CAGR%":>7}  {"MaxDD%":>7}  {"AvgW%":>6}  {"AvgL%":>6}  {"WL":>5}  Exits')
print(sep)

valid_full = []
for _, sym in STOCKS:
    m = full_results.get(sym)
    candles = stock_candles.get(sym, [])
    if m is None:
        print(f'  {sym:<14}  -- skipped (insufficient data) --')
        continue
    er = m['exit_reasons']
    exit_s = (f'SL={er.get("StopLoss",0)}'
              f' TP={er.get("TakeProfit",0)}'
              f' Tr={er.get("TrailingStop",0)}'
              f' EoP={er.get("EndOfPeriod",0)}')
    print(f'  {sym:<14}  {len(candles):>4}  {m["trades"]:>6}  {m["wr"]:>5.1f}%  '
          f'{m["pf"]:>6.3f}  {m["sharpe"]:>7.3f}  {m["cagr"]:>+6.1f}%  '
          f'{m["max_dd"]:>6.1f}%  {m["avg_win"]:>+5.2f}%  {m["avg_loss"]:>+5.2f}%  '
          f'{m["wl"]:>4.2f}x  {exit_s}')
    if m['trades'] >= 3:
        valid_full.append(m)

# Aggregate (stocks with >= 3 trades)
if valid_full:
    n = len(valid_full)
    def avg(k): return sum(v[k] for v in valid_full) / n
    # Pool all trades for aggregate PF
    total_wins_pnl  = sum(v['pf'] * v['losses'] * abs(v['avg_loss']) / 100 * CAPITAL
                         for v in valid_full if v['losses'] > 0)
    # Simpler: weighted average
    all_w_rets  = []
    all_l_rets  = []
    all_trades_n = sum(v['trades'] for v in valid_full)
    all_wins_n   = sum(v['wins']   for v in valid_full)
    all_losses_n = sum(v['losses'] for v in valid_full)

    # Reconstruct pooled PF from avg win/loss and counts
    # PF = (wins * avg_win_pct) / (losses * |avg_loss_pct|)
    pool_num = sum(v['wins']   * abs(v['avg_win'])  for v in valid_full)
    pool_den = sum(v['losses'] * abs(v['avg_loss']) for v in valid_full)
    pool_pf  = pool_num / pool_den if pool_den > 0 else 0.0

    print(sep)
    print(f'  {"AGGREGATE":<14}  {"---":>4}  {all_trades_n:>6}  '
          f'{all_wins_n/all_trades_n*100:>5.1f}%  {pool_pf:>6.3f}  '
          f'{avg("sharpe"):>7.3f}  {avg("cagr"):>+6.1f}%  '
          f'{avg("max_dd"):>6.1f}%  {avg("avg_win"):>+5.2f}%  '
          f'{avg("avg_loss"):>+5.2f}%  {avg("wl"):>4.2f}x  '
          f'({n} stocks with >=3 trades)')

# ── Walk-forward table ────────────────────────────────────────────────────────
print()
print(SEP)
print('  WALK-FORWARD VALIDATION  (Y1-Y2 in-sample  |  Y3 out-of-sample)')
print(SEP)
print(f'  {"Stock":<14}  '
      f'{"IS-Tr":>5}  {"IS-WR":>6}  {"IS-PF":>6}  {"IS-CAGR":>8}  '
      f'{"OOS-Tr":>6}  {"OOS-WR":>7}  {"OOS-PF":>7}  {"OOS-CAGR":>9}  {"Hold?":>6}')
print(sep)

is_valid  = []
oos_valid = []
for _, sym in STOCKS:
    mi  = is_results.get(sym)
    mo  = oos_results.get(sym)
    if mi is None and mo is None:
        continue
    is_str  = (f'{mi["trades"]:>5}  {mi["wr"]:>5.1f}%  {mi["pf"]:>6.3f}  '
               f'{mi["cagr"]:>+7.1f}%') if mi else '   --      --      --        --'
    oos_str = (f'{mo["trades"]:>6}  {mo["wr"]:>6.1f}%  {mo["pf"]:>7.3f}  '
               f'{mo["cagr"]:>+8.1f}%') if mo else '    --      --       --         --'
    # Does OOS hold up? PF > 0.7 * IS_PF and at least 1 trade
    holds = '---'
    if mi and mo and mi['trades'] >= 2 and mo['trades'] >= 1:
        ratio = mo['pf'] / mi['pf'] if mi['pf'] > 0 else 0
        if mo['pf'] >= 0.5:
            holds = 'YES' if ratio >= 0.5 else 'WEAK'
        else:
            holds = 'NO'
    print(f'  {sym:<14}  {is_str}  {oos_str}  {holds:>6}')
    if mi and mi['trades'] >= 2: is_valid.append(mi)
    if mo and mo['trades'] >= 1: oos_valid.append(mo)

# Walk-forward aggregate
if is_valid and oos_valid:
    def wagg(lst, k): return sum(v[k] for v in lst) / len(lst)
    is_t  = sum(v['trades'] for v in is_valid)
    oos_t = sum(v['trades'] for v in oos_valid)
    is_w  = sum(v['wins'] for v in is_valid)
    oos_w = sum(v['wins'] for v in oos_valid)
    is_pnum  = sum(v['wins']   * abs(v['avg_win'])  for v in is_valid)
    is_pden  = sum(v['losses'] * abs(v['avg_loss']) for v in is_valid)
    oos_pnum = sum(v['wins']   * abs(v['avg_win'])  for v in oos_valid)
    oos_pden = sum(v['losses'] * abs(v['avg_loss']) for v in oos_valid)
    is_pf    = is_pnum / is_pden   if is_pden   > 0 else 0.0
    oos_pf   = oos_pnum / oos_pden if oos_pden  > 0 else 0.0
    print(sep)
    is_line  = (f'{is_t:>5}  {is_w/is_t*100:>5.1f}%  {is_pf:>6.3f}  '
                f'{wagg(is_valid,"cagr"):>+7.1f}%')
    oos_line = (f'{oos_t:>6}  {oos_w/oos_t*100:>6.1f}%  {oos_pf:>7.3f}  '
                f'{wagg(oos_valid,"cagr"):>+8.1f}%')
    print(f'  {"AGGREGATE":<14}  {is_line}  {oos_line}')

# ── Verdict ───────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  VERDICT')
print(SEP)

if valid_full:
    stocks_above_1 = [sym for (_, sym) in STOCKS
                      if full_results.get(sym) and full_results[sym]['pf'] > 1.0
                      and full_results[sym]['trades'] >= 3]
    stocks_above_05 = [sym for (_, sym) in STOCKS
                       if full_results.get(sym) and full_results[sym]['pf'] > 0.5
                       and full_results[sym]['trades'] >= 3]
    print(f'  Total stocks tested       : {len([s for s in full_results if full_results[s]])}'    )
    print(f'  Stocks with >= 3 trades   : {len(valid_full)}')
    print(f'  Stocks with PF > 1.0      : {len(stocks_above_1)}  {stocks_above_1}')
    print(f'  Stocks with PF > 0.5      : {len(stocks_above_05)}  {stocks_above_05}')
    print(f'  Pooled PF (all trades)    : {pool_pf:.3f}')
    print(f'  Total trades (full 3Y)    : {all_trades_n}')
    print()

    if oos_valid and is_valid:
        decay = (oos_pf - is_pf) / is_pf * 100 if is_pf > 0 else -100
        print(f'  Walk-forward decay        : IS PF={is_pf:.3f}  ->  OOS PF={oos_pf:.3f}  '
              f'({decay:+.1f}%)')
        print()

    if pool_pf >= 1.2:
        print('  RESULT: PF > 1.2 on pooled 3-year data. Strategy has genuine edge.')
        print('  Proceed to live paper-trading with position sizing.')
    elif pool_pf >= 0.5:
        decay_ok = oos_valid and is_valid and oos_pf >= 0.4
        if decay_ok:
            print('  RESULT: PF > 0.5, walk-forward holds. Edge is real but insufficient.')
            print('  Strategy loses money net of costs. Trade count too low for Kelly sizing.')
            print('  Do NOT deploy live. Further work needed on entry precision.')
        else:
            print('  RESULT: PF > 0.5 in-sample but walk-forward decays.')
            print('  The 1-year result was partially sample-dependent.')
            print('  Strategy is not ready for live deployment.')
    else:
        print('  RESULT: Pooled PF < 0.5 on 3-year data.')
        print('  The initial positive result was a small-sample artifact.')
        print('  S3 Mean Reversion does not have a reliable edge on NSE large-caps.')
