"""
cb_forensics.py — Compression Breakout Forensics Study.

Part 1: Signal classification — incremental condition analysis
  A  Compression only         (2% range, 5 bars, no breakout required)
  B  Compression + Breakout   (our base signal — OOS PF=0.996)
  C  B + Volume expansion     (current vol > 1.5x 20-day avg)
  D  B + Close above EMA50    (long-term trend alignment)
  E  B + Volume + EMA50       (all three conditions)

  Each condition runs independently. Report IS and OOS metrics.
  Incremental lift = OOS PF change from adding each condition to B.

Part 2: Position size study
  Sizes tested: Rs.5,000 / 10,000 / 25,000 / 50,000 / 1,00,000
  Signal: Range=2%, Base=5bars (best config from sweep)
  Fixed position sizing — each trade uses exactly Rs.X regardless of capital.
  Goal: determine whether the edge exists at scale or is permanently cost-limited.

Test: 50 NSE stocks, 5 years, walk-forward Y1-Y3 IS / Y4-Y5 OOS.
"""

import time, math, logging, warnings, statistics
from collections import Counter, defaultdict

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

# ── Cost model ────────────────────────────────────────────────────────────────
BROKERAGE    = 20.0       # Rs. per order (flat)
STT_PCT      = 0.001      # 0.1% on sell side
EXCHANGE_PCT = 0.0000345  # NSE exchange fee, both sides
SLIPPAGE     = 0.002      # 0.2% each way (market impact + spread)
SL_PCT       = 2.0
TP_PCT       = 6.0
TRAIL_PCT    = 1.5
LOOKBACK     = 20
WF_SPLIT     = 0.60

# Best config from compression sweep
RANGE_PCT  = 2.0
BASE_BARS  = 5
VOL_MULT   = 1.5    # volume expansion threshold

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


# ── Indicators ────────────────────────────────────────────────────────────────
def ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    r = [sum(values[:period]) / period]
    for v in values[period:]:
        r.append(v * k + r[-1] * (1 - k))
    return r


def vol_ratio_fn(window, period=20):
    """Current bar volume vs. prior `period`-bar average."""
    vols = [c[5] for c in window]
    if len(vols) < period + 1:
        return 1.0
    avg = sum(vols[-period - 1:-1]) / period
    return vols[-1] / avg if avg > 0 else 1.0


def ema50_above(closes):
    e50 = ema(closes, 50)
    return bool(e50 and closes[-1] >= e50[-1] * 0.99)


# ── Signal factory ────────────────────────────────────────────────────────────
def make_signal(condition):
    """
    condition : 'A' | 'B' | 'C' | 'D' | 'E'
    Returns a signal function(window) -> bool.
    """
    def signal(window):
        if len(window) < BASE_BARS + 2:
            return False
        closes = [c[4] for c in window]

        # ── Base compression check (common to all) ────────────────────────────
        base   = window[-(BASE_BARS + 1):-1]   # 5 completed bars before current
        b_high = max(c[2] for c in base)        # highest intraday high
        b_low  = min(c[3] for c in base)        # lowest intraday low
        if b_low <= 0:
            return False
        rng_pct = (b_high - b_low) / b_low * 100
        if rng_pct > RANGE_PCT:
            return False

        curr_close = closes[-1]

        # ── Condition A: compression present, no breakout required ────────────
        if condition == 'A':
            return True   # any close while compressed triggers entry

        # ── Condition B: breakout above base high ─────────────────────────────
        broke_out = curr_close > b_high
        if not broke_out:
            return False

        if condition == 'B':
            return True

        # ── Condition C: breakout + volume expansion ──────────────────────────
        vol = vol_ratio_fn(window)
        has_vol = vol >= VOL_MULT

        if condition == 'C':
            return has_vol

        # ── Condition D: breakout + EMA50 ────────────────────────────────────
        above_ema = ema50_above(closes)

        if condition == 'D':
            return above_ema

        # ── Condition E: breakout + volume + EMA50 ───────────────────────────
        if condition == 'E':
            return has_vol and above_ema

        return False
    return signal


