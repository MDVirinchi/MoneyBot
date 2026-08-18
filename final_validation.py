"""
final_validation.py  --  RS60/EP40 Four-Priority Validation
=============================================================
P1  Cost stress test      : slippage 0.2% / 0.4% / 0.6% / 0.8% each side
P2  Sector-neutral        : raw vs within-sector ranking
P3  Market regime engine  : 4 policies (Always / Bull / Bull+Flat / Scaled)
P4  June 15 readiness     : tomorrow's top-10 candidate list with scores

Strategy locked: RS=60%, EP=40%, Top-N=10, Rebal=10d, SL=10%
Walk-forward  : IS = Year 1-3 (60%), OOS = Year 4-5 (40%)
"""

import time, math, statistics, warnings, logging, datetime
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

# ── Constants ──────────────────────────────────────────────────────────────────
W_RS = 0.60; W_EP = 0.40
TOP_N = 10; REBAL_DAYS = 10; SL_PCT = 10.0
BROKERAGE = 20.0; STT = 0.001; EXCHANGE = 0.0000345
BASE_SLIP = 0.002   # 0.2% each side (baseline)
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

nifty_raw = {}
try:
    df = yf.Ticker('^NSEI').history(period='5y', interval='1d', auto_adjust=True)
    nifty_raw = {str(ts.date()): float(r['Close']) for ts, r in df.iterrows()}
except Exception: pass

all_dates = sorted(nifty_raw.keys())
N = len(all_dates)
IS_END = int(N * 0.6)
IS_DATES  = all_dates[:IS_END]
OOS_DATES = all_dates[IS_END:]

n_start = nifty_raw.get(OOS_DATES[0], 1); n_end = nifty_raw.get(OOS_DATES[-1], 1)
NIFTY_OOS_CAGR = ((n_end/n_start)**(252/len(OOS_DATES))-1)*100

print(f'Universe: {len(valid)} stocks  |  {all_dates[0]} to {all_dates[-1]}  ({N} days)')
print(f'IS: {IS_DATES[0]} to {IS_DATES[-1]}  ({len(IS_DATES)}d)')
print(f'OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}  ({len(OOS_DATES)}d)  Nifty={NIFTY_OOS_CAGR:+.1f}%\n')

# ── Nifty DMA lookup (for regime engine) ──────────────────────────────────────
nifty_dma = {}   # date -> {close, dma50, dma200}
nifty_closes = [(d, nifty_raw[d]) for d in all_dates]
for idx, (d, c) in enumerate(nifty_closes):
    dma50  = sum(v for _,v in nifty_closes[max(0,idx-49):idx+1]) / min(idx+1,50)
    dma200 = sum(v for _,v in nifty_closes[max(0,idx-199):idx+1]) / min(idx+1,200)
    nifty_dma[d] = {'close': c, 'dma50': dma50, 'dma200': dma200}

def regime(date):
    r = nifty_dma.get(date)
    if not r: return 'Bull'
    c, d50, d200 = r['close'], r['dma50'], r['dma200']
    if c < d200:              return 'Bear'
    if d50 <= d200:           return 'Flat'
    return 'Bull'

# ── Factor engine ──────────────────────────────────────────────────────────────
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
    result = {'rs': raw_rs, 'ep': raw_ep}
    _raw_cache[gi] = result
    return result

def composite(gi, w_rs=W_RS, w_ep=W_EP):
    raw = get_raw(gi)
    if not raw: return {}
    def pr(d):
        items=sorted(d.items(),key=lambda x:x[1]); n=len(items)
        return {s:(r+1)/n*100 for r,(s,_) in enumerate(items)}
    rnks={}
    if w_rs>0 and raw['rs']: rnks['rs']=pr(raw['rs'])
    if w_ep>0 and raw['ep']: rnks['ep']=pr(raw['ep'])
    if not rnks: return {}
    active=list(rnks.keys()); tw=sum({'rs':w_rs,'ep':w_ep}[f] for f in active)
    syms=set.intersection(*[set(rnks[f].keys()) for f in active])
    return {s:sum({'rs':w_rs,'ep':w_ep}[f]*rnks[f][s] for f in active)/tw for s in syms}

