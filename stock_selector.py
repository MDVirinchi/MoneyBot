"""
stock_selector.py — Characterise Universe A (S3-profitable) vs Universe B (S3-unprofitable).

Metrics computed on 3 years of daily bars:
  1. Trend strength     — annualised price CAGR (log-linear regression slope)
  2. % days above EMA200
  3. Average ADX (14-period)
  4. Annualised volatility (std of daily log returns × sqrt(252))
  5. Maximum drawdown (from equity-style close curve)
  6. RSI<30 event count (each new trip below 30 counts as one event)
  7. RSI<30 avg duration (how many bars RSI stays below 30 per event)
  8. Recovery rate      — of RSI<30 events, how many resolved back above 50 within 20 bars

Run: python stock_selector.py
"""

import math, time, statistics, warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

UNIVERSE_A = [           # S3 profitable (PF > 0.5 in 3-year test)
    ('HDFCBANK.NS', 'HDFCBANK'),
    ('HCLTECH.NS',  'HCLTECH'),
    ('TITAN.NS',    'TITAN'),
    ('SBIN.NS',     'SBIN'),
    ('RELIANCE.NS', 'RELIANCE'),
]
UNIVERSE_B = [           # S3 unprofitable (PF < 0.1 in 3-year test)
    ('INFY.NS',       'INFY'),
    ('WIPRO.NS',      'WIPRO'),
    ('AXISBANK.NS',   'AXISBANK'),
    ('KOTAKBANK.NS',  'KOTAKBANK'),
]
ALL_STOCKS = UNIVERSE_A + UNIVERSE_B


# ── Helpers ───────────────────────────────────────────────────────────────────
def ema_series(values, period):
    if len(values) < period:
        return [None] * len(values)
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    result = [None] * (period - 1) + [seed]
    for v in values[period:]:
        result.append(result[-1] * (1 - k) + v * k)
    return result


def rsi_series(closes, period=14):
    """Return list of RSI values, None for first <period> bars."""
    out = [None] * period
    if len(closes) <= period:
        return [None] * len(closes)
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    rs = avg_g / avg_l if avg_l > 0 else 1e9
    out.append(100 - 100 / (1 + rs))
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0)) / period
        rs = avg_g / avg_l if avg_l > 0 else 1e9
        out.append(100 - 100 / (1 + rs))
    return out


def adx_series(highs, lows, closes, period=14):
    """Returns list of ADX values (None for first 2*period bars)."""
    n = len(closes)
    if n < period * 2 + 2:
        return [None] * n

    trs, pdms, ndms = [], [], []
    for i in range(1, n):
        tr  = max(highs[i] - lows[i],
                  abs(highs[i] - closes[i - 1]),
                  abs(lows[i]  - closes[i - 1]))
        pdm = max(highs[i] - highs[i - 1], 0) if (highs[i] - highs[i - 1]) > (lows[i - 1] - lows[i]) else 0
        ndm = max(lows[i - 1] - lows[i], 0) if (lows[i - 1] - lows[i]) > (highs[i] - highs[i - 1]) else 0
        trs.append(tr); pdms.append(pdm); ndms.append(ndm)

    # Wilder smoothing
    def wilder_smooth(arr, p):
        if len(arr) < p:
            return []
        smoothed = [sum(arr[:p])]
        for v in arr[p:]:
            smoothed.append(smoothed[-1] - smoothed[-1] / p + v)
        return smoothed

    atr   = wilder_smooth(trs,  period)
    s_pdm = wilder_smooth(pdms, period)
    s_ndm = wilder_smooth(ndms, period)

    dxs = []
    for a, p, nd in zip(atr, s_pdm, s_ndm):
        if a == 0:
            dxs.append(0.0)
            continue
        pdi = 100 * p  / a
        ndi = 100 * nd / a
        denom = pdi + ndi
        dxs.append(100 * abs(pdi - ndi) / denom if denom > 0 else 0.0)

    adx_vals = wilder_smooth(dxs, period)
    # Pad back to original length
    pad = n - len(adx_vals)
    return [None] * pad + adx_vals


def linreg_slope(xs, ys):
    """Slope of OLS line through (xs, ys)."""
    n = len(xs)
    if n < 2:
        return 0.0
    xm = sum(xs) / n; ym = sum(ys) / n
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    den = sum((x - xm) ** 2 for x in xs)
    return num / den if den > 0 else 0.0


