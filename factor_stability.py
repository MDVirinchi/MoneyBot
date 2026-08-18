"""
factor_stability.py  --  RS / EP Weight Stability Analysis
============================================================
Sweep RS weight 0->100 in steps of 10 (EP = 100 - RS).
For every weight combination run identical walk-forward.
Report IS and OOS: PF, CAGR, Sharpe, trades.
Also compute rank stability: Spearman correlation of composite
rankings between consecutive rebalance dates (OOS window only).

High rank stability = rankings move slowly = low turnover = durable signal.
A broad OOS plateau = robust edge. A narrow spike = curve fit.
"""

import time, math, statistics, warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

REBAL_DAYS = 10; TOP_N = 10; SL_PCT = 10.0
BROKERAGE = 20.0; STT = 0.001; EXCHANGE = 0.0000345; SLIP = 0.002
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

# ── Fetch ──────────────────────────────────────────────────────────────────────
print('Fetching data...')
price_data = {}; valid = []
for ticker, sym in STOCKS:
    try:
        df = yf.Ticker(ticker).history(period='5y', interval='1d', auto_adjust=True)
        if not df.empty:
            d = {str(ts.date()): {'open':  float(r['Open']),
                                   'close': float(r['Close']),
                                   'vol':   float(r.get('Volume', 0) or 0)}
                 for ts, r in df.iterrows()}
            if len(d) >= 300:
                price_data[sym] = d; valid.append(sym)
    except Exception: pass
    time.sleep(0.22)

nifty = {}
try:
    df = yf.Ticker('^NSEI').history(period='5y', interval='1d', auto_adjust=True)
    nifty = {str(ts.date()): {'close': float(r['Close'])} for ts, r in df.iterrows()}
except Exception: pass

all_dates = sorted(nifty.keys())
N = len(all_dates)
IS_END = int(N * 0.6)   # 60% IS, 40% OOS
print(f'Universe: {len(valid)} stocks  |  {all_dates[0]} to {all_dates[-1]}  ({N} days)')
print(f'IS: {all_dates[0]} to {all_dates[IS_END-1]}  |  OOS: {all_dates[IS_END]} to {all_dates[-1]}\n')

# ── Raw factor computation (cached per date) ───────────────────────────────────
_raw_cache = {}

def get_raw(i):
    if i in _raw_cache: return _raw_cache[i]
    if i < 72: return {}
    dn = all_dates[i]
    nc = nifty.get(dn, {}).get('close')
    np_ = nifty.get(all_dates[i-63], {}).get('close') if i >= 63 else None
    raw_rs = {}; raw_ep = {}
    for sym in valid:
        c = price_data[sym]
        sd = [d for d in all_dates[max(0,i-74):i+1] if d in c]
        if len(sd) < 50: continue
        if nc and np_:
            cn = c.get(dn,{}).get('close'); cp = c.get(all_dates[i-63],{}).get('close')
            if cn and cp: raw_rs[sym] = (cn/cp-1)*100 - (nc/np_-1)*100
        ed = sd[-63:]
        evols = [c[d]['vol'] for d in ed if c[d]['vol'] > 0]
        av = sum(evols)/len(evols) if evols else 0
        ep = 0.0
        for j in range(1, len(ed)):
            cj = c.get(ed[j]); cjm = c.get(ed[j-1])
            if not (cj and cjm and cjm['close'] > 0): continue
            dr = cj['close']/cjm['close'] - 1
            if dr > 0.02 and av > 0 and cj['vol'] > 1.5*av:
                ep = max(ep, dr*100)
        raw_ep[sym] = ep
    result = {'rs': raw_rs, 'ep': raw_ep}
    _raw_cache[i] = result
    return result

def get_composite(i, w_rs, w_ep):
    raw = get_raw(i)
    if not raw: return {}
    raw_rs = raw['rs']; raw_ep = raw['ep']
    def prank(d):
        items = sorted(d.items(), key=lambda x: x[1])
        n = len(items)
        return {s: (r+1)/n*100 for r,(s,_) in enumerate(items)}
    ranks = {}
    if w_rs > 0 and raw_rs: ranks['rs'] = prank(raw_rs)
    if w_ep > 0 and raw_ep: ranks['ep'] = prank(raw_ep)
    if not ranks: return {}
    active = list(ranks.keys())
    syms = set.intersection(*[set(ranks[f].keys()) for f in active])
    tw = sum({'rs':w_rs,'ep':w_ep}[f] for f in active)
    return {s: sum({'rs':w_rs,'ep':w_ep}[f]*ranks[f][s] for f in active)/tw for s in syms}