def sector_neutral_top(gi, top_n=TOP_N):
    """Rank within sector, pick proportionally."""
    comp = composite(gi)
    if not comp: return []
    by_sec = {}
    for s,sc in comp.items():
        sec=SECTOR.get(s,'Others'); by_sec.setdefault(sec,[]).append((s,sc))
    total=sum(len(v) for v in by_sec.values())
    picks=[]; leftover=[]
    for sec,syms_sc in by_sec.items():
        n_pick=max(0,round(top_n*len(syms_sc)/total))
        ranked=sorted(syms_sc,key=lambda x:-x[1])
        picks.extend(s for s,_ in ranked[:n_pick])
        leftover.extend((s,sc) for s,sc in ranked[n_pick:])
    while len(picks)<top_n and leftover:
        leftover.sort(key=lambda x:-x[1]); picks.append(leftover.pop(0)[0])
    return picks[:top_n]

# Pre-cache all rebal points
print('Pre-computing factors...')
gi=72
while gi<N: get_raw(gi); gi+=REBAL_DAYS
print(f'Cached {len(_raw_cache)} rebalance points.\n')

# ── Core portfolio simulator ───────────────────────────────────────────────────
def run_sim(date_range, slip=BASE_SLIP, selector='raw', regime_policy='always',
            size_scale=1.0):
    """
    selector      : 'raw' | 'sector_neutral'
    regime_policy : 'always' | 'bull_only' | 'bull_flat' | 'scaled'
    size_scale    : multiply position size (used for flat-half in scaled policy)
    """
    cash=CAPITAL; pos={}; trades=[]; equity=[]; last=-999
    date_to_gi={d:all_dates.index(d) for d in date_range if d in all_dates}

    def gc(s,d): return price_data[s].get(d,{}).get('close')
    def go(s,d): return price_data[s].get(d,{}).get('open')

    for idx,date in enumerate(date_range):
        gi=date_to_gi.get(date)
        if gi is None or gi<72: equity.append(cash); continue

        # Regime gate
        reg=regime(date)
        if regime_policy=='bull_only' and reg!='Bull':
            # liquidate all if going into non-bull
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                p=pos.pop(sym); ev=p['qty']*fp
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'ret':(fp/p['ep']-1)*100,'exit':'Regime'})
            equity.append(cash); continue
        if regime_policy=='bull_flat' and reg=='Bear':
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                p=pos.pop(sym); ev=p['qty']*fp
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'ret':(fp/p['ep']-1)*100,'exit':'Regime'})
            equity.append(cash); continue

        # Effective size scale for 'scaled' policy
        eff_scale=1.0
        if regime_policy=='scaled':
            if reg=='Bear': eff_scale=0.0
            elif reg=='Flat': eff_scale=0.5

        if eff_scale==0.0:
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                p=pos.pop(sym); ev=p['qty']*fp
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'ret':(fp/p['ep']-1)*100,'exit':'Regime'})
            equity.append(cash); continue

        # SL
        for sym in list(pos):
            curr=gc(sym,date)
            if curr and curr<=pos[sym]['ep']*(1-SL_PCT/100):
                p=pos.pop(sym); fill=curr*(1-slip)
                ev=p['qty']*fill; cost=BROKERAGE+ev*STT+ev*EXCHANGE
                cash+=ev-cost
                trades.append({'pnl':(fill-p['ep'])*p['qty']-cost,'ret':(fill/p['ep']-1)*100,'exit':'SL'})

        # Rebalance
        if idx-last>=REBAL_DAYS:
            last=idx
            if selector=='sector_neutral':
                tgt=set(sector_neutral_top(gi))
            else:
                comp=composite(gi)
                tgt={s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N]}
            for sym in list(pos):
                if sym not in tgt:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                    p=pos.pop(sym); ev=p['qty']*fp
                    cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                    trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'ret':(fp/p['ep']-1)*100,'exit':'Rebal'})
            new=[s for s in tgt if s not in pos]
            avail_cap=(cash*0.95)*eff_scale
            if new and avail_cap>10_000:
                alloc=min(avail_cap/max(len(new),1),CAPITAL/TOP_N*eff_scale)
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
        trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'ret':(fp/p['ep']-1)*100,'exit':'EoP'})

    if not trades: return {'pf':0,'cagr':-100,'sharpe':0,'max_dd':0,'trades':0,'wr':0}
    wins=[t for t in trades if t['pnl']>0]; losses=[t for t in trades if t['pnl']<=0]
    gp=sum(t['pnl'] for t in wins); gl=abs(sum(t['pnl'] for t in losses))
    pf=gp/gl if gl>0 else (1.5 if gp>0 else 0)
    yrs=max(len(date_range)/252,0.1); fv=equity[-1] if equity else CAPITAL
    cagr=((fv/CAPITAL)**(1/yrs)-1)*100 if fv>0 else -100
    dr=[(equity[k]-equity[k-1])/equity[k-1] for k in range(1,len(equity)) if equity[k-1]>0]
    sharpe=statistics.mean(dr)/statistics.stdev(dr)*math.sqrt(252) if len(dr)>2 and statistics.stdev(dr)>0 else 0
    peak=CAPITAL; max_dd=0.0
    for v in equity:
        if v>peak: peak=v
        dd=(peak-v)/peak*100 if peak>0 else 0
        if dd>max_dd: max_dd=dd
    return {'pf':round(pf,3),'cagr':round(cagr,1),'sharpe':round(sharpe,3),
            'max_dd':round(max_dd,1),'trades':len(trades),'wr':round(len(wins)/len(trades)*100,1)}