def analyse(ticker, sym):
    df = yf.Ticker(ticker).history(period='3y', interval='1d', auto_adjust=True)
    if df.empty or len(df) < 220:
        return None

    closes = list(df['Close'])
    highs  = list(df['High'])
    lows   = list(df['Low'])
    n      = len(closes)

    # ── 1. Trend strength: annualised log-linear slope ─────────────────────────
    log_c  = [math.log(c) for c in closes]
    xs     = list(range(n))
    slope  = linreg_slope(xs, log_c)           # log-points per bar
    trend_ann = slope * 252 * 100              # % per year

    # ── 2. % days above EMA200 ─────────────────────────────────────────────────
    e200 = ema_series(closes, 200)
    above_e200 = sum(1 for i in range(n) if e200[i] is not None and closes[i] > e200[i])
    valid_e200 = sum(1 for e in e200 if e is not None)
    pct_above_e200 = above_e200 / valid_e200 * 100 if valid_e200 > 0 else 0.0

    # ── 3. Average ADX ─────────────────────────────────────────────────────────
    adx = adx_series(highs, lows, closes, 14)
    valid_adx = [v for v in adx if v is not None]
    avg_adx = statistics.mean(valid_adx) if valid_adx else 0.0

    # ── 4. Annualised volatility ────────────────────────────────────────────────
    log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, n)]
    ann_vol  = statistics.stdev(log_rets) * math.sqrt(252) * 100

    # ── 5. Maximum drawdown ────────────────────────────────────────────────────
    peak = closes[0]; max_dd = 0.0
    for c in closes:
        if c > peak: peak = c
        dd = (peak - c) / peak * 100
        if dd > max_dd: max_dd = dd

    # ── 6. RSI<30 event count + duration + recovery rate ──────────────────────
    rsi = rsi_series(closes, 14)
    rsi_events = 0
    in_oversold = False
    durations   = []
    dur         = 0
    recovery_count = 0

    for i, r in enumerate(rsi):
        if r is None:
            continue
        if r < 30 and not in_oversold:
            in_oversold = True
            rsi_events += 1
            dur = 1
        elif r < 30 and in_oversold:
            dur += 1
        elif r >= 30 and in_oversold:
            in_oversold = False
            durations.append(dur)
            # Check recovery: does RSI reach 50 within 20 bars?
            for j in range(i, min(i + 20, n)):
                if rsi[j] is not None and rsi[j] >= 50:
                    recovery_count += 1
                    break
            dur = 0

    avg_dur      = statistics.mean(durations) if durations else 0.0
    recovery_pct = recovery_count / rsi_events * 100 if rsi_events > 0 else 0.0

    # ── Price CAGR (simple) ────────────────────────────────────────────────────
    years = n / 252
    price_cagr = ((closes[-1] / closes[0]) ** (1 / years) - 1) * 100

    return {
        'sym':            sym,
        'bars':           n,
        'trend_ann':      round(trend_ann, 1),
        'price_cagr':     round(price_cagr, 1),
        'pct_above_e200': round(pct_above_e200, 1),
        'avg_adx':        round(avg_adx, 1),
        'ann_vol':        round(ann_vol, 1),
        'max_dd':         round(max_dd, 1),
        'rsi30_events':   rsi_events,
        'rsi30_avg_dur':  round(avg_dur, 1),
        'recovery_pct':   round(recovery_pct, 1),
    }


# ── Run ───────────────────────────────────────────────────────────────────────
print('Computing stock characteristics (3 years daily)...')
print()

results = {}
for ticker, sym in ALL_STOCKS:
    r = analyse(ticker, sym)
    results[sym] = r
    if r:
        print(f'  {sym:<14}: done  ({r["bars"]} bars)')
    else:
        print(f'  {sym:<14}: FAILED / insufficient data')
    time.sleep(0.3)

# ── Print comparison tables ───────────────────────────────────────────────────
SEP = '=' * 98
sep = '-' * 98

def row(sym, s3_pf):
    r = results.get(sym)
    if not r:
        return f'  {sym:<14}  -- no data --'
    return (f'  {sym:<14}  {s3_pf:>5.3f}  {r["price_cagr"]:>+7.1f}%  '
            f'{r["trend_ann"]:>+7.1f}%  {r["pct_above_e200"]:>6.1f}%  '
            f'{r["avg_adx"]:>7.1f}  {r["ann_vol"]:>7.1f}%  '
            f'{r["max_dd"]:>7.1f}%  {r["rsi30_events"]:>6}  '
            f'{r["rsi30_avg_dur"]:>8.1f}  {r["recovery_pct"]:>8.1f}%')