# ── Spearman correlation helper ────────────────────────────────────────────────
def spearman(a_dict, b_dict):
    common = sorted(set(a_dict) & set(b_dict))
    if len(common) < 5: return None
    n = len(common)
    a_vals = [a_dict[s] for s in common]
    b_vals = [b_dict[s] for s in common]
    def rank_list(vals):
        idx = sorted(range(n), key=lambda k: vals[k])
        rnk = [0]*n
        for r,k in enumerate(idx): rnk[k] = r+1
        return rnk
    ra = rank_list(a_vals); rb = rank_list(b_vals)
    d2 = sum((ra[k]-rb[k])**2 for k in range(n))
    return 1 - 6*d2/(n*(n*n-1))

# ── Portfolio simulation ───────────────────────────────────────────────────────
def run_portfolio(date_range, w_rs, w_ep):
    cash = CAPITAL; pos = {}; trades = []; equity = []
    last_rebal = -999

    def gc(s, d): return price_data[s].get(d, {}).get('close')
    def go(s, d): return price_data[s].get(d, {}).get('open')

    dates = date_range
    # map dates to global indices for composite lookup
    date_to_gi = {d: all_dates.index(d) for d in dates if d in all_dates}

    for idx, date in enumerate(dates):
        gi = date_to_gi.get(date)
        if gi is None or gi < 72:
            equity.append(cash); continue

        # SL check
        for sym in list(pos):
            curr = gc(sym, date)
            if curr and curr <= pos[sym]['ep'] * (1 - SL_PCT/100):
                p = pos.pop(sym); fill = curr*(1-SLIP)
                ev = p['qty']*fill; cost = BROKERAGE+ev*STT+ev*EXCHANGE
                cash += ev-cost
                trades.append({'pnl':(fill-p['ep'])*p['qty']-cost,
                                'ret':(fill/p['ep']-1)*100})

        # Rebalance
        if idx - last_rebal >= REBAL_DAYS:
            last_rebal = idx
            comp = get_composite(gi, w_rs, w_ep)
            tgt  = {s for s,_ in sorted(comp.items(), key=lambda x:-x[1])[:TOP_N]}
            for sym in list(pos):
                if sym not in tgt:
                    nd = dates[idx+1] if idx+1 < len(dates) else date
                    fp = (go(sym, nd) or gc(sym, date) or pos[sym]['ep'])*(1-SLIP)
                    p  = pos.pop(sym); ev = p['qty']*fp
                    cost = BROKERAGE+ev*STT+ev*EXCHANGE; cash += ev-cost
                    trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,
                                   'ret':(fp/p['ep']-1)*100})
            new = [s for s in tgt if s not in pos]
            if new and cash > 10_000:
                alloc = min(cash*0.95/max(len(new),1), CAPITAL/TOP_N)
                for sym in new:
                    nd = dates[idx+1] if idx+1 < len(dates) else date
                    fpd = go(sym, nd) or gc(sym, date)
                    if not fpd: continue
                    fill = fpd*(1+SLIP); qty = max(1, int(alloc/fill))
                    cost = BROKERAGE+qty*fill*EXCHANGE
                    if cash >= qty*fill+cost:
                        cash -= qty*fill+cost
                        pos[sym] = {'qty':qty,'ep':fill}

        fv = cash + sum(p['qty']*(gc(s,date) or p['ep']) for s,p in pos.items())
        equity.append(fv)

    for s,p in list(pos.items()):
        fp = (gc(s, dates[-1]) or p['ep'])*(1-SLIP)
        ev = p['qty']*fp; cost = BROKERAGE+ev*STT+ev*EXCHANGE; cash += ev-cost
        trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'ret':(fp/p['ep']-1)*100})

    if not trades:
        return {'pf':0,'cagr':-100,'sharpe':0,'trades':0,'wr':0,'equity':equity}
    wins   = [t for t in trades if t['pnl']>0]
    losses = [t for t in trades if t['pnl']<=0]
    gp = sum(t['pnl'] for t in wins); gl = abs(sum(t['pnl'] for t in losses))
    pf = gp/gl if gl>0 else (1.5 if gp>0 else 0)
    yrs = max(len(dates)/252, 0.1)
    fv  = equity[-1] if equity else CAPITAL
    cagr = ((fv/CAPITAL)**(1/yrs)-1)*100 if fv>0 else -100
    dr = [(equity[k]-equity[k-1])/equity[k-1] for k in range(1,len(equity)) if equity[k-1]>0]
    sharpe = statistics.mean(dr)/statistics.stdev(dr)*math.sqrt(252) if len(dr)>2 and statistics.stdev(dr)>0 else 0
    return {'pf':round(pf,3),'cagr':round(cagr,1),'sharpe':round(sharpe,3),
            'trades':len(trades),'wr':round(len(wins)/len(trades)*100,1),'equity':equity}