# ── Backtester (fixed or proportional capital) ────────────────────────────────
def backtest(candles, sig_fn, capital_init=5000.0, fixed_position=None):
    """
    fixed_position: if set (Rs.), each trade uses exactly that amount.
                    if None, uses 95% of remaining capital (proportional).
    """
    capital  = capital_init
    position = None
    trades   = []
    equity   = [capital]

    for i in range(LOOKBACK, len(candles) - 1):
        window = candles[:i + 1]
        ltp    = candles[i][4]

        if position:
            high  = max(position['high'], ltp)
            low   = min(position['low'],  ltp)
            position['high'] = high
            position['low']  = low
            sl    = position['entry'] * (1 - SL_PCT / 100)
            tp    = position['entry'] * (1 + TP_PCT / 100)
            trail = high * (1 - TRAIL_PCT / 100)

            reason = None
            if   ltp <= sl:                                          reason = 'SL'
            elif ltp >= tp:                                          reason = 'TP'
            elif ltp <= trail and high > position['entry'] * 1.005: reason = 'Trail'

            if reason:
                exit_px  = ltp * (1 - SLIPPAGE)
                exit_val = position['qty'] * exit_px
                # Costs: flat brokerage (both legs) + STT (sell) + exchange (both)
                cost_out = (BROKERAGE
                            + exit_val * STT_PCT
                            + exit_val * EXCHANGE_PCT)
                pnl = (exit_px - position['entry']) * position['qty'] - cost_out - position['cost_in']
                capital += pnl + position['cost_in']   # return the locked capital
                # for fixed: capital just holds unrealised value; pnl is realised
                if fixed_position is not None:
                    capital = capital   # bookkeeping handled by pnl accumulation below
                trades.append({
                    'pnl':         pnl,
                    'return_pct':  (exit_px / position['entry'] - 1) * 100,
                    'exit':        reason,
                    'winner':      1 if pnl > 0 else 0,
                    'mfe_pct':    (position['high'] / position['entry'] - 1) * 100,
                    'mae_pct':    (position['low']  / position['entry'] - 1) * 100,
                    'cost_total':  cost_out + position['cost_in'],
                    'trade_val':   position['qty'] * position['entry'],
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
                if fixed_position is not None:
                    qty = max(1, int(fixed_position / fill_px))
                    alloc = qty * fill_px
                else:
                    qty   = max(1, int(capital * 0.95 / fill_px))
                    alloc = qty * fill_px
                cost_in = BROKERAGE + qty * fill_px * EXCHANGE_PCT
                if capital >= alloc + cost_in:
                    capital -= (alloc + cost_in)
                    position = {
                        'qty': qty, 'entry': fill_px,
                        'high': fill_px, 'low': fill_px,
                        'entry_bar': i, 'cost_in': cost_in,
                    }
        equity.append(capital)

    # Close open position
    if position:
        ltp     = candles[-1][4]
        exit_px = ltp * (1 - SLIPPAGE)
        exit_val = position['qty'] * exit_px
        cost_out = BROKERAGE + exit_val * (STT_PCT + EXCHANGE_PCT)
        pnl = (exit_px - position['entry']) * position['qty'] - cost_out - position['cost_in']
        capital += pnl + position['cost_in']
        trades.append({
            'pnl': pnl,
            'return_pct': (exit_px / position['entry'] - 1) * 100,
            'exit': 'EoP', 'winner': 1 if pnl > 0 else 0,
            'mfe_pct': (position['high'] / position['entry'] - 1) * 100,
            'mae_pct': (position['low']  / position['entry'] - 1) * 100,
            'cost_total': cost_out + position['cost_in'],
            'trade_val':  position['qty'] * position['entry'],
        })
        capital += pnl

    return _metrics(trades, equity, capital, len(candles) - LOOKBACK), trades


def _metrics(trades, equity, final_cap, bars):
    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp     = sum(t['pnl'] for t in wins)
    gl     = abs(sum(t['pnl'] for t in losses))
    pf     = gp / gl if gl > 0 else (1.0 if gp > 0 else 0.0)
    wr     = len(wins) / len(trades) * 100 if trades else 0.0
    years  = max(bars / 252, 0.1)
    net    = sum(t['pnl'] for t in trades)
    init   = final_cap - net
    if init > 0 and final_cap > 0:
        cagr = ((final_cap / init) ** (1 / years) - 1) * 100
    elif init > 0:
        cagr = -100.0
    else:
        cagr = 0.0

    peak = equity[0]; max_dd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd

    dr = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity)) if equity[i-1] > 0]
    sharpe = (statistics.mean(dr) / statistics.stdev(dr) * math.sqrt(252)
              if len(dr) > 2 and statistics.stdev(dr) > 0 else 0.0)

    w_rets = [t['return_pct'] for t in wins]
    l_rets = [t['return_pct'] for t in losses]
    avg_w  = statistics.mean(w_rets) if w_rets  else 0.0
    avg_l  = statistics.mean(l_rets) if l_rets  else 0.0
    wl     = abs(avg_w / avg_l)      if avg_l   else 0.0

    net_pnl   = sum(t['pnl'] for t in trades)
    tot_costs = sum(t.get('cost_total', 0) for t in trades)
    tot_val   = sum(t.get('trade_val', 0) for t in trades)
    cost_pct  = tot_costs / tot_val * 100 if tot_val > 0 else 0.0

    return {
        'trades': len(trades), 'wins': len(wins), 'losses': len(losses),
        'wr': round(wr, 1),    'pf':   round(pf, 3),
        'sharpe': round(sharpe, 3),   'cagr':    round(cagr, 1),
        'max_dd': round(max_dd, 1),   'avg_win':  round(avg_w, 2),
        'avg_loss': round(avg_l, 2),  'wl':       round(wl, 2),
        'net_pnl':  round(net_pnl, 2),
        'cost_pct': round(cost_pct, 3),
        'tot_costs': round(tot_costs, 2),
        'exit_reasons': dict(Counter(t['exit'] for t in trades)),
    }


