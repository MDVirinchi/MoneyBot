"""
research_v2.py  --  Strategy improvement research
===================================================
Tests 3 enhancements against the RS60/EP40 baseline on identical OOS data.

Enhancement 1: Rank-weighted position sizing
  Instead of equal weight, allocate more capital to higher-ranked stocks.
  Top-ranked stock gets 2x the allocation of the lowest-ranked in the portfolio.

Enhancement 2: Trailing stop (replaces fixed 10% SL)
  Trails 12% below the highest close seen since entry.
  Locks in profits on winners instead of giving back all gains.

Enhancement 3: Top-5 concentrated (fewer, stronger picks)
  Instead of spreading across 10 stocks, concentrate in the 5 highest-scored.
  Higher conviction = larger positions per stock.

Baseline: RS60/EP40, Top-10, equal weight, fixed 10% SL, Policy-C (bull_flat)
"""

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

# ── Fetch data ────────────────────────────────────────────────────────────────
print('Fetching 5y data...')
price_data = {}; valid = []
for ticker, sym in STOCKS:
    try:
        df = yf.Ticker(ticker).history(period='5y', interval='1d', auto_adjust=True)
        if not df.empty:
            d = {str(ts.date()): {'open': float(r['Open']),
                                   'close': float(r['Close']),
                                   'vol':   float(r.get('Volume', 0) or 0)}
                 for ts, r in df.iterrows()}
            if len(d) >= 300:
                price_data[sym] = d; valid.append(sym)
    except Exception: pass
    time.sleep(0.22)

nifty_raw = {}
try:
    df = yf.Ticker('^NSEI').history(period='5y', interval='1d', auto_adjust=True)
    nifty_raw = {str(ts.date()): float(r['Close']) for ts, r in df.iterrows()}
except Exception: pass

all_dates = sorted(nifty_raw.keys())
N = len(all_dates)
IS_END    = int(N * 0.6)
IS_DATES  = all_dates[:IS_END]
OOS_DATES = all_dates[IS_END:]

n_start = nifty_raw.get(OOS_DATES[0], 1)
n_end   = nifty_raw.get(OOS_DATES[-1], 1)
NIFTY_OOS_CAGR = ((n_end / n_start) ** (252 / len(OOS_DATES)) - 1) * 100

print(f'Universe: {len(valid)} stocks  |  {all_dates[0]} to {all_dates[-1]}')
print(f'OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}  ({len(OOS_DATES)}d)  Nifty OOS CAGR={NIFTY_OOS_CAGR:+.1f}%\n')

# ── Nifty DMA / regime ────────────────────────────────────────────────────────
nifty_closes = [(d, nifty_raw[d]) for d in all_dates]
nifty_dma = {}
for idx, (d, c) in enumerate(nifty_closes):
    dma50  = sum(v for _, v in nifty_closes[max(0, idx-49):idx+1]) / min(idx+1, 50)
    dma200 = sum(v for _, v in nifty_closes[max(0, idx-199):idx+1]) / min(idx+1, 200)
    nifty_dma[d] = {'close': c, 'dma50': dma50, 'dma200': dma200}

def regime(date):
    r = nifty_dma.get(date)
    if not r: return 'Bull'
    c, d50, d200 = r['close'], r['dma50'], r['dma200']
    if c < d200:   return 'Bear'
    if d50 <= d200: return 'Flat'
    return 'Bull'

# ── Factor engine ─────────────────────────────────────────────────────────────
_raw_cache = {}