# ── Rank stability computation ─────────────────────────────────────────────────
def rank_stability(w_rs, w_ep):
    """
    Mean Spearman correlation between composite scores at consecutive
    rebalance dates (OOS window only).
    High = rankings are stable across rebalances = durable signal.
    """
    oos_dates = all_dates[IS_END:]
    corrs = []
    prev_comp = None
    prev_date_idx = None
    i = IS_END
    while i < N:
        comp = get_composite(i, w_rs, w_ep)
        if comp and prev_comp:
            r = spearman(prev_comp, comp)
            if r is not None: corrs.append(r)
        if comp:
            prev_comp = comp
        i += REBAL_DAYS
    return round(statistics.mean(corrs), 3) if corrs else 0.0

# ── Pre-compute raw factor cache for all rebal dates ──────────────────────────
print('Pre-computing factor scores for all rebalance dates...')
i = 72
while i < N:
    get_raw(i)
    i += REBAL_DAYS
print(f'Cached {len(_raw_cache)} rebalance points.\n')

# ── Sweep ──────────────────────────────────────────────────────────────────────
is_dates  = all_dates[:IS_END]
oos_dates = all_dates[IS_END:]

# Nifty OOS return for reference
n_start = nifty.get(oos_dates[0],{}).get('close',1)
n_end   = nifty.get(oos_dates[-1],{}).get('close',1)
nifty_oos_cagr = ((n_end/n_start)**(252/len(oos_dates))-1)*100 if n_start>0 else 0

SWEEP = list(range(0, 101, 10))   # 0, 10, 20, ... 100

SEP = '=' * 126
sep = '-' * 126

print('Running sweep (11 weight combinations x IS + OOS)...')
print()

results = []
for rs_pct in SWEEP:
    ep_pct = 100 - rs_pct
    w_rs = rs_pct/100; w_ep = ep_pct/100
    tag = f'RS={rs_pct:>3}  EP={ep_pct:>3}'
    m_is  = run_portfolio(is_dates,  w_rs, w_ep)
    m_oos = run_portfolio(oos_dates, w_rs, w_ep)
    stab  = rank_stability(w_rs, w_ep)
    decay = round(m_is['pf'] - m_oos['pf'], 3)
    results.append({'rs':rs_pct,'ep':ep_pct,'tag':tag,
                    'is':m_is,'oos':m_oos,'stab':stab,'decay':decay})
    print(f'  {tag}  IS PF={m_is["pf"]:.3f}  OOS PF={m_oos["pf"]:.3f}  '
          f'OOS CAGR={m_oos["cagr"]:>+5.1f}%  stability={stab:.3f}')

# ── Full table ─────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  FACTOR STABILITY SWEEP  --  RS=0..100  EP=100..0  (step 10)')
print(f'  Universe: {len(valid)} stocks  |  Top-N={TOP_N}  Rebal={REBAL_DAYS}d  SL={SL_PCT:.0f}%  |  Nifty OOS CAGR: {nifty_oos_cagr:+.1f}%')
print(SEP)
print(f'  {"Weights":<16}  {"IS PF":>7}  {"IS CAGR":>8}  {"IS Sh":>7}  '
      f'{"OOS PF":>7}  {"OOS CAGR":>9}  {"OOS Sh":>8}  '
      f'{"Decay":>7}  {"Trades":>7}  {"WR%":>6}  {"RankStab":>9}')
print(sep)

oos_pfs = [r['oos']['pf'] for r in results]
best_pf = max(oos_pfs)

