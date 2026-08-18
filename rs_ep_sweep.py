"""RS vs EP weight sweep — Top-N=10, Rebal=10d, SL=10%"""
import time, math, logging, warnings, statistics
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

BROKERAGE=20.0; STT_PCT=0.001; EXCHANGE_PCT=0.0000345; SLIPPAGE=0.002
TOTAL_CAP=500_000.0; SL_PCT=10.0; WF_SPLIT=0.60; TOP_N=10; REBAL_DAYS=10

STOCKS=[
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

def _r2(vals):
    n=len(vals)
    if n<5: return 0.0
    xm=(n-1)/2.0; ym=sum(vals)/n
    sx=sum((i-xm)**2 for i in range(n))
    sxy=sum((i-xm)*(v-ym) for i,v in enumerate(vals))
    sy=sum((v-ym)**2 for v in vals)
    if sx==0 or sy==0: return 0.0
    return (sxy/(sx*sy)**0.5)**2

def factors(price_data, syms, nifty, dates, i):
    if i<72: return {}
    dn=dates[i]; nc=nifty.get(dn,{}).get('close'); np_=nifty.get(dates[i-63],{}).get('close') if i>=63 else None
    raw={}
    for sym in syms:
        c=price_data[sym]
        sd=[d for d in dates[max(0,i-72):i+1] if d in c]
        if len(sd)<50: continue
        # RS
        rs=None
        if nc and np_ and i>=63:
            cn=c.get(dn,{}).get('close'); cp=c.get(dates[i-63],{}).get('close')
            if cn and cp: rs=(cn/cp-1)*100-(nc/np_-1)*100
        # EP
        ep=0.0
        ed=sd[-63:]
        evols=[c[d]['vol'] for d in ed if c[d]['vol']>0]
        av=sum(evols)/len(evols) if evols else 0
        for j in range(1,len(ed)):
            cj=c.get(ed[j]); cjm=c.get(ed[j-1])
            if not(cj and cjm and cjm['close']>0): continue
            dr=cj['close']/cjm['close']-1
            if dr>0.02 and av>0 and cj['vol']>1.5*av: ep=max(ep,dr*100)
        raw[sym]={'rs':rs,'ep':ep}
    return raw

def rank(raw, weights):
    active=[f for f,w in weights.items() if w>0]
    ranks={f:{} for f in active}
    for f in active:
        vals=[(s,raw[s][f]) for s in raw if raw[s].get(f) is not None]
        vals.sort(key=lambda x:x[1])
        n=len(vals)
        for r,(s,_) in enumerate(vals): ranks[f][s]=(r+1)/n*100
    scores={}
    if not active: return scores
    syms=set.intersection(*[set(ranks[f].keys()) for f in active])
    for sym in syms:
        tw=sum(weights[f] for f in active)
        scores[sym]=sum(ranks[f][sym]*weights[f] for f in active)/tw
    return scores

def run(price_data, nifty, dates, syms, weights, capital=TOTAL_CAP):
    cash=capital; pos={}; trades=[]; equity=[]; last=-999
    def gc(s,d): return price_data[s].get(d,{}).get('close')
    def go(s,d): return price_data[s].get(d,{}).get('open')
    for i,date in enumerate(dates):
        if i<72: equity.append(cash); continue
        for sym in list(pos):
            curr=gc(sym,date)
            if curr and curr<=pos[sym]['ep']*(1-SL_PCT/100):
                p=pos.pop(sym); fill=curr*(1-SLIPPAGE)
                ev=p['qty']*fill; c2=BROKERAGE+ev*STT_PCT+ev*EXCHANGE_PCT
                cash+=ev-c2
                trades.append({'pnl':(fill-p['ep'])*p['qty']-c2,
                               'ret':(fill/p['ep']-1)*100})
        if i-last>=REBAL_DAYS:
            last=i
            raw=factors(price_data,syms,nifty,dates,i)
            comp=rank(raw,weights)
            tgt=set(s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N])
            for sym in list(pos):
                if sym not in tgt:
                    nd=dates[i+1] if i+1<len(dates) else date
                    fp=(go(sym,nd) or gc(sym,date) or pos[sym]['ep'])*(1-SLIPPAGE)
                    p=pos.pop(sym); ev=p['qty']*fp
                    c2=BROKERAGE+ev*STT_PCT+ev*EXCHANGE_PCT; cash+=ev-c2
                    trades.append({'pnl':(fp-p['ep'])*p['qty']-c2,'ret':(fp/p['ep']-1)*100})
            new=[s for s in tgt if s not in pos]
            if new and cash>10000:
                alloc=min(cash*0.95/max(len(new),1),capital/TOP_N)
                for sym in new:
                    nd=dates[i+1] if i+1<len(dates) else date
                    fpd=go(sym,nd) or gc(sym,date)
                    if not fpd: continue
                    fill=fpd*(1+SLIPPAGE); qty=max(1,int(alloc/fill))
                    cost=BROKERAGE+qty*fill*EXCHANGE_PCT
                    if cash>=qty*fill+cost:
                        cash-=qty*fill+cost
                        pos[sym]={'qty':qty,'ep':fill}
        fv=cash+sum(p['qty']*(gc(s,date) or p['ep']) for s,p in pos.items())
        equity.append(fv)
    for s,p in list(pos.items()):
        fp=(gc(s,dates[-1]) or p['ep'])*(1-SLIPPAGE); ev=p['qty']*fp
        c2=BROKERAGE+ev*STT_PCT+ev*EXCHANGE_PCT; cash+=ev-c2
        trades.append({'pnl':(fp-p['ep'])*p['qty']-c2,'ret':(fp/p['ep']-1)*100})
    if not trades:
        return {'pf':0,'cagr':-100,'sharpe':0,'trades':0,'wr':0}
    wins=[t for t in trades if t['pnl']>0]; losses=[t for t in trades if t['pnl']<=0]
    gp=sum(t['pnl'] for t in wins); gl=abs(sum(t['pnl'] for t in losses))
    pf=gp/gl if gl>0 else (1.5 if gp>0 else 0)
    wr=len(wins)/len(trades)*100
    yrs=max(len(dates)/252,0.1); fv=equity[-1] if equity else capital
    cagr=((fv/capital)**(1/yrs)-1)*100 if fv>0 else -100
    dr=[(equity[k]-equity[k-1])/equity[k-1] for k in range(1,len(equity)) if equity[k-1]>0]
    sharpe=(statistics.mean(dr)/statistics.stdev(dr)*math.sqrt(252)
            if len(dr)>2 and statistics.stdev(dr)>0 else 0)
    return {'pf':round(pf,3),'cagr':round(cagr,1),'sharpe':round(sharpe,3),
            'trades':len(trades),'wr':round(wr,1)}