def get_raw(gi):
    if gi in _raw_cache: return _raw_cache[gi]
    if gi < 72: return {}
    dn  = all_dates[gi]
    nc  = nifty_raw.get(dn)
    np_ = nifty_raw.get(all_dates[gi-63]) if gi >= 63 else None
    raw_rs = {}; raw_ep = {}
    for sym in valid:
        c  = price_data[sym]
        sd = [d for d in all_dates[max(0, gi-74):gi+1] if d in c]
        if len(sd) < 50: continue
        if nc and np_:
            cn = c.get(dn, {}).get('close')
            cp = c.get(all_dates[gi-63], {}).get('close')
            if cn and cp:
                raw_rs[sym] = (cn/cp - 1)*100 - (nc/np_ - 1)*100
        ed    = sd[-63:]
        evols = [c[d]['vol'] for d in ed if c[d]['vol'] > 0]
        av    = sum(evols) / len(evols) if evols else 0
        ep    = 0.0
        for j in range(1, len(ed)):
            cj  = c.get(ed[j])
            cjm = c.get(ed[j-1])
            if not (cj and cjm and cjm['close'] > 0): continue
            dr = cj['close'] / cjm['close'] - 1
            if dr > 0.02 and av > 0 and cj['vol'] > 1.5 * av:
                ep = max(ep, dr * 100)
        raw_ep[sym] = ep
    result = {'rs': raw_rs, 'ep': raw_ep}
    _raw_cache[gi] = result
    return result

def composite(gi):
    raw = get_raw(gi)
    if not raw: return {}
    def pr(d):
        items = sorted(d.items(), key=lambda x: x[1]); n = len(items)
        return {s: (r+1)/n*100 for r, (s, _) in enumerate(items)}
    rnks = {}
    if raw['rs']: rnks['rs'] = pr(raw['rs'])
    if raw['ep']: rnks['ep'] = pr(raw['ep'])
    if not rnks: return {}
    syms = set.intersection(*[set(rnks[f].keys()) for f in rnks])
    return {s: W_RS * rnks['rs'].get(s, 0) + W_EP * rnks['ep'].get(s, 0) for s in syms}

print('Pre-computing factors...')
gi = 72
while gi < N:
    get_raw(gi); gi += REBAL_DAYS
print(f'Cached {len(_raw_cache)} rebalance points.\n')

# ── Stats helper ──────────────────────────────────────────────────────────────
def stats(trades, equity):
    if not trades:
        return {'pf': 0, 'cagr': -100, 'sharpe': 0, 'max_dd': 0,
                'trades': 0, 'wr': 0, 'avg_win': 0, 'avg_loss': 0}
    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp = sum(t['pnl'] for t in wins)
    gl = abs(sum(t['pnl'] for t in losses))
    pf = gp / gl if gl > 0 else (1.5 if gp > 0 else 0)
    yrs  = max(len(equity) / 252, 0.1)
    fv   = equity[-1] if equity else CAPITAL
    cagr = ((fv / CAPITAL) ** (1/yrs) - 1) * 100 if fv > 0 else -100
    dr   = [(equity[k] - equity[k-1]) / equity[k-1]
            for k in range(1, len(equity)) if equity[k-1] > 0]
    sharpe = (statistics.mean(dr) / statistics.stdev(dr) * math.sqrt(252)
              if len(dr) > 2 and statistics.stdev(dr) > 0 else 0)
    peak = CAPITAL; max_dd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd
    avg_win  = (sum(t['ret'] for t in wins)   / len(wins))  if wins   else 0
    avg_loss = (sum(t['ret'] for t in losses) / len(losses)) if losses else 0
    return {'pf': round(pf, 3), 'cagr': round(cagr, 1), 'sharpe': round(sharpe, 3),
            'max_dd': round(max_dd, 1), 'trades': len(trades),
            'wr': round(len(wins)/len(trades)*100, 1),
            'avg_win': round(avg_win, 2), 'avg_loss': round(avg_loss, 2)}

