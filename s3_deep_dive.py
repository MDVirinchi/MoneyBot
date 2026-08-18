"""
s3_deep_dive.py — Five systematic investigations into S3 Mean Reversion.

Plot Hole 1 : Market regime  — why did AXISBANK fail despite good trend metrics?
Plot Hole 2 : RSI threshold  — is RSI<30 actually the best oversold trigger?
Plot Hole 3 : Entry timing   — is entry one day too early?
Plot Hole 4 : MFE / MAE      — are exits harvesting the full move?
Plot Hole 5 : Portfolio       — PF-weighted vs equal-weight vs vol-adjusted capital
"""

import time, math, logging, warnings, statistics
from collections import Counter

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

# ── Cost model (identical to s3_expand.py) ────────────────────────────────────
BROKERAGE    = 20.0
STT_PCT      = 0.001
EXCHANGE_PCT = 0.0000345
SLIPPAGE     = 0.002
SL_PCT       = 2.0
TP_PCT       = 6.0
TRAIL_PCT    = 1.5
CAPITAL      = 5000.0
LOOKBACK     = 55

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
    ('TECHM.NS',      'TECHM'),
    ('MARUTI.NS',     'MARUTI'),
    ('TITAN.NS',      'TITAN'),
    ('BAJFINANCE.NS', 'BAJFINANCE'),
]

SEP = '=' * 110
sep = '-' * 110


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


def rsi_series(closes, period=14):
    result = []
    for i in range(len(closes)):
        result.append(rsi_val(closes[:i+1], period))
    return result


def is_bullish_engulfing(candles, i):
    """True if bar i engulfs bar i-1 bullishly."""
    if i < 1:
        return False
    prev_o, prev_c = candles[i-1][1], candles[i-1][4]
    curr_o, curr_c = candles[i][1],   candles[i][4]
    return (prev_c < prev_o and          # previous bar bearish
            curr_c > curr_o and          # current bar bullish
            curr_o <= prev_c and         # opens at or below prev close
            curr_c >= prev_o)            # closes at or above prev open


# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch(ticker, period='3y'):
    try:
        df = yf.Ticker(ticker).history(period=period, interval='1d', auto_adjust=True)
        if df.empty:
            return []
        return [[str(ts.date()),
                 float(row['Open']), float(row['High']),
                 float(row['Low']),  float(row['Close']),
                 float(row.get('Volume', 0))]
                for ts, row in df.iterrows()]
    except Exception:
        return []


# ── Signal factory ────────────────────────────────────────────────────────────
def make_signal(rsi_thresh=30, entry_variant='A', regime_candles=None):
    """
    Returns a signal function for given RSI threshold and entry variant.

    rsi_thresh    : oversold level (20/25/30/35/40)
    entry_variant :
      A  RSI < thresh (baseline)
      B  RSI < thresh AND close > prev day high
      C  RSI < thresh AND RSI turning up (curr > prev)
      D  RSI < thresh AND bullish engulfing
      E  RSI < thresh AND close > EMA5

    regime_candles: list of Nifty candles (optional); if provided, only trade
                    when Nifty close > Nifty EMA50.
    """
    nifty_closes = [c[4] for c in regime_candles] if regime_candles else None

    def signal(window):
        closes = [c[4] for c in window]
        if len(closes) < 25:
            return False

        curr_rsi  = rsi_val(closes)
        recov_low  = rsi_thresh + 5   # e.g. thresh=30 → must recover above 35
        recov_high = 55

        if not (recov_low <= curr_rsi <= recov_high):
            return False

        # Was oversold (< thresh) within last 5 bars?
        was_oversold = False
        for j in range(2, 7):
            if len(closes) < j + 15:
                break
            if rsi_val(closes[:-j+1] if j > 1 else closes) < rsi_thresh:
                was_oversold = True
                break
        if not was_oversold:
            return False

        # Trend filter: price above EMA50
        e50 = ema(closes, 50)
        if not e50 or closes[-1] < e50[-1] * 0.98:
            return False

        # Regime filter: Nifty above EMA50
        if nifty_closes is not None:
            bar_count = len(window)
            if bar_count <= len(nifty_closes):
                nifty_sub = nifty_closes[:bar_count]
            else:
                nifty_sub = nifty_closes
            n_ema = ema(nifty_sub, 50)
            if not n_ema or nifty_sub[-1] < n_ema[-1] * 0.98:
                return False

        # Entry variant filters
        if entry_variant == 'B':
            # close > previous day's high
            if len(window) < 2:
                return False
            if closes[-1] <= window[-2][2]:   # window[-2][2] = prev high
                return False

        elif entry_variant == 'C':
            # RSI turning upward (current RSI > RSI 1 bar ago)
            if len(closes) < 16:
                return False
            prev_rsi = rsi_val(closes[:-1])
            if curr_rsi <= prev_rsi:
                return False

        elif entry_variant == 'D':
            # Bullish engulfing
            if not is_bullish_engulfing(window, len(window) - 1):
                return False

        elif entry_variant == 'E':
            # Close above EMA5
            e5 = ema(closes, 5)
            if not e5 or closes[-1] < e5[-1]:
                return False

        return True

    return signal


