"""
research_turnover_audit.py — Turnover decomposition and rebalance frequency sweep.

Questions answered:
  1. Which trades contribute most profit vs most turnover?
  2. CAGR if bottom 20% turnover-generating trades are removed
  3. Rebalance frequency sweep: 5d, 10d, 15d, 20d, 30d
  4. Slippage sensitivity at each frequency
  5. Annual turnover at each frequency

All use RS60/EP40 + Policy C + 50DMA filter + equal weight.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time, math, statistics, warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

W_RS=0.60; W_EP=0.40; TOP_N=10; SL_PCT=10.0
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

print("TURNOVER AUDIT — fetching data...")
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
IS_END=int(N*0.6); IS_DATES=all_dates[:IS_END]; OOS_DATES=all_dates[IS_END:]
n_s=nifty_raw.get(OOS_DATES[0],1); n_e=nifty_raw.get(OOS_DATES[-1],1)
NIFTY_OOS_CAGR=((n_e/n_s)**(252/len(OOS_DATES))-1)*100

nifty_dma={}; nc_list=[(d,nifty_raw[d]) for d in all_dates]
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

print('Pre-computing factors...'); gi=72
while gi<N: get_raw(gi); gi+=1  # cache EVERY day for flexible rebal frequencies
print(f'Cached {len(_raw_cache)} points.\n')

# ── Detailed sim returning per-trade data ─────────────────────────────────────
def run_sim_detailed(date_range, slip, rebal_days):
    cash=CAPITAL; pos={}; trades=[]; equity=[]; last=-999
    date_to_gi={d:all_dates.index(d) for d in date_range if d in all_dates}
    turnover_buy=0.0; turnover_sell=0.0

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
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost; turnover_sell+=ev
                trades.append({'sym':sym,'pnl':(fp-p['ep'])*p['qty']-cost,
                    'turnover':p['qty']*p['ep']+ev,'exit':'Regime',
                    'entry_price':p['ep'],'exit_price':fp,'qty':p['qty'],
                    'holding_days':idx-p.get('entry_idx',idx)})
            equity.append(cash); continue

        for sym in list(pos):
            curr=gc(sym,date)
            if curr and curr<=pos[sym]['ep']*(1-SL_PCT/100):
                p=pos.pop(sym); fill=curr*(1-slip)
                ev=p['qty']*fill; cost=BROKERAGE+ev*STT+ev*EXCHANGE
                cash+=ev-cost; turnover_sell+=ev
                trades.append({'sym':sym,'pnl':(fill-p['ep'])*p['qty']-cost,
                    'turnover':p['qty']*p['ep']+ev,'exit':'SL',
                    'entry_price':p['ep'],'exit_price':fill,'qty':p['qty'],
                    'holding_days':idx-p.get('entry_idx',idx)})

        if idx-last>=rebal_days:
            last=idx
            comp=composite(gi)
            comp={s:sc for s,sc in comp.items() if stock_above_50dma(s,date,gi)}
            tgt={s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N]}
            for sym in list(pos):
                if sym not in tgt:
                    nd=date_range[idx+1] if idx+1<len(date_range) else date
                    fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-slip)
                    p=pos.pop(sym); ev=p['qty']*fp
                    cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost; turnover_sell+=ev
                    trades.append({'sym':sym,'pnl':(fp-p['ep'])*p['qty']-cost,
                        'turnover':p['qty']*p['ep']+ev,'exit':'Rebal',
                        'entry_price':p['ep'],'exit_price':fp,'qty':p['qty'],
                        'holding_days':idx-p.get('entry_idx',idx)})
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
                        cash-=qty*fill+cost; pos[sym]={'qty':qty,'ep':fill,'entry_idx':idx}
                        turnover_buy+=qty*fill

        fv=cash+sum(p['qty']*(gc(s,date) or p['ep']) for s,p in pos.items())
        equity.append(fv)

    for s,p in list(pos.items()):
        fp=(gc(s,date_range[-1]) or p['ep'])*(1-slip)
        ev=p['qty']*fp; cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
        turnover_sell+=ev
        trades.append({'sym':s,'pnl':(fp-p['ep'])*p['qty']-cost,
            'turnover':p['qty']*p['ep']+ev,'exit':'EoP',
            'entry_price':p['ep'],'exit_price':fp,'qty':p['qty'],
            'holding_days':len(date_range)-p.get('entry_idx',0)})

    if not trades: return None
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
    total_turn=turnover_buy+turnover_sell
    avg_eq=sum(equity)/len(equity) if equity else CAPITAL
    ann_turn=(total_turn/avg_eq/yrs)*100
    sl_exits=sum(1 for t in trades if t.get('exit')=='SL')
    rebal_exits=sum(1 for t in trades if t.get('exit')=='Rebal')
    return {
        'cagr':round(cagr,2),'sharpe':round(sharpe,3),'max_dd':round(max_dd,1),
        'trades':len(trades),'wr':round(len(wins)/len(trades)*100,1),
        'pf':round(pf,3),'fv':round(fv,0),'ann_turn':round(ann_turn,1),
        'sl_exits':sl_exits,'rebal_exits':rebal_exits,
        'total_pnl':round(sum(t['pnl'] for t in trades),0),
        'total_costs':round(sum(BROKERAGE*2 for t in trades),0),
        'avg_holding':round(statistics.mean([t['holding_days'] for t in trades]),1) if trades else 0,
        'trade_details':trades,
    }

SEP='='*110; sep='-'*110

# ══════════════════════════════════════════════════════════════════════════════
# Q1 & Q2: PROFIT vs TURNOVER DECOMPOSITION
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{SEP}')
print(f'  Q1 & Q2: PROFIT vs TURNOVER DECOMPOSITION (OOS, 10d rebal, 0.2% slip)')
print(SEP)

result_10d = run_sim_detailed(OOS_DATES, 0.002, 10)
trades = result_10d['trade_details']
trades_sorted_pnl = sorted(trades, key=lambda t: t['pnl'], reverse=True)
trades_sorted_turn = sorted(trades, key=lambda t: t['turnover'], reverse=True)

total_pnl = sum(t['pnl'] for t in trades)
total_turnover = sum(t['turnover'] for t in trades)

print(f'\n  Total trades: {len(trades)}  |  Total PnL: Rs.{total_pnl:,.0f}  |  Total turnover: Rs.{total_turnover:,.0f}')

# Top 10 profit contributors
print(f'\n  TOP 10 PROFIT CONTRIBUTORS')
print(f'  {"Rank":<5} {"Symbol":<14} {"PnL":>10} {"% of total PnL":>15} {"Turnover":>12} {"Exit":>8} {"Days":>5}')
print(f'  {"-"*72}')
cum_pnl = 0
for i, t in enumerate(trades_sorted_pnl[:10]):
    cum_pnl += t['pnl']
    pct = t['pnl']/total_pnl*100 if total_pnl else 0
    print(f'  {i+1:<5} {t["sym"]:<14} {t["pnl"]:>+10,.0f} {pct:>14.1f}% {t["turnover"]:>12,.0f} {t["exit"]:>8} {t["holding_days"]:>5}')
print(f'  {"":>5} {"TOP 10 TOTAL":<14} {cum_pnl:>+10,.0f} {cum_pnl/total_pnl*100 if total_pnl else 0:>14.1f}%')

# Bottom 10 (worst losses)
print(f'\n  BOTTOM 10 LOSS CONTRIBUTORS')
print(f'  {"Rank":<5} {"Symbol":<14} {"PnL":>10} {"% of total PnL":>15} {"Turnover":>12} {"Exit":>8} {"Days":>5}')
print(f'  {"-"*72}')
for i, t in enumerate(trades_sorted_pnl[-10:]):
    pct = t['pnl']/total_pnl*100 if total_pnl else 0
    print(f'  {len(trades)-9+i:<5} {t["sym"]:<14} {t["pnl"]:>+10,.0f} {pct:>14.1f}% {t["turnover"]:>12,.0f} {t["exit"]:>8} {t["holding_days"]:>5}')

# Top 10 turnover consumers
print(f'\n  TOP 10 TURNOVER CONSUMERS')
print(f'  {"Rank":<5} {"Symbol":<14} {"Turnover":>12} {"% of turn":>10} {"PnL":>10} {"PnL/Turn":>10} {"Exit":>8}')
print(f'  {"-"*72}')
cum_turn = 0
for i, t in enumerate(trades_sorted_turn[:10]):
    cum_turn += t['turnover']
    pct = t['turnover']/total_turnover*100 if total_turnover else 0
    efficiency = t['pnl']/t['turnover']*100 if t['turnover'] else 0
    print(f'  {i+1:<5} {t["sym"]:<14} {t["turnover"]:>12,.0f} {pct:>9.1f}% {t["pnl"]:>+10,.0f} {efficiency:>+9.2f}% {t["exit"]:>8}')
print(f'  {"":>5} {"TOP 10 TOTAL":<14} {cum_turn:>12,.0f} {cum_turn/total_turnover*100 if total_turnover else 0:>9.1f}%')

# Exit type breakdown
print(f'\n  EXIT TYPE BREAKDOWN')
exit_types = {}
for t in trades:
    ex = t['exit']
    if ex not in exit_types:
        exit_types[ex] = {'count':0, 'pnl':0, 'turnover':0, 'holding_days':[]}
    exit_types[ex]['count'] += 1
    exit_types[ex]['pnl'] += t['pnl']
    exit_types[ex]['turnover'] += t['turnover']
    exit_types[ex]['holding_days'].append(t['holding_days'])

print(f'  {"Exit":<10} {"Count":>6} {"PnL":>12} {"Avg PnL":>10} {"Turnover":>14} {"Avg Hold":>9} {"Win%":>6}')
print(f'  {"-"*70}')
for ex in ['Rebal','SL','Regime','EoP']:
    if ex not in exit_types: continue
    e = exit_types[ex]
    wins = sum(1 for t in trades if t['exit']==ex and t['pnl']>0)
    wr = wins/e['count']*100 if e['count'] else 0
    avg_hold = statistics.mean(e['holding_days']) if e['holding_days'] else 0
    print(f'  {ex:<10} {e["count"]:>6} {e["pnl"]:>+12,.0f} {e["pnl"]/e["count"]:>+10,.0f} {e["turnover"]:>14,.0f} {avg_hold:>8.1f}d {wr:>5.1f}%')

# ══════════════════════════════════════════════════════════════════════════════
# Q3: REBALANCE FREQUENCY SWEEP
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{SEP}')
print(f'  Q3: REBALANCE FREQUENCY SWEEP (OOS, 0.2% slippage)')
print(f'  All use RS60/EP40 + Policy C + 50DMA + equal weight')
print(SEP)

rebal_freqs = [5, 7, 10, 15, 20, 30]

print(f'\n  {"Rebal":>6} {"CAGR":>8} {"Sharpe":>7} {"MaxDD":>6} {"WR":>6} {"PF":>6} {"Trades":>7} {"SL":>4} '
      f'{"Rebal":>6} {"AvgHold":>8} {"Turn%/yr":>9} {"FinalVal":>11}')
print(sep)

freq_results = {}
for freq in rebal_freqs:
    m = run_sim_detailed(OOS_DATES, 0.002, freq)
    freq_results[freq] = m
    beat = '*' if m['cagr']>NIFTY_OOS_CAGR else ' '
    print(f'  {freq:>4}d  {m["cagr"]:>+7.2f}%{beat} {m["sharpe"]:>7.3f} {m["max_dd"]:>5.1f}% {m["wr"]:>5.1f}% '
          f'{m["pf"]:>6.3f} {m["trades"]:>7} {m["sl_exits"]:>4} {m["rebal_exits"]:>6} '
          f'{m["avg_holding"]:>7.1f}d {m["ann_turn"]:>8.1f}% {m["fv"]:>11,.0f}')
print(sep)

# ══════════════════════════════════════════════════════════════════════════════
# Q4: SLIPPAGE SENSITIVITY AT EACH FREQUENCY
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{SEP}')
print(f'  Q4: SLIPPAGE SENSITIVITY BY REBALANCE FREQUENCY (OOS)')
print(SEP)

slips = [0.002, 0.004, 0.006]
print(f'\n  {"Rebal":>6} {"0.2% CAGR":>10} {"0.4% CAGR":>10} {"0.6% CAGR":>10} {"Degrade":>9} {"Break-even":>12}')
print(sep)

for freq in rebal_freqs:
    cagrs = []
    for sl in slips:
        m = run_sim_detailed(OOS_DATES, sl, freq)
        cagrs.append(m['cagr'])
    degrade = cagrs[0] - cagrs[2]
    # Estimate break-even slip by linear interpolation
    if cagrs[0] > 0 and cagrs[2] < 0:
        be = 0.002 + (0.004 * cagrs[0]) / (cagrs[0] - cagrs[2])
        be_str = f"{be*100:.2f}%"
    elif cagrs[2] >= 0:
        be_str = ">0.6%"
    else:
        be_str = "<0.2%"
    print(f'  {freq:>4}d  {cagrs[0]:>+9.2f}% {cagrs[1]:>+9.2f}% {cagrs[2]:>+9.2f}% {degrade:>8.2f}pp {be_str:>12}')
print(sep)

# ══════════════════════════════════════════════════════════════════════════════
# Q5: INCREMENTAL DELTA TABLE
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{SEP}')
print(f'  Q5: INCREMENTAL DELTA vs CURRENT (10d rebal)')
print(SEP)

base = freq_results[10]
print(f'\n  {"Rebal":>6} {"dCAGR":>8} {"dSharpe":>9} {"dMaxDD":>8} {"dTrades":>8} {"dTurn%":>9} {"Net effect"}')
print(sep)
for freq in rebal_freqs:
    m = freq_results[freq]
    if freq == 10:
        print(f'  {freq:>4}d  {"(current)":>8} {"(current)":>9} {"(current)":>8} {"(current)":>8} {"(current)":>9}')
    else:
        dc = m['cagr']-base['cagr']
        ds = m['sharpe']-base['sharpe']
        dd = m['max_dd']-base['max_dd']
        dt = m['trades']-base['trades']
        dtu = m['ann_turn']-base['ann_turn']
        # Assess
        better = []
        if dc > 0.1: better.append('CAGR+')
        if ds > 0.01: better.append('Sharpe+')
        if dd < -0.3: better.append('DD-')
        if dtu < -50: better.append('Turn-')
        worse = []
        if dc < -0.3: worse.append('CAGR-')
        if ds < -0.02: worse.append('Sharpe-')
        if dd > 0.5: worse.append('DD+')
        effect = ' '.join(better) if better else ''
        if worse: effect += (' | ' if effect else '') + ' '.join(worse)
        if not effect: effect = 'neutral'
        print(f'  {freq:>4}d  {dc:>+7.2f}% {ds:>+8.3f} {dd:>+7.1f}% {dt:>+8} {dtu:>+8.1f}% {effect}')
print(sep)

# ══════════════════════════════════════════════════════════════════════════════
# VERDICT
# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{SEP}')
print(f'  VERDICT')
print(SEP)

best_sharpe_freq = max(rebal_freqs, key=lambda f: freq_results[f]['sharpe'])
best_cagr_freq = max(rebal_freqs, key=lambda f: freq_results[f]['cagr'])
least_dd_freq = min(rebal_freqs, key=lambda f: freq_results[f]['max_dd'])
least_turn_freq = min(rebal_freqs, key=lambda f: freq_results[f]['ann_turn'])

print(f'  Best CAGR:    {best_cagr_freq}d  ({freq_results[best_cagr_freq]["cagr"]:+.2f}%)')
print(f'  Best Sharpe:  {best_sharpe_freq}d  ({freq_results[best_sharpe_freq]["sharpe"]:.3f})')
print(f'  Lowest DD:    {least_dd_freq}d  ({freq_results[least_dd_freq]["max_dd"]:.1f}%)')
print(f'  Lowest Turn:  {least_turn_freq}d  ({freq_results[least_turn_freq]["ann_turn"]:.1f}%)')

# Check if any freq beats 10d on CAGR AND has lower turnover
for freq in rebal_freqs:
    if freq == 10: continue
    m = freq_results[freq]
    if m['cagr'] > base['cagr'] and m['ann_turn'] < base['ann_turn']:
        print(f'\n  {freq}d rebalance BEATS current 10d on BOTH CAGR and turnover.')
        print(f'  CAGR: {m["cagr"]:+.2f}% vs {base["cagr"]:+.2f}% (+{m["cagr"]-base["cagr"]:.2f}pp)')
        print(f'  Turnover: {m["ann_turn"]:.1f}% vs {base["ann_turn"]:.1f}% ({m["ann_turn"]-base["ann_turn"]:.1f}pp)')
        print(f'  RECOMMENDATION: Consider switching rebalance frequency to {freq}d.')

print(SEP)