# ── Simulator ─────────────────────────────────────────────────────────────────
def run_sim(date_range,
            top_n=10,
            sl_pct=10.0,
            trailing_stop=False,
            trail_pct=12.0,
            rank_weighted=False):
    """
    top_n         : number of stocks to hold
    sl_pct        : fixed stop-loss % below entry (used if trailing_stop=False)
    trailing_stop : if True, use trailing stop at trail_pct% below peak close
    rank_weighted : if True, weight allocations by composite rank score
    """
    cash = CAPITAL; pos = {}; trades = []; equity = []
    trail_highs = {}   # sym -> highest close seen since entry
    last_rebal  = -999

    def gc(s, d): return price_data[s].get(d, {}).get('close')
    def go(s, d): return price_data[s].get(d, {}).get('open')

    date_to_gi = {d: all_dates.index(d) for d in date_range if d in all_dates}

    for idx, date in enumerate(date_range):
        gi = date_to_gi.get(date)
        if gi is None or gi < 72:
            equity.append(cash); continue

        # Policy-C: Bear = cash
        reg = regime(date)
        if reg == 'Bear':
            for sym in list(pos):
                nd  = date_range[idx+1] if idx+1 < len(date_range) else date
                fp  = (go(sym, nd) or gc(sym, date) or pos[sym]['ep']) * (1 - SLIP)
                p   = pos.pop(sym); trail_highs.pop(sym, None)
                ev  = p['qty'] * fp
                cost = BROKERAGE + ev*STT + ev*EXCHANGE
                cash += ev - cost
                trades.append({'pnl': (fp - p['ep'])*p['qty'] - cost,
                                'ret': (fp/p['ep'] - 1)*100, 'exit': 'Regime'})
            equity.append(cash); continue

        # ── Stop-loss (fixed or trailing) ─────────────────────────────────────
        for sym in list(pos):
            curr = gc(sym, date)
            if curr is None: continue

            if trailing_stop:
                # Update trailing high
                if sym not in trail_highs:
                    trail_highs[sym] = pos[sym]['ep']
                if curr > trail_highs[sym]:
                    trail_highs[sym] = curr
                stop_level = trail_highs[sym] * (1 - trail_pct/100)
                triggered  = curr <= stop_level
            else:
                stop_level = pos[sym]['ep'] * (1 - sl_pct/100)
                triggered  = curr <= stop_level

            if triggered:
                p    = pos.pop(sym); trail_highs.pop(sym, None)
                fill = curr * (1 - SLIP)
                ev   = p['qty'] * fill
                cost = BROKERAGE + ev*STT + ev*EXCHANGE
                cash += ev - cost
                trades.append({'pnl': (fill - p['ep'])*p['qty'] - cost,
                                'ret': (fill/p['ep'] - 1)*100,
                                'exit': 'Trail' if trailing_stop else 'SL'})

        # ── Rebalance ─────────────────────────────────────────────────────────
        if idx - last_rebal >= REBAL_DAYS:
            last_rebal = idx
            comp = composite(gi)
            ranked = sorted(comp.items(), key=lambda x: -x[1])
            tgt_ranked = ranked[:top_n]   # list of (sym, score) in rank order
            tgt = {s for s, _ in tgt_ranked}

            # Exit positions no longer in target
            for sym in list(pos):
                if sym not in tgt:
                    nd   = date_range[idx+1] if idx+1 < len(date_range) else date
                    fp   = (go(sym, nd) or gc(sym, date) or pos[sym]['ep']) * (1 - SLIP)
                    p    = pos.pop(sym); trail_highs.pop(sym, None)
                    ev   = p['qty'] * fp
                    cost = BROKERAGE + ev*STT + ev*EXCHANGE
                    cash += ev - cost
                    trades.append({'pnl': (fp - p['ep'])*p['qty'] - cost,
                                    'ret': (fp/p['ep'] - 1)*100, 'exit': 'Rebal'})

            new = [(s, sc) for s, sc in tgt_ranked if s not in pos]
            avail = cash * 0.95

            if new and avail > 10_000:
                if rank_weighted and len(new) > 1:
                    # Allocate proportional to rank score (min weight = 0.5x, max = 1.5x)
                    scores = [sc for _, sc in new]
                    min_sc = min(scores); max_sc = max(scores)
                    rng    = max_sc - min_sc if max_sc > min_sc else 1
                    weights = [0.5 + (sc - min_sc) / rng for _, sc in new]
                    total_w = sum(weights)
                    allocs  = [avail * w / total_w for w in weights]
                else:
                    # Equal weight
                    alloc_each = min(avail / max(len(new), 1), CAPITAL / top_n)
                    allocs     = [alloc_each] * len(new)

                for (sym, _), alloc in zip(new, allocs):
                    nd   = date_range[idx+1] if idx+1 < len(date_range) else date
                    fpd  = go(sym, nd) or gc(sym, date)
                    if not fpd: continue
                    fill = fpd * (1 + SLIP)
                    qty  = max(1, int(alloc / fill))
                    cost = BROKERAGE + qty*fill*EXCHANGE
                    if cash >= qty*fill + cost:
                        cash -= qty*fill + cost
                        pos[sym] = {'qty': qty, 'ep': fill}
                        trail_highs[sym] = fill

        fv = cash + sum(p['qty'] * (gc(s, date) or p['ep']) for s, p in pos.items())
        equity.append(fv)

    # Close all at end
    for s, p in list(pos.items()):
        fp   = (gc(s, date_range[-1]) or p['ep']) * (1 - SLIP)
        ev   = p['qty'] * fp
        cost = BROKERAGE + ev*STT + ev*EXCHANGE
        cash += ev - cost
        trades.append({'pnl': (fp - p['ep'])*p['qty'] - cost,
                        'ret': (fp/p['ep'] - 1)*100, 'exit': 'EoP'})

    return stats(trades, equity)