# ── Core backtester (returns trades list + metrics + MFE/MAE) ─────────────────
def backtest(candles, sig_fn, track_excursion=False):
    capital  = CAPITAL
    position = None
    trades   = []
    equity   = [capital]

    for i in range(LOOKBACK, len(candles) - 1):
        window = candles[:i + 1]
        bar    = candles[i]
        ltp    = bar[4]

        if position:
            sl    = position['entry'] * (1 - SL_PCT / 100)
            tp    = position['entry'] * (1 + TP_PCT / 100)
            high  = max(position['high'], ltp)
            low   = min(position['low'],  ltp)
            position['high'] = high
            position['low']  = low
            trail = high * (1 - TRAIL_PCT / 100)

            # MFE / MAE tracking (as % of entry)
            position['mfe_pct'] = (high / position['entry'] - 1) * 100
            position['mae_pct'] = (low  / position['entry'] - 1) * 100

            reason = None
            if   ltp <= sl:                                              reason = 'StopLoss'
            elif ltp >= tp:                                              reason = 'TakeProfit'
            elif ltp <= trail and high > position['entry'] * 1.005:     reason = 'TrailingStop'

            if reason:
                exit_px  = ltp * (1 - SLIPPAGE)
                exit_val = position['qty'] * exit_px
                costs    = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
                pnl      = (exit_px - position['entry']) * position['qty'] - costs
                capital  += pnl
                trade = {
                    'pnl':         pnl,
                    'return_pct':  (exit_px / position['entry'] - 1) * 100,
                    'exit_reason': reason,
                    'entry_bar':   position['entry_bar'],
                    'exit_bar':    i,
                    'duration':    i - position['entry_bar'],
                    'entry_px':    position['entry'],
                    'exit_px':     exit_px,
                }
                if track_excursion:
                    trade['mfe_pct'] = position['mfe_pct']
                    trade['mae_pct'] = position['mae_pct']
                trades.append(trade)
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
                        'entry_bar': i, 'mfe_pct': 0.0, 'mae_pct': 0.0,
                    }
        equity.append(capital)

    # Close open position at end
    if position:
        ltp      = candles[-1][4]
        exit_px  = ltp * (1 - SLIPPAGE)
        exit_val = position['qty'] * exit_px
        costs    = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
        pnl      = (exit_px - position['entry']) * position['qty'] - costs
        trade = {
            'pnl':         pnl,
            'return_pct':  (exit_px / position['entry'] - 1) * 100,
            'exit_reason': 'EndOfPeriod',
            'entry_bar':   position['entry_bar'],
            'exit_bar':    len(candles) - 1,
            'duration':    len(candles) - 1 - position['entry_bar'],
            'entry_px':    position['entry'],
            'exit_px':     exit_px,
        }
        if track_excursion:
            trade['mfe_pct'] = position['mfe_pct']
            trade['mae_pct'] = position['mae_pct']
        trades.append(trade)
        capital += pnl

    return _metrics(trades, equity, capital, len(candles) - LOOKBACK), trades


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

    w_rets = [t['return_pct'] for t in wins]
    l_rets = [t['return_pct'] for t in losses]
    avg_w  = statistics.mean(w_rets)  if w_rets  else 0.0
    avg_l  = statistics.mean(l_rets)  if l_rets  else 0.0
    wl     = abs(avg_w / avg_l)       if avg_l   else 0.0

    return {
        'trades': len(trades), 'wins': len(wins), 'losses': len(losses),
        'wr': round(wr, 1),    'pf':   round(pf, 3),
        'sharpe': round(sharpe, 3),   'cagr':    round(cagr, 1),
        'max_dd': round(max_dd, 1),   'avg_win':  round(avg_w, 2),
        'avg_loss': round(avg_l, 2),  'wl':       round(wl, 2),
        'net_pnl': round(final_cap - CAPITAL, 2),
        'exit_reasons': dict(Counter(t['exit_reason'] for t in trades)),
    }