SEP='='*100; sep='-'*100

# ══════════════════════════════════════════════════════════════════════════════
# PRIORITY 1 — COST STRESS TEST
# ══════════════════════════════════════════════════════════════════════════════
print(SEP)
print('  PRIORITY 1  --  COST STRESS TEST  (RS=60/EP=40, raw, no regime filter)')
print(f'  Nifty OOS CAGR: {NIFTY_OOS_CAGR:+.1f}%')
print(SEP)
print(f'  {"Slippage":>12}  {"Total cost/RT":>14}  {"IS PF":>7}  {"IS CAGR":>8}  '
      f'{"OOS PF":>7}  {"OOS CAGR":>9}  {"OOS Sh":>8}  {"MaxDD":>7}  {"Trades":>7}')
print(sep)

slip_levels = [0.002, 0.004, 0.006, 0.008]
p1_results = []
for slip in slip_levels:
    rt_cost = slip*2*100   # total round-trip slippage %
    m_is  = run_sim(IS_DATES,  slip=slip)
    m_oos = run_sim(OOS_DATES, slip=slip)
    beat = ' *' if m_oos['cagr']>NIFTY_OOS_CAGR else '  '
    p1_results.append({'slip':slip,'is':m_is,'oos':m_oos})
    print(f'  {slip*100:.1f}% each side  {rt_cost:.1f}% round-trip  '
          f'{m_is["pf"]:>7.3f}  {m_is["cagr"]:>+7.1f}%  '
          f'{m_oos["pf"]:>7.3f}  {m_oos["cagr"]:>+8.1f}%{beat}  '
          f'{m_oos["sharpe"]:>8.3f}  {m_oos["max_dd"]:>6.1f}%  {m_oos["trades"]:>7}')
print(sep)
# Find break-even slippage
breakeven = [r for r in p1_results if r['oos']['pf'] >= 1.0]
broken    = [r for r in p1_results if r['oos']['pf'] < 1.0]
print()
if breakeven:
    last_ok  = breakeven[-1]
    print(f'  Last profitable slippage: {last_ok["slip"]*100:.1f}% each side  '
          f'(OOS PF={last_ok["oos"]["pf"]:.3f}  CAGR={last_ok["oos"]["cagr"]:+.1f}%)')
if broken:
    first_fail=broken[0]
    print(f'  First unprofitable:       {first_fail["slip"]*100:.1f}% each side  '
          f'(OOS PF={first_fail["oos"]["pf"]:.3f}  CAGR={first_fail["oos"]["cagr"]:+.1f}%)')
    margin = broken[0]['slip']/BASE_SLIP
    print(f'  Safety margin: {margin:.0f}x baseline slippage before edge disappears.')
    if margin>=3: print('  VERDICT: COST-ROBUST. Edge survives 3x realistic slippage.')
    elif margin>=2: print('  VERDICT: MODERATE. Edge survives 2x but check live fills carefully.')
    else: print('  VERDICT: FRAGILE. Live slippage must stay at or below baseline.')

