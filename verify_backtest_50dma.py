"""
verify_backtest_50dma.py — Head-to-head comparison:
  A) Original RS60/EP40 (Policy C: bull_flat)
  B) RS60/EP40 + 50-DMA trend filter (Policy C: bull_flat)

Uses the same simulation engine as final_validation.py.
Run: python verify_backtest_50dma.py
Expected runtime: 10-15 minutes (mostly yfinance download).
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time, math, statistics, warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

# ── Constants (identical to final_validation.py) ──────────────────────────────
W_RS = 0.60; W_EP = 0.40
TOP_N = 10; REBAL_DAYS = 10; SL_PCT = 10.0
BROKERAGE = 20.0; STT = 0.001; EXCHANGE = 0.0000345
SLIP = 0.002
CAPITAL = 500_000.0

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
    ('BALKRISIND.NS','BALKRISIND'),('TATAPOWER.NS','TATAPOWER'),
    ('M&M.NS','M&M'),('HEROMOTOCO.NS','HEROMOTOCO'),('BAJAJ-AUTO.NS','BAJAJ-AUTO'),
    ('BOSCHLTD.NS','BOSCHLTD'),('SIEMENS.NS','SIEMENS'),('ABB.NS','ABB'),
    ('CUMMINSIND.NS','CUMMINSIND'),('VOLTAS.NS','VOLTAS'),
    ('BERGEPAINT.NS','BERGEPAINT'),('KANSAINER.NS','KANSAINER'),
    ('DABUR.NS','DABUR'),('MARICO.NS','MARICO'),('COLPAL.NS','COLPAL'),
    ('GODREJCP.NS','GODREJCP'),('EMAMILTD.NS','EMAMILTD'),('PGHH.NS','PGHH'),
    ('LUPIN.NS','LUPIN'),('AUROPHARMA.NS','AUROPHARMA'),('BIOCON.NS','BIOCON'),
    ('ALKEM.NS','ALKEM'),('PFIZER.NS','PFIZER'),
    ('LICHSGFIN.NS','LICHSGFIN'),('M&MFIN.NS','M&MFIN'),('CHOLAFIN.NS','CHOLAFIN'),
    ('PFC.NS','PFC'),('RECLTD.NS','RECLTD'),('IRFC.NS','IRFC'),
    ('SAIL.NS','SAIL'),('NMDC.NS','NMDC'),('VEDL.NS','VEDL'),
    ('IGL.NS','IGL'),('MGL.NS','MGL'),('GUJGASLTD.NS','GUJGASLTD'),
    ('INDIGO.NS','INDIGO'),('SBILIFE.NS','SBILIFE'),('HDFCLIFE.NS','HDFCLIFE'),
    ('NAUKRI.NS','NAUKRI'),('IRCTC.NS','IRCTC'),
    ('TORNTPOWER.NS','TORNTPOWER'),('TATAELXSI.NS','TATAELXSI'),
    ('MPHASIS.NS','MPHASIS'),('LTTS.NS','LTTS'),('COFORGE.NS','COFORGE'),
    ('PERSISTENT.NS','PERSISTENT'),('OFSS.NS','OFSS'),
    ('TRENT.NS','TRENT'),('DMART.NS','DMART'),
    ('IDFCFIRSTB.NS','IDFCFIRSTB'),('AUBANK.NS','AUBANK'),
    ('POLYCAB.NS','POLYCAB'),('KEI.NS','KEI'),
    ('APLAPOLLO.NS','APLAPOLLO'),('DEEPAKNTR.NS','DEEPAKNTR'),
    ('RBLBANK.NS','RBLBANK'),('TATAMOTORS.NS','TATAMOTORS'),
    ('WHIRLPOOL.NS','WHIRLPOOL'),('PAGEIND.NS','PAGEIND'),
    ('VBL.NS','VBL'),('TVSMOTOR.NS','TVSMOTOR'),('ASHOKLEY.NS','ASHOKLEY'),
    ('MOTHERSON.NS','MOTHERSON'),('BHARATFORG.NS','BHARATFORG'),
    ('EXIDEIND.NS','EXIDEIND'),('CESC.NS','CESC'),('NHPC.NS','NHPC'),
    ('RVNL.NS','RVNL'),('MANAPPURAM.NS','MANAPPURAM'),
    ('KPITTECH.NS','KPITTECH'),('CYIENT.NS','CYIENT'),
    ('NAVINFLUOR.NS','NAVINFLUOR'),('PIIND.NS','PIIND'),
    ('METROPOLIS.NS','METROPOLIS'),('MAXHEALTH.NS','MAXHEALTH'),
    ('PNBHOUSING.NS','PNBHOUSING'),('CANFINHOME.NS','CANFINHOME'),
    ('CDSL.NS','CDSL'),('MCX.NS','MCX'),('ANGELONE.NS','ANGELONE'),
    ('RAMCOCEM.NS','RAMCOCEM'),('JKCEMENT.NS','JKCEMENT'),
    ('DALBHARAT.NS','DALBHARAT'),('SUNDARMFIN.NS','SUNDARMFIN'),
    ('ZENSARTECH.NS','ZENSARTECH'),('ASTRAL.NS','ASTRAL'),
    ('MCDOWELL-N.NS','MCDOWELL-N'),
]

SEP = '=' * 100
sep = '-' * 100

# ── Fetch ─────────────────────────────────────────────────────────────────────
print('Fetching price data for 136 stocks + Nifty... (this takes a few minutes)')
t0 = time.time()
price_data = {}; valid = []
for i, (ticker, sym) in enumerate(STOCKS):
    try:
        df = yf.Ticker(ticker).history(period='5y', interval='1d', auto_adjust=True)
        if not df.empty:
            d = {str(ts.date()): {'open': float(r['Open']),
                                   'close': float(r['Close']),
                                   'vol': float(r.get('Volume', 0) or 0)}
                 for ts, r in df.iterrows()}
            if len(d) >= 300:
                price_data[sym] = d; valid.append(sym)
    except Exception:
        pass
    if (i + 1) % 20 == 0:
        print(f'  ... {i+1}/{len(STOCKS)} stocks fetched')
    time.sleep(0.22)

nifty_raw = {}
try:
    df = yf.Ticker('^NSEI').history(period='5y', interval='1d', auto_adjust=True)
    nifty_raw = {str(ts.date()): float(r['Close']) for ts, r in df.iterrows()}
except Exception:
    pass

fetch_time = time.time() - t0
print(f'Data fetched: {len(valid)} stocks, {len(nifty_raw)} Nifty days in {fetch_time:.0f}s')

all_dates = sorted(nifty_raw.keys())
N = len(all_dates)
IS_END = int(N * 0.6)
IS_DATES = all_dates[:IS_END]
OOS_DATES = all_dates[IS_END:]

n_start = nifty_raw.get(OOS_DATES[0], 1)
n_end = nifty_raw.get(OOS_DATES[-1], 1)
NIFTY_OOS_CAGR = ((n_end / n_start) ** (252 / len(OOS_DATES)) - 1) * 100

print(f'IS:  {IS_DATES[0]} to {IS_DATES[-1]}  ({len(IS_DATES)} days)')
print(f'OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}  ({len(OOS_DATES)} days)')
print(f'Nifty OOS CAGR: {NIFTY_OOS_CAGR:+.1f}%\n')

# ── Nifty DMA ─────────────────────────────────────────────────────────────────
nifty_dma = {}
nifty_closes = [(d, nifty_raw[d]) for d in all_dates]
for idx, (d, c) in enumerate(nifty_closes):
    dma50 = sum(v for _, v in nifty_closes[max(0, idx - 49):idx + 1]) / min(idx + 1, 50)
    dma200 = sum(v for _, v in nifty_closes[max(0, idx - 199):idx + 1]) / min(idx + 1, 200)
    nifty_dma[d] = {'close': c, 'dma50': dma50, 'dma200': dma200}

def regime(date):
    r = nifty_dma.get(date)
    if not r: return 'Bull'
    c, d50, d200 = r['close'], r['dma50'], r['dma200']
    if c < d200: return 'Bear'
    if d50 <= d200: return 'Flat'
    return 'Bull'

# ── Factor engine ─────────────────────────────────────────────────────────────
_raw_cache = {}

def get_raw(gi):
    if gi in _raw_cache: return _raw_cache[gi]
    if gi < 72: return {}
    dn = all_dates[gi]
    nc = nifty_raw.get(dn)
    np_ = nifty_raw.get(all_dates[gi - 63]) if gi >= 63 else None
    raw_rs = {}; raw_ep = {}
    for sym in valid:
        c = price_data[sym]
        sd = [d for d in all_dates[max(0, gi - 74):gi + 1] if d in c]
        if len(sd) < 50: continue
        if nc and np_:
            cn = c.get(dn, {}).get('close')
            cp = c.get(all_dates[gi - 63], {}).get('close')
            if cn and cp: raw_rs[sym] = (cn / cp - 1) * 100 - (nc / np_ - 1) * 100
        ed = sd[-63:]
        evols = [c[d]['vol'] for d in ed if c[d]['vol'] > 0]
        av = sum(evols) / len(evols) if evols else 0
        ep = 0.0
        for j in range(1, len(ed)):
            cj = c.get(ed[j]); cjm = c.get(ed[j - 1])
            if not (cj and cjm and cjm['close'] > 0): continue
            dr = cj['close'] / cjm['close'] - 1
            if dr > 0.02 and av > 0 and cj['vol'] > 1.5 * av: ep = max(ep, dr * 100)
        raw_ep[sym] = ep
    result = {'rs': raw_rs, 'ep': raw_ep}
    _raw_cache[gi] = result
    return result

def composite(gi):
    raw = get_raw(gi)
    if not raw: return {}
    def pr(d):
        items = sorted(d.items(), key=lambda x: x[1]); n = len(items)
        return {s: (r + 1) / n * 100 for r, (s, _) in enumerate(items)}
    rnks = {}
    if raw['rs']: rnks['rs'] = pr(raw['rs'])
    if raw['ep']: rnks['ep'] = pr(raw['ep'])
    if not rnks: return {}
    active = list(rnks.keys())
    tw = sum({'rs': W_RS, 'ep': W_EP}[f] for f in active)
    syms = set.intersection(*[set(rnks[f].keys()) for f in active])
    return {s: sum({'rs': W_RS, 'ep': W_EP}[f] * rnks[f][s] for f in active) / tw for s in syms}

# Pre-cache
print('Pre-computing factors...')
gi = 72
while gi < N: get_raw(gi); gi += REBAL_DAYS
print(f'Cached {len(_raw_cache)} rebalance points.\n')

# ── 50-DMA filter for individual stocks ───────────────────────────────────────
def stock_above_50dma(sym, date, gi):
    """Returns True if stock's close > its 50-day moving average."""
    c = price_data.get(sym, {})
    # Get last 50 trading days for this stock up to gi
    dates_window = [d for d in all_dates[max(0, gi - 60):gi + 1] if d in c]
    if len(dates_window) < 50:
        return True  # not enough data, include stock
    closes_50 = [c[d]['close'] for d in dates_window[-50:]]
    dma50 = sum(closes_50) / len(closes_50)
    current_close = c.get(date, {}).get('close')
    if current_close is None:
        return True  # no data for today, include
    return current_close > dma50