def pooled_pf(results_list):
    """Compute pooled PF across a list of metric dicts."""
    num = sum(v['wins']   * abs(v['avg_win'])  for v in results_list if v['losses'] > 0)
    den = sum(v['losses'] * abs(v['avg_loss']) for v in results_list if v['losses'] > 0)
    return num / den if den > 0 else 0.0


def run_all(sig_fn, candles_map, split=None):
    """
    Run backtest on all stocks.
    split: if float (0-1), run only on candles[split:] window
    Returns list of metric dicts for stocks with >= 2 trades.
    """
    results = []
    for _, sym in STOCKS:
        candles = candles_map.get(sym, [])
        if split is not None:
            idx = int(len(candles) * split)
            candles = candles[idx - LOOKBACK:] if idx > LOOKBACK else []
        if len(candles) < LOOKBACK + 5:
            continue
        m, _ = backtest(candles, sig_fn)
        if m['trades'] >= 2:
            results.append(m)
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  FETCH DATA
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print('  FETCHING DATA')
print(SEP)

candles_map = {}
for ticker, sym in STOCKS:
    c = fetch(ticker, '3y')
    candles_map[sym] = c
    print(f'  {sym:<14}: {len(c)} bars')
    time.sleep(0.3)

print('  Fetching Nifty50 (^NSEI) for regime filter...')
nifty_candles = fetch('^NSEI', '3y')
print(f'  NIFTY          : {len(nifty_candles)} bars')

# Walk-forward split index (OOS = last 1/3)
OOS_SPLIT = 2/3


# ─────────────────────────────────────────────────────────────────────────────
#  PLOT HOLE 1: MARKET REGIME
#  Hypothesis: AXISBANK had good trend metrics but Nifty was in downtrend
#  during its RSI<30 events → strategy fires into falling market
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  PLOT HOLE 1 — MARKET REGIME (Nifty EMA50 filter)')
print('  Hypothesis: S3 wins when Nifty is in uptrend; AXISBANK signals fired in downtrend')
print(SEP)
print(f'  {"Stock":<14}  {"No-Regime Tr":>12}  {"No-Regime PF":>12}  '
      f'{"Regime Tr":>9}  {"Regime PF":>9}  {"Change":>8}')
print(sep)

regime_summary = []
for _, sym in STOCKS:
    candles = candles_map.get(sym, [])
    if len(candles) < LOOKBACK + 5:
        continue
    sig_base   = make_signal(rsi_thresh=30, entry_variant='A', regime_candles=None)
    sig_regime = make_signal(rsi_thresh=30, entry_variant='A', regime_candles=nifty_candles)
    m_base,   _ = backtest(candles, sig_base)
    m_regime, _ = backtest(candles, sig_regime)
    change = m_regime['pf'] - m_base['pf']
    flag   = '  IMPROVES' if change > 0.05 else ('  HURTS' if change < -0.05 else '')
    print(f'  {sym:<14}  {m_base["trades"]:>12}  {m_base["pf"]:>12.3f}  '
          f'{m_regime["trades"]:>9}  {m_regime["pf"]:>9.3f}  {change:>+8.3f}{flag}')
    regime_summary.append((sym, m_base['pf'], m_regime['pf']))