# ══════════════════════════════════════════════════════════════════════════════
# RUN ALL EXPERIMENTS
# ══════════════════════════════════════════════════════════════════════════════

SEP = '=' * 90
sep = '-' * 90

print(SEP)
print('  STRATEGY RESEARCH v2  --  Testing 3 enhancements vs baseline')
print(f'  Nifty OOS CAGR benchmark: {NIFTY_OOS_CAGR:+.1f}%')
print(SEP)

experiments = [
    # (label,                        top_n, sl,   trail, trail_pct, rank_w)
    ('Baseline (current system)',      10,   10.0, False, 12.0,     False),
    ('E1: Rank-weighted sizing',       10,   10.0, False, 12.0,     True),
    ('E2: Trailing stop 12%',          10,   10.0, True,  12.0,     False),
    ('E3: Concentrated Top-5',          5,   10.0, False, 12.0,     False),
    ('E4: E1 + E2 combined',           10,   10.0, True,  12.0,     True),
    ('E5: E2 + E3 combined',            5,   10.0, True,  12.0,     False),
    ('E6: All three combined',          5,   10.0, True,  12.0,     True),
]

print(f'\n  {"Experiment":<35}  {"OOS CAGR":>9}  {"vs Base":>8}  {"vs Nifty":>9}  '
      f'{"PF":>6}  {"MaxDD":>7}  {"Sharpe":>7}  {"WR":>6}  {"Trades":>7}')
print(sep)

baseline_cagr = None
results = []

for label, top_n, sl, trail, tpct, rankw in experiments:
    r_oos = run_sim(OOS_DATES, top_n=top_n, sl_pct=sl,
                    trailing_stop=trail, trail_pct=tpct, rank_weighted=rankw)
    results.append((label, r_oos))

    if baseline_cagr is None:
        baseline_cagr = r_oos['cagr']

    vs_base  = r_oos['cagr'] - baseline_cagr
    vs_nifty = r_oos['cagr'] - NIFTY_OOS_CAGR
    beat_b   = '+' if vs_base  > 0 else ''
    beat_n   = '*' if vs_nifty > 0 else ' '

    print(f'  {label:<35}  {r_oos["cagr"]:>+8.1f}%  {beat_b}{vs_base:>+6.1f}pp'
          f'  {vs_nifty:>+7.1f}pp{beat_n}'
          f'  {r_oos["pf"]:>6.3f}  {r_oos["max_dd"]:>6.1f}%'
          f'  {r_oos["sharpe"]:>7.3f}  {r_oos["wr"]:>5.1f}%  {r_oos["trades"]:>7}')