def pooled_pf(mlist):
    num = sum(v['wins']   * abs(v['avg_win'])  for v in mlist if v.get('losses', 0) > 0)
    den = sum(v['losses'] * abs(v['avg_loss']) for v in mlist if v.get('losses', 0) > 0)
    return round(num / den, 3) if den > 0 else 0.0

def safe_mean(lst): return round(statistics.mean(lst), 3) if lst else 0.0
def agg(mlist, key): return safe_mean([m[key] for m in mlist if m['trades'] > 0])


# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch(ticker, period='5y'):
    try:
        df = yf.Ticker(ticker).history(period=period, interval='1d', auto_adjust=True)
        if df.empty:
            return []
        return [[str(ts.date()),
                 float(row['Open']), float(row['High']),
                 float(row['Low']),  float(row['Close']),
                 float(row.get('Volume', 0) or 0)]
                for ts, row in df.iterrows()]
    except Exception:
        return []


# ═════════════════════════════════════════════════════════════════════════════
#  FETCH
# ═════════════════════════════════════════════════════════════════════════════
print(SEP)
print('  FETCHING 5-YEAR DAILY DATA — 50 NSE STOCKS')
print(SEP)

candles_map = {}
for ticker, sym in STOCKS:
    c = fetch(ticker, '5y')
    candles_map[sym] = c
    print(f'  {sym:<14}: {len(c)} bars  vol_ok={sum(1 for x in c if x[5]>0)} bars with volume')
    time.sleep(0.22)

valid = [(t, s) for t, s in STOCKS if len(candles_map.get(s, [])) >= LOOKBACK + 20]
print(f'\n  Valid: {len(valid)} / {len(STOCKS)} stocks')