for r in results:
    marker = '  <-- BEST OOS PF' if r['oos']['pf'] == best_pf else ''
    beat   = ' *' if r['oos']['cagr'] > nifty_oos_cagr else '  '
    print(f'  {r["tag"]}  '
          f'{r["is"]["pf"]:>7.3f}  {r["is"]["cagr"]:>+7.1f}%  {r["is"]["sharpe"]:>7.3f}  '
          f'{r["oos"]["pf"]:>7.3f}  {r["oos"]["cagr"]:>+8.1f}%{beat}  '
          f'{r["oos"]["sharpe"]:>8.3f}  '
          f'{r["decay"]:>+6.3f}  {r["oos"]["trades"]:>7}  '
          f'{r["oos"]["wr"]:>5.1f}%  {r["stab"]:>9.3f}{marker}')

print(sep)
print(f'  {"Nifty B&H":16}  {"":>7}  {"":>8}  {"":>7}  {"1.000":>7}  '
      f'{nifty_oos_cagr:>+8.1f}%    {"":>8}  {"":>7}')

# ── Plateau analysis ───────────────────────────────────────────────────────────
oos_pos  = [r for r in results if r['oos']['pf'] > 1.0]
oos_beat = [r for r in results if r['oos']['cagr'] > nifty_oos_cagr]

print()
print(SEP)
print('  PLATEAU ANALYSIS  --  Width of profitable region')
print(SEP)
pos_str = ", ".join("RS="+str(r["rs"]) for r in oos_pos)
pos_str = ", ".join("RS="+str(r["rs"]) for r in oos_pos)
print(f"  Combinations with OOS PF > 1.0      : {len(oos_pos)}/11  ({pos_str})")
beat_str = ", ".join("RS="+str(r["rs"]) for r in oos_beat)
print(f"  Combinations beating Nifty CAGR      : {len(oos_beat)}/11  ({beat_str})")
if len(oos_pos) >= 5:
    print('  Verdict: WIDE PLATEAU -- edge is robust across a broad weight range.')
elif len(oos_pos) >= 3:
    print('  Verdict: MODERATE PLATEAU -- edge exists but is weight-sensitive.')
else:
    print('  Verdict: NARROW SPIKE -- edge is concentrated; likely curve-fitted.')

# ── Rank stability table ───────────────────────────────────────────────────────
print()
print(SEP)
print('  RANK STABILITY  --  Mean Spearman corr of rankings between consecutive rebalances (OOS)')
print('  0.0 = completely random each period  |  1.0 = identical rankings every period')
print('  >0.6 = durable signal, low unforced turnover  |  <0.3 = noisy, high churn')
print(SEP)
print(f'  {"Weights":<16}  {"Rank Stability":>14}  {"Bar":}')
print(sep)
for r in results:
    s = r['stab']
    bar = '#' * int(s * 50)
    print(f'  {r["tag"]}  {s:>14.3f}  |{bar}')

# ── Decay profile ──────────────────────────────────────────────────────────────
print()
print(SEP)
print('  IS -> OOS DECAY PROFILE  --  Lower decay = more generalizable factor')
print(SEP)
print(f'  {"Weights":<16}  {"IS PF":>7}  {"OOS PF":>7}  {"Decay":>7}  {"Decay Bar"}')
print(sep)
max_decay = max(r['decay'] for r in results)
for r in results:
    d = r['decay']
    scaled = int((d/max(max_decay,0.001))*40) if d>0 else 0
    bar = '#'*scaled
    flag = '  <-- min decay' if d == min(r2['decay'] for r2 in results) else ''
    print(f'  {r["tag"]}  {r["is"]["pf"]:>7.3f}  {r["oos"]["pf"]:>7.3f}  '
          f'{d:>+6.3f}  |{bar}{flag}')

# ── OOS metric visualisation ──────────────────────────────────────────────────
print()
print(SEP)
print('  OOS PF ACROSS WEIGHT SWEEP  --  Visual')
print(SEP)
min_pf = min(r['oos']['pf'] for r in results)
max_pf = max(r['oos']['pf'] for r in results)
for r in results:
    v = r['oos']['pf']
    scaled = int(((v-min_pf)/(max_pf-min_pf+1e-9))*50)
    bar = '#'*scaled
    beat = ' *beats Nifty*' if r['oos']['cagr'] > nifty_oos_cagr else ''
    print(f'  {r["tag"]}  OOS PF {v:.3f}  |{bar}{beat}')

