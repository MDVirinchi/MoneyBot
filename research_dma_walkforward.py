"""
research_dma_walkforward.py — Multi-window walk-forward validation.
Tests 200, 210, 220, 230 DMA across 4 independent OOS windows:
  Window 1: 2018-2020  (if data available)
  Window 2: 2020-2022
  Window 3: 2022-2024
  Window 4: 2024-2026

If 220/230 consistently wins across every window, the result is robust.
If it only wins in one window, it's period-specific luck.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import time, math, statistics, warnings, logging
warnings.filterwarnings('ignore'); logging.disable(logging.CRITICAL)
import yfinance as yf

W_RS=0.60; W_EP=0.40; TOP_N=10; REBAL_DAYS=10; SL_PCT=10.0
BROKERAGE=20.0; STT=0.001; EXCHANGE=0.0000345; SLIP=0.002; CAPITAL=500_000.0

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

print("WALK-FORWARD DMA VALIDATION — fetching data...")
t0=time.time()
price_data={}; valid=[]
for i,(ticker,sym) in enumerate(STOCKS):
    try:
        df=yf.Ticker(ticker).history(period='max',interval='1d',auto_adjust=True)
        if not df.empty:
            d={str(ts.date()):{'open':float(r['Open']),'close':float(r['Close']),
               'vol':float(r.get('Volume',0) or 0)} for ts,r in df.iterrows()}
            if len(d)>=300: price_data[sym]=d; valid.append(sym)
    except: pass
    if (i+1)%20==0: print(f"  ... {i+1}/{len(STOCKS)}")
    time.sleep(0.22)
nifty_raw={}
try:
    df=yf.Ticker('^NSEI').history(period='max',interval='1d',auto_adjust=True)
    nifty_raw={str(ts.date()):float(r['Close']) for ts,r in df.iterrows()}
except: pass
print(f"Data: {len(valid)} stocks, {len(nifty_raw)} Nifty days in {time.time()-t0:.0f}s")

all_dates=sorted(nifty_raw.keys()); N=len(all_dates)

nc_list=[(d,nifty_raw[d]) for d in all_dates]
nifty_dma_all={}
for dma in [200,210,220,230]:
    vals={}
    for idx,(d,c) in enumerate(nc_list):
        w=min(idx+1,dma)
        vals[d]=sum(v for _,v in nc_list[max(0,idx-dma+1):idx+1])/w
    nifty_dma_all[dma]=vals

nifty_50dma={}
for idx,(d,c) in enumerate(nc_list):
    nifty_50dma[d]=sum(v for _,v in nc_list[max(0,idx-49):idx+1])/min(idx+1,50)

def regime_at(date,dma_period):
    c=nifty_raw.get(date); dma=nifty_dma_all[dma_period].get(date); d50=nifty_50dma.get(date)
    if not c or not dma: return 'Bull'
    if c<dma: return 'Bear'
    if d50 and d50<=dma: return 'Flat'
    return 'Bull'

_raw_cache={}
def get_raw(gi):
    if gi in _raw_cache: return _raw_cache[gi]
    if gi<72: return {}
    dn=all_dates[gi]; nc=nifty_raw.get(dn)
    np_=nifty_raw.get(all_dates[gi-63]) if gi>=63 else None
    raw_rs={}; raw_ep={}
    for sym in valid:
        c=price_data[sym]; sd=[d for d in all_dates[max(0,gi-74):gi+1] if d in c]
        if len(sd)<50: continue
        if nc and np_:
            cn=c.get(dn,{}).get('close'); cp=c.get(all_dates[gi-63],{}).get('close')
            if cn and cp: raw_rs[sym]=(cn/cp-1)*100-(nc/np_-1)*100
        ed=sd[-63:]; evols=[c[d]['vol'] for d in ed if c[d]['vol']>0]
        av=sum(evols)/len(evols) if evols else 0; ep=0.0
        for j in range(1,len(ed)):
            cj=c.get(ed[j]); cjm=c.get(ed[j-1])
            if not(cj and cjm and cjm['close']>0): continue
            dr=cj['close']/cjm['close']-1
            if dr>0.02 and av>0 and cj['vol']>1.5*av: ep=max(ep,dr*100)
        raw_ep[sym]=ep
    _raw_cache[gi]={'rs':raw_rs,'ep':raw_ep}; return _raw_cache[gi]
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
    active=list(rnks.keys()); tw=sum({'rs':W_RS,'ep':W_EP}[f] for f in active)
    syms=set.intersection(*[set(rnks[f].keys()) for f in active])
    return {s:sum({'rs':W_RS,'ep':W_EP}[f]*rnks[f][s] for f in active)/tw for s in syms}
def stock_above_50dma(sym,date,gi):
    c=price_data.get(sym,{}); dw=[d for d in all_dates[max(0,gi-60):gi+1] if d in c]
    if len(dw)<50: return True
    cls=[c[d]['close'] for d in dw[-50:]]; d50=sum(cls)/len(cls)
    cur=c.get(date,{}).get('close')
    if cur is None: return True
    return cur>d50

print('Pre-computing factors...')
gi=72
while gi<N: get_raw(gi); gi+=REBAL_DAYS
print(f'Cached {len(_raw_cache)} points.\n')

def run_sim(date_range, dma_period, slip=SLIP):
    cash=CAPITAL; pos={}; trades=[]; equity=[]; last=-999
    date_to_gi={d:all_dates.index(d) for d in date_range if d in all_dates}
    def gc(s,d): return price_data[s].get(d,{}).get('close')
    def go(s,d): return price_data[s].get(d,{}).get('open')
    for idx,date in enumerate(date_range):
        gi=date_to_gi.get(date)
        if gi is None or gi<72: equity.append(cash); continue
        if regime_at(date,dma_period)=='Bear':
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                p=pos.pop(sym); ev=p['qty']*fp; cost=BROKERAGE+ev*STT+ev*EXCHANGE
                cash+=ev-cost; trades.append({'pnl':(fp-p['ep'])*p['qty']-cost})
            equity.append(cash); continue
        for sym in list(pos):
            curr=gc(sym,date)
            if curr and curr<=pos[sym]['ep']*(1-SL_PCT/100):
                p=pos.pop(sym); fill=curr*(1-slip); ev=p['qty']*fill
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({'pnl':(fill-p['ep'])*p['qty']-cost})
        if idx-last>=REBAL_DAYS:
            last=idx; comp=composite(gi)
            comp={s:sc for s,sc in comp.items() if stock_above_50dma(s,date,gi)}
            tgt={s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N]}
            for sym in list(pos):
                if sym not in tgt:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                    p=pos.pop(sym); ev=p['qty']*fp; cost=BROKERAGE+ev*STT+ev*EXCHANGE
                    cash+=ev-cost; trades.append({'pnl':(fp-p['ep'])*p['qty']-cost})
            new=[s for s in tgt if s not in pos]; avail=cash*0.95
            if new and avail>10_000:
                alloc=min(avail/max(len(new),1),CAPITAL/TOP_N)
                for sym in new:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fpd=go(sym,nd) or gc(sym,date)
                    if not fpd: continue
                    fill=fpd*(1+slip); qty=max(1,int(alloc/fill))
                    cost=BROKERAGE+qty*fill*EXCHANGE
                    if cash>=qty*fill+cost: cash-=qty*fill+cost; pos[sym]={'qty':qty,'ep':fill}
        fv=cash+sum(p['qty']*(gc(s,date) or p['ep']) for s,p in pos.items()); equity.append(fv)
    for s,p in list(pos.items()):
        fp=(gc(s,date_range[-1]) or p['ep'])*(1-slip); ev=p['qty']*fp
        cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
        trades.append({'pnl':(fp-p['ep'])*p['qty']-cost})
    if not trades: return {'cagr':0,'sharpe':0,'max_dd':0}
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
    return {'cagr':round(cagr,2),'sharpe':round(sharpe,3),'max_dd':round(max_dd,1),
            'trades':len(trades),'wr':round(len(wins)/len(trades)*100,1) if trades else 0,
            'pf':round(pf,3)}

# Define windows
windows = []
for year_start in range(2018, 2025, 2):
    start_str = f"{year_start}-06-01"
    end_str = f"{year_start+2}-06-01"
    w_dates = [d for d in all_dates if start_str <= d < end_str]
    if len(w_dates) >= 200:
        windows.append((f"{year_start}-{year_start+2}", w_dates))

dma_options = [200, 210, 220, 230]
SEP='='*100; sep='-'*100

print(f'{SEP}')
print(f'  WALK-FORWARD DMA VALIDATION')
print(f'  Testing 200/210/220/230 DMA across {len(windows)} independent 2-year windows')
print(f'  All data: {all_dates[0]} to {all_dates[-1]} ({N} days)')
print(SEP)

# Main results table
print(f'\n  {"Window":<12} {"Days":>5}', end='')
for dma in dma_options: print(f'  {"DMA"+str(dma):>12}', end='')
print(f'  {"Winner":>8}')
print(sep)

win_count = {d:0 for d in dma_options}
all_results = {}

for wname, wdates in windows:
    print(f'  {wname:<12} {len(wdates):>5}', end='')
    best_sharpe = -999
    best_dma = 200
    for dma in dma_options:
        m = run_sim(wdates, dma)
        all_results[(wname,dma)] = m
        print(f'  {m["cagr"]:>+6.1f}%/{m["sharpe"]:.2f}', end='')
        if m['sharpe'] > best_sharpe:
            best_sharpe = m['sharpe']
            best_dma = dma
    win_count[best_dma] += 1
    print(f'  {best_dma:>6}d')

print(sep)
print(f'  {"WINS":<12} {"":>5}', end='')
for dma in dma_options:
    print(f'  {win_count[dma]:>12}', end='')
print()

# Detailed per-window
for wname, wdates in windows:
    print(f'\n  --- {wname} ---')
    print(f'  {"DMA":>5} {"CAGR":>8} {"Sharpe":>7} {"MaxDD":>6} {"WR":>6} {"PF":>6} {"Trades":>7}')
    for dma in dma_options:
        m = all_results[(wname,dma)]
        best = ' <<<' if m['sharpe'] == max(all_results[(wname,d)]['sharpe'] for d in dma_options) else ''
        print(f'  {dma:>4}d {m["cagr"]:>+7.2f}% {m["sharpe"]:>7.3f} {m["max_dd"]:>5.1f}% '
              f'{m["wr"]:>5.1f}% {m["pf"]:>6.3f} {m["trades"]:>7}{best}')

# Average across all windows
print(f'\n{SEP}')
print(f'  AVERAGE ACROSS ALL WINDOWS')
print(sep)
print(f'  {"DMA":>5} {"Avg CAGR":>10} {"Avg Sharpe":>11} {"Avg MaxDD":>10} {"Windows Won":>12} {"Consistency":>12}')
print(sep)
for dma in dma_options:
    cagrs = [all_results[(w,dma)]['cagr'] for w,_ in windows]
    sharpes = [all_results[(w,dma)]['sharpe'] for w,_ in windows]
    dds = [all_results[(w,dma)]['max_dd'] for w,_ in windows]
    consistency = sum(1 for c in cagrs if c > 0) / len(cagrs) * 100
    deployed = ' <<<' if dma == 200 else ''
    print(f'  {dma:>4}d {statistics.mean(cagrs):>+9.2f}% {statistics.mean(sharpes):>10.3f} '
          f'{statistics.mean(dds):>9.1f}% {win_count[dma]:>12} {consistency:>11.0f}%{deployed}')
print(sep)

# Verdict
print(f'\n{SEP}')
print(f'  VERDICT')
print(SEP)
most_wins = max(dma_options, key=lambda d: win_count[d])
best_avg_sharpe = max(dma_options, key=lambda d: statistics.mean([all_results[(w,d)]['sharpe'] for w,_ in windows]))
print(f'  Most windows won: {most_wins}-DMA ({win_count[most_wins]}/{len(windows)})')
print(f'  Best avg Sharpe:  {best_avg_sharpe}-DMA ({statistics.mean([all_results[(w,best_avg_sharpe)]["sharpe"] for w,_ in windows]):.3f})')

if most_wins == best_avg_sharpe and most_wins != 200:
    print(f'\n  {most_wins}-DMA CONSISTENTLY outperforms 200-DMA across multiple windows.')
    print(f'  This is stronger evidence than single-window OOS.')
elif most_wins != 200:
    print(f'\n  {most_wins}-DMA wins most windows but 200-DMA may still be appropriate')
    print(f'  for conservative paper trading. Evidence is mixed.')
else:
    print(f'\n  200-DMA wins or ties the most windows. Current deployment is validated.')

if win_count[200] >= len(windows) // 2:
    print(f'  200-DMA is ROBUST across multiple market regimes.')
else:
    print(f'  200-DMA underperforms in {len(windows)-win_count[200]}/{len(windows)} windows.')
    print(f'  Consider upgrading after live slippage validation.')
print(SEP)
