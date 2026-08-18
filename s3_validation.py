"""
s3_validation.py — Decisive validation of RSI<20 + Variant B hypothesis.

Investigation 1 : RSI<20 + prev-high breakout, 50 stocks, 5Y, walk-forward Y1-3 IS / Y4-5 OOS
Investigation 2 : Trade morphology — V-shape / Sideways base / Continued breakdown
Investigation 3 : Confusion matrix + feature importance (which indicators predict wins?)
Investigation 4 : Regime map — Bull / Bear / Sideways via Nifty
Investigation 5 : Random Forest classifier — feature importance + AUC vs raw RSI<20

Goal: FALSIFY the RSI<20 edge. If OOS PF >= 1.0 with >= 50 OOS trades → edge is real.
"""

import time, math, logging, warnings, statistics
from collections import Counter, defaultdict

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

import yfinance as yf

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score, precision_score, recall_score
    from sklearn.preprocessing import StandardScaler
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print('  [sklearn not installed — Investigation 5 will be skipped]')
    print('  Install with: pip install scikit-learn')

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

SEP = '=' * 112
sep = '-' * 112

# ── 50 liquid NSE stocks (Nifty 50 + Nifty Next 50 liquid names) ──────────────
STOCKS = [
    # Nifty 50
    ('RELIANCE.NS',    'RELIANCE'),
    ('TCS.NS',         'TCS'),
    ('INFY.NS',        'INFY'),
    ('HDFCBANK.NS',    'HDFCBANK'),
    ('ICICIBANK.NS',   'ICICIBANK'),
    ('SBIN.NS',        'SBIN'),
    ('HCLTECH.NS',     'HCLTECH'),
    ('WIPRO.NS',       'WIPRO'),
    ('AXISBANK.NS',    'AXISBANK'),
    ('KOTAKBANK.NS',   'KOTAKBANK'),
    ('TECHM.NS',       'TECHM'),
    ('MARUTI.NS',      'MARUTI'),
    ('TITAN.NS',       'TITAN'),
    ('BAJFINANCE.NS',  'BAJFINANCE'),
    ('ITC.NS',         'ITC'),
    ('HINDUNILVR.NS',  'HINDUNILVR'),
    ('BHARTIARTL.NS',  'BHARTIARTL'),
    ('ASIANPAINT.NS',  'ASIANPAINT'),
    ('SUNPHARMA.NS',   'SUNPHARMA'),
    ('DRREDDY.NS',     'DRREDDY'),
    ('CIPLA.NS',       'CIPLA'),
    ('POWERGRID.NS',   'POWERGRID'),
    ('NTPC.NS',        'NTPC'),
    ('COALINDIA.NS',   'COALINDIA'),
    ('ONGC.NS',        'ONGC'),
    ('BPCL.NS',        'BPCL'),
    ('ULTRACEMCO.NS',  'ULTRACEMCO'),
    ('GRASIM.NS',      'GRASIM'),
    ('ADANIENT.NS',    'ADANIENT'),
    ('ADANIPORTS.NS',  'ADANIPORTS'),
    ('BAJAJFINSV.NS',  'BAJAJFINSV'),
    ('EICHERMOT.NS',   'EICHERMOT'),
    ('TATACONSUM.NS',  'TATACONSUM'),
    ('BRITANNIA.NS',   'BRITANNIA'),
    ('APOLLOHOSP.NS',  'APOLLOHOSP'),
    ('JSWSTEEL.NS',    'JSWSTEEL'),
    ('TATASTEEL.NS',   'TATASTEEL'),
    ('HINDALCO.NS',    'HINDALCO'),
    ('LT.NS',          'LT'),
    ('NESTLEIND.NS',   'NESTLEIND'),
    # Liquid mid/large caps
    ('PIDILITIND.NS',  'PIDILITIND'),
    ('HAVELLS.NS',     'HAVELLS'),
    ('DIVISLAB.NS',    'DIVISLAB'),
    ('TORNTPHARM.NS',  'TORNTPHARM'),
    ('MUTHOOTFIN.NS',  'MUTHOOTFIN'),
    ('INDUSINDBK.NS',  'INDUSINDBK'),
    ('BANDHANBNK.NS',  'BANDHANBNK'),
    ('FEDERALBNK.NS',  'FEDERALBNK'),
    ('ESCORTS.NS',     'ESCORTS'),
    ('BALKRISIND.NS',  'BALKRISIND'),
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


def atr_val(candles, period=14):
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i][2], candles[i][3], candles[i-1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / len(recent) if recent else 0.0


def adx_val(candles, period=14):
    if len(candles) < period * 2:
        return 0.0
    trs, pdm, ndm = [], [], []
    for i in range(1, len(candles)):
        h, l, ph, pl = candles[i][2], candles[i][3], candles[i-1][2], candles[i-1][3]
        pc = candles[i-1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - ph, pl - l
        pdm.append(up if up > dn and up > 0 else 0.0)
        ndm.append(dn if dn > up and dn > 0 else 0.0)
    def wilder(lst, p):
        if len(lst) < p: return []
        r = [sum(lst[:p])]
        for v in lst[p:]:
            r.append(r[-1] - r[-1] / p + v)
        return r
    atr_w = wilder(trs, period)
    pdm_w = wilder(pdm, period)
    ndm_w = wilder(ndm, period)
    dxs = []
    for a, p_, n in zip(atr_w, pdm_w, ndm_w):
        if a == 0: continue
        pdi, ndi = 100 * p_ / a, 100 * n / a
        s = pdi + ndi
        dxs.append(100 * abs(pdi - ndi) / s if s > 0 else 0)
    if not dxs: return 0.0
    adx_w = wilder(dxs, period)
    return adx_w[-1] if adx_w else 0.0


def vol_ratio(candles, period=20):
    if len(candles) < period + 1:
        return 1.0
    vols = [c[5] for c in candles]
    avg = sum(vols[-period-1:-1]) / period if period > 0 else 1
    return vols[-1] / avg if avg > 0 else 1.0


# ── Signal: RSI<20 + close > previous day's high ──────────────────────────────
def signal_rsi20_varB(window):
    closes = [c[4] for c in window]
    if len(closes) < 25:
        return False
    curr_rsi = rsi_val(closes)
    # Recovering into 25-55 range after being below 20
    if not (25 <= curr_rsi <= 55):
        return False
    # Was below 20 within last 5 bars
    was_extreme = False
    for j in range(2, 7):
        if len(closes) < j + 15:
            break
        if rsi_val(closes[:-j+1] if j > 1 else closes) < 20:
            was_extreme = True
            break
    if not was_extreme:
        return False
    # Trend filter: price above EMA50
    e50 = ema(closes, 50)
    if not e50 or closes[-1] < e50[-1] * 0.98:
        return False
    # Variant B: close > previous day's high
    if len(window) < 2 or closes[-1] <= window[-2][2]:
        return False
    return True


# ── Backtester (full trade record with features) ──────────────────────────────
def backtest_full(candles, sig_fn, nifty_closes=None):
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
                t = dict(position['features'])
                t.update({
                    'pnl':         pnl,
                    'return_pct':  (exit_px / position['entry'] - 1) * 100,
                    'exit_reason': reason,
                    'duration':    i - position['entry_bar'],
                    'mfe_pct':     (position['high'] / position['entry'] - 1) * 100,
                    'mae_pct':     (position['low']  / position['entry'] - 1) * 100,
                    'winner':      1 if pnl > 0 else 0,
                    'entry_bar':   position['entry_bar'],
                    'exit_bar':    i,
                })
                trades.append(t)
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
                    closes  = [c[4] for c in window]
                    e50     = ema(closes, 50)
                    e200    = ema(closes, 200)
                    curr_rsi = rsi_val(closes)
                    curr_atr = atr_val(window)
                    curr_adx = adx_val(window)
                    curr_vol = vol_ratio(window)
                    dist_e50  = (closes[-1] / e50[-1]  - 1) * 100 if e50  else 0.0
                    dist_e200 = (closes[-1] / e200[-1] - 1) * 100 if e200 else 0.0
                    # Nifty regime at entry
                    regime = 'BULL'
                    if nifty_closes is not None and i < len(nifty_closes):
                        nc = nifty_closes[:i+1]
                        ne = ema(nc, 50)
                        ne200 = ema(nc, 200)
                        if ne and ne200:
                            nc_val = nc[-1]
                            if nc_val > ne[-1] * 1.01:
                                regime = 'BULL'
                            elif nc_val < ne[-1] * 0.99:
                                # Further distinguish bear vs sideways using 200
                                regime = 'BEAR' if nc_val < ne200[-1] * 0.97 else 'SIDEWAYS'
                            else:
                                regime = 'SIDEWAYS'
                    # Trade morphology: how did RSI fall below 20?
                    # V-shape: RSI<20 for <= 2 bars
                    # Sideways base: RSI oscillated 20-35 for >= 5 bars
                    # Continued breakdown: price still below 5-bar low at entry
                    morphology = _classify_morphology(window, closes)
                    features = {
                        'rsi':        curr_rsi,
                        'atr_pct':    curr_atr / closes[-1] * 100 if closes[-1] > 0 else 0,
                        'adx':        curr_adx,
                        'dist_e50':   dist_e50,
                        'dist_e200':  dist_e200,
                        'vol_ratio':  curr_vol,
                        'regime':     regime,
                        'morphology': morphology,
                    }
                    position = {
                        'qty': qty, 'entry': fill_px,
                        'high': fill_px, 'low': fill_px,
                        'entry_bar': i, 'features': features,
                    }
        equity.append(capital)

    if position:
        ltp     = candles[-1][4]
        exit_px = ltp * (1 - SLIPPAGE)
        costs   = BROKERAGE + position['qty'] * exit_px * (STT_PCT + EXCHANGE_PCT)
        pnl     = (exit_px - position['entry']) * position['qty'] - costs
        t = dict(position['features'])
        t.update({
            'pnl': pnl,
            'return_pct': (exit_px / position['entry'] - 1) * 100,
            'exit_reason': 'EndOfPeriod',
            'duration': len(candles) - 1 - position['entry_bar'],
            'mfe_pct': (position['high'] / position['entry'] - 1) * 100,
            'mae_pct': (position['low']  / position['entry'] - 1) * 100,
            'winner': 1 if pnl > 0 else 0,
            'entry_bar': position['entry_bar'],
            'exit_bar': len(candles) - 1,
        })
        trades.append(t)
        capital += pnl

    return _metrics(trades, equity, capital, len(candles) - LOOKBACK), trades


def _classify_morphology(window, closes):
    """Classify how the oversold condition formed."""
    if len(closes) < 20:
        return 'Unknown'
    # How many consecutive bars was RSI below 25?
    consec = 0
    for j in range(1, min(15, len(closes))):
        r = rsi_val(closes[:-j] if j > 0 else closes)
        if r < 25:
            consec += 1
        else:
            break
    # Is current price still near the low?
    recent_low  = min(c[3] for c in window[-10:]) if len(window) >= 10 else closes[-1]
    near_low    = closes[-1] < recent_low * 1.02

    if consec <= 2 and not near_low:
        return 'V-Reversal'
    elif near_low:
        return 'Breakdown'
    else:
        return 'Sideways'


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
        'wr': round(wr, 1),    'pf':   round(pf, 3),
        'sharpe': round(sharpe, 3),   'cagr':    round(cagr, 1),
        'max_dd': round(max_dd, 1),   'avg_win':  round(avg_w, 2),
        'avg_loss': round(avg_l, 2),  'wl':       round(wl, 2),
        'net_pnl': round(final_cap - CAPITAL, 2),
        'exit_reasons': dict(Counter(t['exit_reason'] for t in trades)),
    }


def pooled_pf(mlist):
    num = sum(v['wins']   * abs(v['avg_win'])  for v in mlist if v.get('losses', 0) > 0)
    den = sum(v['losses'] * abs(v['avg_loss']) for v in mlist if v.get('losses', 0) > 0)
    return round(num / den, 3) if den > 0 else 0.0


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
#  FETCH ALL DATA
# ═════════════════════════════════════════════════════════════════════════════
print(SEP)
print('  FETCHING 5-YEAR DAILY DATA — 50 NSE STOCKS + NIFTY')
print(SEP)

candles_map = {}
failed = []
for ticker, sym in STOCKS:
    c = fetch(ticker, '5y')
    candles_map[sym] = c
    status = f'{len(c)} bars' if c else 'FAILED'
    if not c:
        failed.append(sym)
    print(f'  {sym:<14}: {status}')
    time.sleep(0.25)

nifty_candles = fetch('^NSEI', '5y')
nifty_closes  = [c[4] for c in nifty_candles]
print(f'  NIFTY50        : {len(nifty_candles)} bars')
print(f'  Failed fetches : {failed if failed else "None"}')

# Walk-forward: first 60% IS (≈3Y), last 40% OOS (≈2Y)
WF_SPLIT = 0.60


# ═════════════════════════════════════════════════════════════════════════════
#  INVESTIGATION 1 — Walk-forward validation
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  INVESTIGATION 1 — RSI<20 + VARIANT B: 50 STOCKS, 5Y, WALK-FORWARD')
print('  Y1-Y3 in-sample (60%)  |  Y4-Y5 out-of-sample (40%)')
print(SEP)
print(f'  {"Stock":<14}  {"IS-Tr":>5}  {"IS-WR":>6}  {"IS-PF":>6}  {"IS-CAGR":>8}  '
      f'{"OOS-Tr":>6}  {"OOS-WR":>7}  {"OOS-PF":>7}  {"OOS-CAGR":>9}  {"Edge?":>6}')
print(sep)

is_all_trades  = []
oos_all_trades = []
is_metrics     = []
oos_metrics    = []
per_stock_is   = {}
per_stock_oos  = {}

for ticker, sym in STOCKS:
    candles = candles_map.get(sym, [])
    if len(candles) < LOOKBACK + 20:
        print(f'  {sym:<14}  -- insufficient data ({len(candles)} bars) --')
        continue

    split = int(len(candles) * WF_SPLIT)
    c_is  = candles[:split]
    c_oos = candles[split - LOOKBACK:]

    m_is,  t_is  = backtest_full(c_is,  signal_rsi20_varB, nifty_closes[:split] if nifty_closes else None)
    m_oos, t_oos = backtest_full(c_oos, signal_rsi20_varB, nifty_closes[split-LOOKBACK:] if nifty_closes else None)

    per_stock_is[sym]  = (m_is,  t_is)
    per_stock_oos[sym] = (m_oos, t_oos)

    for t in t_is:
        t['sym'] = sym
    for t in t_oos:
        t['sym'] = sym

    is_all_trades.extend(t_is)
    oos_all_trades.extend(t_oos)

    if m_is['trades']  >= 1: is_metrics.append(m_is)
    if m_oos['trades'] >= 1: oos_metrics.append(m_oos)

    is_str  = (f'{m_is["trades"]:>5}  {m_is["wr"]:>5.1f}%  {m_is["pf"]:>6.3f}  '
               f'{m_is["cagr"]:>+7.1f}%')
    oos_str = (f'{m_oos["trades"]:>6}  {m_oos["wr"]:>6.1f}%  {m_oos["pf"]:>7.3f}  '
               f'{m_oos["cagr"]:>+8.1f}%')

    edge = '---'
    if m_oos['trades'] >= 3:
        if   m_oos['pf'] >= 1.2: edge = 'STRONG'
        elif m_oos['pf'] >= 1.0: edge = 'HOLDS'
        elif m_oos['pf'] >= 0.7: edge = 'WEAK'
        else:                     edge = 'FAILS'

    print(f'  {sym:<14}  {is_str}  {oos_str}  {edge:>6}')

# Aggregate
print(sep)
is_t   = sum(m['trades'] for m in is_metrics)
oos_t  = sum(m['trades'] for m in oos_metrics)
is_w   = sum(m['wins']   for m in is_metrics)
oos_w  = sum(m['wins']   for m in oos_metrics)
is_pf  = pooled_pf(is_metrics)
oos_pf = pooled_pf(oos_metrics)
is_wr  = is_w  / is_t  * 100 if is_t  > 0 else 0
oos_wr = oos_w / oos_t * 100 if oos_t > 0 else 0
is_cagr  = statistics.mean([m['cagr']  for m in is_metrics])  if is_metrics  else 0
oos_cagr = statistics.mean([m['cagr']  for m in oos_metrics]) if oos_metrics else 0
oos_dd   = statistics.mean([m['max_dd'] for m in oos_metrics]) if oos_metrics else 0
oos_sh   = statistics.mean([m['sharpe'] for m in oos_metrics]) if oos_metrics else 0

is_avgw  = statistics.mean([m['avg_win']  for m in is_metrics])  if is_metrics  else 0
is_avgl  = statistics.mean([m['avg_loss'] for m in is_metrics])  if is_metrics  else 0
oos_avgw = statistics.mean([m['avg_win']  for m in oos_metrics]) if oos_metrics else 0
oos_avgl = statistics.mean([m['avg_loss'] for m in oos_metrics]) if oos_metrics else 0

print(f'  {"AGGREGATE":<14}  '
      f'{is_t:>5}  {is_wr:>5.1f}%  {is_pf:>6.3f}  {is_cagr:>+7.1f}%  '
      f'{oos_t:>6}  {oos_wr:>6.1f}%  {oos_pf:>7.3f}  {oos_cagr:>+8.1f}%')

print()
print('  WALK-FORWARD SUMMARY:')
print(f'    IS  trades={is_t:>4}  WR={is_wr:.1f}%  PF={is_pf:.3f}  '
      f'AvgW={is_avgw:+.2f}%  AvgL={is_avgl:+.2f}%  CAGR={is_cagr:+.1f}%')
print(f'    OOS trades={oos_t:>4}  WR={oos_wr:.1f}%  PF={oos_pf:.3f}  '
      f'AvgW={oos_avgw:+.2f}%  AvgL={oos_avgl:+.2f}%  CAGR={oos_cagr:+.1f}%  '
      f'MaxDD={oos_dd:.1f}%  Sharpe={oos_sh:.3f}')

print()
if oos_pf >= 1.2 and oos_t >= 50:
    verdict1 = 'EDGE CONFIRMED — OOS PF >= 1.2 with sufficient trade count.'
elif oos_pf >= 1.0 and oos_t >= 50:
    verdict1 = 'EDGE HOLDS — OOS PF >= 1.0 with sufficient trade count. Marginally profitable.'
elif oos_pf >= 1.0 and oos_t < 50:
    verdict1 = f'INCONCLUSIVE — OOS PF >= 1.0 but only {oos_t} OOS trades. Need more data.'
elif oos_pf >= 0.7:
    verdict1 = f'EDGE DEGRADES — OOS PF={oos_pf:.3f}. Genuine but sub-breakeven.'
else:
    verdict1 = f'EDGE COLLAPSES — OOS PF={oos_pf:.3f}. IS result was data snooping.'
print(f'  VERDICT: {verdict1}')

stocks_oos_above_1 = [sym for (_, sym) in STOCKS
                      if per_stock_oos.get(sym) and per_stock_oos[sym][0]['pf'] >= 1.0
                      and per_stock_oos[sym][0]['trades'] >= 3]
stocks_oos_fails   = [sym for (_, sym) in STOCKS
                      if per_stock_oos.get(sym) and per_stock_oos[sym][0]['pf'] < 0.5
                      and per_stock_oos[sym][0]['trades'] >= 3]
print(f'  OOS PF >= 1.0 stocks ({len(stocks_oos_above_1)}): {stocks_oos_above_1}')
print(f'  OOS PF <  0.5 stocks ({len(stocks_oos_fails)}):   {stocks_oos_fails}')


# ═════════════════════════════════════════════════════════════════════════════
#  INVESTIGATION 2 — Trade morphology
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  INVESTIGATION 2 — TRADE MORPHOLOGY (all trades IS + OOS)')
print('  V-Reversal: RSI<20 for <= 2 bars, price already recovering')
print('  Sideways:   RSI oscillated below 25 for > 2 bars, price stabilised')
print('  Breakdown:  Price still near recent low at entry (falling knife)')
print(SEP)

all_trades = is_all_trades + oos_all_trades
morph_groups = defaultdict(list)
for t in all_trades:
    morph_groups[t.get('morphology', 'Unknown')].append(t)

print(f'  {"Morphology":<16}  {"Trades":>7}  {"WR%":>7}  {"PF":>7}  '
      f'{"AvgW%":>7}  {"AvgL%":>7}  {"WL":>6}  {"AvgDur":>7}')
print(sep)

for mtype in ['V-Reversal', 'Sideways', 'Breakdown', 'Unknown']:
    group = morph_groups[mtype]
    if not group:
        continue
    wins   = [t for t in group if t['winner'] == 1]
    losses = [t for t in group if t['winner'] == 0]
    gp = sum(t['pnl'] for t in wins)
    gl = abs(sum(t['pnl'] for t in losses))
    pf = gp / gl if gl > 0 else (0.0 if not wins else 99.0)
    wr = len(wins) / len(group) * 100 if group else 0
    avgw = statistics.mean([t['return_pct'] for t in wins])  if wins   else 0
    avgl = statistics.mean([t['return_pct'] for t in losses]) if losses else 0
    wl   = abs(avgw / avgl) if avgl else 0
    dur  = statistics.mean([t['duration'] for t in group]) if group else 0
    print(f'  {mtype:<16}  {len(group):>7}  {wr:>6.1f}%  {pf:>7.3f}  '
          f'{avgw:>+6.2f}%  {avgl:>+6.2f}%  {wl:>5.2f}x  {dur:>6.1f}d')

print()
best_morph = max(['V-Reversal','Sideways','Breakdown'],
                 key=lambda m: (sum(t['pnl'] for t in morph_groups[m] if t['winner'])
                                / abs(sum(t['pnl'] for t in morph_groups[m] if not t['winner']))
                                if any(not t['winner'] for t in morph_groups[m]) else 0))
print(f'  Best morphology: {best_morph}')
print(f'  Worst morphology (avoid): '
      f'{min(["V-Reversal","Sideways","Breakdown"], key=lambda m: len(morph_groups[m]) and (sum(t["pnl"] for t in morph_groups[m] if t["winner"]) / max(1, abs(sum(t["pnl"] for t in morph_groups[m] if not t["winner"])))))}')


# ═════════════════════════════════════════════════════════════════════════════
#  INVESTIGATION 3 — Confusion matrix + feature importance
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  INVESTIGATION 3 — CONFUSION MATRIX + FEATURE PREDICTIVENESS')
print('  Target: Did price reach +4% before -2%? (1=yes, 0=no)')
print(SEP)

FEATURES = ['rsi', 'atr_pct', 'adx', 'dist_e50', 'dist_e200', 'vol_ratio']
FEAT_LABELS = {
    'rsi':       'RSI level at entry',
    'atr_pct':   'ATR % of price',
    'adx':       'ADX (trend strength)',
    'dist_e50':  'Distance from EMA50 %',
    'dist_e200': 'Distance from EMA200 %',
    'vol_ratio': 'Volume ratio (vs 20d avg)',
}

# Label: +4% before -2%?
def label_4v2(t):
    return 1 if t['mfe_pct'] >= 4.0 and t['mae_pct'] > -2.0 else 0

labeled = [t for t in all_trades if all(f in t for f in FEATURES)]
for t in labeled:
    t['target_4v2'] = label_4v2(t)

pos = sum(1 for t in labeled if t['target_4v2'] == 1)
neg = len(labeled) - pos
print(f'  Total labeled trades: {len(labeled)}  ({pos} hit +4% first, {neg} hit -2% first)')
print()

# Point-biserial correlation for each feature
def corr(x_list, y_list):
    if len(x_list) < 3:
        return 0.0
    mx, my = statistics.mean(x_list), statistics.mean(y_list)
    num = sum((x - mx) * (y - my) for x, y in zip(x_list, y_list))
    dx  = math.sqrt(sum((x - mx)**2 for x in x_list))
    dy  = math.sqrt(sum((y - my)**2 for y in y_list))
    return num / (dx * dy) if dx * dy > 0 else 0.0

print(f'  {"Feature":<35}  {"Corr with win":>14}  {"Win-avg":>9}  {"Loss-avg":>10}  {"Direction"}')
print(sep)

feat_corrs = {}
for feat in FEATURES:
    vals  = [t[feat] for t in labeled]
    tgts  = [t['target_4v2'] for t in labeled]
    wins_ = [t[feat] for t in labeled if t['target_4v2'] == 1]
    loss_ = [t[feat] for t in labeled if t['target_4v2'] == 0]
    r     = corr(vals, tgts)
    feat_corrs[feat] = abs(r)
    w_avg = statistics.mean(wins_) if wins_ else 0
    l_avg = statistics.mean(loss_) if loss_ else 0
    direction = 'Higher = better' if r > 0 else 'Lower = better'
    print(f'  {FEAT_LABELS[feat]:<35}  {r:>+14.4f}  {w_avg:>+9.3f}  {l_avg:>+10.3f}  {direction}')

print()
ranked = sorted(FEATURES, key=lambda f: feat_corrs[f], reverse=True)
print('  Feature ranking by predictive power (|correlation|):')
for i, feat in enumerate(ranked, 1):
    print(f'    {i}. {FEAT_LABELS[feat]:<35}  |r|={feat_corrs[feat]:.4f}')

# Simple confusion matrix: use top feature as binary threshold
print()
print('  Win rate by RSI quartile at entry:')
rsi_vals = sorted([t['rsi'] for t in labeled])
if rsi_vals:
    q25 = rsi_vals[len(rsi_vals)//4]
    q50 = rsi_vals[len(rsi_vals)//2]
    q75 = rsi_vals[3*len(rsi_vals)//4]
    buckets = [
        (f'RSI < {q25:.0f}',        lambda t: t['rsi'] < q25),
        (f'RSI {q25:.0f}-{q50:.0f}', lambda t: q25 <= t['rsi'] < q50),
        (f'RSI {q50:.0f}-{q75:.0f}', lambda t: q50 <= t['rsi'] < q75),
        (f'RSI >= {q75:.0f}',        lambda t: t['rsi'] >= q75),
    ]
    for label, fn in buckets:
        group = [t for t in labeled if fn(t)]
        if not group: continue
        wr_b = sum(1 for t in group if t['target_4v2'] == 1) / len(group) * 100
        print(f'    {label:<18}: {len(group):>4} trades, {wr_b:.0f}% hit +4% first')


# ═════════════════════════════════════════════════════════════════════════════
#  INVESTIGATION 4 — Regime map
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  INVESTIGATION 4 — REGIME MAP (Bull / Bear / Sideways via Nifty)')
print(SEP)

regime_groups = defaultdict(list)
for t in all_trades:
    regime_groups[t.get('regime', 'UNKNOWN')].append(t)

print(f'  {"Regime":<12}  {"Trades":>7}  {"WR%":>7}  {"PF":>8}  '
      f'{"AvgW%":>7}  {"AvgL%":>7}  {"WL":>6}  Recommendation')
print(sep)

for regime in ['BULL', 'SIDEWAYS', 'BEAR', 'UNKNOWN']:
    group = regime_groups[regime]
    if not group:
        continue
    wins_r   = [t for t in group if t['winner'] == 1]
    losses_r = [t for t in group if t['winner'] == 0]
    gp_r = sum(t['pnl'] for t in wins_r)
    gl_r = abs(sum(t['pnl'] for t in losses_r))
    pf_r = gp_r / gl_r if gl_r > 0 else (0.0 if not wins_r else 99.0)
    wr_r = len(wins_r) / len(group) * 100 if group else 0
    avgw_r = statistics.mean([t['return_pct'] for t in wins_r])  if wins_r   else 0
    avgl_r = statistics.mean([t['return_pct'] for t in losses_r]) if losses_r else 0
    wl_r   = abs(avgw_r / avgl_r) if avgl_r else 0
    rec = 'TRADE' if pf_r >= 1.0 else ('CAUTION' if pf_r >= 0.7 else 'AVOID')
    print(f'  {regime:<12}  {len(group):>7}  {wr_r:>6.1f}%  {pf_r:>8.3f}  '
          f'{avgw_r:>+6.2f}%  {avgl_r:>+6.2f}%  {wl_r:>5.2f}x  {rec}')

print()
bull_pf = (lambda g: sum(t['pnl'] for t in g if t['winner']) /
           max(1, abs(sum(t['pnl'] for t in g if not t['winner']))))(regime_groups['BULL'])
bear_pf = (lambda g: sum(t['pnl'] for t in g if t['winner']) /
           max(1, abs(sum(t['pnl'] for t in g if not t['winner']))))(regime_groups['BEAR'])
print(f'  Bull vs Bear PF: {bull_pf:.3f} vs {bear_pf:.3f}  '
      f'(ratio {bull_pf/bear_pf:.1f}x)' if bear_pf > 0 else '')
print(f'  Regime filter impact: trade ONLY in BULL regime would keep '
      f'{len(regime_groups["BULL"])} of {len(all_trades)} trades '
      f'({len(regime_groups["BULL"])/max(1,len(all_trades))*100:.0f}%)')


# ═════════════════════════════════════════════════════════════════════════════
#  INVESTIGATION 5 — ML Classifier
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  INVESTIGATION 5 — RANDOM FOREST CLASSIFIER')
print(SEP)

if not ML_AVAILABLE:
    print('  scikit-learn not installed. Run: pip install scikit-learn')
else:
    feat_data = [[t[f] for f in FEATURES] for t in labeled]
    targets   = [t['target_4v2'] for t in labeled]

    if len(feat_data) < 20:
        print(f'  Not enough trades ({len(feat_data)}) for ML. Need at least 20.')
    else:
        # Time-based split: first 60% train, last 40% test
        split_ml = int(len(feat_data) * 0.60)
        X_train, X_test = feat_data[:split_ml], feat_data[split_ml:]
        y_train, y_test = targets[:split_ml],   targets[split_ml:]

        scaler  = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s  = scaler.transform(X_test)

        rf = RandomForestClassifier(n_estimators=200, max_depth=4,
                                    min_samples_leaf=5, random_state=42,
                                    class_weight='balanced')
        rf.fit(X_train_s, y_train)
        y_pred  = rf.predict(X_test_s)
        y_proba = rf.predict_proba(X_test_s)[:, 1]

        prec = precision_score(y_test, y_pred, zero_division=0)
        rec  = recall_score(y_test, y_pred, zero_division=0)
        auc  = roc_auc_score(y_test, y_proba) if len(set(y_test)) > 1 else 0.5

        print(f'  Training set: {len(X_train)} trades  |  Test set: {len(X_test)} trades')
        print(f'  Test class balance: {sum(y_test)} positive, {len(y_test)-sum(y_test)} negative')
        print()
        print(f'  CLASSIFIER PERFORMANCE:')
        print(f'    Precision  : {prec:.3f}  (of predicted wins, {prec*100:.0f}% actually won)')
        print(f'    Recall     : {rec:.3f}  (caught {rec*100:.0f}% of actual wins)')
        print(f'    AUC        : {auc:.3f}  (0.5 = random, 1.0 = perfect)')
        print()

        # Baseline: raw RSI<20 (all signals taken) win rate
        baseline_wr = sum(y_test) / len(y_test) if y_test else 0
        print(f'  Baseline (take all signals):')
        print(f'    Win rate = {baseline_wr*100:.1f}%  AUC = 0.500')
        print()

        if auc > 0.55:
            print(f'  RF AUC={auc:.3f} > 0.55 — features have PREDICTIVE POWER beyond raw signal.')
        else:
            print(f'  RF AUC={auc:.3f} <= 0.55 — features add little; edge is in signal, not filtering.')

        print()
        print('  FEATURE IMPORTANCE (Random Forest Gini):')
        importances = list(zip(FEATURES, rf.feature_importances_))
        importances.sort(key=lambda x: -x[1])
        for feat, imp in importances:
            bar = '#' * int(imp * 40)
            print(f'    {FEAT_LABELS[feat]:<35}  {imp:.4f}  {bar}')

        # Backtest using RF filter: only take trades where RF predicts win
        print()
        print('  BACKTEST: RF-filtered vs unfiltered (test period OOS trades):')
        test_trades   = labeled[split_ml:]
        rf_filter_idx = [i for i, p in enumerate(y_pred) if p == 1]
        rf_trades     = [test_trades[i] for i in rf_filter_idx]
        all_test_wins = [t for t in test_trades if t['winner']]
        all_test_loss = [t for t in test_trades if not t['winner']]
        rf_wins       = [t for t in rf_trades   if t['winner']]
        rf_loss       = [t for t in rf_trades   if not t['winner']]

        def simple_pf(wins, losses):
            gp = sum(t['pnl'] for t in wins)
            gl = abs(sum(t['pnl'] for t in losses))
            return gp / gl if gl > 0 else (0.0 if not wins else 99.0)

        all_pf = simple_pf(all_test_wins, all_test_loss)
        rf_pf  = simple_pf(rf_wins, rf_loss)
        print(f'    All signals    : {len(test_trades):>4} trades  WR={len(all_test_wins)/max(1,len(test_trades))*100:.1f}%  PF={all_pf:.3f}')
        print(f'    RF-filtered    : {len(rf_trades):>4} trades  WR={len(rf_wins)/max(1,len(rf_trades))*100:.1f}%  PF={rf_pf:.3f}')
        if rf_pf > all_pf:
            print(f'    RF filter IMPROVES PF by +{rf_pf-all_pf:.3f} at cost of {len(test_trades)-len(rf_trades)} fewer trades.')
        else:
            print(f'    RF filter does NOT improve PF. Edge is in the signal structure, not feature filtering.')


# ═════════════════════════════════════════════════════════════════════════════
#  MASTER VERDICT
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  MASTER VERDICT — RSI<20 HYPOTHESIS TEST')
print(SEP)
print(f'  IS  : {is_t} trades  WR={is_wr:.1f}%  PF={is_pf:.3f}  CAGR={is_cagr:+.1f}%')
print(f'  OOS : {oos_t} trades  WR={oos_wr:.1f}%  PF={oos_pf:.3f}  CAGR={oos_cagr:+.1f}%  '
      f'MaxDD={oos_dd:.1f}%  Sharpe={oos_sh:.3f}')
print()

if oos_pf >= 1.2 and oos_t >= 50:
    print('  RESULT: EDGE CONFIRMED.')
    print(f'  OOS PF={oos_pf:.3f} >= 1.2 across {oos_t} out-of-sample trades on 50 stocks.')
    print('  RSI<20 + Variant B has a statistically meaningful edge on NSE large/mid caps.')
    print('  Recommended next step: paper-trade live for 60 days before capital deployment.')
elif oos_pf >= 1.0 and oos_t >= 50:
    print('  RESULT: EDGE PRESENT BUT MARGINAL.')
    print(f'  OOS PF={oos_pf:.3f} is profitable but narrow. Transaction costs dominate on small capital.')
    print(f'  At Rs.5000/stock, costs eat ~{BROKERAGE*2/CAPITAL*100:.1f}% per trade.')
    print('  With Rs.50000/stock, same strategy has ~5x better cost ratio.')
    print('  Recommended: scale capital or reduce brokerage before live deployment.')
elif oos_pf >= 1.0 and oos_t < 50:
    print(f'  RESULT: INCONCLUSIVE. OOS PF={oos_pf:.3f} looks good but only {oos_t} trades.')
    print('  Expand universe or extend period to get >= 100 OOS trades before concluding.')
elif oos_pf >= 0.7:
    print(f'  RESULT: EDGE DEGRADES OOS. IS PF={is_pf:.3f} -> OOS PF={oos_pf:.3f}.')
    print('  Genuine edge exists but insufficient to cover costs. Need entry precision improvement.')
    print('  Best next step: apply regime filter (BULL only) + best morphology filter.')
else:
    decay = (1 - oos_pf / is_pf) * 100 if is_pf > 0 else 100
    print(f'  RESULT: EDGE COLLAPSES OOS. IS PF={is_pf:.3f} -> OOS PF={oos_pf:.3f} ({decay:.0f}% decay).')
    print('  RSI<20 result was data-snooped on the 3-stock 1-year sample.')
    print('  The earlier OOS PF=2.113 was a small-sample artifact (3 OOS trades).')
    print('  Do not trade this strategy.')

print()
print('  PER-INVESTIGATION FINDINGS:')
print(f'  INV1 OOS PF={oos_pf:.3f}  trades={oos_t}  — main falsification result')
morph_pfs = {}
for m in ['V-Reversal','Sideways','Breakdown']:
    g = morph_groups[m]
    w = [t for t in g if t['winner']]
    l = [t for t in g if not t['winner']]
    morph_pfs[m] = sum(t['pnl'] for t in w) / max(1, abs(sum(t['pnl'] for t in l)))
print(f'  INV2 Best morphology={max(morph_pfs, key=morph_pfs.get)}  '
      f'PF={max(morph_pfs.values()):.3f}')
print(f'  INV3 Top predictor={FEAT_LABELS[ranked[0]]}  |r|={feat_corrs[ranked[0]]:.4f}')
print(f'  INV4 Bull regime PF={bull_pf:.3f}  Bear regime PF={bear_pf:.3f}')
if ML_AVAILABLE and len(feat_data) >= 20:
    print(f'  INV5 RF AUC={auc:.3f}  RF-filtered PF={rf_pf:.3f} vs unfiltered={all_pf:.3f}')
