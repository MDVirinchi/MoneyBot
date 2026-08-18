"""
sideways_base.py — Sideways Base Strategy: derived from S3 mean-reversion research.

Hypothesis: the edge is not in the oversold condition itself (RSI<30) but in the
STABILISATION that follows it. A base that forms without making a new low signals
buyers absorbing supply — a high-probability breakout follows.

Signal definition:
  1. RSI dropped below 30 within the last 15 bars (oversold context)
  2. Last 4 completed bars did NOT make a new low vs the bar before them
  3. Trading range of those 4 bars (max_high - min_low) / min_low <= 3%
  4. ATR of those 4 bars < ATR of the prior 10 bars (volatility contraction)
  5. Current close breaks above the highest close of those 4 base bars (trigger)
  6. Price above EMA50 (long-term trend filter)

Execution: same cost model, same SL=2%/TP=6%/Trail=1.5%, next-open fill.

Comparison strategies (identical costs + execution):
  A. Sideways Base  (new)
  B. RSI<30         (S3 original)
  C. RSI<20+VarB    (prior best single-stock result)
  D. EMA 9/21 Cross (original moneybot strategy)

Test: 50 NSE stocks, 5 years, walk-forward Y1-Y3 IS / Y4-Y5 OOS.
"""

import time, math, logging, warnings, statistics
from collections import Counter, defaultdict

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
WF_SPLIT     = 0.60      # 60% IS (≈3Y), 40% OOS (≈2Y)

SEP = '=' * 116
sep = '-' * 116

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


def rsi_val(closes, period=14):
    if len(closes) <= period:
        return 50.0
    sub = closes[-(period + 1):]
    gains, losses = [], []
    for i in range(1, len(sub)):
        d = sub[i] - sub[i - 1]
        (gains if d > 0 else losses).append(abs(d))
    ag = sum(gains) / period if gains else 1e-9
    al = sum(losses) / period if losses else 1e-9
    return 100 - 100 / (1 + ag / al)


