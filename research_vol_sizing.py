"""
research_vol_sizing.py — Compare 4 position sizing methods.
All use the SAME signal generation: RS60/EP40 + Policy C + 50DMA filter.
Only the allocation per position changes.

Methods:
  1. Equal weight (baseline): Rs.50,000 per position
  2. ATR sizing: allocate inversely proportional to 14-day ATR
  3. Volatility parity: allocate so each position contributes equal risk
  4. Inverse volatility: weight by 1/stdev(20d returns)

Run: python research_vol_sizing.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time, math, statistics, warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

W_RS=0.60; W_EP=0.40; TOP_N=10; REBAL_DAYS=10; SL_PCT=10.0
BROKERAGE=20.0; STT=0.001; EXCHANGE=0.0000345
CAPITAL=500_000.0

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

print("VOLATILITY SIZING RESEARCH — fetching data...")
t0 = time.time()
price_data = {}; valid = []
for i, (ticker, sym) in enumerate(STOCKS):
    try:
        df = yf.Ticker(ticker).history(period='5y', interval='1d', auto_adjust=True)
        if not df.empty:
            d = {str(ts.date()): {'open': float(r['Open']), 'close': float(r['Close']),
                                   'high': float(r['High']), 'low': float(r['Low']),
                                   'vol': float(r.get('Volume', 0) or 0)}
                 for ts, r in df.iterrows()}
            if len(d) >= 300:
                price_data[sym] = d; valid.append(sym)
    except Exception: pass
    if (i+1) % 20 == 0: print(f"  ... {i+1}/{len(STOCKS)}")
    time.sleep(0.22)

nifty_raw = {}
try:
    df = yf.Ticker('^NSEI').history(period='5y', interval='1d', auto_adjust=True)
    nifty_raw = {str(ts.date()): float(r['Close']) for ts, r in df.iterrows()}
except Exception: pass
print(f"Data: {len(valid)} stocks, {len(nifty_raw)} Nifty days in {time.time()-t0:.0f}s")

all_dates = sorted(nifty_raw.keys())
N = len(all_dates)
IS_END = int(N*0.6)
IS_DATES = all_dates[:IS_END]
OOS_DATES = all_dates[IS_END:]
n_s=nifty_raw.get(OOS_DATES[0],1); n_e=nifty_raw.get(OOS_DATES[-1],1)
NIFTY_OOS_CAGR=((n_e/n_s)**(252/len(OOS_DATES))-1)*100

nifty_dma = {}
nc_list = [(d, nifty_raw[d]) for d in all_dates]
for idx,(d,c) in enumerate(nc_list):
    d50=sum(v for _,v in nc_list[max(0,idx-49):idx+1])/min(idx+1,50)
    d200=sum(v for _,v in nc_list[max(0,idx-199):idx+1])/min(idx+1,200)
    nifty_dma[d] = {'close':c,'dma50':d50,'dma200':d200}
def regime(date):
    r=nifty_dma.get(date)
    if not r: return 'Bull'
    if r['close']<r['dma200']: return 'Bear'
    if r['dma50']<=r['dma200']: return 'Flat'
    return 'Bull'

_raw_cache = {}
def get_raw(gi):
    if gi in _raw_cache: return _raw_cache[gi]
    if gi<72: return {}
    dn=all_dates[gi]
    nc=nifty_raw.get(dn); np_=nifty_raw.get(all_dates[gi-63]) if gi>=63 else None
    raw_rs={}; raw_ep={}
    for sym in valid:
        c=price_data[sym]
        sd=[d for d in all_dates[max(0,gi-74):gi+1] if d in c]
        if len(sd)<50: continue
        if nc and np_:
            cn=c.get(dn,{}).get('close'); cp=c.get(all_dates[gi-63],{}).get('close')
            if cn and cp: raw_rs[sym]=(cn/cp-1)*100-(nc/np_-1)*100
        ed=sd[-63:]
        evols=[c[d]['vol'] for d in ed if c[d]['vol']>0]
        av=sum(evols)/len(evols) if evols else 0
        ep=0.0
        for j in range(1,len(ed)):
            cj=c.get(ed[j]); cjm=c.get(ed[j-1])
            if not(cj and cjm and cjm['close']>0): continue
            dr=cj['close']/cjm['close']-1
            if dr>0.02 and av>0 and cj['vol']>1.5*av: ep=max(ep,dr*100)
        raw_ep[sym]=ep
    _raw_cache[gi]={'rs':raw_rs,'ep':raw_ep}
    return _raw_cache[gi]

def composite(gi):
    raw=get_raw(gi)
    if not raw: return {}
    def pr(d):
        items=sorted(d.items(),key=lambda x:x[1]); n=len(items)
        return {s:(r+1)/n*100 for r,(s,_) in enumerate(items)}
    rnks={}
    if raw['rs']: rnks['rs']=pr(raw['rs'])
    if raw['ep']: rnks['ep']=pr(raw['ep'])
    if not rnks: return {}
    active=list(rnks.keys())
    tw=sum({'rs':W_RS,'ep':W_EP}[f] for f in active)
    syms=set.intersection(*[set(rnks[f].keys()) for f in active])
    return {s:sum({'rs':W_RS,'ep':W_EP}[f]*rnks[f][s] for f in active)/tw for s in syms}

def stock_above_50dma(sym, date, gi):
    c=price_data.get(sym,{})
    dw=[d for d in all_dates[max(0,gi-60):gi+1] if d in c]
    if len(dw)<50: return True
    cls=[c[d]['close'] for d in dw[-50:]]
    d50=sum(cls)/len(cls)
    cur=c.get(date,{}).get('close')
    if cur is None: return True
    return cur>d50

print('Pre-computing factors...')
gi=72
while gi<N: get_raw(gi); gi+=REBAL_DAYS
print(f'Cached {len(_raw_cache)} points.\n')

# ── Volatility measures ───────────────────────────────────────────────────────
def compute_atr(sym, date, gi, period=14):
    """14-day Average True Range."""
    c = price_data.get(sym, {})
    recent = [d for d in all_dates[max(0,gi-period-5):gi+1] if d in c]
    if len(recent) < period+1: return None
    trs = []
    for i in range(1, len(recent)):
        bar = c[recent[i]]
        prev_c = c[recent[i-1]]['close']
        tr = max(bar['high']-bar['low'], abs(bar['high']-prev_c), abs(bar['low']-prev_c))
        trs.append(tr)
    return sum(trs[-period:]) / period if len(trs) >= period else None

def compute_vol(sym, date, gi, period=20):
    """20-day realized volatility (stdev of daily returns)."""
    c = price_data.get(sym, {})
    recent = [d for d in all_dates[max(0,gi-period-5):gi+1] if d in c]
    if len(recent) < period+1: return None
    rets = []
    for i in range(1, len(recent)):
        p0 = c[recent[i-1]]['close']
        p1 = c[recent[i]]['close']
        if p0 > 0: rets.append(p1/p0 - 1)
    if len(rets) < period: return None
    return statistics.stdev(rets[-period:])


# ── Allocation methods ────────────────────────────────────────────────────────
def alloc_equal(syms, cash, date, gi):
    """Equal weight: CAPITAL/TOP_N per position."""
    per = min(cash*0.95/max(len(syms),1), CAPITAL/TOP_N)
    return {s: per for s in syms}

def alloc_atr(syms, cash, date, gi):
    """ATR-based: allocate inversely proportional to ATR.
    High ATR stock → smaller position. Targets equal dollar-risk per position."""
    atrs = {}
    for s in syms:
        a = compute_atr(s, date, gi)
        if a and a > 0: atrs[s] = a
    if not atrs: return alloc_equal(syms, cash, date, gi)
    inv_atrs = {s: 1.0/a for s,a in atrs.items()}
    total_inv = sum(inv_atrs.values())
    avail = cash * 0.95
    result = {}
    for s in syms:
        if s in inv_atrs:
            w = inv_atrs[s] / total_inv
            result[s] = min(avail * w, CAPITAL/TOP_N * 2)  # cap at 2x equal weight
        else:
            result[s] = CAPITAL/TOP_N
    return result

def alloc_vol_parity(syms, cash, date, gi):
    """Volatility parity: each position contributes equal portfolio variance.
    weight_i proportional to 1/vol_i, normalized."""
    vols = {}
    for s in syms:
        v = compute_vol(s, date, gi)
        if v and v > 0: vols[s] = v
    if not vols: return alloc_equal(syms, cash, date, gi)
    inv_vols = {s: 1.0/v for s,v in vols.items()}
    total = sum(inv_vols.values())
    avail = cash * 0.95
    result = {}
    for s in syms:
        if s in inv_vols:
            w = inv_vols[s] / total
            result[s] = min(avail * w, CAPITAL/TOP_N * 2)
        else:
            result[s] = CAPITAL/TOP_N
    return result

def alloc_inv_vol(syms, cash, date, gi):
    """Inverse volatility: simple 1/stdev weighting.
    Same as vol parity but without the squared-risk interpretation."""
    return alloc_vol_parity(syms, cash, date, gi)  # mathematically equivalent


# ── Simulation engine ─────────────────────────────────────────────────────────
def run_sim(date_range, slip, alloc_fn):
    cash=CAPITAL; pos={}; trades=[]; equity=[]; last=-999
    date_to_gi={d:all_dates.index(d) for d in date_range if d in all_dates}
    turnover=0.0

    def gc(s,d): return price_data[s].get(d,{}).get('close')
    def go(s,d): return price_data[s].get(d,{}).get('open')

    for idx,date in enumerate(date_range):
        gi=date_to_gi.get(date)
        if gi is None or gi<72: equity.append(cash); continue

        if regime(date)=='Bear':
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                p=pos.pop(sym); ev=p['qty']*fp
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost; turnover+=ev
                trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'exit':'Regime'})
            equity.append(cash); continue

        for sym in list(pos):
            curr=gc(sym,date)
            if curr and curr<=pos[sym]['ep']*(1-SL_PCT/100):
                p=pos.pop(sym); fill=curr*(1-slip)
                ev=p['qty']*fill; cost=BROKERAGE+ev*STT+ev*EXCHANGE
                cash+=ev-cost; turnover+=ev
                trades.append({'pnl':(fill-p['ep'])*p['qty']-cost,'exit':'SL'})

        if idx-last>=REBAL_DAYS:
            last=idx
            comp=composite(gi)
            comp={s:sc for s,sc in comp.items() if stock_above_50dma(s,date,gi)}
            tgt={s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N]}

            for sym in list(pos):
                if sym not in tgt:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                    p=pos.pop(sym); ev=p['qty']*fp
                    cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost; turnover+=ev
                    trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'exit':'Rebal'})

            new=[s for s in tgt if s not in pos]
            if new and cash*0.95>10_000:
                allocs = alloc_fn(new, cash, date, gi)
                for sym in new:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fpd=go(sym,nd) or gc(sym,date)
                    if not fpd: continue
                    fill=fpd*(1+slip)
                    alloc_amt = allocs.get(sym, CAPITAL/TOP_N)
                    qty=max(1,int(alloc_amt/fill))
                    cost=BROKERAGE+qty*fill*EXCHANGE
                    if cash>=qty*fill+cost:
                        cash-=qty*fill+cost; pos[sym]={'qty':qty,'ep':fill}
                        turnover+=qty*fill

        fv=cash+sum(p['qty']*(gc(s,date) or p['ep']) for s,p in pos.items())
        equity.append(fv)

    for s,p in list(pos.items()):
        fp=(gc(s,date_range[-1]) or p['ep'])*(1-slip)
        ev=p['qty']*fp; cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost; turnover+=ev
        trades.append({'pnl':(fp-p['ep'])*p['qty']-cost,'exit':'EoP'})

    if not trades: return {'cagr':0,'sharpe':0,'max_dd':0,'trades':0,'wr':0,'pf':0,'fv':CAPITAL,'turnover':0}
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
    avg_eq=sum(equity)/len(equity) if equity else CAPITAL
    ann_turn=(turnover/avg_eq/yrs)*100 if avg_eq>0 else 0
    sl_exits=sum(1 for t in trades if t.get('exit')=='SL')
    return {'cagr':round(cagr,2),'sharpe':round(sharpe,3),'max_dd':round(max_dd,1),
            'trades':len(trades),'wr':round(len(wins)/len(trades)*100,1),
            'pf':round(pf,3),'fv':round(fv,0),'turnover':round(ann_turn,1),
            'sl_exits':sl_exits}

# ═══════════════════════════════════════════════════════════════════════════════
# RUN ALL SIZING METHODS AT 3 SLIPPAGE LEVELS
# ═══════════════════════════════════════════════════════════════════════════════
SEP='='*120
sep='-'*120

methods = [
    ("Equal weight (baseline)", alloc_equal),
    ("ATR sizing (1/ATR14)",    alloc_atr),
    ("Volatility parity",       alloc_vol_parity),
    ("Inverse volatility",      alloc_inv_vol),
]
slips = [0.002, 0.004, 0.006]

print(f'\n{SEP}')
print(f'  POSITION SIZING RESEARCH — RS60/EP40 + Policy C + 50DMA')
print(f'  Signal generation IDENTICAL across all methods. Only allocation changes.')
print(f'  IS: {IS_DATES[0]} to {IS_DATES[-1]}  |  OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}')
print(f'  Universe: {len(valid)} stocks  |  Nifty OOS: {NIFTY_OOS_CAGR:+.1f}%')
print(SEP)

# OOS at baseline slip
print(f'\n  OOS RESULTS — 0.2% slippage (baseline)')
print(sep)
print(f'  {"Method":<28} {"CAGR":>8} {"Sharpe":>7} {"MaxDD":>6} {"WR":>6} {"PF":>6} {"Trades":>7} {"SL":>4} {"Turn%":>7} {"FinalVal":>12}')
print(sep)

oos_base = {}
for label, fn in methods:
    m = run_sim(OOS_DATES, 0.002, fn)
    oos_base[label] = m
    beat = '*' if m['cagr'] > NIFTY_OOS_CAGR else ' '
    print(f'  {label:<28} {m["cagr"]:>+7.2f}%{beat} {m["sharpe"]:>7.3f} {m["max_dd"]:>5.1f}% {m["wr"]:>5.1f}% {m["pf"]:>6.3f} {m["trades"]:>7} {m["sl_exits"]:>4} {m["turnover"]:>6.1f}% {m["fv"]:>11,.0f}')
print(sep)

# IS for comparison
print(f'\n  IS RESULTS — 0.2% slippage')
print(sep)
print(f'  {"Method":<28} {"CAGR":>8} {"Sharpe":>7} {"MaxDD":>6} {"WR":>6} {"PF":>6} {"Trades":>7}')
print(sep)
for label, fn in methods:
    m = run_sim(IS_DATES, 0.002, fn)
    print(f'  {label:<28} {m["cagr"]:>+7.2f}% {m["sharpe"]:>7.3f} {m["max_dd"]:>5.1f}% {m["wr"]:>5.1f}% {m["pf"]:>6.3f} {m["trades"]:>7}')
print(sep)

# Slippage sensitivity
print(f'\n  SLIPPAGE SENSITIVITY (OOS CAGR at each slippage level)')
print(sep)
print(f'  {"Method":<28} {"0.2%":>10} {"0.4%":>10} {"0.6%":>10} {"Degrades":>10}')
print(sep)
for label, fn in methods:
    cagrs = []
    for sl in slips:
        m = run_sim(OOS_DATES, sl, fn)
        cagrs.append(m['cagr'])
    degrade = cagrs[0] - cagrs[2]
    print(f'  {label:<28} {cagrs[0]:>+9.2f}% {cagrs[1]:>+9.2f}% {cagrs[2]:>+9.2f}% {degrade:>9.2f}pp')
print(sep)

# ── Incremental delta ────────────────────────────────────────────────────────
print(f'\n  INCREMENTAL DELTA vs EQUAL WEIGHT (OOS, 0.2% slip)')
print(sep)
base = oos_base["Equal weight (baseline)"]
print(f'  {"Method":<28} {"dCAGR":>8} {"dSharpe":>9} {"dMaxDD":>8} {"dWR":>7} {"dPF":>7}')
print(sep)
for label, _ in methods:
    m = oos_base[label]
    if label == "Equal weight (baseline)":
        print(f'  {label:<28} {"(base)":>8} {"(base)":>9} {"(base)":>8} {"(base)":>7} {"(base)":>7}')
    else:
        print(f'  {label:<28} {m["cagr"]-base["cagr"]:>+7.2f}% {m["sharpe"]-base["sharpe"]:>+8.3f} {m["max_dd"]-base["max_dd"]:>+7.1f}% {m["wr"]-base["wr"]:>+6.1f}% {m["pf"]-base["pf"]:>+6.3f}')
print(sep)

# ── Verdict ───────────────────────────────────────────────────────────────────
print(f'\n{SEP}')
print('  VERDICT')
print(SEP)
best_sharpe_label = max(oos_base, key=lambda k: oos_base[k]['sharpe'])
best_cagr_label = max(oos_base, key=lambda k: oos_base[k]['cagr'])
best_dd_label = min(oos_base, key=lambda k: oos_base[k]['max_dd'])
print(f'  Best Sharpe:  {best_sharpe_label} ({oos_base[best_sharpe_label]["sharpe"]:.3f})')
print(f'  Best CAGR:    {best_cagr_label} ({oos_base[best_cagr_label]["cagr"]:+.2f}%)')
print(f'  Lowest MaxDD: {best_dd_label} ({oos_base[best_dd_label]["max_dd"]:.1f}%)')

# Check if any method beats baseline on ALL three key metrics
baseline = oos_base["Equal weight (baseline)"]
for label, m in oos_base.items():
    if label == "Equal weight (baseline)": continue
    beats_cagr = m['cagr'] > baseline['cagr']
    beats_sharpe = m['sharpe'] > baseline['sharpe']
    beats_dd = m['max_dd'] < baseline['max_dd']
    if beats_cagr and beats_sharpe and beats_dd:
        print(f'\n  {label} BEATS baseline on all 3 metrics (CAGR, Sharpe, DD).')
        print(f'  RECOMMENDATION: Consider adopting after paper trading validation.')
    elif beats_sharpe and beats_dd:
        print(f'\n  {label} improves risk-adjusted (Sharpe+DD) but costs CAGR.')
        print(f'  Adopt only if drawdown reduction is the priority.')

print(SEP)