# ══════════════════════════════════════════════════════════════════════════════
# PRIORITY 2 — SECTOR-NEUTRAL VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  PRIORITY 2  --  SECTOR-NEUTRAL VALIDATION')
print('  Raw: any stock can win. Neutral: pick proportionally from each sector.')
print(SEP)
print(f'  {"Version":<28}  {"IS PF":>7}  {"IS CAGR":>8}  {"IS Sh":>7}  '
      f'{"OOS PF":>7}  {"OOS CAGR":>9}  {"OOS Sh":>8}  {"MaxDD":>7}  {"Trades":>7}')
print(sep)

configs = [
    ('Raw RS60/EP40',          'raw'),
    ('Sector-neutral RS60/EP40','sector_neutral'),
]
p2_results = {}
for label, sel in configs:
    m_is  = run_sim(IS_DATES,  selector=sel)
    m_oos = run_sim(OOS_DATES, selector=sel)
    p2_results[sel] = {'is': m_is, 'oos': m_oos}
    beat = ' *' if m_oos['cagr']>NIFTY_OOS_CAGR else '  '
    print(f'  {label:<28}  {m_is["pf"]:>7.3f}  {m_is["cagr"]:>+7.1f}%  {m_is["sharpe"]:>7.3f}  '
          f'{m_oos["pf"]:>7.3f}  {m_oos["cagr"]:>+8.1f}%{beat}  '
          f'{m_oos["sharpe"]:>8.3f}  {m_oos["max_dd"]:>6.1f}%  {m_oos["trades"]:>7}')
print(sep)
raw_oos = p2_results['raw']['oos'];  sn_oos = p2_results['sector_neutral']['oos']
alpha_lost = raw_oos['cagr'] - sn_oos['cagr']
print(f'\n  Alpha retained after sector neutralisation: '
      f'{sn_oos["cagr"]:+.1f}% vs {raw_oos["cagr"]:+.1f}% raw  '
      f'(lost {alpha_lost:.1f}pp)')
if sn_oos['pf']>=1.0 and sn_oos['cagr']>NIFTY_OOS_CAGR:
    print('  VERDICT: SECTOR-NEUTRAL STILL PROFITABLE AND BEATS NIFTY.')
    print('  Factor has genuine within-sector stock selection skill.')
elif sn_oos['pf']>=1.0:
    print('  VERDICT: SECTOR-NEUTRAL PROFITABLE but below Nifty.')
    print('  Within-sector skill exists but sector tilt is required to beat Nifty.')
else:
    print('  VERDICT: SECTOR-NEUTRAL FAILS. Edge is entirely from sector tilts, not stock selection.')

# ══════════════════════════════════════════════════════════════════════════════
# PRIORITY 3 — MARKET REGIME ENGINE
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  PRIORITY 3  --  MARKET REGIME ENGINE')
print('  Bull: Nifty > 200DMA and 50DMA > 200DMA')
print('  Flat: Nifty > 200DMA and 50DMA <= 200DMA')
print('  Bear: Nifty < 200DMA')
print(SEP)

# Regime breakdown of OOS period
regime_counts = {'Bull':0,'Flat':0,'Bear':0}
for d in OOS_DATES: regime_counts[regime(d)]+=1
print(f'  OOS regime breakdown: '
      f'Bull={regime_counts["Bull"]} days ({regime_counts["Bull"]/len(OOS_DATES)*100:.0f}%)  '
      f'Flat={regime_counts["Flat"]} days ({regime_counts["Flat"]/len(OOS_DATES)*100:.0f}%)  '
      f'Bear={regime_counts["Bear"]} days ({regime_counts["Bear"]/len(OOS_DATES)*100:.0f}%)\n')

print(f'  {"Policy":<35}  {"IS PF":>7}  {"IS CAGR":>8}  {"IS Sh":>7}  '
      f'{"OOS PF":>7}  {"OOS CAGR":>9}  {"OOS Sh":>8}  {"MaxDD":>7}  {"Trades":>7}')
print(sep)