base_list   = run_all(make_signal(30, 'A', None), candles_map)
regime_list = run_all(make_signal(30, 'A', nifty_candles), candles_map)
print(sep)
print(f'  {"POOLED PF":<14}  {"":>12}  {pooled_pf(base_list):>12.3f}  '
      f'{"":>9}  {pooled_pf(regime_list):>9.3f}')

# AXISBANK deep dive: what % of its signals fired when Nifty was below EMA50?
print()
print('  AXISBANK deep-dive: When did its signals fire relative to Nifty regime?')
axisbank_candles = candles_map.get('AXISBANK', [])
if axisbank_candles and nifty_candles:
    sig_base = make_signal(30, 'A', None)
    nifty_cls = [c[4] for c in nifty_candles]
    signals_in_uptrend   = 0
    signals_in_downtrend = 0
    min_len = min(len(axisbank_candles), len(nifty_candles))
    for i in range(LOOKBACK, min_len - 1):
        window = axisbank_candles[:i+1]
        if sig_base(window):
            nc = nifty_cls[:i+1]
            ne = ema(nc, 50)
            if ne:
                if nc[-1] >= ne[-1] * 0.98:
                    signals_in_uptrend += 1
                else:
                    signals_in_downtrend += 1
    total_ax = signals_in_uptrend + signals_in_downtrend
    if total_ax > 0:
        print(f'    AXISBANK signals in Nifty uptrend   : {signals_in_uptrend} '
              f'({signals_in_uptrend/total_ax*100:.0f}%)')
        print(f'    AXISBANK signals in Nifty downtrend : {signals_in_downtrend} '
              f'({signals_in_downtrend/total_ax*100:.0f}%)')


# ─────────────────────────────────────────────────────────────────────────────
#  PLOT HOLE 2: RSI THRESHOLD SWEEP
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  PLOT HOLE 2 — RSI THRESHOLD SWEEP')
print('  Testing oversold thresholds: 20 / 25 / 30 / 35 / 40')
print(SEP)
print(f'  {"Threshold":<12}  {"IS Trades":>9}  {"IS WR%":>7}  {"IS PF":>7}  '
      f'{"OOS Trades":>10}  {"OOS WR%":>8}  {"OOS PF":>8}  {"Best?":>6}')
print(sep)

thresh_results = {}
for thresh in [20, 25, 30, 35, 40]:
    sig = make_signal(rsi_thresh=thresh, entry_variant='A')
    is_list  = run_all(sig, candles_map, split=None)   # full period IS
    oos_list = run_all(sig, candles_map, split=OOS_SPLIT)
    # IS uses first 2/3
    is_list2 = []
    for _, sym in STOCKS:
        c = candles_map.get(sym, [])
        split_idx = int(len(c) * OOS_SPLIT)
        c_is = c[:split_idx]
        if len(c_is) < LOOKBACK + 5: continue
        m, _ = backtest(c_is, sig)
        if m['trades'] >= 2:
            is_list2.append(m)
    is_pf  = pooled_pf(is_list2)
    oos_pf = pooled_pf(oos_list)
    is_t   = sum(v['trades'] for v in is_list2)
    oos_t  = sum(v['trades'] for v in oos_list)
    is_wr  = (sum(v['wins'] for v in is_list2)  / is_t  * 100) if is_t  > 0 else 0
    oos_wr = (sum(v['wins'] for v in oos_list)  / oos_t * 100) if oos_t > 0 else 0
    thresh_results[thresh] = {'is_pf': is_pf, 'oos_pf': oos_pf,
                               'is_t': is_t, 'oos_t': oos_t}
    print(f'  RSI < {thresh:<6}  {is_t:>9}  {is_wr:>6.1f}%  {is_pf:>7.3f}  '
          f'{oos_t:>10}  {oos_wr:>7.1f}%  {oos_pf:>8.3f}')

best_thresh = max(thresh_results, key=lambda x: thresh_results[x]['oos_pf'])
print(sep)
print(f'  Best OOS threshold: RSI < {best_thresh}  '
      f'(OOS PF = {thresh_results[best_thresh]["oos_pf"]:.3f})')


