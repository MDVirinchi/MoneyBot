"""
prove_5k_vs_500k.py — Prove whether the strategy behaves the same at Rs.5,000.
Runs IDENTICAL simulation at both capital levels. Measures:
  - How many candidates are skipped (qty=0)
  - Actual exposure vs target
  - CAGR, Sharpe, MaxDD differences
  - Cash drag

This is the proof ChatGPT demanded before allowing real money.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import time, math, statistics, warnings, logging
warnings.filterwarnings('ignore'); logging.disable(logging.CRITICAL)
import yfinance as yf

W_RS=0.60; W_EP=0.40; TOP_N=10; REBAL_DAYS=10; SL_PCT=10.0
BROKERAGE=20.0; STT=0.001; EXCHANGE=0.0000345; SLIP=0.002

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

print("Rs.5K vs Rs.5L PROOF — fetching data...")
t0=time.time()
price_data={}; valid=[]
for i,(ticker,sym) in enumerate(STOCKS):
    try:
        df=yf.Ticker(ticker).history(period='5y',interval='1d',auto_adjust=True)
        if not df.empty:
            d={str(ts.date()):{'open':float(r['Open']),'close':float(r['Close']),
               'vol':float(r.get('Volume',0) or 0)} for ts,r in df.iterrows()}
            if len(d)>=300: price_data[sym]=d; valid.append(sym)
    except: pass
    if (i+1)%20==0: print(f"  ... {i+1}/{len(STOCKS)}")
    time.sleep(0.22)
nifty_raw={}
try:
    df=yf.Ticker('^NSEI').history(period='5y',interval='1d',auto_adjust=True)
    nifty_raw={str(ts.date()):float(r['Close']) for ts,r in df.iterrows()}
except: pass
print(f"Data: {len(valid)} stocks, {len(nifty_raw)} Nifty days in {time.time()-t0:.0f}s")

all_dates=sorted(nifty_raw.keys()); N=len(all_dates)
IS_END=int(N*0.6); OOS_DATES=all_dates[IS_END:]

nc_list=[(d,nifty_raw[d]) for d in all_dates]
nifty_dma={}
for idx,(d,c) in enumerate(nc_list):
    d50=sum(v for _,v in nc_list[max(0,idx-49):idx+1])/min(idx+1,50)
    d200=sum(v for _,v in nc_list[max(0,idx-199):idx+1])/min(idx+1,200)
    nifty_dma[d]={'close':c,'dma50':d50,'dma200':d200}
def regime(date):
    r=nifty_dma.get(date)
    if not r: return 'Bull'
    if r['close']<r['dma200']: return 'Bear'
    if r['dma50']<=r['dma200']: return 'Flat'
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

def run_sim(date_range, capital):
    per_pos = capital / TOP_N
    cash=capital; pos={}; trades=[]; equity=[]; last=-999
    date_to_gi={d:all_dates.index(d) for d in date_range if d in all_dates}
    total_skipped=0; total_candidates=0; total_rebalances=0
    exposure_samples=[]

    def gc(s,d): return price_data[s].get(d,{}).get('close')
    def go(s,d): return price_data[s].get(d,{}).get('open')

    for idx,date in enumerate(date_range):
        gi=date_to_gi.get(date)
        if gi is None or gi<72: equity.append(cash); continue
        if regime(date)=='Bear':
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-SLIP)
                p=pos.pop(sym); ev=p['qty']*fp
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({'pnl':(fp-p['ep'])*p['qty']-cost})
            equity.append(cash); continue

        for sym in list(pos):
            curr=gc(sym,date)
            if curr and curr<=pos[sym]['ep']*(1-SL_PCT/100):
                p=pos.pop(sym); fill=curr*(1-SLIP); ev=p['qty']*fill
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({'pnl':(fill-p['ep'])*p['qty']-cost})

        if idx-last>=REBAL_DAYS:
            last=idx; total_rebalances+=1
            comp=composite(gi)
            comp={s:sc for s,sc in comp.items() if stock_above_50dma(s,date,gi)}
            tgt={s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N]}
            for sym in list(pos):
                if sym not in tgt:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-SLIP)
                    p=pos.pop(sym); ev=p['qty']*fp
                    cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                    trades.append({'pnl':(fp-p['ep'])*p['qty']-cost})
            new=[s for s in tgt if s not in pos]; avail=cash*0.95
            skipped_this_rebal=0
            if new and avail>100:
                alloc=min(avail/max(len(new),1), per_pos)
                for sym in new:
                    total_candidates+=1
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fpd=go(sym,nd) or gc(sym,date)
                    if not fpd: continue
                    fill=fpd*(1+SLIP); qty=max(0,int(alloc/fill))
                    if qty==0:
                        total_skipped+=1; skipped_this_rebal+=1
                        continue
                    cost=BROKERAGE+qty*fill*EXCHANGE
                    if cash>=qty*fill+cost:
                        cash-=qty*fill+cost; pos[sym]={'qty':qty,'ep':fill}

        invested=sum(p['qty']*(gc(s,date) or p['ep']) for s,p in pos.items())
        fv=cash+invested; equity.append(fv)
        if fv>0: exposure_samples.append(invested/fv*100)

    for s,p in list(pos.items()):
        fp=(gc(s,date_range[-1]) or p['ep'])*(1-SLIP); ev=p['qty']*fp
        cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
        trades.append({'pnl':(fp-p['ep'])*p['qty']-cost})

    if not trades: return None
    wins=[t for t in trades if t['pnl']>0]
    gp=sum(t['pnl'] for t in wins); gl=abs(sum(t['pnl'] for t in trades if t['pnl']<=0))
    pf=gp/gl if gl>0 else 0
    yrs=max(len(date_range)/252,0.1); fv=equity[-1] if equity else capital
    cagr=((fv/capital)**(1/yrs)-1)*100 if fv>0 else -100
    dr=[(equity[k]-equity[k-1])/equity[k-1] for k in range(1,len(equity)) if equity[k-1]>0]
    sharpe=statistics.mean(dr)/statistics.stdev(dr)*math.sqrt(252) if len(dr)>2 and statistics.stdev(dr)>0 else 0
    peak=capital; max_dd=0
    for v in equity:
        if v>peak: peak=v
        dd=(peak-v)/peak*100 if peak>0 else 0
        if dd>max_dd: max_dd=dd
    avg_exposure=statistics.mean(exposure_samples) if exposure_samples else 0
    skip_rate=total_skipped/total_candidates*100 if total_candidates else 0
    return {
        'capital':capital,'cagr':round(cagr,2),'sharpe':round(sharpe,3),
        'max_dd':round(max_dd,1),'trades':len(trades),
        'wr':round(len(wins)/len(trades)*100,1) if trades else 0,
        'pf':round(pf,3),'fv':round(fv,0),
        'total_candidates':total_candidates,'total_skipped':total_skipped,
        'skip_rate':round(skip_rate,1),'avg_exposure':round(avg_exposure,1),
        'rebalances':total_rebalances,
        'avg_positions':round(statistics.mean([len([1 for s,p in pos.items()]) for _ in [0]]),1),
    }

SEP='='*90; sep='-'*90
capitals = [5_000, 10_000, 25_000, 50_000, 100_000, 500_000]

print(f'{SEP}')
print(f'  RS.5K vs RS.5L — CAPITAL IMPACT ANALYSIS')
print(f'  OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}')
print(f'  Strategy: RS60/EP40 + Policy C + 50DMA + equal weight')
print(SEP)

print(f'\n  {"Capital":>12} {"CAGR":>8} {"Sharpe":>7} {"MaxDD":>6} {"Trades":>7} {"Skip%":>6} {"Exposure":>9} {"Skipped":>8} {"FinalVal":>12}')
print(sep)

results = {}
for cap in capitals:
    m = run_sim(OOS_DATES, cap)
    if m:
        results[cap] = m
        print(f'  Rs.{cap:>9,} {m["cagr"]:>+7.2f}% {m["sharpe"]:>7.3f} {m["max_dd"]:>5.1f}% '
              f'{m["trades"]:>7} {m["skip_rate"]:>5.1f}% {m["avg_exposure"]:>8.1f}% '
              f'{m["total_skipped"]:>8} Rs.{m["fv"]:>10,.0f}')
print(sep)

# Detailed comparison
print(f'\n{SEP}')
print(f'  DETAILED COMPARISON: Rs.5,000 vs Rs.5,00,000')
print(SEP)
if 5000 in results and 500000 in results:
    s = results[5000]; l = results[500000]
    print(f'  {"Metric":<25} {"Rs.5,000":>12} {"Rs.5,00,000":>14} {"Difference":>12}')
    print(sep)
    print(f'  {"CAGR":<25} {s["cagr"]:>+11.2f}% {l["cagr"]:>+13.2f}% {s["cagr"]-l["cagr"]:>+11.2f}pp')
    print(f'  {"Sharpe":<25} {s["sharpe"]:>12.3f} {l["sharpe"]:>14.3f} {s["sharpe"]-l["sharpe"]:>+11.3f}')
    print(f'  {"Max Drawdown":<25} {s["max_dd"]:>11.1f}% {l["max_dd"]:>13.1f}% {s["max_dd"]-l["max_dd"]:>+11.1f}pp')
    print(f'  {"Win Rate":<25} {s["wr"]:>11.1f}% {l["wr"]:>13.1f}% {s["wr"]-l["wr"]:>+11.1f}pp')
    print(f'  {"Profit Factor":<25} {s["pf"]:>12.3f} {l["pf"]:>14.3f} {s["pf"]-l["pf"]:>+11.3f}')
    print(f'  {"Total Trades":<25} {s["trades"]:>12} {l["trades"]:>14} {s["trades"]-l["trades"]:>+12}')
    print(f'  {"Candidates Skipped":<25} {s["total_skipped"]:>12} {l["total_skipped"]:>14} {s["total_skipped"]-l["total_skipped"]:>+12}')
    print(f'  {"Skip Rate":<25} {s["skip_rate"]:>11.1f}% {l["skip_rate"]:>13.1f}% {s["skip_rate"]-l["skip_rate"]:>+11.1f}pp')
    print(f'  {"Avg Exposure":<25} {s["avg_exposure"]:>11.1f}% {l["avg_exposure"]:>13.1f}% {s["avg_exposure"]-l["avg_exposure"]:>+11.1f}pp')

    print(f'\n  VERDICT:')
    if abs(s['cagr'] - l['cagr']) < 1.0 and abs(s['sharpe'] - l['sharpe']) < 0.1:
        print(f'  Strategy behaves SIMILARLY at both capital levels.')
        print(f'  Rs.5,000 is viable for validation.')
    elif s['skip_rate'] > 20:
        print(f'  *** Rs.5,000 BREAKS THE STRATEGY ***')
        print(f'  {s["skip_rate"]:.0f}% of candidates are skipped (qty=0)')
        print(f'  Average exposure is only {s["avg_exposure"]:.0f}% (should be ~90%+)')
        print(f'  The bot is running a DIFFERENT strategy than what was backtested.')
        print(f'')
        # Find minimum viable capital
        for cap in capitals:
            if cap in results and results[cap]['skip_rate'] < 5:
                print(f'  MINIMUM VIABLE CAPITAL: Rs.{cap:,}')
                print(f'  At this level, skip rate drops to {results[cap]["skip_rate"]:.1f}%')
                print(f'  and CAGR is {results[cap]["cagr"]:+.2f}% (vs {l["cagr"]:+.2f}% at Rs.5L)')
                break
    else:
        print(f'  Results differ but strategy is partially functional.')
        print(f'  Consider increasing capital for better alignment.')

print(SEP)