regime_configs = [
    ('A) Always invested',          'always'),
    ('B) Bull only (cash in Flat+Bear)', 'bull_only'),
    ('C) Bull + Flat (cash in Bear)', 'bull_flat'),
    ('D) Bull 100% / Flat 50% / Bear 0%', 'scaled'),
]
p3_results = {}
for label, policy in regime_configs:
    m_is  = run_sim(IS_DATES,  regime_policy=policy)
    m_oos = run_sim(OOS_DATES, regime_policy=policy)
    p3_results[policy] = {'is': m_is, 'oos': m_oos}
    beat = ' *' if m_oos['cagr']>NIFTY_OOS_CAGR else '  '
    print(f'  {label:<35}  {m_is["pf"]:>7.3f}  {m_is["cagr"]:>+7.1f}%  {m_is["sharpe"]:>7.3f}  '
          f'{m_oos["pf"]:>7.3f}  {m_oos["cagr"]:>+8.1f}%{beat}  '
          f'{m_oos["sharpe"]:>8.3f}  {m_oos["max_dd"]:>6.1f}%  {m_oos["trades"]:>7}')
print(sep)

best_sharpe = max(regime_configs, key=lambda x: p3_results[x[1]]['oos']['sharpe'])
best_cagr   = max(regime_configs, key=lambda x: p3_results[x[1]]['oos']['cagr'])
best_dd     = min(regime_configs, key=lambda x: p3_results[x[1]]['oos']['max_dd'])
print(f'\n  Best OOS Sharpe  : {best_sharpe[0]}  ({p3_results[best_sharpe[1]]["oos"]["sharpe"]:.3f})')
print(f'  Best OOS CAGR    : {best_cagr[0]}  ({p3_results[best_cagr[1]]["oos"]["cagr"]:+.1f}%)')
print(f'  Lowest MaxDD     : {best_dd[0]}  ({p3_results[best_dd[1]]["oos"]["max_dd"]:.1f}%)')

# Risk-adjusted winner: Sharpe AND beats Nifty AND reduces MaxDD
winners=[lbl for lbl,pol in regime_configs
         if p3_results[pol]['oos']['sharpe']>p3_results['always']['oos']['sharpe']
         and p3_results[pol]['oos']['cagr']>NIFTY_OOS_CAGR]
if winners:
    print(f'\n  Policies improving on Always-invested: {", ".join(w for w in winners)}')
    print('  VERDICT: Regime filtering adds risk-adjusted value. Adopt best policy.')
else:
    print('\n  VERDICT: No regime policy consistently improves on Always-invested.')
    print('  Regime filter is not adding value in this OOS period.')

# ══════════════════════════════════════════════════════════════════════════════
# PRIORITY 4 — JUNE 15 CANDIDATE LIST
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  PRIORITY 4  --  JUNE 15, 2026 CANDIDATE LIST')
print('  Signal computed on latest available close. Enter at Monday June 16 open.')
print(SEP)

# Use most recent date index
latest_gi = N - 1
while latest_gi > 0 and latest_gi not in _raw_cache:
    latest_gi -= 1
# Ensure it's computed
get_raw(latest_gi)

raw = _raw_cache.get(latest_gi, {})
raw_rs = raw.get('rs', {}); raw_ep = raw.get('ep', {})

# Build full ranking table
def prank(d):
    items=sorted(d.items(),key=lambda x:x[1]); n=len(items)
    return {s:(r+1)/n*100 for r,(s,_) in enumerate(items)}

rnk_rs = prank(raw_rs) if raw_rs else {}
rnk_ep = prank(raw_ep) if raw_ep else {}
common = set(rnk_rs) & set(rnk_ep)

scored = []
for sym in common:
    rs_rank  = rnk_rs[sym]; ep_rank = rnk_ep[sym]
    composite_score = W_RS*rs_rank + W_EP*ep_rank
    raw_rs_val = raw_rs.get(sym, 0); raw_ep_val = raw_ep.get(sym, 0)
    scored.append({
        'sym': sym, 'composite': composite_score,
        'rs_rank': rs_rank, 'ep_rank': ep_rank,
        'rs_raw': raw_rs_val, 'ep_raw': raw_ep_val,
        'sector': SECTOR.get(sym, 'Others'),
    })

scored.sort(key=lambda x: -x['composite'])

# Current market regime
today = all_dates[-1]
today_regime = regime(today)
nd = nifty_dma.get(today, {})
print(f'  Signal date   : {today}  (latest available)')
print(f'  Enter date    : June 16, 2026 open (first trading day after signal)')
print(f'  Market regime : {today_regime}  '
      f'(Nifty={nd.get("close",0):.0f}  50DMA={nd.get("dma50",0):.0f}  200DMA={nd.get("dma200",0):.0f})')