# ── Summary statistics ─────────────────────────────────────────────────────────
all_oos_pfs    = [r['oos']['pf']     for r in results]
all_oos_cagrs  = [r['oos']['cagr']   for r in results]
all_oos_stabs  = [r['stab']          for r in results]
all_oos_decays = [r['decay']         for r in results]

print()
print(SEP)
print('  SUMMARY STATISTICS')
print(SEP)
print(f'  OOS PF     --  mean: {statistics.mean(all_oos_pfs):.3f}  '
      f'stdev: {statistics.stdev(all_oos_pfs):.3f}  '
      f'min: {min(all_oos_pfs):.3f}  max: {max(all_oos_pfs):.3f}')
print(f'  OOS CAGR   --  mean: {statistics.mean(all_oos_cagrs):+.1f}%  '
      f'stdev: {statistics.stdev(all_oos_cagrs):.1f}%  '
      f'min: {min(all_oos_cagrs):+.1f}%  max: {max(all_oos_cagrs):+.1f}%')
print(f'  Rank Stab  --  mean: {statistics.mean(all_oos_stabs):.3f}  '
      f'stdev: {statistics.stdev(all_oos_stabs):.3f}  '
      f'min: {min(all_oos_stabs):.3f}  max: {max(all_oos_stabs):.3f}')
print(f'  IS-OOS Decay -- mean: {statistics.mean(all_oos_decays):+.3f}  '
      f'stdev: {statistics.stdev(all_oos_decays):.3f}  '
      f'min: {min(all_oos_decays):+.3f}  max: {max(all_oos_decays):+.3f}')
print()

# Find optimal weight by each metric
best_pf_r   = max(results, key=lambda r: r['oos']['pf'])
best_cagr_r = max(results, key=lambda r: r['oos']['cagr'])
best_stab_r = max(results, key=lambda r: r['stab'])
min_decay_r = min(results, key=lambda r: r['decay'])

print(f'  Best OOS PF      : RS={best_pf_r["rs"]:>3}/EP={best_pf_r["ep"]:>3}  '
      f'(PF={best_pf_r["oos"]["pf"]:.3f}  CAGR={best_pf_r["oos"]["cagr"]:+.1f}%)')
print(f'  Best OOS CAGR    : RS={best_cagr_r["rs"]:>3}/EP={best_cagr_r["ep"]:>3}  '
      f'(PF={best_cagr_r["oos"]["pf"]:.3f}  CAGR={best_cagr_r["oos"]["cagr"]:+.1f}%)')
print(f'  Most stable ranks: RS={best_stab_r["rs"]:>3}/EP={best_stab_r["ep"]:>3}  '
      f'(stability={best_stab_r["stab"]:.3f}  OOS PF={best_stab_r["oos"]["pf"]:.3f})')
print(f'  Min IS-OOS decay : RS={min_decay_r["rs"]:>3}/EP={min_decay_r["ep"]:>3}  '
      f'(decay={min_decay_r["decay"]:+.3f}  OOS PF={min_decay_r["oos"]["pf"]:.3f})')
print()

# Final verdict
n_agree = sum(1 for r in [best_pf_r, best_cagr_r, best_stab_r, min_decay_r]
              if abs(r['rs'] - 50) <= 20)
plateau_width = len(oos_pos)
mean_stab = statistics.mean(all_oos_stabs)

print(SEP)
print('  FINAL VERDICT')
print(SEP)
if plateau_width >= 5 and mean_stab > 0.5:
    print('  ROBUST EDGE. Wide profitable plateau and high rank stability.')
    print('  The weight choice is a second-order decision. Any blend in the')
    print('  profitable range will perform similarly in live trading.')
elif plateau_width >= 3:
    print('  MODERATE EDGE. The factor works in a limited weight range.')
    print('  Stick to the validated RS=50/EP=50 and do not re-optimise.')
else:
    print('  FRAGILE EDGE. Profitable only at narrow weight settings.')
    print('  The optimised weight is likely curve-fitted to OOS history.')
print()
print(f'  Recommendation: use RS={best_pf_r["rs"]}/EP={best_pf_r["ep"]} '
      f'(highest OOS PF) or RS=50/EP=50 (most studied).')
print(f'  Re-test if market regime changes significantly (new bull run or prolonged bear).')