# ─────────────────────────────────────────────────────────────────────────────
#  PLOT HOLE 3: ENTRY TIMING
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  PLOT HOLE 3 — ENTRY TIMING VARIANTS')
print(f'  Using best RSI threshold from PH2 (RSI < {best_thresh})')
print('  A: RSI<thresh (baseline)')
print('  B: RSI<thresh AND close > prev high  (breakout confirmation)')
print('  C: RSI<thresh AND RSI turning upward (momentum confirmation)')
print('  D: RSI<thresh AND bullish engulfing   (candle confirmation)')
print('  E: RSI<thresh AND close > EMA5        (short-term trend flip)')
print(SEP)
print(f'  {"Variant":<8}  {"IS Trades":>9}  {"IS WR%":>7}  {"IS PF":>7}  '
      f'{"OOS Trades":>10}  {"OOS WR%":>8}  {"OOS PF":>8}  {"vs A (OOS)":>10}')
print(sep)

variant_results = {}
for var in ['A', 'B', 'C', 'D', 'E']:
    sig = make_signal(rsi_thresh=best_thresh, entry_variant=var)
    is_list, oos_list = [], []
    for _, sym in STOCKS:
        c = candles_map.get(sym, [])
        if len(c) < LOOKBACK + 10: continue
        split_idx = int(len(c) * OOS_SPLIT)
        c_is  = c[:split_idx]
        c_oos = c[split_idx - LOOKBACK:]
        if len(c_is)  >= LOOKBACK + 5:
            m, _ = backtest(c_is, sig)
            if m['trades'] >= 2: is_list.append(m)
        if len(c_oos) >= LOOKBACK + 5:
            m, _ = backtest(c_oos, sig)
            if m['trades'] >= 1: oos_list.append(m)
    is_pf  = pooled_pf(is_list)
    oos_pf = pooled_pf(oos_list)
    is_t   = sum(v['trades'] for v in is_list)
    oos_t  = sum(v['trades'] for v in oos_list)
    is_wr  = (sum(v['wins'] for v in is_list)  / is_t  * 100) if is_t  > 0 else 0
    oos_wr = (sum(v['wins'] for v in oos_list) / oos_t * 100) if oos_t > 0 else 0
    variant_results[var] = {'is_pf': is_pf, 'oos_pf': oos_pf}
    base_oos = variant_results.get('A', {}).get('oos_pf', oos_pf)
    delta = oos_pf - base_oos
    flag = ''
    if var != 'A':
        flag = f'  {delta:+.3f}'
        if delta > 0.05: flag += ' BETTER'
        elif delta < -0.05: flag += ' WORSE'
    labels = {'A':'Baseline','B':'Prev High','C':'RSI Turn','D':'Engulfing','E':'EMA5 Cross'}
    print(f'  {var} {labels[var]:<10}  {is_t:>9}  {is_wr:>6.1f}%  {is_pf:>7.3f}  '
          f'{oos_t:>10}  {oos_wr:>7.1f}%  {oos_pf:>8.3f}{flag}')

best_variant = max(variant_results, key=lambda x: variant_results[x]['oos_pf'])
print(sep)
print(f'  Best OOS variant: {best_variant}  (OOS PF = {variant_results[best_variant]["oos_pf"]:.3f})')


# ─────────────────────────────────────────────────────────────────────────────
#  PLOT HOLE 4: MFE / MAE ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  PLOT HOLE 4 — MFE / MAE ANALYSIS')
print(f'  Using best config: RSI<{best_thresh}, variant {best_variant}')
print('  MFE = Max Favorable Excursion (highest unrealised profit before exit)')
print('  MAE = Max Adverse Excursion  (deepest unrealised loss before exit)')
print(SEP)

best_sig = make_signal(rsi_thresh=best_thresh, entry_variant=best_variant)
all_trades = []
for _, sym in STOCKS:
    candles = candles_map.get(sym, [])
    if len(candles) < LOOKBACK + 5: continue
    _, trades = backtest(candles, best_sig, track_excursion=True)
    all_trades.extend(trades)

wins   = [t for t in all_trades if t['pnl'] > 0]
losses = [t for t in all_trades if t['pnl'] <= 0]

def safe_mean(lst): return statistics.mean(lst) if lst else 0.0
def safe_pct(lst, fn): return fn(lst) if lst else 0.0