# ═════════════════════════════════════════════════════════════════════════════
#  PART 1 — FORENSICS: CONDITIONS A through E
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  PART 1 — SIGNAL FORENSICS: CONDITIONS A THROUGH E')
print(f'  Base: Range={RANGE_PCT}%, Base={BASE_BARS}bars, Vol mult={VOL_MULT}x, Capital=Rs.5,000/stock')
print(SEP)

CONDITIONS = {
    'A': 'Compression only       (no breakout)',
    'B': 'Compression + Breakout (base signal)',
    'C': 'B + Volume > 1.5x avg  (+vol filter)',
    'D': 'B + Close > EMA50      (+trend filter)',
    'E': 'B + Volume + EMA50     (all filters)',
}

# Run IS and OOS for each condition
cond_results = {}
for cname in 'ABCDE':
    sig = make_signal(cname)
    is_list, oos_list = [], []
    all_is_trades, all_oos_trades = [], []
    for _, sym in valid:
        c = candles_map[sym]
        split = int(len(c) * WF_SPLIT)
        c_is  = c[:split]
        c_oos = c[split - LOOKBACK:]
        if len(c_is)  >= LOOKBACK + BASE_BARS + 2:
            m, t = backtest(c_is, sig, capital_init=5000.0)
            if m['trades'] >= 1:
                is_list.append(m)
                all_is_trades.extend(t)
        if len(c_oos) >= LOOKBACK + BASE_BARS + 2:
            m, t = backtest(c_oos, sig, capital_init=5000.0)
            if m['trades'] >= 1:
                oos_list.append(m)
                all_oos_trades.extend(t)
    cond_results[cname] = {
        'is': is_list, 'oos': oos_list,
        'is_trades': all_is_trades, 'oos_trades': all_oos_trades,
    }
    i_t = sum(m['trades'] for m in is_list)
    o_t = sum(m['trades'] for m in oos_list)
    print(f'  [{cname}] Done — IS trades={i_t}  OOS trades={o_t}')

# ── IS Table ──────────────────────────────────────────────────────────────────
print()
print('  IN-SAMPLE RESULTS (Y1-Y3)')
print(f'  {"Cond":<4}  {"Description":<40}  {"Trades":>7}  {"WR%":>6}  {"PF":>7}  '
      f'{"AvgW%":>7}  {"AvgL%":>7}  {"WL":>5}  {"Sharpe":>7}  {"MaxDD%":>7}')
print(sep)

for cname in 'ABCDE':
    r = cond_results[cname]
    m_list = r['is']
    if not m_list:
        print(f'  [{cname}]  {CONDITIONS[cname]:<40}  -- no trades --')
        continue
    t  = sum(m['trades'] for m in m_list)
    wr = sum(m['wins']   for m in m_list) / max(1, t) * 100
    pf = pooled_pf(m_list)
    print(f'  [{cname}]  {CONDITIONS[cname]:<40}  {t:>7}  {wr:>5.1f}%  {pf:>7.3f}  '
          f'{agg(m_list,"avg_win"):>+6.2f}%  {agg(m_list,"avg_loss"):>+6.2f}%  '
          f'{agg(m_list,"wl"):>4.2f}x  {agg(m_list,"sharpe"):>7.3f}  {agg(m_list,"max_dd"):>6.1f}%')

# ── OOS Table ─────────────────────────────────────────────────────────────────
print()
print('  OUT-OF-SAMPLE RESULTS (Y4-Y5)  <-- primary verdict')
print(f'  {"Cond":<4}  {"Description":<40}  {"Trades":>7}  {"WR%":>6}  {"PF":>7}  '
      f'{"AvgW%":>7}  {"AvgL%":>7}  {"WL":>5}  {"Sharpe":>7}  {"MaxDD%":>7}  {"CAGR%":>7}')
print(sep)