# ---- fetch ----
print('Fetching data...')
price_data={}; valid=[]
for ticker,sym in STOCKS:
    try:
        df=yf.Ticker(ticker).history(period='5y',interval='1d',auto_adjust=True)
        if not df.empty:
            d={str(ts.date()):{'open':float(r['Open']),'close':float(r['Close']),
               'vol':float(r.get('Volume',0) or 0)} for ts,r in df.iterrows()}
            if len(d)>=300: price_data[sym]=d; valid.append(sym)
    except Exception: pass
    time.sleep(0.22)
nifty={}
try:
    df=yf.Ticker('^NSEI').history(period='5y',interval='1d',auto_adjust=True)
    nifty={str(ts.date()):{'close':float(r['Close'])} for ts,r in df.iterrows()}
except Exception: pass
all_dates=sorted(nifty.keys())
sp=int(len(all_dates)*WF_SPLIT)
IS=all_dates[:sp]; OOS=all_dates[sp:]
nos=nifty.get(OOS[0],{}).get('close',0); noe=nifty.get(OOS[-1],{}).get('close',0)
nc=((noe/nos)**(1/(len(OOS)/252))-1)*100 if nos>0 else 0
nis=nifty.get(IS[0],{}).get('close',0); nie=nifty.get(IS[-1],{}).get('close',0)
nc_is=((nie/nis)**(1/(len(IS)/252))-1)*100 if nis>0 else 0

print(f'Universe: {len(valid)} stocks  |  IS: {IS[0]} to {IS[-1]} (Nifty={nc_is:+.1f}%)')
print(f'OOS: {OOS[0]} to {OOS[-1]} (Nifty={nc:+.1f}%)  |  Top-N={TOP_N}  Rebal={REBAL_DAYS}d\n')

# ---- sweep ----
SWEEP=[
    ('RS=100  EP=0',   {'rs':1.00,'ep':0.00}),
    ('RS=75   EP=25',  {'rs':0.75,'ep':0.25}),
    ('RS=50   EP=50',  {'rs':0.50,'ep':0.50}),
    ('RS=25   EP=75',  {'rs':0.25,'ep':0.75}),
    ('RS=0    EP=100', {'rs':0.00,'ep':1.00}),
]

SEP='='*94; sep='-'*94
print(SEP)
print(f'  RS / EP WEIGHT SWEEP  (Top-N={TOP_N}  Rebal={REBAL_DAYS}d  SL={SL_PCT:.0f}%  Universe={len(valid)} stocks)')
print(SEP)
print(f'  {"Config":<16}  {"IS PF":>7}  {"IS CAGR":>9}  {"IS Sh":>8}  '
      f'{"OOS PF":>7}  {"OOS CAGR":>9}  {"OOS Sh":>8}  {"PF Decay":>9}')
print(sep)

for label,w in SWEEP:
    mi=run(price_data,nifty,IS, valid,w)
    mo=run(price_data,nifty,OOS,valid,w)
    decay=mi['pf']-mo['pf']
    flag='  ** BEATS NIFTY' if mo['cagr']>nc else ''
    print(f'  {label:<16}  {mi["pf"]:>7.3f}  {mi["cagr"]:>+8.1f}%  {mi["sharpe"]:>8.3f}'
          f'  {mo["pf"]:>7.3f}  {mo["cagr"]:>+8.1f}%  {mo["sharpe"]:>8.3f}'
          f'  {decay:>+8.3f}{flag}')

print(sep)
print(f'  {"Nifty buy-and-hold":<16}  {"":>7}  {"":>9}  {"":>8}'
      f'  {"1.000":>7}  {nc:>+8.1f}%  {"0.000":>8}')
print(SEP)
print('\n  SUMMARY: Which RS:EP ratio maximises OOS Sharpe?')
results=[]
for label,w in SWEEP:
    mo=run(price_data,nifty,OOS,valid,w)
    results.append((label,mo['cagr'],mo['sharpe'],mo['pf']))
best_sh =max(results,key=lambda x:x[2])
best_ca =max(results,key=lambda x:x[1])
best_pf =max(results,key=lambda x:x[3])
print(f'  Best Sharpe : {best_sh[0]}  Sharpe={best_sh[2]:.3f}  CAGR={best_sh[1]:+.1f}%')
print(f'  Best CAGR   : {best_ca[0]}  CAGR={best_ca[1]:+.1f}%  Sharpe={best_ca[2]:.3f}')
print(f'  Best PF     : {best_pf[0]}  PF={best_pf[3]:.3f}')