# ── Simulation engine ─────────────────────────────────────────────────────────
def run_sim(date_range, use_50dma_filter=False, regime_policy='bull_flat'):
    cash = CAPITAL; pos = {}; trades = []; equity = []; last = -999
    date_to_gi = {d: all_dates.index(d) for d in date_range if d in all_dates}
    turnover_total = 0.0  # track total buy+sell volume for turnover calc

    def gc(s, d): return price_data[s].get(d, {}).get('close')
    def go(s, d): return price_data[s].get(d, {}).get('open')

    for idx, date in enumerate(date_range):
        gi = date_to_gi.get(date)
        if gi is None or gi < 72: equity.append(cash); continue

        # Regime gate (Policy C: bull_flat)
        reg = regime(date)
        if regime_policy == 'bull_flat' and reg == 'Bear':
            for sym in list(pos):
                nd = date_range[idx + 1] if idx + 1 < len(date_range) else date
                fp = (go(sym, nd) or gc(sym, date) or pos[sym]['ep']) * (1 - SLIP)
                p = pos.pop(sym); ev = p['qty'] * fp
                cost = BROKERAGE + ev * STT + ev * EXCHANGE; cash += ev - cost
                turnover_total += ev
                trades.append({'pnl': (fp - p['ep']) * p['qty'] - cost,
                               'ret': (fp / p['ep'] - 1) * 100, 'exit': 'Regime'})
            equity.append(cash); continue

        # SL
        for sym in list(pos):
            curr = gc(sym, date)
            if curr and curr <= pos[sym]['ep'] * (1 - SL_PCT / 100):
                p = pos.pop(sym); fill = curr * (1 - SLIP)
                ev = p['qty'] * fill; cost = BROKERAGE + ev * STT + ev * EXCHANGE
                cash += ev - cost; turnover_total += ev
                trades.append({'pnl': (fill - p['ep']) * p['qty'] - cost,
                               'ret': (fill / p['ep'] - 1) * 100, 'exit': 'SL'})

        # Rebalance
        if idx - last >= REBAL_DAYS:
            last = idx
            comp = composite(gi)

            if use_50dma_filter:
                # FILTER: remove stocks where close < 50-DMA
                filtered = {s: sc for s, sc in comp.items()
                            if stock_above_50dma(s, date, gi)}
                tgt = {s for s, _ in sorted(filtered.items(), key=lambda x: -x[1])[:TOP_N]}
            else:
                tgt = {s for s, _ in sorted(comp.items(), key=lambda x: -x[1])[:TOP_N]}

            for sym in list(pos):
                if sym not in tgt:
                    nd = date_range[idx + 1] if idx + 1 < len(date_range) else date
                    fp = (go(sym, nd) or gc(sym, date) or pos[sym]['ep']) * (1 - SLIP)
                    p = pos.pop(sym); ev = p['qty'] * fp
                    cost = BROKERAGE + ev * STT + ev * EXCHANGE; cash += ev - cost
                    turnover_total += ev
                    trades.append({'pnl': (fp - p['ep']) * p['qty'] - cost,
                                   'ret': (fp / p['ep'] - 1) * 100, 'exit': 'Rebal'})
            new = [s for s in tgt if s not in pos]
            avail_cap = cash * 0.95
            if new and avail_cap > 10_000:
                alloc = min(avail_cap / max(len(new), 1), CAPITAL / TOP_N)
                for sym in new:
                    nd = date_range[idx + 1] if idx + 1 < len(date_range) else date
                    fpd = go(sym, nd) or gc(sym, date)
                    if not fpd: continue
                    fill = fpd * (1 + SLIP); qty = max(1, int(alloc / fill))
                    cost = BROKERAGE + qty * fill * EXCHANGE
                    if cash >= qty * fill + cost:
                        cash -= qty * fill + cost; pos[sym] = {'qty': qty, 'ep': fill}
                        turnover_total += qty * fill

        fv = cash + sum(p['qty'] * (gc(s, date) or p['ep']) for s, p in pos.items())
        equity.append(fv)

    # Liquidate remaining
    for s, p in list(pos.items()):
        fp = (gc(s, date_range[-1]) or p['ep']) * (1 - SLIP)
        ev = p['qty'] * fp; cost = BROKERAGE + ev * STT + ev * EXCHANGE
        cash += ev - cost; turnover_total += ev
        trades.append({'pnl': (fp - p['ep']) * p['qty'] - cost,
                       'ret': (fp / p['ep'] - 1) * 100, 'exit': 'EoP'})

    if not trades:
        return {'pf': 0, 'cagr': -100, 'sharpe': 0, 'max_dd': 0,
                'trades': 0, 'wr': 0, 'turnover': 0}

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp = sum(t['pnl'] for t in wins)
    gl = abs(sum(t['pnl'] for t in losses))
    pf = gp / gl if gl > 0 else (1.5 if gp > 0 else 0)
    yrs = max(len(date_range) / 252, 0.1)
    fv = equity[-1] if equity else CAPITAL
    cagr = ((fv / CAPITAL) ** (1 / yrs) - 1) * 100 if fv > 0 else -100
    dr = [(equity[k] - equity[k - 1]) / equity[k - 1]
          for k in range(1, len(equity)) if equity[k - 1] > 0]
    sharpe = (statistics.mean(dr) / statistics.stdev(dr) * math.sqrt(252)
              if len(dr) > 2 and statistics.stdev(dr) > 0 else 0)
    peak = CAPITAL; max_dd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd

    # Annualized turnover: total trade volume / average portfolio value / years
    avg_equity = sum(equity) / len(equity) if equity else CAPITAL
    ann_turnover = (turnover_total / avg_equity / yrs) * 100 if avg_equity > 0 else 0

    # Exit type breakdown
    sl_count = sum(1 for t in trades if t['exit'] == 'SL')
    rebal_count = sum(1 for t in trades if t['exit'] == 'Rebal')
    regime_count = sum(1 for t in trades if t['exit'] == 'Regime')

    return {
        'pf': round(pf, 3), 'cagr': round(cagr, 2), 'sharpe': round(sharpe, 3),
        'max_dd': round(max_dd, 1), 'trades': len(trades),
        'wr': round(len(wins) / len(trades) * 100, 1),
        'turnover': round(ann_turnover, 1),
        'sl_exits': sl_count, 'rebal_exits': rebal_count, 'regime_exits': regime_count,
        'final_value': round(fv, 0),
    }