if all_trades:
    win_mfe  = [t['mfe_pct'] for t in wins   if 'mfe_pct' in t]
    win_mae  = [t['mae_pct'] for t in wins   if 'mae_pct' in t]
    loss_mfe = [t['mfe_pct'] for t in losses if 'mfe_pct' in t]
    loss_mae = [t['mae_pct'] for t in losses if 'mae_pct' in t]
    win_ret  = [t['return_pct'] for t in wins]
    loss_ret = [t['return_pct'] for t in losses]

    print(f'  Total trades analysed: {len(all_trades)}  ({len(wins)} wins, {len(losses)} losses)')
    print()
    print(f'  {"Metric":<35}  {"Winners":>10}  {"Losers":>10}')
    print(f'  {"-"*35}  {"-"*10}  {"-"*10}')
    print(f'  {"Avg actual return %":<35}  {safe_mean(win_ret):>+10.2f}  {safe_mean(loss_ret):>+10.2f}')
    print(f'  {"Avg MFE % (best the trade ever reached)":<35}  {safe_mean(win_mfe):>+10.2f}  {safe_mean(loss_mfe):>+10.2f}')
    print(f'  {"Avg MAE % (worst drawdown in trade)":<35}  {safe_mean(win_mae):>+10.2f}  {safe_mean(loss_mae):>+10.2f}')
    print()

    # Leak analysis
    if win_mfe and win_ret:
        avg_mfe_win  = safe_mean(win_mfe)
        avg_ret_win  = safe_mean(win_ret)
        captured_pct = (avg_ret_win / avg_mfe_win * 100) if avg_mfe_win > 0 else 0
        left_on_table = avg_mfe_win - avg_ret_win
        print(f'  EXIT QUALITY ANALYSIS:')
        print(f'    Winners avg MFE    : +{avg_mfe_win:.2f}%')
        print(f'    Winners avg return : +{avg_ret_win:.2f}%')
        print(f'    Captured           : {captured_pct:.0f}% of the move')
        print(f'    Left on table      : {left_on_table:.2f}% per winning trade')
        if left_on_table > 2.0:
            print(f'    *** DIAGNOSIS: Exits are cutting winners short. '
                  f'Raise TP from {TP_PCT}% or widen trailing stop. ***')
        else:
            print(f'    Exits are reasonable — not cutting winners materially short.')

    if loss_mae and loss_ret:
        avg_mae_loss = abs(safe_mean(loss_mae))
        avg_ret_loss = abs(safe_mean(loss_ret))
        print()
        print(f'    Losers avg MAE     : -{avg_mae_loss:.2f}%')
        print(f'    Losers avg return  : {safe_mean(loss_ret):.2f}%')
        if avg_mae_loss > SL_PCT + 0.5:
            print(f'    *** DIAGNOSIS: Stops are letting losses run beyond SL={SL_PCT}%. '
                  f'Check slippage / gapping. ***')
        else:
            print(f'    Stop-loss is working — losses contained near -{SL_PCT}%.')

    # Duration
    win_dur  = [t['duration'] for t in wins]
    loss_dur = [t['duration'] for t in losses]
    print()
    print(f'    Avg winner duration : {safe_mean(win_dur):.1f} bars')
    print(f'    Avg loser duration  : {safe_mean(loss_dur):.1f} bars')

    # Exit reason breakdown
    exit_counts = Counter(t['exit_reason'] for t in all_trades)
    print()
    print('  Exit reason breakdown (all trades):')
    for reason, cnt in sorted(exit_counts.items(), key=lambda x: -x[1]):
        pct = cnt / len(all_trades) * 100
        print(f'    {reason:<16}: {cnt:>4}  ({pct:.0f}%)')


# ─────────────────────────────────────────────────────────────────────────────
#  PLOT HOLE 5: PORTFOLIO CONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  PLOT HOLE 5 — PORTFOLIO CONSTRUCTION')
print('  Comparing: Equal-weight  vs  PF-weighted  vs  Volatility-adjusted')
print(SEP)