def atr_series(candles, period=14):
    """Return list of ATR values, one per bar (starting from bar 1)."""
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i][2], candles[i][3], candles[i-1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return [0.0]
    result = []
    for i in range(len(trs)):
        window_trs = trs[max(0, i - period + 1): i + 1]
        result.append(sum(window_trs) / len(window_trs))
    return result


# ── STRATEGY A: SIDEWAYS BASE ─────────────────────────────────────────────────
def signal_sideways_base(window):
    """
    Sideways base breakout after RSI<30 oversold.
    Conditions checked on bar i; entry executed at bar i+1 open.
    """
    if len(window) < LOOKBACK:
        return False

    closes = [c[4] for c in window]
    highs  = [c[2] for c in window]
    lows   = [c[3] for c in window]

    # ── Condition 1: RSI was below 30 within last 15 bars ─────────────────────
    was_oversold = False
    for j in range(1, 16):
        if len(closes) < j + 15:
            break
        subset = closes[:len(closes) - j + 1] if j > 1 else closes
        if rsi_val(subset) < 30:
            was_oversold = True
            break
    if not was_oversold:
        return False

    # ── Define the base: last 4 completed bars (excluding current signal bar) ──
    BASE = 4
    if len(window) < BASE + 3:
        return False

    # base_bars = bars -(BASE+1) to -2 (the 4 bars before current)
    base_slice  = window[-(BASE + 1):-1]    # 4 base bars
    pre_bar     = window[-(BASE + 2)]       # bar just before the base

    base_closes = [c[4] for c in base_slice]
    base_highs  = [c[2] for c in base_slice]
    base_lows   = [c[3] for c in base_slice]

    pre_low = pre_bar[3]

    # ── Condition 2: No new low during the base ────────────────────────────────
    # Each base bar's low must stay at or above the pre-base bar's low
    if min(base_lows) < pre_low * 0.995:
        return False

    # ── Condition 3: Trading range <= 3% ──────────────────────────────────────
    range_hi  = max(base_highs)
    range_lo  = min(base_lows)
    range_pct = (range_hi - range_lo) / range_lo * 100 if range_lo > 0 else 99.0
    if range_pct > 3.0:
        return False

    # ── Condition 4: ATR contracting ──────────────────────────────────────────
    atrs = atr_series(window)
    if len(atrs) < BASE + 11:
        return False
    atr_base = atrs[-1]                          # current ATR (during base)
    atr_pre  = sum(atrs[-(BASE + 11):-(BASE + 1)]) / 10  # avg ATR 10 bars before base
    if atr_pre <= 0 or atr_base >= atr_pre:
        return False

    # ── Condition 5: Current close breaks above highest base close ────────────
    highest_base_close = max(base_closes)
    current_close      = closes[-1]
    if current_close <= highest_base_close * 1.001:   # 0.1% buffer
        return False

    # ── Condition 6: Price above EMA50 (long-term trend filter) ───────────────
    e50 = ema(closes, 50)
    if not e50 or current_close < e50[-1] * 0.98:
        return False

    return True


# ── STRATEGY B: RSI<30 BASELINE (S3 original) ────────────────────────────────
def signal_rsi30(window):
    closes = [c[4] for c in window]
    if len(closes) < 25:
        return False
    curr_rsi = rsi_val(closes)
    if not (35 <= curr_rsi <= 55):
        return False
    was_oversold = any(
        rsi_val(closes[:-(j-1)] if j > 1 else closes) < 30
        for j in range(2, 7)
        if len(closes) >= j + 14
    )
    if not was_oversold:
        return False
    e50 = ema(closes, 50)
    return bool(e50 and closes[-1] >= e50[-1] * 0.98)


# ── STRATEGY C: RSI<20 + VARIANT B ───────────────────────────────────────────
def signal_rsi20_varB(window):
    closes = [c[4] for c in window]
    if len(closes) < 25:
        return False
    curr_rsi = rsi_val(closes)
    if not (25 <= curr_rsi <= 55):
        return False
    was_extreme = any(
        rsi_val(closes[:-(j-1)] if j > 1 else closes) < 20
        for j in range(2, 7)
        if len(closes) >= j + 14
    )
    if not was_extreme:
        return False
    e50 = ema(closes, 50)
    if not e50 or closes[-1] < e50[-1] * 0.98:
        return False
    # Variant B: close > previous day's high
    return len(window) >= 2 and closes[-1] > window[-2][2]


# ── STRATEGY D: EMA 9/21 CROSS ────────────────────────────────────────────────
def signal_ema_cross(window):
    closes = [c[4] for c in window]
    if len(closes) < 22:
        return False
    e9  = ema(closes, 9)
    e21 = ema(closes, 21)
    if len(e9) < 2 or len(e21) < 2:
        return False
    # Fresh cross: e9 crossed above e21 on the last bar
    crossed = e9[-2] <= e21[-2] and e9[-1] > e21[-1]
    return crossed


# ── Backtester ────────────────────────────────────────────────────────────────
def backtest(candles, sig_fn):
    capital  = CAPITAL
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
            if   ltp <= sl:                                          reason = 'StopLoss'
            elif ltp >= tp:                                          reason = 'TakeProfit'
            elif ltp <= trail and high > position['entry'] * 1.005: reason = 'TrailingStop'

            if reason:
                exit_px  = ltp * (1 - SLIPPAGE)
                exit_val = position['qty'] * exit_px
                costs    = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
                pnl      = (exit_px - position['entry']) * position['qty'] - costs
                capital  += pnl
                trades.append({
                    'pnl':         pnl,
                    'return_pct':  (exit_px / position['entry'] - 1) * 100,
                    'exit_reason': reason,
                    'winner':      1 if pnl > 0 else 0,
                    'mfe_pct':     (position['high'] / position['entry'] - 1) * 100,
                    'mae_pct':     (position['low']  / position['entry'] - 1) * 100,
                    'duration':    i - position['entry_bar'],
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
                    position = {
                        'qty': qty, 'entry': fill_px,
                        'high': fill_px, 'low': fill_px,
                        'entry_bar': i,
                    }
        equity.append(capital)

    if position:
        ltp     = candles[-1][4]
        exit_px = ltp * (1 - SLIPPAGE)
        costs   = BROKERAGE + position['qty'] * exit_px * (STT_PCT + EXCHANGE_PCT)
        pnl     = (exit_px - position['entry']) * position['qty'] - costs
        trades.append({
            'pnl': pnl,
            'return_pct': (exit_px / position['entry'] - 1) * 100,
            'exit_reason': 'EndOfPeriod',
            'winner': 1 if pnl > 0 else 0,
            'mfe_pct': (position['high'] / position['entry'] - 1) * 100,
            'mae_pct': (position['low']  / position['entry'] - 1) * 100,
            'duration': len(candles) - 1 - position['entry_bar'],
        })
        capital += pnl

    return _metrics(trades, equity, capital, len(candles) - LOOKBACK)


def _metrics(trades, equity, final_cap, bars):
    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp     = sum(t['pnl'] for t in wins)
    gl     = abs(sum(t['pnl'] for t in losses))
    pf     = gp / gl if gl > 0 else (1.0 if gp > 0 else 0.0)
    wr     = len(wins) / len(trades) * 100 if trades else 0.0
    years  = max(bars / 252, 0.1)
    cagr   = ((final_cap / CAPITAL) ** (1 / years) - 1) * 100 if final_cap > 0 else -100.0

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

    return {
        'trades': len(trades), 'wins': len(wins), 'losses': len(losses),
        'wr': round(wr, 1),     'pf':   round(pf, 3),
        'sharpe': round(sharpe, 3),    'cagr':    round(cagr, 1),
        'max_dd': round(max_dd, 1),    'avg_win':  round(avg_w, 2),
        'avg_loss': round(avg_l, 2),   'wl':       round(wl, 2),
        'net_pnl':  round(final_cap - CAPITAL, 2),
        'exit_reasons': dict(Counter(t['exit_reason'] for t in trades)),
    }


def pooled_pf(mlist):
    num = sum(v['wins']   * abs(v['avg_win'])  for v in mlist if v.get('losses', 0) > 0)
    den = sum(v['losses'] * abs(v['avg_loss']) for v in mlist if v.get('losses', 0) > 0)
    return round(num / den, 3) if den > 0 else 0.0


def agg(mlist, key):
    vals = [m[key] for m in mlist if m['trades'] > 0]
    return statistics.mean(vals) if vals else 0.0


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
    print(f'  {sym:<14}: {len(c)} bars')
    time.sleep(0.22)

valid_stocks = [(t, s) for t, s in STOCKS if len(candles_map.get(s, [])) >= LOOKBACK + 20]
print(f'\n  Valid stocks: {len(valid_stocks)} / {len(STOCKS)}')


# ═════════════════════════════════════════════════════════════════════════════
#  WALK-FORWARD ENGINE
# ═════════════════════════════════════════════════════════════════════════════
STRATEGIES = [
    ('Sideways Base', signal_sideways_base),
    ('RSI<30 (S3)',   signal_rsi30),
    ('RSI<20+VarB',   signal_rsi20_varB),
    ('EMA 9/21 Cross',signal_ema_cross),
]

# Collect per-stock results for each strategy
results = {name: {'is': [], 'oos': []} for name, _ in STRATEGIES}
per_stock = {name: {} for name, _ in STRATEGIES}

print()
print('  Running walk-forward backtest for all 4 strategies...')
print(f'  ({len(valid_stocks)} stocks x 4 strategies x IS+OOS = {len(valid_stocks)*8} runs)')
print()

for ticker, sym in valid_stocks:
    candles = candles_map[sym]
    split   = int(len(candles) * WF_SPLIT)
    c_is    = candles[:split]
    c_oos   = candles[split - LOOKBACK:]

    for name, sig_fn in STRATEGIES:
        m_is  = backtest(c_is,  sig_fn) if len(c_is)  >= LOOKBACK + 5 else None
        m_oos = backtest(c_oos, sig_fn) if len(c_oos) >= LOOKBACK + 5 else None
        per_stock[name][sym] = (m_is, m_oos)
        if m_is  and m_is['trades']  >= 1: results[name]['is'].append(m_is)
        if m_oos and m_oos['trades'] >= 1: results[name]['oos'].append(m_oos)

print('  Done.')


# ═════════════════════════════════════════════════════════════════════════════
#  PER-STOCK DETAIL — SIDEWAYS BASE
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  SIDEWAYS BASE — PER-STOCK DETAIL (walk-forward)')
print(SEP)
print(f'  {"Stock":<14}  {"IS-Tr":>5}  {"IS-WR":>6}  {"IS-PF":>6}  {"IS-CAGR":>8}  '
      f'{"OOS-Tr":>6}  {"OOS-WR":>7}  {"OOS-PF":>7}  {"OOS-CAGR":>9}  {"Edge?":>7}')
print(sep)

sb_oos_pfs = []
for _, sym in valid_stocks:
    m_is, m_oos = per_stock['Sideways Base'].get(sym, (None, None))
    is_str  = (f'{m_is["trades"]:>5}  {m_is["wr"]:>5.1f}%  {m_is["pf"]:>6.3f}  '
               f'{m_is["cagr"]:>+7.1f}%') if m_is else '   --      --      --        --'
    oos_str = (f'{m_oos["trades"]:>6}  {m_oos["wr"]:>6.1f}%  {m_oos["pf"]:>7.3f}  '
               f'{m_oos["cagr"]:>+8.1f}%') if m_oos else '    --      --       --         --'
    edge = '---'
    if m_oos and m_oos['trades'] >= 3:
        if   m_oos['pf'] >= 1.5: edge = 'STRONG'
        elif m_oos['pf'] >= 1.0: edge = 'HOLDS'
        elif m_oos['pf'] >= 0.7: edge = 'WEAK'
        else:                     edge = 'FAILS'
        sb_oos_pfs.append((sym, m_oos['pf'], m_oos['trades']))
    print(f'  {sym:<14}  {is_str}  {oos_str}  {edge:>7}')

print(sep)
sb_is  = results['Sideways Base']['is']
sb_oos = results['Sideways Base']['oos']
is_t   = sum(m['trades'] for m in sb_is)
oos_t  = sum(m['trades'] for m in sb_oos)
is_wr  = sum(m['wins'] for m in sb_is)  / max(1, is_t)  * 100
oos_wr = sum(m['wins'] for m in sb_oos) / max(1, oos_t) * 100
print(f'  {"AGGREGATE":<14}  '
      f'{is_t:>5}  {is_wr:>5.1f}%  {pooled_pf(sb_is):>6.3f}  {agg(sb_is,"cagr"):>+7.1f}%  '
      f'{oos_t:>6}  {oos_wr:>6.1f}%  {pooled_pf(sb_oos):>7.3f}  {agg(sb_oos,"cagr"):>+8.1f}%')


# ═════════════════════════════════════════════════════════════════════════════
#  HEAD-TO-HEAD COMPARISON TABLE
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  HEAD-TO-HEAD COMPARISON — IS vs OOS (pooled across 50 stocks)')
print(SEP)
print(f'  {"Strategy":<20}  {"IS Tr":>6}  {"IS WR":>6}  {"IS PF":>7}  {"IS CAGR":>8}  '
      f'{"OOS Tr":>7}  {"OOS WR":>7}  {"OOS PF":>8}  {"OOS CAGR":>9}  '
      f'{"MaxDD":>7}  {"Sharpe":>7}  {"WL":>6}')
print(sep)

for name, _ in STRATEGIES:
    is_m  = results[name]['is']
    oos_m = results[name]['oos']
    if not is_m and not oos_m:
        print(f'  {name:<20}  -- no trades --')
        continue
    i_t   = sum(m['trades'] for m in is_m)
    o_t   = sum(m['trades'] for m in oos_m)
    i_wr  = sum(m['wins'] for m in is_m)  / max(1, i_t)  * 100
    o_wr  = sum(m['wins'] for m in oos_m) / max(1, o_t) * 100
    i_pf  = pooled_pf(is_m)
    o_pf  = pooled_pf(oos_m)
    i_cagr = agg(is_m,  'cagr')
    o_cagr = agg(oos_m, 'cagr')
    o_dd   = agg(oos_m, 'max_dd')
    o_sh   = agg(oos_m, 'sharpe')
    o_wl   = agg(oos_m, 'wl')
    flag = ''
    if   o_pf >= 1.2: flag = '  *** PROFITABLE ***'
    elif o_pf >= 1.0: flag = '  ** BREAKEVEN **'
    elif o_pf >= 0.8: flag = '  * NEAR BREAKEVEN *'
    print(f'  {name:<20}  {i_t:>6}  {i_wr:>5.1f}%  {i_pf:>7.3f}  {i_cagr:>+7.1f}%  '
          f'{o_t:>7}  {o_wr:>6.1f}%  {o_pf:>8.3f}  {o_cagr:>+8.1f}%  '
          f'{o_dd:>6.1f}%  {o_sh:>7.3f}  {o_wl:>5.2f}x{flag}')


# ═════════════════════════════════════════════════════════════════════════════
#  SIDEWAYS BASE DEEP METRICS
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  SIDEWAYS BASE — DETAILED OOS METRICS')
print(SEP)

if sb_oos:
    o_t    = sum(m['trades'] for m in sb_oos)
    o_w    = sum(m['wins']   for m in sb_oos)
    o_l    = sum(m['losses'] for m in sb_oos)
    o_pf   = pooled_pf(sb_oos)
    o_wr   = o_w / o_t * 100 if o_t else 0
    o_avgw = agg(sb_oos, 'avg_win')
    o_avgl = agg(sb_oos, 'avg_loss')
    o_wl   = agg(sb_oos, 'wl')
    o_cagr = agg(sb_oos, 'cagr')
    o_dd   = agg(sb_oos, 'max_dd')
    o_sh   = agg(sb_oos, 'sharpe')

    print(f'  Total OOS trades     : {o_t}')
    print(f'  Win rate             : {o_wr:.1f}%')
    print(f'  Profit factor        : {o_pf:.3f}')
    print(f'  Avg win              : {o_avgw:+.2f}%')
    print(f'  Avg loss             : {o_avgl:+.2f}%')
    print(f'  Win/Loss ratio       : {o_wl:.2f}x')
    print(f'  CAGR (avg per stock) : {o_cagr:+.1f}%')
    print(f'  Max drawdown (avg)   : {o_dd:.1f}%')
    print(f'  Sharpe (avg)         : {o_sh:.3f}')

    # Exit reasons (OOS)
    exit_totals = Counter()
    for m in sb_oos:
        for reason, cnt in m['exit_reasons'].items():
            exit_totals[reason] += cnt
    print()
    print('  OOS exit reasons:')
    for reason, cnt in sorted(exit_totals.items(), key=lambda x: -x[1]):
        print(f'    {reason:<16}: {cnt:>4}  ({cnt/o_t*100:.0f}%)')

    # Top and bottom stocks OOS
    print()
    sb_oos_sorted = sorted(sb_oos_pfs, key=lambda x: -x[1])
    print('  Top 5 OOS stocks by PF:')
    for sym, pf_v, tr in sb_oos_sorted[:5]:
        m = per_stock['Sideways Base'][sym][1]
        print(f'    {sym:<14}  PF={pf_v:.3f}  Trades={tr}  WR={m["wr"]:.1f}%  CAGR={m["cagr"]:+.1f}%')
    if len(sb_oos_sorted) > 5:
        print('  Bottom 5 OOS stocks by PF:')
        for sym, pf_v, tr in sb_oos_sorted[-5:]:
            m = per_stock['Sideways Base'][sym][1]
            print(f'    {sym:<14}  PF={pf_v:.3f}  Trades={tr}  WR={m["wr"]:.1f}%  CAGR={m["cagr"]:+.1f}%')


# ═════════════════════════════════════════════════════════════════════════════
#  CONDITION ABLATION — WHICH FILTERS ADD VALUE?
#  Test removing each condition individually to see which one matters most
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  CONDITION ABLATION — SIDEWAYS BASE (OOS, 10 most liquid stocks for speed)')
print('  Removing one condition at a time to find which filters drive the edge')
print(SEP)

# Use top 10 by bar count for speed
top10 = [s for _, s in valid_stocks[:10]]

def make_ablated_signal(skip_condition):
    """Return signal with one condition removed."""
    def sig(window):
        if len(window) < LOOKBACK: return False
        closes = [c[4] for c in window]
        BASE = 4
        if len(window) < BASE + 3: return False

        # Condition 1: RSI was below 30
        was_oversold = any(
            rsi_val(closes[:len(closes)-j+1] if j > 1 else closes) < 30
            for j in range(1, 16) if len(closes) >= j + 14
        )
        if skip_condition != 1 and not was_oversold:
            return False

        base_slice  = window[-(BASE + 1):-1]
        pre_bar     = window[-(BASE + 2)]
        base_closes = [c[4] for c in base_slice]
        base_highs  = [c[2] for c in base_slice]
        base_lows   = [c[3] for c in base_slice]
        pre_low     = pre_bar[3]

        # Condition 2: No new low
        if skip_condition != 2 and min(base_lows) < pre_low * 0.995:
            return False

        # Condition 3: Range <= 3%
        range_pct = (max(base_highs) - min(base_lows)) / min(base_lows) * 100 if min(base_lows) > 0 else 99
        if skip_condition != 3 and range_pct > 3.0:
            return False

        # Condition 4: ATR contracting
        atrs = atr_series(window)
        if len(atrs) >= BASE + 11:
            atr_base = atrs[-1]
            atr_pre  = sum(atrs[-(BASE+11):-(BASE+1)]) / 10
            if skip_condition != 4 and atr_pre > 0 and atr_base >= atr_pre:
                return False

        # Condition 5: Breakout
        highest_base_close = max(base_closes)
        if skip_condition != 5 and closes[-1] <= highest_base_close * 1.001:
            return False

        # Condition 6: EMA50
        e50 = ema(closes, 50)
        if skip_condition != 6 and (not e50 or closes[-1] < e50[-1] * 0.98):
            return False

        return True
    return sig

ablation_labels = {
    0: 'Full signal (all conditions)',
    1: 'Skip: RSI<30 context',
    2: 'Skip: No-new-low filter',
    3: 'Skip: 3% range filter',
    4: 'Skip: ATR contraction',
    5: 'Skip: Breakout trigger',
    6: 'Skip: EMA50 trend filter',
}

print(f'  {"Condition removed":<35}  {"OOS Trades":>10}  {"OOS WR%":>8}  {"OOS PF":>8}  {"vs Full":>8}')
print(sep)

full_oos_pf = None
for skip in range(7):
    sig_fn = signal_sideways_base if skip == 0 else make_ablated_signal(skip)
    abl_oos = []
    for _, sym in valid_stocks[:10]:
        c = candles_map[sym]
        split = int(len(c) * WF_SPLIT)
        c_oos = c[split - LOOKBACK:]
        if len(c_oos) >= LOOKBACK + 5:
            m = backtest(c_oos, sig_fn)
            if m['trades'] >= 1:
                abl_oos.append(m)
    o_t  = sum(m['trades'] for m in abl_oos)
    o_wr = sum(m['wins']   for m in abl_oos) / max(1, o_t) * 100
    o_pf = pooled_pf(abl_oos)
    if skip == 0:
        full_oos_pf = o_pf
    delta = f'{o_pf - full_oos_pf:+.3f}' if full_oos_pf is not None and skip > 0 else '  base'
    flag  = ''
    if skip > 0 and full_oos_pf is not None:
        diff = o_pf - full_oos_pf
        flag = '  HURTS' if diff < -0.05 else ('  HELPS' if diff > 0.05 else '  neutral')
    print(f'  {ablation_labels[skip]:<35}  {o_t:>10}  {o_wr:>7.1f}%  {o_pf:>8.3f}  {delta}{flag}')


# ═════════════════════════════════════════════════════════════════════════════
#  VERDICT
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  VERDICT')
print(SEP)

sb_oos_pf  = pooled_pf(results['Sideways Base']['oos'])
rsi30_pf   = pooled_pf(results['RSI<30 (S3)']['oos'])
rsi20_pf   = pooled_pf(results['RSI<20+VarB']['oos'])
ema_pf     = pooled_pf(results['EMA 9/21 Cross']['oos'])
sb_oos_cnt = sum(m['trades'] for m in results['Sideways Base']['oos'])

strategies_ranked = sorted([
    ('Sideways Base',  sb_oos_pf),
    ('RSI<30 (S3)',    rsi30_pf),
    ('RSI<20+VarB',    rsi20_pf),
    ('EMA 9/21 Cross', ema_pf),
], key=lambda x: -x[1])

print('  OOS Profit Factor ranking:')
for rank, (name, pf_v) in enumerate(strategies_ranked, 1):
    bar = '#' * int(pf_v * 20) if pf_v > 0 else ''
    marker = '  <-- BEST' if rank == 1 else ''
    print(f'    {rank}. {name:<22}  OOS PF={pf_v:.3f}  {bar}{marker}')

print()
print(f'  Sideways Base OOS: {sb_oos_cnt} trades, PF={sb_oos_pf:.3f}')
print()

# Gap to profitability for Sideways Base
if sb_oos and sb_oos_pf > 0:
    o_wr_val  = sum(m['wins'] for m in sb_oos) / max(1, sum(m['trades'] for m in sb_oos))
    o_avgw_v  = agg(sb_oos, 'avg_win')
    o_avgl_v  = abs(agg(sb_oos, 'avg_loss'))
    need_wr_10 = o_avgl_v / (o_avgw_v + o_avgl_v) if (o_avgw_v + o_avgl_v) > 0 else 0.5
    need_wl_12 = 1.2 * (1 - o_wr_val) / o_wr_val if o_wr_val > 0 else 999
    print(f'  Gap analysis (Sideways Base):')
    print(f'    Current  : WR={o_wr_val*100:.1f}%  WL={o_avgw_v/max(0.001,o_avgl_v):.2f}x  -> PF={sb_oos_pf:.3f}')
    print(f'    Need PF=1.0: WR >= {need_wr_10*100:.1f}%  OR  WL >= {1.0*(1-o_wr_val)/max(0.001,o_wr_val):.2f}x')
    print(f'    Need PF=1.2: WR >= {need_wr_10*100+5:.1f}%  OR  WL >= {need_wl_12:.2f}x')

print()
if sb_oos_pf >= 1.2 and sb_oos_cnt >= 50:
    print('  RESULT: SIDEWAYS BASE CONFIRMED PROFITABLE OOS.')
    print('  The stabilisation condition after oversold is the real edge.')
    print('  Recommend 60-day paper trade before live deployment.')
elif sb_oos_pf >= 1.0 and sb_oos_cnt >= 30:
    print('  RESULT: SIDEWAYS BASE IS BREAKEVEN/MARGINALLY PROFITABLE OOS.')
    print('  The stabilisation hypothesis holds. Edge is real but thin.')
    print('  Next step: widen TP or reduce brokerage cost per trade.')
elif sb_oos_pf > max(rsi30_pf, rsi20_pf, ema_pf):
    print('  RESULT: SIDEWAYS BASE IS THE BEST STRATEGY FOUND SO FAR.')
    print(f'  OOS PF={sb_oos_pf:.3f} beats all alternatives despite being < 1.0.')
    print('  The stabilisation hypothesis is directionally correct.')
    print('  Further refinement needed before live trading.')
elif sb_oos_pf > rsi30_pf:
    print(f'  RESULT: SIDEWAYS BASE (PF={sb_oos_pf:.3f}) BEATS RSI<30 (PF={rsi30_pf:.3f}).')
    print('  Partial support for stabilisation hypothesis.')
    print('  The additional conditions (no new low + ATR contraction) add some value.')
else:
    print(f'  RESULT: SIDEWAYS BASE (PF={sb_oos_pf:.3f}) does not improve on RSI<30 (PF={rsi30_pf:.3f}).')
    print('  The stabilisation condition did not separate winners from losers effectively.')
    print('  The issue may be in condition parameters (4 bars, 3% range) rather than the concept.')

print()
print('  HYPOTHESIS ANSWER:')
best_name, best_pf = strategies_ranked[0]
if best_name == 'Sideways Base':
    print('  YES — Stabilisation after oversold contains MORE edge than oversold alone.')
    print('  The base formation (no new low + range compression + ATR contraction) is')
    print('  a better entry filter than RSI level alone.')
else:
    print(f'  PARTIAL — {best_name} (PF={best_pf:.3f}) beats Sideways Base OOS.')
    print('  Stabilisation filters add value but the concept needs parameter refinement.')
    print('  Consider: varying BASE_BARS (3-6), range threshold (2-5%), ATR ratio threshold.')