base_oos_pf = None
for cname in 'ABCDE':
    r = cond_results[cname]
    m_list = r['oos']
    if not m_list:
        print(f'  [{cname}]  {CONDITIONS[cname]:<40}  -- no trades --')
        continue
    t  = sum(m['trades'] for m in m_list)
    wr = sum(m['wins']   for m in m_list) / max(1, t) * 100
    pf = pooled_pf(m_list)
    if cname == 'B':
        base_oos_pf = pf
    delta = f'{pf - base_oos_pf:+.3f}' if base_oos_pf is not None and cname != 'B' else '  base'
    flag = ''
    if cname != 'B' and base_oos_pf is not None:
        diff = pf - base_oos_pf
        if   diff >  0.05: flag = '  ADDS EDGE'
        elif diff < -0.05: flag = '  HURTS'
        else:              flag = '  neutral'
    print(f'  [{cname}]  {CONDITIONS[cname]:<40}  {t:>7}  {wr:>5.1f}%  {pf:>7.3f}  '
          f'{agg(m_list,"avg_win"):>+6.2f}%  {agg(m_list,"avg_loss"):>+6.2f}%  '
          f'{agg(m_list,"wl"):>4.2f}x  {agg(m_list,"sharpe"):>7.3f}  '
          f'{agg(m_list,"max_dd"):>6.1f}%  {agg(m_list,"cagr"):>+6.1f}%  {delta}{flag}')

# ── Incremental lift table ────────────────────────────────────────────────────
print()
print('  INCREMENTAL LIFT ANALYSIS (vs Condition B baseline)')
print(f'  {"Addition":<35}  {"OOS Trades":>10}  {"OOS PF":>8}  {"Lift":>8}  '
      f'{"Trade reduction":>16}  Verdict')
print(sep)

b_t  = sum(m['trades'] for m in cond_results['B']['oos'])
b_pf = pooled_pf(cond_results['B']['oos'])

additions = [
    ('C', 'Volume > 1.5x avg'),
    ('D', 'Close above EMA50'),
    ('E', 'Volume + EMA50 (both)'),
]
for cname, desc in additions:
    r   = cond_results[cname]
    m_list = r['oos']
    if not m_list:
        print(f'  {desc:<35}  {"0":>10}  {"---":>8}  {"---":>8}  {"---":>16}  No trades')
        continue
    c_t  = sum(m['trades'] for m in m_list)
    c_pf = pooled_pf(m_list)
    lift = c_pf - b_pf
    reduction = b_t - c_t
    red_pct   = reduction / b_t * 100 if b_t > 0 else 0
    verdict = ('KEEP — PF gain worth trade loss' if lift > 0.05
               else 'SKIP — filters too many good trades' if lift < -0.02
               else 'MARGINAL — negligible impact')
    print(f'  {desc:<35}  {c_t:>10}  {c_pf:>8.3f}  {lift:>+8.3f}  '
          f'{reduction:>6} ({red_pct:.0f}%)  {verdict}')

# ── Exit reason breakdown ─────────────────────────────────────────────────────
print()
print('  EXIT REASON BREAKDOWN — OOS (all conditions)')
print(f'  {"Cond":<4}  {"SL":>6}  {"TP":>6}  {"Trail":>7}  {"EoP":>6}  '
      f'{"SL%":>6}  {"TP%":>6}  Notes')
print(sep)
for cname in 'ABCDE':
    m_list = cond_results[cname]['oos']
    if not m_list: continue
    er = Counter()
    t_total = 0
    for m in m_list:
        for k, v in m['exit_reasons'].items():
            er[k] += v
        t_total += m['trades']
    if t_total == 0: continue
    sl_n = er.get('SL', 0); tp_n = er.get('TP', 0)
    tr_n = er.get('Trail', 0); ep_n = er.get('EoP', 0)
    note = ''
    if sl_n / max(1, t_total) > 0.6:
        note = 'High SL rate — entries too early or SL too tight'
    elif tp_n / max(1, t_total) > 0.3:
        note = 'Good TP hit rate — winners running well'
    print(f'  [{cname}]  {sl_n:>6}  {tp_n:>6}  {tr_n:>7}  {ep_n:>6}  '
          f'{sl_n/t_total*100:>5.0f}%  {tp_n/t_total*100:>5.0f}%  {note}')

