"""
performance_registry.py — Single authoritative performance report.
Runs ALL strategy variants through the same simulation engine and produces
a comparison table showing exactly why reported numbers differ.

Run: python performance_registry.py
Expected runtime: ~12 minutes (data download + 10 sim variants)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time, math, statistics, warnings, logging, json
from datetime import datetime
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

W_RS = 0.60; W_EP = 0.40
TOP_N = 10; REBAL_DAYS = 10; SL_PCT = 10.0
BROKERAGE = 20.0; STT = 0.001; EXCHANGE = 0.0000345
SLIP = 0.002
CAPITAL = 500_000.0

SECTOR = {
    'TCS':'IT','INFY':'IT','HCLTECH':'IT','WIPRO':'IT','TECHM':'IT',
    'MPHASIS':'IT','LTTS':'IT','COFORGE':'IT','PERSISTENT':'IT','OFSS':'IT',
    'TATAELXSI':'IT','KPITTECH':'IT','CYIENT':'IT','ZENSARTECH':'IT',
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
    'MARUTI':'Auto','M&M':'Auto','HEROMOTOCO':'Auto','BAJAJ-AUTO':'Auto',
    'TATAMOTORS':'Auto','EICHERMOT':'Auto','TVSMOTOR':'Auto','ASHOKLEY':'Auto',
    'MOTHERSON':'Auto','BHARATFORG':'Auto','EXIDEIND':'Auto',
    'ESCORTS':'Auto','BALKRISIND':'Auto','BOSCHLTD':'Auto',
    'ITC':'FMCG','HINDUNILVR':'FMCG','NESTLEIND':'FMCG','BRITANNIA':'FMCG',
    'DABUR':'FMCG','MARICO':'FMCG','COLPAL':'FMCG','GODREJCP':'FMCG',
    'EMAMILTD':'FMCG','PGHH':'FMCG','TATACONSUM':'FMCG',
    'VBL':'FMCG','MCDOWELL-N':'FMCG',
    'SUNPHARMA':'Pharma','DRREDDY':'Pharma','CIPLA':'Pharma',
    'LUPIN':'Pharma','AUROPHARMA':'Pharma','BIOCON':'Pharma',
    'ALKEM':'Pharma','TORNTPHARM':'Pharma','DIVISLAB':'Pharma',
    'PFIZER':'Pharma','METROPOLIS':'Pharma',
    'ONGC':'Energy','BPCL':'Energy','COALINDIA':'Energy',
    'TATAPOWER':'Energy','NTPC':'Energy','POWERGRID':'Energy',
    'NHPC':'Energy','CESC':'Energy','TORNTPOWER':'Energy',
    'IGL':'Energy','MGL':'Energy','GUJGASLTD':'Energy',
    'JSWSTEEL':'Metals','TATASTEEL':'Metals','HINDALCO':'Metals',
    'SAIL':'Metals','NMDC':'Metals','VEDL':'Metals',
    'RELIANCE':'Industrials','LT':'Industrials','SIEMENS':'Industrials',
    'ABB':'Industrials','CUMMINSIND':'Industrials','POLYCAB':'Industrials',
    'KEI':'Industrials','HAVELLS':'Industrials','VOLTAS':'Industrials',
    'APLAPOLLO':'Industrials','DEEPAKNTR':'Industrials',
    'TITAN':'Consumer','ASIANPAINT':'Consumer','BERGEPAINT':'Consumer',
    'KANSAINER':'Consumer','PIDILITIND':'Consumer','ASTRAL':'Consumer',
    'TRENT':'Consumer','DMART':'Consumer','WHIRLPOOL':'Consumer','PAGEIND':'Consumer',
    'APOLLOHOSP':'Healthcare','MAXHEALTH':'Healthcare',
    'ADANIENT':'Infra','ADANIPORTS':'Infra','RVNL':'Infra',
    'ULTRACEMCO':'Cement','GRASIM':'Cement','RAMCOCEM':'Cement',
    'JKCEMENT':'Cement','DALBHARAT':'Cement',
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

# ── Fetch data ────────────────────────────────────────────────────────────────
print("PERFORMANCE REGISTRY — fetching 5 years of data for 136 stocks...")
t0 = time.time()
price_data = {}; valid = []
for i, (ticker, sym) in enumerate(STOCKS):
    try:
        df = yf.Ticker(ticker).history(period='5y', interval='1d', auto_adjust=True)
        if not df.empty:
            d = {str(ts.date()): {'open': float(r['Open']), 'close': float(r['Close']),
                                   'vol': float(r.get('Volume', 0) or 0)}
                 for ts, r in df.iterrows()}
            if len(d) >= 300:
                price_data[sym] = d; valid.append(sym)
    except Exception: pass
    if (i + 1) % 20 == 0:
        print(f"  ... {i+1}/{len(STOCKS)} stocks fetched")
    time.sleep(0.22)

nifty_raw = {}
try:
    df = yf.Ticker('^NSEI').history(period='5y', interval='1d', auto_adjust=True)
    nifty_raw = {str(ts.date()): float(r['Close']) for ts, r in df.iterrows()}
except Exception: pass

print(f"Data fetched: {len(valid)} stocks, {len(nifty_raw)} Nifty days in {time.time()-t0:.0f}s")

all_dates = sorted(nifty_raw.keys())
N = len(all_dates)
IS_END = int(N * 0.6)
IS_DATES = all_dates[:IS_END]
OOS_DATES = all_dates[IS_END:]

n_s = nifty_raw.get(OOS_DATES[0], 1); n_e = nifty_raw.get(OOS_DATES[-1], 1)
NIFTY_OOS_CAGR = ((n_e/n_s)**(252/len(OOS_DATES))-1)*100

# ── Nifty DMA ─────────────────────────────────────────────────────────────────
nifty_dma = {}
nc_list = [(d, nifty_raw[d]) for d in all_dates]
for idx, (d, c) in enumerate(nc_list):
    d50 = sum(v for _,v in nc_list[max(0,idx-49):idx+1]) / min(idx+1,50)
    d200 = sum(v for _,v in nc_list[max(0,idx-199):idx+1]) / min(idx+1,200)
    nifty_dma[d] = {'close': c, 'dma50': d50, 'dma200': d200}

def regime(date):
    r = nifty_dma.get(date)
    if not r: return 'Bull'
    if r['close'] < r['dma200']: return 'Bear'
    if r['dma50'] <= r['dma200']: return 'Flat'
    return 'Bull'

# ── Factor engine ─────────────────────────────────────────────────────────────
_raw_cache = {}
def get_raw(gi):
    if gi in _raw_cache: return _raw_cache[gi]
    if gi < 72: return {}
    dn = all_dates[gi]
    nc = nifty_raw.get(dn); np_ = nifty_raw.get(all_dates[gi-63]) if gi>=63 else None
    raw_rs = {}; raw_ep = {}
    for sym in valid:
        c = price_data[sym]
        sd = [d for d in all_dates[max(0,gi-74):gi+1] if d in c]
        if len(sd) < 50: continue
        if nc and np_:
            cn = c.get(dn,{}).get('close'); cp = c.get(all_dates[gi-63],{}).get('close')
            if cn and cp: raw_rs[sym] = (cn/cp-1)*100 - (nc/np_-1)*100
        ed = sd[-63:]
        evols = [c[d]['vol'] for d in ed if c[d]['vol']>0]
        av = sum(evols)/len(evols) if evols else 0
        ep = 0.0
        for j in range(1,len(ed)):
            cj=c.get(ed[j]); cjm=c.get(ed[j-1])
            if not(cj and cjm and cjm['close']>0): continue
            dr = cj['close']/cjm['close']-1
            if dr>0.02 and av>0 and cj['vol']>1.5*av: ep=max(ep,dr*100)
        raw_ep[sym] = ep
    _raw_cache[gi] = {'rs': raw_rs, 'ep': raw_ep}
    return _raw_cache[gi]

def composite(gi):
    raw = get_raw(gi)
    if not raw: return {}
    def pr(d):
        items=sorted(d.items(),key=lambda x:x[1]); n=len(items)
        return {s:(r+1)/n*100 for r,(s,_) in enumerate(items)}
    rnks = {}
    if raw['rs']: rnks['rs'] = pr(raw['rs'])
    if raw['ep']: rnks['ep'] = pr(raw['ep'])
    if not rnks: return {}
    active = list(rnks.keys())
    tw = sum({'rs':W_RS,'ep':W_EP}[f] for f in active)
    syms = set.intersection(*[set(rnks[f].keys()) for f in active])
    return {s:sum({'rs':W_RS,'ep':W_EP}[f]*rnks[f][s] for f in active)/tw for s in syms}

print('Pre-computing factors...')
gi=72
while gi<N: get_raw(gi); gi+=REBAL_DAYS
print(f'Cached {len(_raw_cache)} rebalance points.\n')

# ── 50-DMA filter ─────────────────────────────────────────────────────────────
def stock_above_50dma(sym, date, gi):
    c = price_data.get(sym, {})
    dates_w = [d for d in all_dates[max(0,gi-60):gi+1] if d in c]
    if len(dates_w) < 50: return True
    closes = [c[d]['close'] for d in dates_w[-50:]]
    dma50 = sum(closes)/len(closes)
    curr = c.get(date,{}).get('close')
    if curr is None: return True
    return curr > dma50

# ── Sector cap filter ─────────────────────────────────────────────────────────
def apply_sector_cap(ranked_syms, max_per_sector=2):
    """From a ranked list of symbols, pick top-N respecting sector cap."""
    sector_count = {}
    result = []
    for sym in ranked_syms:
        sec = SECTOR.get(sym, 'Others')
        if sector_count.get(sec, 0) >= max_per_sector:
            continue
        result.append(sym)
        sector_count[sec] = sector_count.get(sec, 0) + 1
        if len(result) >= TOP_N:
            break
    return set(result)

# ── Simulation engine ─────────────────────────────────────────────────────────
def run_sim(date_range, slip=SLIP, regime_policy='bull_flat',
            use_50dma=False, sector_cap=0):
    cash=CAPITAL; pos={}; trades=[]; equity=[]; last=-999
    date_to_gi={d:all_dates.index(d) for d in date_range if d in all_dates}

    def gc(s,d): return price_data[s].get(d,{}).get('close')
    def go(s,d): return price_data[s].get(d,{}).get('open')

    for idx,date in enumerate(date_range):
        gi=date_to_gi.get(date)
        if gi is None or gi<72: equity.append(cash); continue
        reg=regime(date)

        if regime_policy=='bull_flat' and reg=='Bear':
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                p=pos.pop(sym); ev=p['qty']*fp
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'exit':'Regime'})
            equity.append(cash); continue

        if regime_policy=='always': pass
        elif regime_policy=='bull_only' and reg!='Bull':
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                p=pos.pop(sym); ev=p['qty']*fp
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'exit':'Regime'})
            equity.append(cash); continue

        for sym in list(pos):
            curr=gc(sym,date)
            if curr and curr<=pos[sym]['ep']*(1-SL_PCT/100):
                p=pos.pop(sym); fill=curr*(1-slip)
                ev=p['qty']*fill; cost=BROKERAGE+ev*STT+ev*EXCHANGE
                cash+=ev-cost
                trades.append({'pnl':(fill-p['ep'])*p['qty']-cost,'exit':'SL'})

        if idx-last>=REBAL_DAYS:
            last=idx
            comp=composite(gi)

            if use_50dma:
                comp = {s:sc for s,sc in comp.items() if stock_above_50dma(s,date,gi)}

            if sector_cap > 0:
                ranked = [s for s,_ in sorted(comp.items(),key=lambda x:-x[1])]
                tgt = apply_sector_cap(ranked, sector_cap)
            else:
                tgt={s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N]}

            for sym in list(pos):
                if sym not in tgt:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                    p=pos.pop(sym); ev=p['qty']*fp
                    cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                    trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'exit':'Rebal'})
            new=[s for s in tgt if s not in pos]
            avail=cash*0.95
            if new and avail>10_000:
                alloc=min(avail/max(len(new),1),CAPITAL/TOP_N)
                for sym in new:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fpd=go(sym,nd) or gc(sym,date)
                    if not fpd: continue
                    fill=fpd*(1+slip); qty=max(1,int(alloc/fill))
                    cost=BROKERAGE+qty*fill*EXCHANGE
                    if cash>=qty*fill+cost:
                        cash-=qty*fill+cost; pos[sym]={'qty':qty,'ep':fill}

        fv=cash+sum(p['qty']*(gc(s,date) or p['ep']) for s,p in pos.items())
        equity.append(fv)

    for s,p in list(pos.items()):
        fp=(gc(s,date_range[-1]) or p['ep'])*(1-slip)
        ev=p['qty']*fp; cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
        trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'exit':'EoP'})

    if not trades: return {'cagr':0,'sharpe':0,'max_dd':0,'trades':0,'wr':0,'pf':0,'fv':CAPITAL}
    wins=[t for t in trades if t['pnl']>0]
    gp=sum(t['pnl'] for t in wins); gl=abs(sum(t['pnl'] for t in trades if t['pnl']<=0))
    pf=gp/gl if gl>0 else 0
    yrs=max(len(date_range)/252,0.1); fv=equity[-1] if equity else CAPITAL
    cagr=((fv/CAPITAL)**(1/yrs)-1)*100 if fv>0 else -100
    dr=[(equity[k]-equity[k-1])/equity[k-1] for k in range(1,len(equity)) if equity[k-1]>0]
    sharpe=statistics.mean(dr)/statistics.stdev(dr)*math.sqrt(252) if len(dr)>2 and statistics.stdev(dr)>0 else 0
    peak=CAPITAL; max_dd=0
    for v in equity:
        if v>peak: peak=v
        dd=(peak-v)/peak*100 if peak>0 else 0
        if dd>max_dd: max_dd=dd
    sl_exits = sum(1 for t in trades if t.get('exit')=='SL')
    return {'cagr':round(cagr,2),'sharpe':round(sharpe,3),'max_dd':round(max_dd,1),
            'trades':len(trades),'wr':round(len(wins)/len(trades)*100,1),
            'pf':round(pf,3),'fv':round(fv,0),'sl_exits':sl_exits}


# ══════════════════════════════════════════════════════════════════════════════
# RUN ALL VARIANTS
# ══════════════════════════════════════════════════════════════════════════════
SEP = '=' * 120
sep = '-' * 120

configs = [
    # (Label, regime_policy, slip, use_50dma, sector_cap, version_tag)
    ("v1.0  Raw RS60/EP40, no regime",      "always",    SLIP, False, 0, "v1.0"),
    ("v1.1  + Policy B (Bull-only)",         "bull_only", SLIP, False, 0, "v1.1"),
    ("v1.2  + Policy C (Bull+Flat)",         "bull_flat", SLIP, False, 0, "v1.2"),
    ("v1.3  + Policy C + 2x slippage",       "bull_flat", 0.004,False, 0, "v1.3"),
    ("v1.4  + Policy C + 3x slippage",       "bull_flat", 0.006,False, 0, "v1.4"),
    ("v2.0  + Policy C + 50DMA filter",      "bull_flat", SLIP, True,  0, "v2.0"),
    ("v2.1  + Policy C + 50DMA + 2x slip",   "bull_flat", 0.004,True,  0, "v2.1"),
    ("v3.0  + Policy C + 50DMA + Sector(2)", "bull_flat", SLIP, True,  2, "v3.0"),
    ("v3.1  + Policy C + 50DMA + Sector(3)", "bull_flat", SLIP, True,  3, "v3.1"),
]

print(f'\n{SEP}')
print(f'  PERFORMANCE REGISTRY — ALL STRATEGY VARIANTS')
print(f'  Data: {all_dates[0]} to {all_dates[-1]}  ({N} trading days)')
print(f'  IS: {IS_DATES[0]} to {IS_DATES[-1]}  ({len(IS_DATES)}d)')
print(f'  OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}  ({len(OOS_DATES)}d)')
print(f'  Nifty OOS CAGR: {NIFTY_OOS_CAGR:+.1f}%  |  Universe: {len(valid)} stocks')
print(f'  Weights: RS={W_RS*100:.0f}% EP={W_EP*100:.0f}%  |  Top-{TOP_N}  |  Rebal {REBAL_DAYS}d  |  SL {SL_PCT}%')
print(f'  Base costs: Brokerage Rs.{BROKERAGE}  STT {STT*100:.1f}%  Exchange {EXCHANGE*100:.4f}%')
print(SEP)

print(f'\n  {"Version":<42} {"Slip":>6} {"50D":>4} {"Sec":>4} {"Regime":>10}'
      f'  |  {"IS CAGR":>8} {"IS Sh":>7} {"IS DD":>6}'
      f'  |  {"OOS CAGR":>9} {"OOS Sh":>7} {"OOS DD":>7} {"OOS WR":>7} {"OOS PF":>7} {"Trades":>7} {"SL":>4} {"FV":>12}')
print(sep)

results = []
for label, rpol, sl, d50, scap, vtag in configs:
    m_is  = run_sim(IS_DATES,  slip=sl, regime_policy=rpol, use_50dma=d50, sector_cap=scap)
    m_oos = run_sim(OOS_DATES, slip=sl, regime_policy=rpol, use_50dma=d50, sector_cap=scap)

    beat = '*' if m_oos['cagr'] > NIFTY_OOS_CAGR else ' '
    deployed = ' <<<' if vtag == 'v2.0' else ''

    print(f'  {label:<42} {sl*100:>5.1f}% {"Y" if d50 else "N":>4} {scap if scap else "-":>4} {rpol:>10}'
          f'  |  {m_is["cagr"]:>+7.1f}% {m_is["sharpe"]:>7.3f} {m_is["max_dd"]:>5.1f}%'
          f'  |  {m_oos["cagr"]:>+8.2f}%{beat} {m_oos["sharpe"]:>7.3f} {m_oos["max_dd"]:>6.1f}% {m_oos["wr"]:>6.1f}% {m_oos["pf"]:>7.3f} {m_oos["trades"]:>7} {m_oos["sl_exits"]:>4} {m_oos["fv"]:>11,.0f}{deployed}')

    results.append({
        'version': vtag, 'label': label.strip(),
        'regime_policy': rpol, 'slip': sl, 'use_50dma': d50, 'sector_cap': scap,
        'is': m_is, 'oos': m_oos
    })

print(sep)

# ── Identify deployed version ─────────────────────────────────────────────────
deployed = next(r for r in results if r['version'] == 'v2.0')
print(f'\n{SEP}')
print(f'  CURRENTLY DEPLOYED CONFIGURATION')
print(SEP)
print(f'  Version         : {deployed["version"]} — {deployed["label"]}')
print(f'  Regime filter   : Policy C (Bull+Flat = trade, Bear = 100% cash)')
print(f'  RS/EP weights   : {W_RS*100:.0f}% / {W_EP*100:.0f}%')
print(f'  Rebalance       : Every {REBAL_DAYS} trading days')
print(f'  Stop-loss       : {SL_PCT}% below entry fill')
print(f'  50-DMA filter   : YES (stock close must be above its own 50-day MA)')
print(f'  Sector cap      : NONE')
print(f'  Slippage        : {SLIP*100:.1f}% each side')
print(f'  Universe        : {len(valid)} stocks')
print(f'  Capital         : Rs.{CAPITAL:,.0f}')
print(f'  Date range IS   : {IS_DATES[0]} to {IS_DATES[-1]}')
print(f'  Date range OOS  : {OOS_DATES[0]} to {OOS_DATES[-1]}')
print(f'  ')
print(f'  AUTHORITATIVE OOS PERFORMANCE:')
m = deployed['oos']
print(f'    CAGR           : {m["cagr"]:+.2f}%')
print(f'    Sharpe Ratio   : {m["sharpe"]:.3f}')
print(f'    Max Drawdown   : {m["max_dd"]:.1f}%')
print(f'    Win Rate       : {m["wr"]:.1f}%')
print(f'    Profit Factor  : {m["pf"]:.3f}')
print(f'    Total Trades   : {m["trades"]}')
print(f'    SL Exits       : {m["sl_exits"]}')
print(f'    Final Value    : Rs.{m["fv"]:,.0f}')
print(f'    Beats Nifty    : {"YES" if m["cagr"] > NIFTY_OOS_CAGR else "NO"} (Nifty OOS: {NIFTY_OOS_CAGR:+.1f}%)')

# ── Why other numbers differ ──────────────────────────────────────────────────
print(f'\n{SEP}')
print(f'  WHY OTHER REPORTED NUMBERS DIFFER')
print(SEP)
print(f'  {"Version":>6}  {"vs Deployed CAGR":>18}  {"Difference explained by"}')
print(sep)
for r in results:
    if r['version'] == 'v2.0': continue
    delta = r['oos']['cagr'] - deployed['oos']['cagr']
    reasons = []
    if r['regime_policy'] != deployed['regime_policy']:
        reasons.append(f"regime={r['regime_policy']} vs bull_flat")
    if r['slip'] != deployed['slip']:
        reasons.append(f"slip={r['slip']*100:.1f}% vs {deployed['slip']*100:.1f}%")
    if r['use_50dma'] != deployed['use_50dma']:
        reasons.append("no 50-DMA filter" if not r['use_50dma'] else "has 50-DMA filter")
    if r['sector_cap'] != deployed['sector_cap']:
        reasons.append(f"sector_cap={r['sector_cap']}" if r['sector_cap'] else "no sector cap")
    print(f'  {r["version"]:>6}  {r["oos"]["cagr"]:>+8.2f}% ({delta:>+6.2f}pp)  {"; ".join(reasons)}')

print(SEP)

# ── Save JSON ─────────────────────────────────────────────────────────────────
registry = {
    "generated_at": str(datetime.now()),
    "data_range": f"{all_dates[0]} to {all_dates[-1]}",
    "is_range": f"{IS_DATES[0]} to {IS_DATES[-1]}",
    "oos_range": f"{OOS_DATES[0]} to {OOS_DATES[-1]}",
    "nifty_oos_cagr": round(NIFTY_OOS_CAGR, 2),
    "universe_size": len(valid),
    "deployed_version": "v2.0",
    "variants": [{
        "version": r["version"], "label": r["label"],
        "config": {"regime": r["regime_policy"], "slip": r["slip"],
                   "50dma": r["use_50dma"], "sector_cap": r["sector_cap"]},
        "is": r["is"], "oos": r["oos"]
    } for r in results]
}
out = "performance_registry.json"
with open(out, "w") as f:
    json.dump(registry, f, indent=2)
print(f'\nRegistry saved to {out}')