print(sep)
print('  * = beats Nifty')

# ── Best combination ──────────────────────────────────────────────────────────
best = max(results[1:], key=lambda x: x[1]['sharpe'])
print(f'\n  Best OOS Sharpe (risk-adjusted): {best[0]}')
best_cagr = max(results[1:], key=lambda x: x[1]['cagr'])
print(f'  Best OOS CAGR (raw return):      {best_cagr[0]}')
best_dd = min(results[1:], key=lambda x: x[1]['max_dd'])
print(f'  Lowest MaxDD (safety):           {best_dd[0]}')

# ── Detailed breakdown of best vs baseline ────────────────────────────────────
print(f'\n{SEP}')
print(f'  DETAILED COMPARISON: Baseline vs Best CAGR ({best_cagr[0]})')
print(SEP)
b = results[0][1]
e = best_cagr[1]
rows = [
    ('OOS CAGR',         f'{b["cagr"]:+.1f}%',    f'{e["cagr"]:+.1f}%'),
    ('Profit Factor',    f'{b["pf"]:.3f}',         f'{e["pf"]:.3f}'),
    ('Max Drawdown',     f'{b["max_dd"]:.1f}%',    f'{e["max_dd"]:.1f}%'),
    ('Sharpe Ratio',     f'{b["sharpe"]:.3f}',     f'{e["sharpe"]:.3f}'),
    ('Win Rate',         f'{b["wr"]:.1f}%',        f'{e["wr"]:.1f}%'),
    ('Total Trades',     f'{b["trades"]}',          f'{e["trades"]}'),
    ('Avg Win %',        f'{b["avg_win"]:.2f}%',   f'{e["avg_win"]:.2f}%'),
    ('Avg Loss %',       f'{b["avg_loss"]:.2f}%',  f'{e["avg_loss"]:.2f}%'),
]
print(f'  {"Metric":<20}  {"Baseline":>12}  {"Best":>12}  {"Change":>10}')
print(f'  {"-"*56}')
for name, bv, ev in rows:
    print(f'  {name:<20}  {bv:>12}  {ev:>12}')

print(f'\n  Nifty OOS CAGR for reference: {NIFTY_OOS_CAGR:+.1f}%')

# ── Verdict ───────────────────────────────────────────────────────────────────
print(f'\n{SEP}')
print('  VERDICT')
print(SEP)

winners = [(l, r) for l, r in results[1:] if r['cagr'] > baseline_cagr]
nifty_beaters = [(l, r) for l, r in results[1:] if r['cagr'] > NIFTY_OOS_CAGR]

print(f'  Enhancements that beat baseline:  {len(winners)}/6')
print(f'  Enhancements that beat Nifty:     {len(nifty_beaters)}/6')
print()

for label, r in results[1:]:
    vs_b = r['cagr'] - baseline_cagr
    status = 'IMPROVEMENT' if vs_b > 0.5 else ('NEUTRAL' if vs_b > -0.5 else 'WORSE')
    print(f'  {status:<12}  {label}  ({vs_b:+.1f}pp vs baseline)')

print(f'\n  RECOMMENDATION: ', end='')
if best_cagr[1]['cagr'] > baseline_cagr + 1.0:
    print(f'Adopt {best_cagr[0]}')
    print(f'  Expected improvement: {best_cagr[1]["cagr"] - baseline_cagr:+.1f}pp CAGR')
else:
    print('No enhancement materially improves the strategy.')
    print('  The baseline RS60/EP40 is already near-optimal for this universe.')

print(f'\n{"="*90}\n')