# ══════════════════════════════════════════════════════════════════════════════
# RUN COMPARISON
# ══════════════════════════════════════════════════════════════════════════════
print(SEP)
print('  50-DMA TREND FILTER — BACKTEST COMPARISON')
print(f'  Strategy: RS=60% / EP=40% / Top-10 / Rebal-10d / SL-10% / Policy-C')
print(f'  Slippage: 0.2% each side | Brokerage: Rs.20 flat | STT: 0.1% sell')
print(SEP)

print('\nRunning simulations...')

# IS period
t1 = time.time()
is_original = run_sim(IS_DATES, use_50dma_filter=False)
is_filtered = run_sim(IS_DATES, use_50dma_filter=True)
# OOS period
oos_original = run_sim(OOS_DATES, use_50dma_filter=False)
oos_filtered = run_sim(OOS_DATES, use_50dma_filter=True)
sim_time = time.time() - t1
print(f'Simulations completed in {sim_time:.1f}s\n')

# ── Results table ─────────────────────────────────────────────────────────────
print(SEP)
print('  IN-SAMPLE RESULTS')
print(SEP)
print(f'  {"Metric":<25}  {"Original":>12}  {"+ 50-DMA Filter":>15}  {"Delta":>10}')
print(sep)
metrics_is = [
    ('CAGR (%)',           is_original['cagr'],    is_filtered['cagr']),
    ('Sharpe Ratio',       is_original['sharpe'],  is_filtered['sharpe']),
    ('Max Drawdown (%)',   is_original['max_dd'],  is_filtered['max_dd']),
    ('Win Rate (%)',       is_original['wr'],      is_filtered['wr']),
    ('Total Trades',       is_original['trades'],  is_filtered['trades']),
    ('Profit Factor',      is_original['pf'],      is_filtered['pf']),
    ('Turnover (%/yr)',    is_original['turnover'],is_filtered['turnover']),
    ('SL Exits',           is_original['sl_exits'],is_filtered['sl_exits']),
    ('Rebal Exits',        is_original['rebal_exits'], is_filtered['rebal_exits']),
]
for label, orig, filt in metrics_is:
    delta = filt - orig
    sign = '+' if delta > 0 else ''
    if label == 'Max Drawdown (%)':
        sign = '' if delta > 0 else ''  # lower DD is better
    print(f'  {label:<25}  {orig:>12.2f}  {filt:>15.2f}  {sign}{delta:>9.2f}')