# Best regime policy from P3
best_pol_label, best_pol = best_sharpe   # use best-Sharpe policy
pol_oos = p3_results[best_pol]['oos']
active_policy = best_pol

if active_policy=='bull_only' and today_regime!='Bull':
    print(f'\n  REGIME GATE: Policy "{best_pol_label}" requires Bull market.')
    print(f'  Current regime: {today_regime}.  --> DO NOT DEPLOY tomorrow.')
elif active_policy=='bull_flat' and today_regime=='Bear':
    print(f'\n  REGIME GATE: Policy "{best_pol_label}" exits in Bear market.')
    print(f'  Current regime: {today_regime}.  --> DO NOT DEPLOY tomorrow.')
elif active_policy=='scaled' and today_regime=='Bear':
    print(f'\n  REGIME GATE: Policy "Scaled" is flat in Bear market.  --> CASH tomorrow.')
else:
    scale_note = '(50% position size)' if active_policy=='scaled' and today_regime=='Flat' else '(full size)'
    print(f'\n  REGIME GATE: {today_regime} -- deploy is ACTIVE {scale_note}')

per_stock_cap = CAPITAL / TOP_N
print()
print(f'  {"Rank":<5}  {"Symbol":<14}  {"Sector":<12}  {"RS rank":>8}  '
      f'{"EP rank":>8}  {"Composite":>10}  {"RS 63d%":>9}  {"EP best%":>9}  {"Alloc":>10}')
print(sep)

for rank, s in enumerate(scored[:TOP_N], 1):
    alloc_pct = 100.0 / TOP_N
    print(f'  {rank:<5}  {s["sym"]:<14}  {s["sector"]:<12}  '
          f'{s["rs_rank"]:>7.1f}  {s["ep_rank"]:>8.1f}  {s["composite"]:>10.2f}  '
          f'{s["rs_raw"]:>+8.2f}%  {s["ep_raw"]:>8.2f}%  '
          f'{alloc_pct:>8.1f}%  Rs.{per_stock_cap:,.0f}')

print(sep)
print(f'  Total capital: Rs.{CAPITAL:,.0f}  |  Per position: Rs.{per_stock_cap:,.0f}  '
      f'|  Top-{TOP_N} equal weight')

# Next rebalance check: which of today's top-10 are new vs existing
print()
print(f'  NOTE: This is the entry candidate list. On next rebalance (10 trading days)')
print(f'  re-run this script to see which positions to hold, add, or exit.')

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY VERDICT
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  FINAL VALIDATION SUMMARY  --  RS=60% / EP=40%')
print(SEP)

baseline_oos = p1_results[0]['oos']  # 0.2% slip
p1_pass = p1_results[1]['oos']['pf'] >= 1.0   # survives 2x
p2_pass = p2_results['sector_neutral']['oos']['pf'] >= 1.0
best_regime_cagr = max(p3_results[pol]['oos']['cagr'] for _,pol in regime_configs)
p3_pass = best_regime_cagr > baseline_oos['cagr']

checks = [
    ('Cost stress (2x slippage PF > 1.0)',       p1_pass,   f'PF={p1_results[1]["oos"]["pf"]:.3f} at 0.4% slip'),
    ('Sector-neutral PF > 1.0',                  p2_pass,   f'PF={p2_results["sector_neutral"]["oos"]["pf"]:.3f}'),
    ('Regime filter improves CAGR',               p3_pass,   f'Best={best_regime_cagr:+.1f}% vs always={baseline_oos["cagr"]:+.1f}%'),
]

all_pass = all(v for _,v,_ in checks)
for label, passed, detail in checks:
    icon = 'PASS' if passed else 'FAIL'
    print(f'  [{icon}]  {label:<42}  {detail}')

print()
if all_pass:
    print('  ALL THREE CHECKS PASSED.')
    print('  RS=60/EP=40 survives realistic costs, sector stripping, and regime filtering.')
    print('  RECOMMENDATION: FREEZE RESEARCH. Proceed to deployment scaffold.')
else:
    failed = [label for label,v,_ in checks if not v]
    print(f'  FAILED: {", ".join(failed)}')
    print('  Do not deploy until failed checks are resolved.')