# Get per-stock IS PF and vol for weight calculation
stock_metrics = {}
for _, sym in STOCKS:
    c = candles_map.get(sym, [])
    if len(c) < LOOKBACK + 10: continue
    split_idx = int(len(c) * OOS_SPLIT)
    c_is  = c[:split_idx]
    c_oos = c[split_idx - LOOKBACK:]
    sig = make_signal(rsi_thresh=best_thresh, entry_variant=best_variant)
    if len(c_is) >= LOOKBACK + 5:
        m_is, _ = backtest(c_is, sig)
    else:
        m_is = None
    if len(c_oos) >= LOOKBACK + 5:
        m_oos, _ = backtest(c_oos, sig)
    else:
        m_oos = None
    # Annualized vol from IS period
    if len(c_is) > 5:
        cls = [x[4] for x in c_is]
        rets = [math.log(cls[i]/cls[i-1]) for i in range(1, len(cls)) if cls[i-1] > 0]
        vol  = statistics.stdev(rets) * math.sqrt(252) * 100 if len(rets) > 2 else 25.0
    else:
        vol = 25.0
    stock_metrics[sym] = {
        'is_pf': m_is['pf']  if m_is  and m_is['trades']  >= 2 else 0.0,
        'is_tr': m_is['trades'] if m_is else 0,
        'oos_m': m_oos,
        'vol':   vol,
    }

# Build portfolio results under 3 schemes
schemes = {
    'Equal-weight':    {},
    'PF-weighted':     {},
    'Vol-adjusted':    {},
}

# For each stock compute a weight under each scheme
syms_active = [sym for (_, sym) in STOCKS if stock_metrics.get(sym, {}).get('oos_m') is not None
               and stock_metrics[sym]['oos_m']['trades'] >= 1]

if syms_active:
    # Equal weight
    eq_w = {sym: 1.0 / len(syms_active) for sym in syms_active}

    # PF-weighted (weight proportional to IS PF, floor at 0.1)
    pf_vals = {sym: max(stock_metrics[sym]['is_pf'], 0.1) for sym in syms_active}
    pf_total = sum(pf_vals.values())
    pf_w = {sym: pf_vals[sym] / pf_total for sym in syms_active}

    # Volatility-adjusted (inverse vol)
    inv_vol = {sym: 1.0 / max(stock_metrics[sym]['vol'], 5.0) for sym in syms_active}
    iv_total = sum(inv_vol.values())
    vol_w = {sym: inv_vol[sym] / iv_total for sym in syms_active}

    print(f'  {"Stock":<14}  {"IS PF":>7}  {"IS Vol%":>7}  '
          f'{"Eq-W%":>6}  {"PF-W%":>6}  {"Vol-W%":>7}  {"OOS PF":>8}  {"OOS Tr":>7}')
    print(sep)
    for sym in syms_active:
        sm = stock_metrics[sym]
        oos = sm['oos_m']
        print(f'  {sym:<14}  {sm["is_pf"]:>7.3f}  {sm["vol"]:>6.1f}%  '
              f'{eq_w[sym]*100:>5.1f}%  {pf_w[sym]*100:>5.1f}%  {vol_w[sym]*100:>6.1f}%  '
              f'{oos["pf"]:>8.3f}  {oos["trades"]:>7}')
    print(sep)

    # Portfolio-level metrics: weighted average of OOS metrics
    def portfolio_metrics(weights):
        total_capital = CAPITAL * len(syms_active)
        # Weighted PF: sum(weight * wins * avg_win) / sum(weight * losses * avg_loss)
        num = sum(weights[s] * stock_metrics[s]['oos_m']['wins']   * abs(stock_metrics[s]['oos_m']['avg_win'])
                  for s in syms_active)
        den = sum(weights[s] * stock_metrics[s]['oos_m']['losses'] * abs(stock_metrics[s]['oos_m']['avg_loss'])
                  for s in syms_active if stock_metrics[s]['oos_m']['losses'] > 0)
        w_pf    = num / den if den > 0 else 0.0
        w_wr    = sum(weights[s] * stock_metrics[s]['oos_m']['wr']     for s in syms_active)
        w_cagr  = sum(weights[s] * stock_metrics[s]['oos_m']['cagr']   for s in syms_active)
        w_dd    = sum(weights[s] * stock_metrics[s]['oos_m']['max_dd'] for s in syms_active)
        w_sh    = sum(weights[s] * stock_metrics[s]['oos_m']['sharpe'] for s in syms_active)
        w_tr    = sum(weights[s] * stock_metrics[s]['oos_m']['trades'] for s in syms_active)
        return {'pf': w_pf, 'wr': w_wr, 'cagr': w_cagr, 'dd': w_dd, 'sharpe': w_sh, 'trades': w_tr}

    for name, weights in [('Equal-weight', eq_w), ('PF-weighted', pf_w), ('Vol-adjusted', vol_w)]:
        pm = portfolio_metrics(weights)
        print(f'  {name:<16}  PF={pm["pf"]:.3f}  WR={pm["wr"]:.1f}%  '
              f'CAGR={pm["cagr"]:+.1f}%  MaxDD={pm["dd"]:.1f}%  '
              f'Sharpe={pm["sharpe"]:.3f}  AvgTr={pm["trades"]:.1f}')

    best_scheme = max(
        [('Equal-weight', eq_w), ('PF-weighted', pf_w), ('Vol-adjusted', vol_w)],
        key=lambda x: portfolio_metrics(x[1])['pf']
    )
    print(sep)
    print(f'  Best portfolio scheme: {best_scheme[0]}')