print(f'\n{SEP}')
print('  OUT-OF-SAMPLE RESULTS')
print(SEP)
print(f'  {"Metric":<25}  {"Original":>12}  {"+ 50-DMA Filter":>15}  {"Delta":>10}')
print(sep)
metrics_oos = [
    ('CAGR (%)',           oos_original['cagr'],    oos_filtered['cagr']),
    ('Sharpe Ratio',       oos_original['sharpe'],  oos_filtered['sharpe']),
    ('Max Drawdown (%)',   oos_original['max_dd'],  oos_filtered['max_dd']),
    ('Win Rate (%)',       oos_original['wr'],      oos_filtered['wr']),
    ('Total Trades',       oos_original['trades'],  oos_filtered['trades']),
    ('Profit Factor',      oos_original['pf'],      oos_filtered['pf']),
    ('Turnover (%/yr)',    oos_original['turnover'],oos_filtered['turnover']),
    ('SL Exits',           oos_original['sl_exits'],oos_filtered['sl_exits']),
    ('Rebal Exits',        oos_original['rebal_exits'], oos_filtered['rebal_exits']),
    ('Final Value (Rs)',   oos_original['final_value'], oos_filtered['final_value']),
]
for label, orig, filt in metrics_oos:
    delta = filt - orig
    sign = '+' if delta > 0 else ''
    print(f'  {label:<25}  {orig:>12.2f}  {filt:>15.2f}  {sign}{delta:>9.2f}')