# ── MFE / MAE analysis for Condition B ────────────────────────────────────────
print()
print('  MFE / MAE ANALYSIS — Condition B OOS (are exits harvesting the full move?)')
b_oos_trades = cond_results['B']['oos_trades']
if b_oos_trades:
    winners = [t for t in b_oos_trades if t['winner'] == 1]
    losers  = [t for t in b_oos_trades if t['winner'] == 0]
    print(f'  OOS trades: {len(b_oos_trades)}  ({len(winners)} wins, {len(losers)} losses)')
    if winners:
        w_mfe = safe_mean([t['mfe_pct'] for t in winners])
        w_ret = safe_mean([t['return_pct'] for t in winners])
        w_cap = w_ret / w_mfe * 100 if w_mfe > 0 else 0
        print(f'  Winners: Avg MFE={w_mfe:+.2f}%  Avg Return={w_ret:+.2f}%  '
              f'Captured={w_cap:.0f}%  Left on table={w_mfe-w_ret:.2f}%')
    if losers:
        l_mae = safe_mean([t['mae_pct'] for t in losers])
        l_ret = safe_mean([t['return_pct'] for t in losers])
        print(f'  Losers:  Avg MAE={l_mae:+.2f}%  Avg Return={l_ret:+.2f}%  '
              f'(SL={SL_PCT}% is {"tight" if abs(l_mae) > SL_PCT else "holding"})')


# ═════════════════════════════════════════════════════════════════════════════
#  PART 2 — POSITION SIZE STUDY
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  PART 2 — POSITION SIZE vs TRANSACTION COSTS')
print(f'  Signal: Range={RANGE_PCT}%, Base={BASE_BARS}bars (Condition B, best config)')
print('  Walk-forward OOS period (Y4-Y5), 50 stocks, fixed position per trade')
print(SEP)

POSITION_SIZES = [5_000, 10_000, 25_000, 50_000, 1_00_000]
sig_B = make_signal('B')

# Cost breakdown per position size (theoretical, at SLIPPAGE=0.2% each way)
print('  THEORETICAL COST BREAKDOWN PER TRADE (before any trade):')
print(f'  {"Position":>12}  {"Brokerage":>10}  {"STT":>8}  {"Slippage":>10}  '
      f'{"Exchange":>10}  {"Total Rs.":>10}  {"Total %":>9}')
print(sep)
for pos in POSITION_SIZES:
    brk  = BROKERAGE * 2                          # Rs.20 in + Rs.20 out
    stt  = pos * STT_PCT                          # on sell (approx pos size)
    slip = pos * SLIPPAGE * 2                     # both ways
    exch = pos * EXCHANGE_PCT * 2                 # both ways
    tot  = brk + stt + slip + exch
    pct  = tot / pos * 100
    print(f'  Rs.{pos:>9,}  Rs.{brk:>7.0f}  Rs.{stt:>5.1f}  Rs.{slip:>7.0f}  '
          f'Rs.{exch:>7.2f}  Rs.{tot:>8.1f}  {pct:>8.2f}%')

print()
print('  BACKTEST RESULTS BY POSITION SIZE (OOS, 50 stocks, fixed allocation):')
print(f'  {"Position":>12}  {"Trades":>7}  {"WR%":>6}  {"PF":>7}  '
      f'{"Net P&L":>10}  {"Avg P&L/tr":>11}  {"Cost%":>7}  '
      f'{"Sharpe":>7}  {"MaxDD%":>7}  {"CAGR%":>7}')
print(sep)