# S3 PF from 3-year expanded test (from s3_expand.py results)
S3_PF = {
    'HDFCBANK': 3.344, 'HCLTECH': 1.908, 'TITAN': 1.458,
    'SBIN': 0.990,     'RELIANCE': 0.681,
    'INFY': 0.000,     'WIPRO': 0.059,
    'AXISBANK': 0.070, 'KOTAKBANK': 0.000,
}

print()
print(SEP)
print('  UNIVERSE A  —  S3-PROFITABLE  (PF > 0.5)')
print(SEP)
print(f'  {"Stock":<14}  {"S3-PF":>5}  {"PricCAGR":>8}  {"TrendAnn":>8}  '
      f'{"AbvE200":>7}  {"AvgADX":>7}  {"AnnVol":>7}  '
      f'{"MaxDD":>7}  {"RSI<30":>6}  {"DurBars":>8}  {"Recov%":>8}')
print(sep)
for _, sym in UNIVERSE_A:
    print(row(sym, S3_PF.get(sym, 0)))

# Universe A averages
a_vals = [results[sym] for _, sym in UNIVERSE_A if results.get(sym)]
if a_vals:
    def avg_a(k): return statistics.mean(v[k] for v in a_vals)
    print(sep)
    print(f'  {"A AVERAGE":<14}  {statistics.mean(S3_PF[sym] for _,sym in UNIVERSE_A if sym in S3_PF):>5.3f}  '
          f'{avg_a("price_cagr"):>+7.1f}%  {avg_a("trend_ann"):>+7.1f}%  '
          f'{avg_a("pct_above_e200"):>6.1f}%  {avg_a("avg_adx"):>7.1f}  '
          f'{avg_a("ann_vol"):>7.1f}%  {avg_a("max_dd"):>7.1f}%  '
          f'{avg_a("rsi30_events"):>6.1f}  {avg_a("rsi30_avg_dur"):>8.1f}  '
          f'{avg_a("recovery_pct"):>8.1f}%')

print()
print(SEP)
print('  UNIVERSE B  —  S3-UNPROFITABLE  (PF < 0.1)')
print(SEP)
print(f'  {"Stock":<14}  {"S3-PF":>5}  {"PricCAGR":>8}  {"TrendAnn":>8}  '
      f'{"AbvE200":>7}  {"AvgADX":>7}  {"AnnVol":>7}  '
      f'{"MaxDD":>7}  {"RSI<30":>6}  {"DurBars":>8}  {"Recov%":>8}')
print(sep)
for _, sym in UNIVERSE_B:
    print(row(sym, S3_PF.get(sym, 0)))

b_vals = [results[sym] for _, sym in UNIVERSE_B if results.get(sym)]
if b_vals:
    def avg_b(k): return statistics.mean(v[k] for v in b_vals)
    print(sep)
    print(f'  {"B AVERAGE":<14}  {statistics.mean(S3_PF[sym] for _,sym in UNIVERSE_B if sym in S3_PF):>5.3f}  '
          f'{avg_b("price_cagr"):>+7.1f}%  {avg_b("trend_ann"):>+7.1f}%  '
          f'{avg_b("pct_above_e200"):>6.1f}%  {avg_b("avg_adx"):>7.1f}  '
          f'{avg_b("ann_vol"):>7.1f}%  {avg_b("max_dd"):>7.1f}%  '
          f'{avg_b("rsi30_events"):>6.1f}  {avg_b("rsi30_avg_dur"):>8.1f}  '
          f'{avg_b("recovery_pct"):>8.1f}%')

# ── Delta table ───────────────────────────────────────────────────────────────
if a_vals and b_vals:
    print()
    print(SEP)
    print('  SEPARATION ANALYSIS  —  Universe A minus Universe B')
    print(SEP)
    metrics = [
        ('Price CAGR %',      'price_cagr',      True),
        ('Trend Ann %',       'trend_ann',        True),
        ('% Above EMA200',    'pct_above_e200',   True),
        ('Avg ADX',           'avg_adx',          True),
        ('Ann Volatility %',  'ann_vol',          False),
        ('Max Drawdown %',    'max_dd',           False),
        ('RSI<30 Events',     'rsi30_events',     False),
        ('RSI<30 Dur (bars)', 'rsi30_avg_dur',    False),
        ('Recovery Rate %',   'recovery_pct',     True),
    ]
    print(f'  {"Metric":<22}  {"A avg":>9}  {"B avg":>9}  {"Delta":>9}  {"Separation"}')
    print(sep)
    for label, key, higher_better in metrics:
        av = avg_a(key); bv = avg_b(key); d = av - bv
        # Separation strength: how cleanly does this separate the groups?
        # Check if all A values are on the "better" side vs all B values
        a_list = sorted([v[key] for v in a_vals], reverse=higher_better)
        b_list = sorted([v[key] for v in b_vals], reverse=not higher_better)
        # Overlap: does worst A overlap with best B?
        worst_a = min(a_list) if higher_better else max(a_list)
        best_b  = max(b_list) if higher_better else min(b_list)
        no_overlap = (worst_a > best_b) if higher_better else (worst_a < best_b)
        separation = 'CLEAN SPLIT' if no_overlap else f'overlap'

        fmt_a = f'{av:>+8.1f}' if isinstance(av, float) else f'{av:>8.1f}'
        fmt_b = f'{bv:>+8.1f}' if isinstance(bv, float) else f'{bv:>8.1f}'
        fmt_d = f'{d:>+8.1f}'
        print(f'  {label:<22}  {fmt_a}  {fmt_b}  {fmt_d}  {separation}')