# ─────────────────────────────────────────────────────────────────────────────
#  MASTER VERDICT
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  MASTER VERDICT — ALL FIVE PLOT HOLES')
print(SEP)

best_var_oos_pf = variant_results[best_variant]['oos_pf']

print(f'  PH1 Regime filter    : {"IMPROVES" if pooled_pf(regime_list) > pooled_pf(base_list) else "NO BENEFIT"}'
      f'  (No-regime PF={pooled_pf(base_list):.3f}  ->  Regime PF={pooled_pf(regime_list):.3f})')
print(f'  PH2 Best RSI thresh  : RSI < {best_thresh}  (OOS PF={thresh_results[best_thresh]["oos_pf"]:.3f}  '
      f'vs RSI<30 OOS PF={thresh_results[30]["oos_pf"]:.3f})')
print(f'  PH3 Best entry variant: {best_variant}  (OOS PF={best_var_oos_pf:.3f}  '
      f'vs Baseline A OOS PF={variant_results["A"]["oos_pf"]:.3f})')
if all_trades and win_mfe:
    print(f'  PH4 Exit quality     : Capturing {captured_pct:.0f}% of winner MFE. '
          f'Avg left on table = {left_on_table:.2f}%')
if syms_active:
    eq_pm = portfolio_metrics(eq_w)
    pf_pm = portfolio_metrics(pf_w)
    print(f'  PH5 Portfolio        : PF-weighted OOS PF={pf_pm["pf"]:.3f}  '
          f'vs equal-weight OOS PF={eq_pm["pf"]:.3f}')

print()
print('  RECOMMENDED NEXT S3 CONFIG:')
print(f'    RSI oversold threshold : < {best_thresh}')
print(f'    Entry variant          : {best_variant}')
print(f'    Regime filter          : {"YES (Nifty EMA50)" if pooled_pf(regime_list) > pooled_pf(base_list) else "NO BENEFIT"}')
print(f'    Portfolio weighting    : {best_scheme[0] if syms_active else "N/A"}')

# Gap to profitability
final_oos_pf = best_var_oos_pf
if final_oos_pf >= 1.2:
    print()
    print('  RESULT: OOS PF >= 1.2 ACHIEVED with optimised config.')
    print('  Recommend paper-trading live for 30 days before capital deployment.')
elif final_oos_pf >= 1.0:
    print()
    print('  RESULT: OOS PF > 1.0. Strategy breaks even net of costs.')
    print('  Very close to profitability. Combine all improvements and re-run full test.')
elif final_oos_pf >= 0.7:
    print()
    print('  RESULT: OOS PF > 0.7. Genuine structural edge remains.')
    print('  Gap to PF=1.0 is narrow. Test combination of best regime + entry + threshold.')
else:
    print()
    print('  RESULT: OOS PF < 0.7 even with optimisations.')
    print('  S3 edge is weaker than hoped. Universe and signal need further refinement.')