size_results = {}
for pos in POSITION_SIZES:
    is_list, oos_list, all_oos_t = [], [], []
    big_capital = pos * 200   # ensure we never run out of capital

    for _, sym in valid:
        c = candles_map[sym]
        split = int(len(c) * WF_SPLIT)
        c_oos = c[split - LOOKBACK:]
        if len(c_oos) < LOOKBACK + BASE_BARS + 2:
            continue
        m, t = backtest(c_oos, sig_B,
                        capital_init=big_capital,
                        fixed_position=pos)
        if m['trades'] >= 1:
            oos_list.append(m)
            all_oos_t.extend(t)

    size_results[pos] = {'oos': oos_list, 'trades': all_oos_t}

    if not oos_list:
        print(f'  Rs.{pos:>9,}  -- no trades --')
        continue

    o_t     = sum(m['trades']  for m in oos_list)
    o_w     = sum(m['wins']    for m in oos_list)
    o_pf    = pooled_pf(oos_list)
    o_wr    = o_w / o_t * 100 if o_t else 0
    net_pnl = sum(t['pnl']     for t in all_oos_t)
    avg_pnl = net_pnl / o_t    if o_t else 0
    cost_pct = safe_mean([m['cost_pct'] for m in oos_list if m['trades'] > 0])
    o_sh    = agg(oos_list, 'sharpe')
    o_dd    = agg(oos_list, 'max_dd')
    o_cagr  = agg(oos_list, 'cagr')

    flag = ''
    if   o_pf >= 1.2: flag = '  *** PROFITABLE ***'
    elif o_pf >= 1.0: flag = '  ** BREAKEVEN **'

    print(f'  Rs.{pos:>9,}  {o_t:>7}  {o_wr:>5.1f}%  {o_pf:>7.3f}  '
          f'Rs.{net_pnl:>+8,.0f}  Rs.{avg_pnl:>+8,.0f}  {cost_pct:>6.2f}%  '
          f'{o_sh:>7.3f}  {o_dd:>6.1f}%  {o_cagr:>+6.1f}%{flag}')

# ── Cost impact visualisation ──────────────────────────────────────────────────
print()
print('  COST DRAG vs EDGE VISUALISATION:')
print(f'  {"Position":>12}  {"Cost drag":>10}  {"Raw edge":>10}  '
      f'{"Net edge":>10}  {"Viable?"}')
print(sep)

# Estimate raw edge from OOS win/loss at different sizes
# Raw edge ≈ PF without costs (back-calculate)
# Approximate: raw_edge = (wr * avg_win - (1-wr) * avg_loss) / position
for pos in POSITION_SIZES:
    oos_list = size_results[pos]['oos']
    if not oos_list: continue
    all_t = size_results[pos]['trades']
    o_t   = len(all_t)
    if o_t == 0: continue

    # Cost drag: total costs / total trade value
    tot_cost = sum(t.get('cost_total', 0) for t in all_t)
    tot_val  = sum(t.get('trade_val',  0) for t in all_t)
    cost_drag = tot_cost / tot_val * 100 if tot_val > 0 else 0

    # Net return per trade vs cost per trade
    net_pnl_per_trade = sum(t['pnl'] for t in all_t) / o_t
    net_pct = net_pnl_per_trade / pos * 100

    # Cost per trade as % of position
    cost_per_trade_pct = (tot_cost / o_t) / pos * 100 if o_t > 0 else 0

    # Raw edge = net + cost drag (what we'd make without any costs)
    raw_edge = net_pct + cost_per_trade_pct
    viable = 'YES' if net_pct > 0 else ('NEAR' if net_pct > -0.3 else 'NO')
    print(f'  Rs.{pos:>9,}  {cost_per_trade_pct:>9.2f}%  {raw_edge:>+9.2f}%  '
          f'{net_pct:>+9.2f}%  {viable}')

print()
print('  INTERPRETATION:')
print('  Raw edge   = what the strategy earns per trade BEFORE costs')
print('  Cost drag  = brokerage + STT + slippage as % of position')
print('  Net edge   = raw edge - cost drag (actual P&L per trade)')


# ═════════════════════════════════════════════════════════════════════════════
#  MASTER VERDICT
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  MASTER VERDICT')
print(SEP)

