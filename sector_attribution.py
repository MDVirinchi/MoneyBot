"""
sector_attribution.py  --  Factor vs Sector Attribution
=========================================================
Question: Is RS+EP selecting good stocks, or just overweighting IT?

Three tests:
  1. Sector composition of D1 vs universe at every rebalance
  2. Sector-neutral factor: rank within sector, pick top from each
  3. Pure sector rotation baseline: buy the top sector, equal-weight

If factor-neutral-of-sector still beats, the FACTOR is the edge.
If sector explains everything, it's just IT beta.
"""

import time, math, statistics, warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

REBAL_DAYS   = 10
FORWARD_DAYS = 10
TOP_N        = 10
CAPITAL      = 500_000.0
SL_PCT       = 10.0
BROKERAGE=20.0; STT=0.001; EXCHANGE=0.0000345; SLIP=0.002

# ── Sector map ─────────────────────────────────────────────────────────────────
SECTOR = {
    # IT
    'TCS':'IT','INFY':'IT','HCLTECH':'IT','WIPRO':'IT','TECHM':'IT',
    'MPHASIS':'IT','LTTS':'IT','COFORGE':'IT','PERSISTENT':'IT','OFSS':'IT',
    'TATAELXSI':'IT','KPITTECH':'IT','CYIENT':'IT','ZENSARTECH':'IT',
    # Banking & Finance
    'HDFCBANK':'Finance','ICICIBANK':'Finance','SBIN':'Finance',
    'AXISBANK':'Finance','KOTAKBANK':'Finance','INDUSINDBK':'Finance',
    'BANDHANBNK':'Finance','FEDERALBNK':'Finance','RBLBANK':'Finance',
    'IDFCFIRSTB':'Finance','AUBANK':'Finance','BAJFINANCE':'Finance',
    'BAJAJFINSV':'Finance','CHOLAFIN':'Finance','LICHSGFIN':'Finance',
    'M&MFIN':'Finance','MUTHOOTFIN':'Finance','MANAPPURAM':'Finance',
    'PFC':'Finance','RECLTD':'Finance','IRFC':'Finance',
    'CDSL':'Finance','MCX':'Finance','ANGELONE':'Finance',
    'SBILIFE':'Finance','HDFCLIFE':'Finance',
    'PNBHOUSING':'Finance','CANFINHOME':'Finance','SUNDARMFIN':'Finance',
    # Auto
    'MARUTI':'Auto','M&M':'Auto','HEROMOTOCO':'Auto','BAJAJ-AUTO':'Auto',
    'TATAMOTORS':'Auto','EICHERMOT':'Auto','TVSMOTOR':'Auto','ASHOKLEY':'Auto',
    'MOTHERSON':'Auto','BHARATFORG':'Auto','EXIDEIND':'Auto',
    'ESCORTS':'Auto','BALKRISIND':'Auto','BOSCHLTD':'Auto',
    # FMCG
    'ITC':'FMCG','HINDUNILVR':'FMCG','NESTLEIND':'FMCG','BRITANNIA':'FMCG',
    'DABUR':'FMCG','MARICO':'FMCG','COLPAL':'FMCG','GODREJCP':'FMCG',
    'EMAMILTD':'FMCG','PGHH':'FMCG','TATACONSUM':'FMCG',
    'VBL':'FMCG','MCDOWELL-N':'FMCG',
    # Pharma
    'SUNPHARMA':'Pharma','DRREDDY':'Pharma','CIPLA':'Pharma',
    'LUPIN':'Pharma','AUROPHARMA':'Pharma','BIOCON':'Pharma',
    'ALKEM':'Pharma','TORNTPHARM':'Pharma','DIVISLAB':'Pharma',
    'PFIZER':'Pharma','METROPOLIS':'Pharma',
    # Energy & Utilities
    'ONGC':'Energy','BPCL':'Energy','COALINDIA':'Energy',
    'TATAPOWER':'Energy','NTPC':'Energy','POWERGRID':'Energy',
    'NHPC':'Energy','CESC':'Energy','TORNTPOWER':'Energy',
    'IGL':'Energy','MGL':'Energy','GUJGASLTD':'Energy',
    # Metals
    'JSWSTEEL':'Metals','TATASTEEL':'Metals','HINDALCO':'Metals',
    'SAIL':'Metals','NMDC':'Metals','VEDL':'Metals',
    # Industrials & Capital Goods
    'RELIANCE':'Industrials','LT':'Industrials','SIEMENS':'Industrials',
    'ABB':'Industrials','CUMMINSIND':'Industrials','POLYCAB':'Industrials',
    'KEI':'Industrials','HAVELLS':'Industrials','VOLTAS':'Industrials',
    'APLAPOLLO':'Industrials','DEEPAKNTR':'Industrials',
    # Consumer & Retail
    'TITAN':'Consumer','ASIANPAINT':'Consumer','BERGEPAINT':'Consumer',
    'KANSAINER':'Consumer','PIDILITIND':'Consumer','ASTRAL':'Consumer',
    'TRENT':'Consumer','DMART':'Consumer','WHIRLPOOL':'Consumer','PAGEIND':'Consumer',
    # Healthcare Services
    'APOLLOHOSP':'Healthcare','MAXHEALTH':'Healthcare',
    # Infra & Conglomerate
    'ADANIENT':'Infra','ADANIPORTS':'Infra','RVNL':'Infra',
    # Cement
    'ULTRACEMCO':'Cement','GRASIM':'Cement','RAMCOCEM':'Cement',
    'JKCEMENT':'Cement','DALBHARAT':'Cement',
    # Telecom & Others
    'BHARTIARTL':'Telecom',
    'NAUKRI':'Others','IRCTC':'Others','INDIGO':'Others',
    'NAVINFLUOR':'Others','PIIND':'Others',
}

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
            d = {str(ts.date()): {'close': float(r['Close']),
                                   'vol':   float(r.get('Volume',0) or 0)}
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
IS_CUTOFF = all_dates[int(N * 0.6)]
print(f'Universe: {len(valid)} stocks  |  {all_dates[0]} to {all_dates[-1]}')
print(f'IS cutoff: {IS_CUTOFF}\n')

# ── Factor score (same as before) ──────────────────────────────────────────────
def get_scores(i):
    if i < 72: return {}
    dn = all_dates[i]
    nc = nifty.get(dn,{}).get('close')
    np_ = nifty.get(all_dates[i-63],{}).get('close') if i >= 63 else None
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
    if not raw_rs or not raw_ep: return {}
    def pr(d):
        items = sorted(d.items(), key=lambda x: x[1])
        n = len(items)
        return {s: (r+1)/n*100 for r,(s,_) in enumerate(items)}
    rrs = pr(raw_rs); rep = pr(raw_ep)
    common = set(rrs) & set(rep)
    return {s: 0.5*rrs[s] + 0.5*rep[s] for s in common}

def fwd_ret(sym, i):
    c = price_data[sym]
    p0 = c.get(all_dates[i],{}).get('close')
    p1 = c.get(all_dates[i+FORWARD_DAYS],{}).get('close')
    if p0 and p1 and p0 > 0: return (p1/p0-1)*100
    return None

# ── Test 1: Sector composition of D1 over time ────────────────────────────────
# Track what fraction of the D1 (top-10%) each sector gets, per rebal date
sector_list = sorted(set(SECTOR.values()))
# universe sector count (static)
univ_sector = {}
for s in valid:
    sec = SECTOR.get(s, 'Others')
    univ_sector[sec] = univ_sector.get(sec, 0) + 1
univ_total = len(valid)

# per-rebal: count of each sector in top-10%
d1_sector_counts = {p: {s: [] for s in sector_list} for p in ('full','is','oos')}
d1_fwd_by_sector = {p: {s: [] for s in sector_list} for p in ('full','is','oos')}
sector_fwd       = {p: {s: [] for s in sector_list} for p in ('full','is','oos')}

# sector equity curves (equal-weight-within-sector returns for pure sector rotation)
sector_period_rets = {p: {s: [] for s in sector_list} for p in ('full','is','oos')}

i = 72
while i < N - FORWARD_DAYS:
    scores = get_scores(i)
    if len(scores) < 20:
        i += REBAL_DAYS; continue

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    d1_cutoff = max(1, int(len(ranked) * 0.10))  # top 10%
    d1_syms = {s for s,_ in ranked[:d1_cutoff]}

    period = 'is' if all_dates[i] < IS_CUTOFF else 'oos'

    # sector composition of D1
    d1_sec = {}
    for s in d1_syms:
        sec = SECTOR.get(s,'Others')
        d1_sec[sec] = d1_sec.get(sec, 0) + 1

    # forward returns by sector (all stocks)
    sec_fwds = {s: [] for s in sector_list}
    for sym,_ in ranked:
        r = fwd_ret(sym, i)
        if r is not None:
            sec = SECTOR.get(sym,'Others')
            sec_fwds[sec].append(r)
            # D1 sector fwd returns
            if sym in d1_syms:
                d1_fwd_by_sector[period][sec].append(r)
                d1_fwd_by_sector['full'][sec].append(r)

    for sec in sector_list:
        cnt = d1_sec.get(sec, 0)
        d1_sector_counts['full'][sec].append(cnt)
        d1_sector_counts[period][sec].append(cnt)
        avg = sum(sec_fwds[sec])/len(sec_fwds[sec]) if sec_fwds[sec] else None
        if avg is not None:
            sector_period_rets['full'][sec].append(avg)
            sector_period_rets[period][sec].append(avg)

    i += REBAL_DAYS

# ── Test 2: Sector-neutral factor ─────────────────────────────────────────────
# Rank within sector, pick top 1-2 per sector proportionally
def sector_neutral_portfolio(scores, top_n):
    """Pick top floor(top_n * sector_share) from each sector, ranked by composite within sector."""
    by_sector = {}
    for sym, sc in scores.items():
        sec = SECTOR.get(sym,'Others')
        by_sector.setdefault(sec, []).append((sym, sc))
    # count stocks per sector in universe (from current scores)
    sec_sizes = {s: len(v) for s,v in by_sector.items()}
    total = sum(sec_sizes.values())
    picks = []
    leftover = []
    alloc = {}
    for sec, syms_sc in by_sector.items():
        proportion = sec_sizes[sec] / total
        n_pick = max(0, round(top_n * proportion))
        alloc[sec] = n_pick
        ranked_sec = sorted(syms_sc, key=lambda x: -x[1])
        picks.extend([s for s,_ in ranked_sec[:n_pick]])
        leftover.extend([(s,sc) for s,sc in ranked_sec[n_pick:]])
    # fill remaining slots with best leftover
    while len(picks) < top_n and leftover:
        leftover.sort(key=lambda x: -x[1])
        picks.append(leftover.pop(0)[0])
    return picks[:top_n]

# Run sector-neutral and raw strategies side by side (simple forward return, no position sizing)
sn_rets  = {'full':[], 'is':[], 'oos':[]}  # sector-neutral top-10
raw_rets = {'full':[], 'is':[], 'oos':[]}  # raw top-10

i = 72
while i < N - FORWARD_DAYS:
    scores = get_scores(i)
    if len(scores) < 20:
        i += REBAL_DAYS; continue
    period = 'is' if all_dates[i] < IS_CUTOFF else 'oos'

    # raw top-10
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    raw10  = [s for s,_ in ranked[:TOP_N]]
    raw_fwds = [r for s in raw10 for r in [fwd_ret(s,i)] if r is not None]
    if raw_fwds:
        m = sum(raw_fwds)/len(raw_fwds)
        raw_rets['full'].append(m); raw_rets[period].append(m)

    # sector-neutral top-10
    sn10 = sector_neutral_portfolio(scores, TOP_N)
    sn_fwds = [r for s in sn10 for r in [fwd_ret(s,i)] if r is not None]
    if sn_fwds:
        m = sum(sn_fwds)/len(sn_fwds)
        sn_rets['full'].append(m); sn_rets[period].append(m)

    i += REBAL_DAYS

# ── Test 3: Pure sector rotation baseline ─────────────────────────────────────
# At each rebal: buy the sector with highest average RS (no stock selection at all)
def get_sector_rs(i):
    if i < 72: return {}
    dn = all_dates[i]
    nc = nifty.get(dn,{}).get('close')
    np_ = nifty.get(all_dates[i-63],{}).get('close') if i >= 63 else None
    if not nc or not np_: return {}
    sec_rs = {}
    for sym in valid:
        c = price_data[sym]
        cn = c.get(dn,{}).get('close'); cp = c.get(all_dates[i-63],{}).get('close')
        if cn and cp:
            r = (cn/cp-1)*100 - (nc/np_-1)*100
            sec = SECTOR.get(sym,'Others')
            sec_rs.setdefault(sec,[]).append(r)
    return {s: sum(v)/len(v) for s,v in sec_rs.items() if v}

sector_rot_rets = {'full':[], 'is':[], 'oos':[]}
i = 72
while i < N - FORWARD_DAYS:
    sec_rs = get_sector_rs(i)
    if not sec_rs:
        i += REBAL_DAYS; continue
    period = 'is' if all_dates[i] < IS_CUTOFF else 'oos'
    best_sec = max(sec_rs, key=lambda s: sec_rs[s])
    # all stocks in that sector, equal weight
    sec_syms = [s for s in valid if SECTOR.get(s,'Others') == best_sec]
    fwds = [r for s in sec_syms for r in [fwd_ret(s,i)] if r is not None]
    if fwds:
        m = sum(fwds)/len(fwds)
        sector_rot_rets['full'].append(m); sector_rot_rets[period].append(m)
    i += REBAL_DAYS

# nifty forward
nifty_avg_fwd = {p: 0.0 for p in ('full','is','oos')}
temp = {'full':[], 'is':[], 'oos':[]}
i = 72
while i < N - FORWARD_DAYS:
    d0 = all_dates[i]; d1 = all_dates[i+FORWARD_DAYS]
    n0 = nifty.get(d0,{}).get('close'); n1 = nifty.get(d1,{}).get('close')
    if n0 and n1:
        r = (n1/n0-1)*100; period = 'is' if d0 < IS_CUTOFF else 'oos'
        temp['full'].append(r); temp[period].append(r)
    i += REBAL_DAYS
for p in ('full','is','oos'):
    if temp[p]: nifty_avg_fwd[p] = sum(temp[p])/len(temp[p])

def mean(lst): return sum(lst)/len(lst) if lst else 0.0
def ann(avg_per_10d): return ((1+avg_per_10d/100)**(252/10)-1)*100

SEP = '=' * 96
sep = '-' * 96

# ── Print results ──────────────────────────────────────────────────────────────

# --- Test 1: Sector composition ---
print(SEP)
print('  TEST 1: SECTOR COMPOSITION OF D1 (TOP 10%)')
print('  Does the factor systematically overweight one sector?')
print(SEP)
print(f'  {"Sector":<14} {"Universe%":>10}  {"D1% (IS)":>10}  {"D1% (OOS)":>10}  '
      f'{"Overweight IS":>14}  {"Overweight OOS":>14}  {"OOS fwd ret":>11}')
print(sep)

# average D1 slots vs universe slots
univ_n_per_rebal_is  = 67   # approx rebal points in IS
univ_n_per_rebal_oos = 49
d1_size_per_rebal = int(len(valid) * 0.10)  # ~13 stocks per rebal in D1

for sec in sorted(sector_list, key=lambda s: -mean(d1_sector_counts['oos'][s])):
    univ_pct  = univ_sector.get(sec,0) / univ_total * 100
    d1_is_pct = mean(d1_sector_counts['is'][sec])  / max(d1_size_per_rebal,1) * 100
    d1_oos_pct= mean(d1_sector_counts['oos'][sec]) / max(d1_size_per_rebal,1) * 100
    ow_is     = d1_is_pct  - univ_pct
    ow_oos    = d1_oos_pct - univ_pct
    oos_fr    = mean([r for lst in d1_fwd_by_sector['oos'][sec] for r in [lst]])
    flag_is  = ' <-- OVER' if ow_is  >  8 else (' <-- UNDER' if ow_is  < -8 else '')
    flag_oos = ' <-- OVER' if ow_oos >  8 else (' <-- UNDER' if ow_oos < -8 else '')
    if univ_sector.get(sec,0) == 0: continue
    print(f'  {sec:<14} {univ_pct:>9.1f}%  {d1_is_pct:>9.1f}%  {d1_oos_pct:>9.1f}%  '
          f'{ow_is:>+12.1f}%{flag_is:<10}  {ow_oos:>+12.1f}%{flag_oos:<10}  '
          f'{oos_fr:>+9.3f}%')

# --- Test 2: Strategy comparison ---
print()
print(SEP)
print('  TEST 2: RAW FACTOR vs SECTOR-NEUTRAL FACTOR vs PURE SECTOR ROTATION')
print('  If sector-neutral underperforms, the edge is in sector tilts.')
print('  If sector-neutral matches, the edge is in stock selection within sectors.')
print(SEP)
print(f'  {"Strategy":<35} {"IS avg/10d":>11}  {"IS ann%":>9}  {"OOS avg/10d":>12}  {"OOS ann%":>9}')
print(sep)

strategies = [
    ('Raw RS+EP (top-10, any sector)',   raw_rets),
    ('Sector-neutral RS+EP (top-10)',    sn_rets),
    ('Pure sector rotation (top sector)',sector_rot_rets),
]
for label, rets in strategies:
    is_m  = mean(rets['is']);  is_a  = ann(is_m)
    oos_m = mean(rets['oos']); oos_a = ann(oos_m)
    print(f'  {label:<35} {is_m:>+10.3f}%  {is_a:>+8.1f}%  {oos_m:>+11.3f}%  {oos_a:>+8.1f}%')

nifty_is = nifty_avg_fwd['is']; nifty_oos = nifty_avg_fwd['oos']
print(sep)
print(f'  {"Nifty Buy & Hold":<35} {nifty_is:>+10.3f}%  {ann(nifty_is):>+8.1f}%  '
      f'{nifty_oos:>+11.3f}%  {ann(nifty_oos):>+8.1f}%')

# --- Test 3: Sector return table (what each sector actually did) ---
print()
print(SEP)
print('  TEST 3: EACH SECTOR\'S OWN RETURN (equal-weight all stocks in sector)')
print('  Shows whether the factor is selecting within sectors or just choosing the right sectors.')
print(SEP)
print(f'  {"Sector":<14} {"IS avg/10d":>11}  {"IS ann%":>9}  {"OOS avg/10d":>12}  {"OOS ann%":>9}  {"# stocks":>9}')
print(sep)
sector_rows = []
for sec in sector_list:
    if univ_sector.get(sec,0) == 0: continue
    is_m  = mean(sector_period_rets['is'][sec])
    oos_m = mean(sector_period_rets['oos'][sec])
    sector_rows.append((sec, is_m, oos_m))
for sec, is_m, oos_m in sorted(sector_rows, key=lambda x: -x[2]):
    n = univ_sector.get(sec,0)
    print(f'  {sec:<14} {is_m:>+10.3f}%  {ann(is_m):>+8.1f}%  {oos_m:>+10.3f}%  '
          f'{ann(oos_m):>+8.1f}%  {n:>9}')

# --- Summary verdict ---
raw_oos  = mean(raw_rets['oos'])
sn_oos   = mean(sn_rets['oos'])
rot_oos  = mean(sector_rot_rets['oos'])

print()
print(SEP)
print('  VERDICT: IS THE EDGE IN THE FACTOR OR IN SECTOR TILTS?')
print(SEP)
print(f'  Raw factor OOS return       : {raw_oos:>+.3f}%/10d  ({ann(raw_oos):>+.1f}% ann)')
print(f'  Sector-neutral OOS return   : {sn_oos:>+.3f}%/10d  ({ann(sn_oos):>+.1f}% ann)')
print(f'  Pure sector rotation OOS    : {rot_oos:>+.3f}%/10d  ({ann(rot_oos):>+.1f}% ann)')
print(f'  Nifty OOS                   : {nifty_oos:>+.3f}%/10d  ({ann(nifty_oos):>+.1f}% ann)')
print()

factor_premium = raw_oos - rot_oos
sector_premium = rot_oos - nifty_oos
total_alpha    = raw_oos - nifty_oos
if abs(total_alpha) > 0.001:
    factor_share = factor_premium / total_alpha * 100
    sector_share = sector_premium / total_alpha * 100
else:
    factor_share = sector_share = 0

print(f'  Alpha decomposition (vs Nifty):')
print(f'    Total alpha              : {total_alpha:>+.3f}%/10d')
print(f'    From sector tilts        : {sector_premium:>+.3f}%/10d  ({sector_share:>+.0f}% of total alpha)')
print(f'    From stock selection     : {factor_premium:>+.3f}%/10d  ({factor_share:>+.0f}% of total alpha)')
print()

sn_vs_raw = sn_oos - raw_oos
if sn_vs_raw > -0.05:
    print('  CONCLUSION: FACTOR IS THE EDGE.')
    print('  Sector-neutral version retains the return. The ranking skill')
    print('  works within sectors, not just by picking the right sector.')
elif rot_oos > raw_oos:
    print('  CONCLUSION: SECTOR IS THE EDGE.')
    print('  Pure sector rotation beats the stock-level factor. You could')
    print('  replace the whole scoring model with "buy the top 2 sectors".')
else:
    pct = abs(sn_vs_raw / raw_oos * 100) if raw_oos != 0 else 0
    print(f'  CONCLUSION: MIXED -- sector neutralisation costs {pct:.0f}% of return.')
    print(f'  Both the sector tilt AND the within-sector ranking contribute.')
    print(f'  The factor is real but not sector-independent.')