# ── Screening criteria ────────────────────────────────────────────────────────
print()
print(SEP)
print('  PROPOSED SCREENING CRITERIA  (for S3 universe selection)')
print(SEP)

# Derive thresholds from the data: midpoint between worst-A and best-B
def threshold(key, higher_better):
    a_list = [v[key] for v in a_vals]
    b_list = [v[key] for v in b_vals]
    worst_a = min(a_list) if higher_better else max(a_list)
    best_b  = max(b_list) if higher_better else min(b_list)
    return (worst_a + best_b) / 2

criteria = [
    ('% Above EMA200',   'pct_above_e200',  True,  '>'),
    ('Price CAGR %',     'price_cagr',      True,  '>'),
    ('Trend Ann %',      'trend_ann',       True,  '>'),
    ('Recovery Rate %',  'recovery_pct',    True,  '>'),
    ('RSI<30 Events',    'rsi30_events',    False, '<'),
    ('Max Drawdown %',   'max_dd',          False, '<'),
]

print(f'  {"Criterion":<22}  {"Threshold":>10}  {"A pass":>8}  {"B pass":>8}  {"Discriminates?"}')
print(sep)
for label, key, hb, op in criteria:
    t = threshold(key, hb)
    a_pass = sum(1 for v in a_vals if (v[key] > t if op == '>' else v[key] < t))
    b_pass = sum(1 for v in b_vals if (v[key] > t if op == '>' else v[key] < t))
    discriminates = 'YES' if a_pass == len(a_vals) and b_pass == 0 else \
                    f'partial ({a_pass}/{len(a_vals)} A, {b_pass}/{len(b_vals)} B)'
    print(f'  {label:<22}  {op} {t:>7.1f}  {a_pass:>5}/{len(a_vals)}  '
          f'{b_pass:>5}/{len(b_vals)}  {discriminates}')

print()
print(SEP)
print('  CONCLUSION')
print(SEP)
if a_vals and b_vals:
    best_metric = None
    for label, key, hb, op in criteria:
        a_list = [v[key] for v in a_vals]
        b_list = [v[key] for v in b_vals]
        worst_a = min(a_list) if hb else max(a_list)
        best_b  = max(b_list) if hb else min(b_list)
        if (worst_a > best_b) if hb else (worst_a < best_b):
            best_metric = (label, key, op, threshold(key, hb))
            break
    if best_metric:
        label, key, op, t = best_metric
        print(f'  Strongest single discriminator : {label} {op} {t:.1f}')
    print()
    pct_a = avg_a('pct_above_e200')
    pct_b = avg_b('pct_above_e200')
    rec_a = avg_a('recovery_pct')
    rec_b = avg_b('recovery_pct')
    cagr_a = avg_a('price_cagr')
    cagr_b = avg_b('price_cagr')
    print(f'  Universe A (profitable)   : {pct_a:.0f}% days above EMA200,  '
          f'{rec_a:.0f}% RSI<30 recovery rate,  {cagr_a:+.0f}% price CAGR')
    print(f'  Universe B (unprofitable) : {pct_b:.0f}% days above EMA200,  '
          f'{rec_b:.0f}% RSI<30 recovery rate,  {cagr_b:+.0f}% price CAGR')
    print()
    if pct_a - pct_b >= 20:
        print('  HYPOTHESIS CONFIRMED: S3 works on stocks in persistent long-term uptrends.')
        print('  Proposed filter: include stocks where % days above EMA200 >= threshold.')
    else:
        print('  HYPOTHESIS PARTIALLY CONFIRMED: some separation, but not clean enough.')
        print('  Multiple criteria may be needed to reliably screen stocks.')