# Best condition
best_cond = max('ABCDE', key=lambda c:
    pooled_pf(cond_results[c]['oos']) if cond_results[c]['oos'] else 0)
best_cond_pf = pooled_pf(cond_results[best_cond]['oos'])

# Best position size
def net_for_pos(pos):
    t = size_results[pos]['trades']
    return sum(x['pnl'] for x in t) if t else 0

best_pos = max(POSITION_SIZES, key=net_for_pos)

# Is the strategy fundamentally unprofitable or just cost-limited?
b_oos_pf = pooled_pf(cond_results['B']['oos'])

print(f'  1. MINIMUM VIABLE SIGNAL:')
print(f'     Condition B (Compression + Breakout) is the minimum viable signal.')
b_list = cond_results['B']['oos']
b_t = sum(m['trades'] for m in b_list)
print(f'     OOS: {b_t} trades, PF={b_oos_pf:.3f}')
b_d = pooled_pf(cond_results['D']['oos'])
b_c = pooled_pf(cond_results['C']['oos'])
if b_d > b_oos_pf + 0.03:
    print(f'     Adding EMA50 filter (Condition D) improves PF to {b_d:.3f} — worth adding.')
elif b_c > b_oos_pf + 0.03:
    print(f'     Adding Volume filter (Condition C) improves PF to {b_c:.3f} — worth adding.')
else:
    print(f'     Adding filters (C/D/E) does not meaningfully improve OOS PF.')
    print(f'     The breakout itself contains the full edge. No extra filters needed.')

print()
print(f'  2. IS THE STRATEGY FUNDAMENTALLY UNPROFITABLE OR COST-LIMITED?')
# Check: does raw edge > 0?
b_trades_oos = cond_results['B']['oos_trades']
if b_trades_oos:
    tot_cost_b = sum(t.get('cost_total',0) for t in b_trades_oos)
    tot_val_b  = sum(t.get('trade_val', 0) for t in b_trades_oos)
    net_pnl_b  = sum(t['pnl'] for t in b_trades_oos)
    raw_edge_b = net_pnl_b + tot_cost_b
    print(f'     Total OOS net P&L (Cond B, Rs.5000): Rs.{net_pnl_b:+,.0f}')
    print(f'     Total costs incurred               : Rs.{tot_cost_b:+,.0f}')
    print(f'     P&L before costs (raw edge)        : Rs.{raw_edge_b:+,.0f}')
    if raw_edge_b > 0:
        print(f'     ANSWER: COST-LIMITED. The raw edge is POSITIVE (Rs.{raw_edge_b:+,.0f}).')
        print(f'     The strategy makes money before costs but costs consume it at small sizes.')
        breakeven_pos = tot_cost_b / len(b_trades_oos) / (raw_edge_b / len(b_trades_oos) / 100) * 100
        print(f'     Estimated breakeven position size: ~Rs.{breakeven_pos:,.0f}')
    else:
        print(f'     ANSWER: FUNDAMENTALLY UNPROFITABLE. Raw edge is negative (Rs.{raw_edge_b:+,.0f}).')
        print(f'     Even with zero costs, the signal does not produce a positive expectancy.')

print()
print(f'  3. RECOMMENDED DEPLOYMENT CONFIG:')
if b_oos_pf >= 0.95:
    print(f'     Signal   : Compression + Breakout (Condition B)')
    print(f'     Range    : {RANGE_PCT}%  Base: {BASE_BARS} bars')
    print(f'     Min size : Rs.25,000-50,000 per position for viability')
    print(f'     Universe : Screen stocks monthly — prefer low-vol, EMA uptrend')
    print(f'     Caution  : OOS PF={b_oos_pf:.3f} — marginally below breakeven at Rs.5k')
    print(f'               Scale position or reduce broker fees before going live')
else:
    print(f'     OOS PF={b_oos_pf:.3f} — strategy needs further improvement before deployment.')