print(f'\n  Nifty OOS CAGR: {NIFTY_OOS_CAGR:+.1f}%')
print(f'  Original beats Nifty: {"YES" if oos_original["cagr"] > NIFTY_OOS_CAGR else "NO"}')
print(f'  Filtered beats Nifty: {"YES" if oos_filtered["cagr"] > NIFTY_OOS_CAGR else "NO"}')

# ── Verdict ───────────────────────────────────────────────────────────────────
print(f'\n{SEP}')
print('  VERDICT')
print(SEP)

cagr_better = oos_filtered['cagr'] > oos_original['cagr']
sharpe_better = oos_filtered['sharpe'] > oos_original['sharpe']
dd_better = oos_filtered['max_dd'] < oos_original['max_dd']
wr_better = oos_filtered['wr'] > oos_original['wr']
sl_fewer = oos_filtered['sl_exits'] <= oos_original['sl_exits']

improvements = sum([cagr_better, sharpe_better, dd_better, wr_better, sl_fewer])

print(f'  CAGR improved:        {"YES" if cagr_better else "NO"} ({oos_original["cagr"]:+.2f}% -> {oos_filtered["cagr"]:+.2f}%)')
print(f'  Sharpe improved:      {"YES" if sharpe_better else "NO"} ({oos_original["sharpe"]:.3f} -> {oos_filtered["sharpe"]:.3f})')
print(f'  Max DD reduced:       {"YES" if dd_better else "NO"} ({oos_original["max_dd"]:.1f}% -> {oos_filtered["max_dd"]:.1f}%)')
print(f'  Win Rate improved:    {"YES" if wr_better else "NO"} ({oos_original["wr"]:.1f}% -> {oos_filtered["wr"]:.1f}%)')
print(f'  Fewer SL exits:       {"YES" if sl_fewer else "NO"} ({oos_original["sl_exits"]} -> {oos_filtered["sl_exits"]})')

print()
if improvements >= 3:
    print(f'  RECOMMENDATION: ADOPT 50-DMA filter. {improvements}/5 OOS metrics improved.')
    print(f'  The filter reduces momentum-crash entries without changing core RS/EP weights.')
elif improvements >= 2:
    print(f'  RECOMMENDATION: CAUTIOUS ADOPT. {improvements}/5 metrics improved.')
    print(f'  Monitor for 1 rebalance cycle before committing.')
else:
    print(f'  RECOMMENDATION: DO NOT ADOPT. Only {improvements}/5 metrics improved.')
    print(f'  The 50-DMA filter does not help in this backtest period.')
    print(f'  Consider removing it from daily_ops_report.py.')

print(SEP)
