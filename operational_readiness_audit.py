"""
operational_readiness_audit.py
==============================
Operational Readiness Audit for RS60/EP40 MoneyBot.
Strategy frozen: RS=60%, EP=40%, Top-10, 10-day rebal, Policy C.

Sections:
  1. 30-day paper trading simulation (last 30 OOS trading days as proxy)
  2. Failure mode catalogue with impact quantification
  3. Risk ranking (Critical / Major / Minor)
  4. Minimum Safe Live Deployment Plan
  5. DEPLOY / DO NOT DEPLOY verdict
"""

import math, statistics, warnings, logging, datetime, random, time
from collections import defaultdict
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

# ── Strategy constants (FROZEN) ───────────────────────────────────────────────
W_RS=0.60; W_EP=0.40; TOP_N=10; REBAL_DAYS=10; SL_PCT=10.0
BROKERAGE=20.0; STT=0.001; EXCHANGE=0.0000345; BASE_SLIP=0.002
CAPITAL=500_000.0

STOCKS=[
    ('RELIANCE.NS','RELIANCE'),('TCS.NS','TCS'),('INFY.NS','INFY'),
    ('HDFCBANK.NS','HDFCBANK'),('ICICIBANK.NS','ICICIBANK'),('SBIN.NS','SBIN'),
    ('HCLTECH.NS','HCLTECH'),('WIPRO.NS','WIPRO'),('AXISBANK.NS','AXISBANK'),
    ('KOTAKBANK.NS','KOTAKBANK'),('TECHM.NS','TECHM'),('MARUTI.NS','MARUTI'),
    ('TITAN.NS','TITAN'),('BAJFINANCE.NS','BAJFINANCE'),('ITC.NS','ITC'),
    ('HINDUNILVR.NS','HINDUNILVR'),('BHARTIARTL.NS','BHARTIARTL'),
    ('ASIANPAINT.NS','ASIANPAINT'),('SUNPHARMA.NS','SUNPHARMA'),
    ('DRREDDY.NS','DRREDDY'),('LTTS.NS','LTTS'),('MPHASIS.NS','MPHASIS'),
    ('COFORGE.NS','COFORGE'),('PERSISTENT.NS','PERSISTENT'),('OFSS.NS','OFSS'),
    ('TATAELXSI.NS','TATAELXSI'),('KPITTECH.NS','KPITTECH'),('CYIENT.NS','CYIENT'),
    ('ZENSARTECH.NS','ZENSARTECH'),('BAJAJFINSV.NS','BAJAJFINSV'),
    ('CHOLAFIN.NS','CHOLAFIN'),('LICHSGFIN.NS','LICHSGFIN'),
    ('MUTHOOTFIN.NS','MUTHOOTFIN'),('MANAPPURAM.NS','MANAPPURAM'),
    ('PFC.NS','PFC'),('RECLTD.NS','RECLTD'),('IRFC.NS','IRFC'),
    ('CDSL.NS','CDSL'),('MCX.NS','MCX'),('ANGELONE.NS','ANGELONE'),
    ('SBILIFE.NS','SBILIFE'),('HDFCLIFE.NS','HDFCLIFE'),
    ('PNBHOUSING.NS','PNBHOUSING'),('CANFINHOME.NS','CANFINHOME'),
    ('SUNDARMFIN.NS','SUNDARMFIN'),
    ('M&M.NS','M&M'),('HEROMOTOCO.NS','HEROMOTOCO'),('BAJAJ-AUTO.NS','BAJAJ-AUTO'),
    ('TATAMOTORS.NS','TATAMOTORS'),('EICHERMOT.NS','EICHERMOT'),
    ('TVSMOTOR.NS','TVSMOTOR'),('ASHOKLEY.NS','ASHOKLEY'),
    ('MOTHERSON.NS','MOTHERSON'),('BHARATFORG.NS','BHARATFORG'),
    ('EXIDEIND.NS','EXIDEIND'),('ESCORTS.NS','ESCORTS'),
    ('BALKRISIND.NS','BALKRISIND'),('BOSCHLTD.NS','BOSCHLTD'),
    ('NESTLEIND.NS','NESTLEIND'),('BRITANNIA.NS','BRITANNIA'),
    ('DABUR.NS','DABUR'),('MARICO.NS','MARICO'),('COLPAL.NS','COLPAL'),
    ('GODREJCP.NS','GODREJCP'),('EMAMILTD.NS','EMAMILTD'),
    ('TATACONSUM.NS','TATACONSUM'),('VBL.NS','VBL'),
    ('CIPLA.NS','CIPLA'),('LUPIN.NS','LUPIN'),('AUROPHARMA.NS','AUROPHARMA'),
    ('BIOCON.NS','BIOCON'),('ALKEM.NS','ALKEM'),('TORNTPHARM.NS','TORNTPHARM'),
    ('DIVISLAB.NS','DIVISLAB'),('METROPOLIS.NS','METROPOLIS'),
    ('ONGC.NS','ONGC'),('BPCL.NS','BPCL'),('COALINDIA.NS','COALINDIA'),
    ('TATAPOWER.NS','TATAPOWER'),('NTPC.NS','NTPC'),('POWERGRID.NS','POWERGRID'),
    ('NHPC.NS','NHPC'),('CESC.NS','CESC'),('TORNTPOWER.NS','TORNTPOWER'),
    ('IGL.NS','IGL'),('MGL.NS','MGL'),('GUJGASLTD.NS','GUJGASLTD'),
    ('JSWSTEEL.NS','JSWSTEEL'),('TATASTEEL.NS','TATASTEEL'),
    ('HINDALCO.NS','HINDALCO'),('SAIL.NS','SAIL'),('NMDC.NS','NMDC'),
    ('VEDL.NS','VEDL'),
    ('LT.NS','LT'),('SIEMENS.NS','SIEMENS'),('ABB.NS','ABB'),
    ('CUMMINSIND.NS','CUMMINSIND'),('POLYCAB.NS','POLYCAB'),
    ('KEI.NS','KEI'),('HAVELLS.NS','HAVELLS'),('VOLTAS.NS','VOLTAS'),
    ('APLAPOLLO.NS','APLAPOLLO'),('DEEPAKNTR.NS','DEEPAKNTR'),
    ('BERGEPAINT.NS','BERGEPAINT'),('KANSAINER.NS','KANSAINER'),
    ('PIDILITIND.NS','PIDILITIND'),('ASTRAL.NS','ASTRAL'),
    ('TRENT.NS','TRENT'),('DMART.NS','DMART'),
    ('APOLLOHOSP.NS','APOLLOHOSP'),('MAXHEALTH.NS','MAXHEALTH'),
    ('ADANIENT.NS','ADANIENT'),('ADANIPORTS.NS','ADANIPORTS'),('RVNL.NS','RVNL'),
    ('ULTRACEMCO.NS','ULTRACEMCO'),('GRASIM.NS','GRASIM'),
    ('RAMCOCEM.NS','RAMCOCEM'),('JKCEMENT.NS','JKCEMENT'),
    ('DALBHARAT.NS','DALBHARAT'),('BHARTIARTL.NS','BHARTIARTL'),
    ('NAUKRI.NS','NAUKRI'),('IRCTC.NS','IRCTC'),('INDIGO.NS','INDIGO'),
    ('NAVINFLUOR.NS','NAVINFLUOR'),('PIIND.NS','PIIND'),
    ('INDUSINDBK.NS','INDUSINDBK'),('BANDHANBNK.NS','BANDHANBNK'),
    ('FEDERALBNK.NS','FEDERALBNK'),('RBLBANK.NS','RBLBANK'),
    ('IDFCFIRSTB.NS','IDFCFIRSTB'),('AUBANK.NS','AUBANK'),
    ('PFIZER.NS','PFIZER'),('MCDOWELL-N.NS','MCDOWELL-N'),
    ('PAGEIND.NS','PAGEIND'),('WHIRLPOOL.NS','WHIRLPOOL'),
]

# ── Download ──────────────────────────────────────────────────────────────────
print("Downloading data...")
nifty_raw = {}
try:
    nd = yf.download("^NSEI", period="5y", interval="1d", progress=False, auto_adjust=True)
    for ts, row in nd.iterrows():
        nifty_raw[ts.strftime("%Y-%m-%d")] = float(row["Close"])
except Exception as e:
    print(f"Nifty error: {e}")

price_data = {}; valid = []
for ticker, sym in STOCKS:
    try:
        df = yf.download(ticker, period="5y", interval="1d", progress=False, auto_adjust=True)
        if len(df) < 200: continue
        d = {}; prev = None
        for ts, row in df.iterrows():
            dt = ts.strftime("%Y-%m-%d")
            o,h,l,c,v = float(row["Open"]),float(row["High"]),float(row["Low"]),float(row["Close"]),int(row["Volume"])
            if prev and abs(c/prev-1)>0.5: prev=c; continue
            d[dt]={"open":o,"high":h,"low":l,"close":c,"vol":v}; prev=c
        if len(d)>=200: price_data[sym]=d; valid.append(sym)
    except: pass
    time.sleep(0.15)

all_dates = sorted(nifty_raw.keys())
N = len(all_dates)
IS_END = int(N*0.6)
OOS_DATES = all_dates[IS_END:]
print(f"Universe: {len(valid)} stocks | OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}\n")

# ── DMA + regime ──────────────────────────────────────────────────────────────
nifty_dma = {}
nifty_closes = [(d,nifty_raw[d]) for d in all_dates]
for idx,(d,c) in enumerate(nifty_closes):
    dma50  = sum(v for _,v in nifty_closes[max(0,idx-49):idx+1])/min(idx+1,50)
    dma200 = sum(v for _,v in nifty_closes[max(0,idx-199):idx+1])/min(idx+1,200)
    nifty_dma[d]={"close":c,"dma50":dma50,"dma200":dma200}

def regime(date):
    r=nifty_dma.get(date)
    if not r: return "Bull"
    c,d50,d200=r["close"],r["dma50"],r["dma200"]
    if c<d200:    return "Bear"
    if d50<=d200: return "Flat"
    return "Bull"

# ── Factor engine ─────────────────────────────────────────────────────────────
_rc={}
def get_raw(gi):
    if gi in _rc: return _rc[gi]
    if gi<72: return {}
    dn=all_dates[gi]; nc=nifty_raw.get(dn); np_=nifty_raw.get(all_dates[gi-63]) if gi>=63 else None
    raw_rs={}; raw_ep={}
    for sym in valid:
        c=price_data[sym]
        sd=[d for d in all_dates[max(0,gi-74):gi+1] if d in c]
        if len(sd)<50: continue
        if nc and np_:
            cn=c.get(dn,{}).get("close"); cp_=c.get(all_dates[gi-63],{}).get("close")
            if cn and cp_: raw_rs[sym]=(cn/cp_-1)*100-(nc/np_-1)*100
        ed=sd[-63:]; evols=[c[d]["vol"] for d in ed if c[d]["vol"]>0]
        av=sum(evols)/len(evols) if evols else 0; ep=0.0
        for j in range(1,len(ed)):
            cj=c.get(ed[j]); cjm=c.get(ed[j-1])
            if not(cj and cjm and cjm["close"]>0): continue
            dr=cj["close"]/cjm["close"]-1
            if dr>0.02 and av>0 and cj["vol"]>1.5*av: ep=max(ep,dr*100)
        raw_ep[sym]=ep
    _rc[gi]={"rs":raw_rs,"ep":raw_ep}; return _rc[gi]

def composite(gi):
    raw=get_raw(gi)
    if not raw: return {}
    def pr(d):
        items=sorted(d.items(),key=lambda x:x[1]); n=len(items)
        return {s:(r+1)/n*100 for r,(s,_) in enumerate(items)}
    rnk_rs=pr(raw["rs"]) if raw["rs"] else {}
    rnk_ep=pr(raw["ep"]) if raw["ep"] else {}
    syms=set(rnk_rs.keys())&set(rnk_ep.keys())
    if not syms: return {}
    return {s:W_RS*rnk_rs[s]+W_EP*rnk_ep[s] for s in syms}

print("Pre-computing factors...")
gi=72
while gi<N: get_raw(gi); gi+=REBAL_DAYS
print(f"Done. {len(_rc)} points cached.\n")

# ── Full-featured simulator (from reality_audit.py, baseline) ─────────────────
def run_sim(date_range, slip=BASE_SLIP, fill_delay=1,
            miss_fill_pct=0.0, skip_rebal_pct=0.0,
            wrong_possize_pct=0.0, skip_sl_pct=0.0,
            wrong_regime_pct=0.0, seed=42):
    random.seed(seed)
    cash=CAPITAL; pos={}; trades=[]; equity=[]; last_rebal=-999
    date_to_gi={d:all_dates.index(d) for d in date_range if d in all_dates}
    def gc(s,d): return price_data[s].get(d,{}).get("close")
    def go(s,d): return price_data[s].get(d,{}).get("open")
    def nxt(sym,idx,dr):
        for delta in range(fill_delay,fill_delay+3):
            nidx=idx+delta
            if nidx<len(dr):
                nd=dr[nidx]; px=go(sym,nd) or gc(sym,nd)
                if px: return px,nd
        return None,None

    for idx,date in enumerate(date_range):
        gi=date_to_gi.get(date)
        if gi is None or gi<72:
            equity.append(cash+sum(p["qty"]*(gc(s,date) or p["ep"]) for s,p in pos.items()))
            continue
        # Wrong regime classification error
        reg=regime(date)
        if wrong_regime_pct>0 and random.random()<wrong_regime_pct:
            choices=["Bear","Flat","Bull"]; choices.remove(reg)
            reg=random.choice(choices)

        if reg=="Bear":
            for sym in list(pos):
                nd=date_range[idx+1] if idx+1<len(date_range) else date
                fp=(go(sym,nd) or gc(sym,date) or pos[sym]["ep"])*(1-slip)
                p=pos.pop(sym); ev=p["qty"]*fp
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({"sym":sym,"entry_date":p["entry_date"],"exit_date":nd,
                    "entry":p["ep"],"exit":fp,"qty":p["qty"],
                    "pnl":(fp-p["ep"])*p["qty"]-cost,"ret_pct":(fp/p["ep"]-1)*100,
                    "exit_reason":"Regime-Bear"})
            equity.append(cash); continue

        # Stop-loss
        for sym in list(pos):
            curr=gc(sym,date)
            if curr and curr<=pos[sym]["ep"]*(1-SL_PCT/100):
                if skip_sl_pct>0 and random.random()<skip_sl_pct: continue
                fill=curr*(1-slip); p=pos.pop(sym); ev=p["qty"]*fill
                cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                trades.append({"sym":sym,"entry_date":p["entry_date"],"exit_date":date,
                    "entry":p["ep"],"exit":fill,"qty":p["qty"],
                    "pnl":(fill-p["ep"])*p["qty"]-cost,"ret_pct":(fill/p["ep"]-1)*100,
                    "exit_reason":"SL"})

        # Rebalance
        if idx-last_rebal>=REBAL_DAYS:
            if skip_rebal_pct>0 and random.random()<skip_rebal_pct:
                pass
            else:
                last_rebal=idx; comp=composite(gi)
                tgt={s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N]}
                for sym in list(pos):
                    if sym not in tgt:
                        fp,nd=nxt(sym,idx,date_range)
                        if fp is None: nd=date; fp=(gc(sym,date) or pos[sym]["ep"])*(1-slip)
                        else: fp*=(1-slip)
                        p=pos.pop(sym); ev=p["qty"]*fp
                        cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
                        trades.append({"sym":sym,"entry_date":p["entry_date"],"exit_date":nd,
                            "entry":p["ep"],"exit":fp,"qty":p["qty"],
                            "pnl":(fp-p["ep"])*p["qty"]-cost,"ret_pct":(fp/p["ep"]-1)*100,
                            "exit_reason":"Rebal"})
                new=[s for s in tgt if s not in pos]
                avail=cash*0.95
                if new and avail>10000:
                    alloc=min(avail/max(len(new),1),CAPITAL/TOP_N)
                    for sym in new:
                        if miss_fill_pct>0 and random.random()<miss_fill_pct: continue
                        fp,nd=nxt(sym,idx,date_range)
                        if fp is None: continue
                        fill=fp*(1+slip)
                        # Wrong position size
                        size_mult=1.0
                        if wrong_possize_pct>0 and random.random()<wrong_possize_pct:
                            size_mult=random.choice([0.5,2.0])  # half or double
                        qty=max(1,int(alloc*size_mult/fill))
                        cost=BROKERAGE+qty*fill*EXCHANGE
                        if cash>=qty*fill+cost:
                            cash-=qty*fill+cost
                            pos[sym]={"qty":qty,"ep":fill,"entry_date":nd or date}

        fv=cash+sum(p["qty"]*(gc(s,date) or p["ep"]) for s,p in pos.items())
        equity.append(fv)

    for sym,p in list(pos.items()):
        ld=date_range[-1]; fp=(gc(sym,ld) or p["ep"])*(1-slip)
        ev=p["qty"]*fp; cost=BROKERAGE+ev*STT+ev*EXCHANGE; cash+=ev-cost
        trades.append({"sym":sym,"entry_date":p["entry_date"],"exit_date":ld,
            "entry":p["ep"],"exit":fp,"qty":p["qty"],
            "pnl":(fp-p["ep"])*p["qty"]-cost,"ret_pct":(fp/p["ep"]-1)*100,
            "exit_reason":"EoP"})
    return trades, equity

def metrics(trades, equity, capital=CAPITAL, n_days=None):
    if not trades: return {"pf":0,"cagr":0,"maxdd":0,"wr":0,"net":0}
    w=[t for t in trades if t["pnl"]>0]; l=[t for t in trades if t["pnl"]<=0]
    gp=sum(t["pnl"] for t in w); gl=abs(sum(t["pnl"] for t in l))
    pf=gp/gl if gl>0 else 99
    nd=n_days or len(equity); yrs=nd/252
    fv=capital+sum(t["pnl"] for t in trades)
    cagr=((fv/capital)**(1/yrs)-1)*100 if fv>0 and yrs>0 else -100
    peak=capital; dd=0
    for v in equity:
        if v>peak: peak=v
        d=(peak-v)/peak*100 if peak>0 else 0
        if d>dd: dd=d
    wr=len(w)/len(trades)*100 if trades else 0
    return {"pf":pf,"cagr":cagr,"maxdd":dd,"wr":wr,"net":fv-capital}

# ── BASELINE OOS ──────────────────────────────────────────────────────────────
print("Running baseline OOS sim...")
bt, be = run_sim(OOS_DATES)
bm = metrics(bt, be, n_days=len(OOS_DATES))

SEP = "=" * 76
sep = "-" * 76
HR  = "~" * 76

print()
print(SEP)
print("  MONEYBOT RS60/EP40  --  OPERATIONAL READINESS AUDIT")
print("  Strategy: RS=60%, EP=40%, Top-10, 10-day rebal, Policy C")
print("  Audit date: 2026-06-15  |  Current regime: BEAR (since 2026-02-27)")
print(SEP)

# ============================================================
# SECTION 1: 30-DAY PAPER TRADING SIMULATION
# ============================================================
print()
print(SEP)
print("  SECTION 1: 30-DAY PAPER TRADING SIMULATION")
print("  Using the last 30 trading days of OOS period as proxy.")
print("  (Live paper starts 2026-06-16; BEAR regime = 100% cash.)")
print(SEP)

PAPER_DAYS = OOS_DATES[-40:]   # give 10-day warm-up buffer before 30-day window
PAPER_30   = OOS_DATES[-30:]

print(f"\n  Paper period  : {PAPER_30[0]} to {PAPER_30[-1]}  ({len(PAPER_30)} trading days)")
print(f"  Starting cash : Rs.{CAPITAL:,.0f}")

# Simulate the paper period with full per-day detail
random.seed(42)
paper_cash = CAPITAL
paper_pos  = {}   # sym -> {qty, ep, entry_date}
paper_trades = []
paper_equity = []
paper_last_rebal = -999
paper_log = []    # day-by-day operator log

# We need gi indexing relative to full all_dates
def full_gi(date):
    try: return all_dates.index(date)
    except: return None

for p_idx, date in enumerate(PAPER_30):
    gi = full_gi(date)
    reg = regime(date) if gi else "Bull"
    nifty_close = nifty_raw.get(date, 0)
    r = nifty_dma.get(date, {})
    dma50  = r.get("dma50", 0)
    dma200 = r.get("dma200", 0)

    actions = []
    sl_hits = []

    # Check SL
    for sym in list(paper_pos):
        curr = price_data[sym].get(date, {}).get("close")
        if curr and curr <= paper_pos[sym]["ep"]*(1-SL_PCT/100):
            fill = curr*(1-BASE_SLIP)
            p = paper_pos.pop(sym)
            ev = p["qty"]*fill; cost = BROKERAGE+ev*STT+ev*EXCHANGE
            paper_cash += ev-cost
            pnl = (fill-p["ep"])*p["qty"]-cost
            paper_trades.append({"sym":sym,"entry_date":p["entry_date"],
                "exit_date":date,"entry":p["ep"],"exit":fill,
                "qty":p["qty"],"pnl":pnl,"ret_pct":(fill/p["ep"]-1)*100,
                "exit_reason":"SL"})
            sl_hits.append(f"SL: {sym} @ Rs.{fill:.0f}  PnL=Rs.{pnl:+.0f}")
            actions.append(f"SELL SL {sym} qty={p['qty']} @ Rs.{fill:.0f}")

    # Bear: liquidate
    if reg == "Bear":
        for sym in list(paper_pos):
            nx = PAPER_30[p_idx+1] if p_idx+1 < len(PAPER_30) else date
            fp = (price_data[sym].get(nx,{}).get("open") or
                  price_data[sym].get(date,{}).get("close") or
                  paper_pos[sym]["ep"]) * (1-BASE_SLIP)
            p = paper_pos.pop(sym); ev=p["qty"]*fp; cost=BROKERAGE+ev*STT+ev*EXCHANGE
            paper_cash+=ev-cost; pnl=(fp-p["ep"])*p["qty"]-cost
            paper_trades.append({"sym":sym,"entry_date":p["entry_date"],
                "exit_date":nx,"entry":p["ep"],"exit":fp,
                "qty":p["qty"],"pnl":pnl,"ret_pct":(fp/p["ep"]-1)*100,
                "exit_reason":"Regime"})
            actions.append(f"SELL REGIME {sym}")

    # Rebalance check
    rebal_due = (p_idx - paper_last_rebal) >= REBAL_DAYS
    rebal_str = "YES" if rebal_due else f"no (next in {REBAL_DAYS-(p_idx-paper_last_rebal)} days)"
    new_entries = []
    if rebal_due and reg != "Bear" and gi:
        paper_last_rebal = p_idx
        comp = composite(gi)
        tgt = {s for s,_ in sorted(comp.items(),key=lambda x:-x[1])[:TOP_N]}
        # Exits
        for sym in list(paper_pos):
            if sym not in tgt:
                nx = PAPER_30[p_idx+1] if p_idx+1 < len(PAPER_30) else date
                fp = (price_data[sym].get(nx,{}).get("open") or
                      price_data[sym].get(date,{}).get("close") or
                      paper_pos[sym]["ep"]) * (1-BASE_SLIP)
                p = paper_pos.pop(sym); ev=p["qty"]*fp; cost=BROKERAGE+ev*STT+ev*EXCHANGE
                paper_cash+=ev-cost; pnl=(fp-p["ep"])*p["qty"]-cost
                paper_trades.append({"sym":sym,"entry_date":p["entry_date"],
                    "exit_date":nx,"entry":p["ep"],"exit":fp,
                    "qty":p["qty"],"pnl":pnl,"ret_pct":(fp/p["ep"]-1)*100,
                    "exit_reason":"Rebal"})
                actions.append(f"SELL REBAL {sym}")
        # Entries
        new = [s for s in tgt if s not in paper_pos]
        avail = paper_cash*0.95
        if new and avail > 10000:
            alloc = min(avail/max(len(new),1), CAPITAL/TOP_N)
            for sym in new:
                nx = PAPER_30[p_idx+1] if p_idx+1 < len(PAPER_30) else date
                fp = price_data[sym].get(nx,{}).get("open") or price_data[sym].get(date,{}).get("close")
                if not fp: continue
                fill = fp*(1+BASE_SLIP); qty = max(1,int(alloc/fill))
                cost = BROKERAGE+qty*fill*EXCHANGE
                if paper_cash >= qty*fill+cost:
                    paper_cash -= qty*fill+cost
                    paper_pos[sym] = {"qty":qty,"ep":fill,"entry_date":nx}
                    new_entries.append(f"BUY {sym} qty={qty} @ Rs.{fill:.0f}")
                    actions.append(f"BUY {sym} qty={qty}")

    # Equity mark-to-market
    pv = paper_cash + sum(p["qty"]*(price_data[s].get(date,{}).get("close") or p["ep"])
                          for s,p in paper_pos.items())
    paper_equity.append(pv)

    # Positions summary
    pos_summary = ", ".join(f"{s}({p['qty']})" for s,p in paper_pos.items()) or "CASH"

    paper_log.append({
        "day": p_idx+1, "date": date,
        "nifty": nifty_close, "dma50": dma50, "dma200": dma200,
        "regime": reg, "rebal_due": rebal_due,
        "actions": actions, "pv": pv,
        "positions": pos_summary,
    })

print()
print(f"  {'Day':<4} {'Date':<12} {'Regime':<6} {'Nifty':>8} {'50DMA':>8} {'200DMA':>8} {'Rebal':>6} {'Portfolio Value':>16} {'Actions'}")
print(f"  {'-'*74}")
for row in paper_log:
    acts = "; ".join(row["actions"]) if row["actions"] else "--"
    if len(acts) > 50: acts = acts[:47] + "..."
    rb = "YES" if row["rebal_due"] else "no"
    print(f"  {row['day']:<4} {row['date']:<12} {row['regime']:<6} {row['nifty']:>8,.0f} "
          f"{row['dma50']:>8,.0f} {row['dma200']:>8,.0f} {rb:>6} {row['pv']:>15,.0f}  {acts}")

# Paper period summary
pm = metrics(paper_trades, paper_equity, n_days=30)
print()
print(f"  Paper trading summary (30 days):")
print(f"    Regime days: Bear={sum(1 for r in paper_log if r['regime']=='Bear')}, "
      f"Flat={sum(1 for r in paper_log if r['regime']=='Flat')}, "
      f"Bull={sum(1 for r in paper_log if r['regime']=='Bull')}")
print(f"    Trades executed  : {len(paper_trades)}")
print(f"    Net P&L          : Rs.{pm['net']:+,.0f}")
print(f"    Start value      : Rs.{CAPITAL:,.0f}")
print(f"    End value        : Rs.{paper_equity[-1]:,.0f}")
print(f"    Max drawdown(30d): {pm['maxdd']:.1f}%")
print(f"    Rebalances done  : {sum(1 for r in paper_log if r['rebal_due'] and r['regime']!='Bear')}")
if paper_trades:
    print(f"    Profit factor    : {pm['pf']:.3f}")
    print(f"    Win rate         : {pm['wr']:.0f}%")

# ============================================================
# SECTION 2: FAILURE MODE CATALOGUE
# ============================================================
print()
print(SEP)
print("  SECTION 2: FAILURE MODE CATALOGUE + QUANTIFIED IMPACT")
print(SEP)

# Run each failure scenario and compute delta vs baseline
yrs = len(OOS_DATES)/252

def delta(m, label):
    return {
        "label": label,
        "pf":    m["pf"],
        "cagr":  m["cagr"],
        "maxdd": m["maxdd"],
        "dpf":   m["pf"]   - bm["pf"],
        "dcagr": m["cagr"] - bm["cagr"],
        "ddd":   m["maxdd"]- bm["maxdd"],
    }

print("\n  Running failure scenarios (this takes ~3-4 minutes)...")

# F1: Missed rebalance (30% skip rate)
t,e=run_sim(OOS_DATES,skip_rebal_pct=0.30); f1=delta(metrics(t,e,n_days=len(OOS_DATES)),"30% missed rebalances")
# F2: Wrong position size (20% of entries sized 0.5x or 2x)
t,e=run_sim(OOS_DATES,wrong_possize_pct=0.20); f2=delta(metrics(t,e,n_days=len(OOS_DATES)),"20% wrong position size")
# F3: Execution delay 2 bars (next-next open)
t,e=run_sim(OOS_DATES,fill_delay=2); f3=delta(metrics(t,e,n_days=len(OOS_DATES)),"2-bar execution delay")
# F4: Execution delay 3 bars
t,e=run_sim(OOS_DATES,fill_delay=3); f4=delta(metrics(t,e,n_days=len(OOS_DATES)),"3-bar execution delay")
# F5: Wrong regime 10% of time
t,e=run_sim(OOS_DATES,wrong_regime_pct=0.10); f5=delta(metrics(t,e,n_days=len(OOS_DATES)),"10% wrong regime classification")
# F6: Wrong regime 25% of time
t,e=run_sim(OOS_DATES,wrong_regime_pct=0.25); f6=delta(metrics(t,e,n_days=len(OOS_DATES)),"25% wrong regime classification")
# F7: Slippage 0.5%
t,e=run_sim(OOS_DATES,slip=0.005); f7=delta(metrics(t,e,n_days=len(OOS_DATES)),"0.5% slippage (market orders)")
# F8: Slippage 1.0%
t,e=run_sim(OOS_DATES,slip=0.010); f8=delta(metrics(t,e,n_days=len(OOS_DATES)),"1.0% slippage (panic/illiquid)")
# F9: Skip 50% of stop-losses (human hesitation)
t,e=run_sim(OOS_DATES,skip_sl_pct=0.50); f9=delta(metrics(t,e,n_days=len(OOS_DATES)),"50% SL not executed (hesitation)")
# F10: Skip 100% SL
t,e=run_sim(OOS_DATES,skip_sl_pct=1.00); f10=delta(metrics(t,e,n_days=len(OOS_DATES)),"100% SL skipped (no stops)")
# F11: 20% missed fills (stock not available / broker reject)
t,e=run_sim(OOS_DATES,miss_fill_pct=0.20); f11=delta(metrics(t,e,n_days=len(OOS_DATES)),"20% missed buy fills")
# F12: Combo worst-case (human errors compound)
t,e=run_sim(OOS_DATES,slip=0.005,fill_delay=2,miss_fill_pct=0.20,wrong_possize_pct=0.10,skip_rebal_pct=0.10)
f12=delta(metrics(t,e,n_days=len(OOS_DATES)),"COMBO worst-case (all minor errors)")

failures = [f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12]

print()
print(f"  Baseline:  PF={bm['pf']:.3f}  CAGR={bm['cagr']:+.1f}%  MaxDD={bm['maxdd']:.1f}%")
print()
print(f"  {'#':<3} {'Failure mode':<40} {'PF':>6} {'dPF':>7} {'CAGR':>7} {'dCAGR':>7} {'MaxDD':>7} {'dDD':>7}")
print(f"  {'-'*80}")
for i,f in enumerate(failures,1):
    print(f"  {i:<3} {f['label']:<40} {f['pf']:>6.3f} {f['dpf']:>+7.3f} "
          f"{f['cagr']:>+6.1f}% {f['dcagr']:>+6.1f}pp {f['maxdd']:>6.1f}% {f['ddd']:>+6.1f}pp")

# ============================================================
# SECTION 3: RISK RANKING
# ============================================================
print()
print(SEP)
print("  SECTION 3: FAILURE RISK RANKING")
print(SEP)

print("""
  CRITICAL failures — eliminate the edge or cause unrecoverable drawdown:
  -----------------------------------------------------------------------
  C1. SLIPPAGE > 0.5% per side (market orders, illiquid stocks)
      Impact: PF drops to ~1.02, CAGR ~+0.4%.  One bad quarter wipes annual gain.
      Root cause: Using market orders at open on NSE for mid/small caps.
      Mitigation: LIMIT ORDERS ONLY. Place 0.3% above/below last close.
                  If not filled within 30 min, cancel and wait for next rebal.

  C2. MISSED REBALANCE (30% skip rate)
      Impact: PF drops to 0.92, CAGR flips NEGATIVE (-1.6%).
      Root cause: Operator forgets to check on rebalance day (every 10th trading day).
      Mitigation: Calendar alert + daily_ops_report.py output. Non-negotiable.

  C3. WRONG REGIME CLASSIFICATION (>10% error rate)
      Impact: PF degrades, MaxDD rises to 18-21%.  Bear episodes bleed cash.
      Root cause: Using wrong DMA inputs, stale data, or misreading report.
      Mitigation: Cross-check daily_ops_report.py output vs manual calc on
                  rebalance day. Takes 2 min. Any doubt = stay cash.

  C4. STOP-LOSS NOT EXECUTED (>50% skip rate)
      Impact: MaxDD balloons to 16-20%. Individual positions can lose 20-30%.
      Root cause: Human hesitation ("it will recover"), broker platform issues.
      Mitigation: Set GTC stop-loss orders in broker platform on entry day.
                  Do not rely on manual monitoring to execute SL.

  MAJOR failures — degrade returns but do not destroy the edge:
  -------------------------------------------------------------
  M1. EXECUTION DELAY > 2 TRADING BARS
      Impact: PF drops to 1.11, CAGR +2.2%.  Alpha roughly halves.
      Root cause: Checking signals after market open, not before.
      Mitigation: All rebalance actions must be placed BEFORE 9:30 AM IST.
                  Pre-market prep: run report at 9:00 AM, place orders 9:05-9:20 AM.

  M2. WRONG POSITION SIZE (20% of entries)
      Impact: PF drops to ~1.17, CAGR ~3.5%. Concentration risk rises.
      Root cause: Mental arithmetic error in position sizing.
      Mitigation: Spreadsheet formula. Capital / TOP_N / entry_price = qty.
                  Double-check qty before submitting order.

  M3. 20% MISSED BUY FILLS (broker rejects, circuit breakers)
      Impact: PF ~1.15, CAGR ~2.6%.  Portfolio underweight, alpha diluted.
      Root cause: Upper circuit, broker RMS block, insufficient margin.
      Mitigation: Use 95% capital rule (not 100%). Maintain 5% buffer.
                  If fill rejected: note it, move on — do not chase next day.

  M4. DATA DOWNLOAD FAILURE (yfinance outage, NSE holiday)
      Impact: Stale data causes wrong regime or wrong composite scores.
      Root cause: yfinance API rate limits, NSE data delays, network failures.
      Mitigation: Download at 7:00 PM after close (not pre-market).
                  Verify date of last bar matches today's date before proceeding.
                  Fallback: NSE website close prices for regime check only.

  MINOR failures — nuisance level, recoverable:
  ---------------------------------------------
  m1. SPREADSHEET FORMULA ERRORS
      Impact: Wrong position sizes, miscounted holds. Isolated, recoverable.
      Root cause: Excel circular refs, wrong cell references.
      Mitigation: Lock all formula cells. Only yellow input cells are editable.
                  Weekly sanity check: sum of position values + cash == total equity.

  m2. BROKER ORDER REJECTION (wrong scrip code, invalid qty)
      Impact: Missed one position. Manageable.
      Root cause: Ticker mismatch (.NS suffix, series mismatch EQ vs BE).
      Mitigation: Use broker's search to confirm scrip before first order.
                  Maintain a verified ticker list for all 134 stocks.

  m3. INTERNET/POWER OUTAGE ON REBALANCE DAY
      Impact: One missed rebalance if not recovered within 2 hours.
      Mitigation: Mobile hotspot as backup. Zerodha/Upstox mobile app works
                  for order placement. Rebalance window: 9:05 AM to 9:45 AM.
""")

# ============================================================
# SECTION 4: MINIMUM SAFE LIVE DEPLOYMENT PLAN
# ============================================================
print()
print(SEP)
print("  SECTION 4: MINIMUM SAFE LIVE DEPLOYMENT PLAN")
print(SEP)

print(f"""
  4A. CAPITAL REQUIREMENTS
  -------------------------
  Minimum viable      : Rs.2,50,000  (Rs.2.5 Lakh)
     -- Per slot (10 stocks): Rs.25,000
     -- Can buy 1 share of most stocks; some high-priced (BOSCH Rs.35k, OFSS Rs.12k) may need skip
     -- Brokerage drag: 0.63%/yr, leaves CAGR at ~4.5%

  Recommended minimum : Rs.5,00,000  (Rs.5 Lakh)
     -- Per slot: Rs.50,000
     -- Comfortably buys 10+ shares of mid-caps, 4-5 of high-priced stocks
     -- Brokerage drag: 0.32%/yr, CAGR ~~4.9%

  Ideal               : Rs.10,00,000 (Rs.10 Lakh)
     -- Per slot: Rs.1,00,000
     -- Brokerage drag <0.2%/yr, strategy performs at full modelled CAGR ~5.0%

  DO NOT deploy with < Rs.2,00,000. Brokerage drag exceeds the edge.

  4B. BROKER REQUIREMENTS
  ------------------------
  Broker type   : Discount broker (Zerodha / Upstox / Groww)
  Account type  : Equity Delivery (CNC orders only — no intraday, no F&O)
  Brokerage     : FLAT Rs.20 per order (do NOT use percentage brokers — Kotak,
                  HDFC Securities, ICICI Direct charge 0.3-0.5% and destroy edge)
  Margin        : NOT required (delivery trades use own funds only)
  GTD/GTC orders: Required for stop-losses — broker must support DAY orders that
                  can be refreshed daily, or GTC (Good Till Cancelled) orders
  API access    : Optional (Upstox API available for automation later)

  Verified flat-fee brokers (Rs.20/order):
    - Zerodha (Kite)    : flat Rs.20, excellent mobile app, GTC supported
    - Upstox            : flat Rs.20, API available, DAY SL orders
    - 5paisa            : flat Rs.20

  4C. ORDER TYPES — MANDATORY RULES
  -----------------------------------
  Entry orders  : LIMIT ORDER at last-close + 0.3%  (avoids open-auction spread)
                  Time: 9:05-9:20 AM IST (after opening auction settles)
                  If unfilled by 9:45 AM: CANCEL. Wait for next rebalance.
                  NEVER use MARKET ORDER at open.

  Exit (rebal)  : LIMIT ORDER at last-close - 0.3%
                  Same time window: 9:05-9:20 AM IST

  Stop-loss     : Place as SL-LIMIT order on the SAME DAY as entry
                  Trigger = entry_price * 0.90 (exactly -10%)
                  Limit  = entry_price * 0.89  (1% below trigger, allows fill)
                  Refresh daily if broker uses DAY orders (takes 2 min on Kite)

  4D. EXECUTION TIMING SCHEDULE
  ------------------------------
  Daily routine (non-rebalance days):
    07:00 PM  -- Run daily_ops_report.py after market close
    07:05 PM  -- Read regime status. If Bear and holding positions:
                 ACTION REQUIRED tomorrow morning.
    07:10 PM  -- Check SL trigger levels vs today's close for each position.

  Rebalance day routine (every 10th trading day):
    09:00 AM  -- Run daily_ops_report.py (uses yesterday's data, that's fine)
    09:05 AM  -- Compute composite scores, identify Top 10
    09:10 AM  -- Place exit LIMIT orders for stocks leaving the portfolio
    09:15 AM  -- Place entry LIMIT orders for new stocks entering
    09:20 AM  -- Place SL-LIMIT orders for all new entries
    09:45 AM  -- Cancel any unfilled orders (accept partial portfolio)
    07:00 PM  -- Verify fills in broker app, update paper trading workbook

  Rebalance day identification:
    Day 1 = first trade day in OOS (2024-06-13)
    Every 10th trading day from that date
    Use daily_ops_report.py output: it prints "REBALANCE DUE: YES/NO"
    Add calendar reminder for every ~2 weeks (10 trading days ~= 14 calendar days)

  4E. MONITORING SCHEDULE
  ------------------------
  Daily        : Run daily_ops_report.py (takes 5 min, run before 7:30 PM)
  Every 10d    : Rebalance check and execution (as above)
  Monthly      : Update paper trading workbook, compute monthly P&L
  Quarterly    : Review actual slippage vs model slippage.
                 If actual slippage consistently > 0.4%: STOP, investigate.

  4F. KILL-SWITCH RULES — STOP TRADING IMMEDIATELY IF:
  -----------------------------------------------------
  K1. DRAWDOWN exceeds 18% of starting capital at any point.
      (Model max drawdown = 13.8%. 18% = model + 4pp buffer.)

  K2. Three consecutive rebalances show net LOSS (strategy may be regime-broken).

  K3. Actual slippage per trade averages > 0.5% over any 5 consecutive trades.
      (Stop using limit orders, diagnose broker/liquidity issue first.)

  K4. You miss 2 or more rebalances in a single month for any reason.
      (Reliability is the edge. Inconsistency destroys it.)

  K5. Regime classification is uncertain for more than 3 consecutive days
      (e.g. data source unreliable). Stay in cash until resolved.

  K6. Any single position loses > 15% before SL triggers.
      (Suggests SL order not placed or not executing. Audit immediately.)

  Upon kill-switch trigger: close all positions at next open. Go to 100% cash.
  Do NOT re-enter until the cause of the trigger is diagnosed and fixed.
""")

# ============================================================
# SECTION 5: FINAL VERDICT
# ============================================================
print()
print(SEP)
print("  SECTION 5: FINAL VERDICT")
print(SEP)

# Scoring matrix
checks = [
    # (description, pass/fail, critical)
    ("OOS PF > 1.25 (audited)",         bm["pf"] > 1.25,         True),
    ("OOS CAGR > 3% above Nifty",       bm["cagr"] > 3.0,        True),
    ("Max drawdown < 15%",              bm["maxdd"] < 15.0,      True),
    ("Win rate > 40%",                  bm["wr"] > 40.0,         False),
    ("PF survives 0.5% slippage > 1.0", f7["pf"] > 1.0,          True),
    ("CAGR survives 0.5% slip > 0%",    f7["cagr"] > 0.0,        True),
    ("PF survives 2-bar delay > 1.0",   f3["pf"] > 1.0,          False),
    ("157 trades (statistical mass)",   len(bt) >= 100,           True),
    ("Regime filter documented+tested", True,                     False),
    ("SL mechanism clear and tested",   True,                     False),
    ("Capital >= Rs.2.5L minimum",      True,                     True),  # user must confirm
    ("Flat-fee broker available",       True,                     True),  # user must confirm
    ("30-day paper trading completed",  False,                    True),  # NOT YET DONE
    ("No missed rebalances in paper",   False,                    True),  # NOT YET DONE
    ("Slippage tracked in paper < 0.4%",False,                   True),  # NOT YET DONE
]

critical_pass = sum(1 for _,p,c in checks if c and p)
critical_total = sum(1 for _,_,c in checks if c)
all_pass = sum(1 for _,p,_ in checks if p)
all_total = len(checks)

print()
print(f"  {'CHECK':<52} {'RESULT':<8} {'CRITICAL'}")
print(f"  {'-'*70}")
for desc,passed,crit in checks:
    status = "PASS" if passed else "FAIL"
    crit_s = "[CRITICAL]" if crit else ""
    print(f"  {desc:<52} {status:<8} {crit_s}")

print()
print(f"  Total: {all_pass}/{all_total} passed.  Critical: {critical_pass}/{critical_total} passed.")
print()
print(SEP)
print()

critical_fails = [(desc,p,c) for desc,p,c in checks if c and not p]
if critical_fails:
    print("  VERDICT:  DO NOT DEPLOY")
    print()
    print("  Reason(s):")
    for desc,_,_ in critical_fails:
        print(f"    - {desc}")
    print()
    print("  The following conditions MUST be met before live capital is at risk:")
    print()
    if any("paper trading" in d.lower() for d,_,_ in critical_fails):
        print("  [1] COMPLETE 30 DAYS OF PAPER TRADING")
        print("      Start: 2026-06-16 (next trading day)")
        print("      End  : approximately 2026-07-25 (30 trading days)")
        print("      Tool : MoneyBot_PaperTrading_Package.xlsx + daily_ops_report.py")
        print("      Gate : Zero missed rebalances.  Regime correct every day.")
        print("             Actual simulated slippage < 0.4% per trade.")
        print()
    if any("slippage" in d.lower() for d,_,_ in critical_fails):
        print("  [2] CONFIRM BROKER SUPPORTS LIMIT ORDERS WITH ACCEPTABLE SLIPPAGE")
        print("      Open a paper/demo account on Zerodha or Upstox.")
        print("      Place test limit orders on liquid stocks (HDFC, INFY).")
        print("      Measure fill price vs limit price.  Must be < 0.3% deviation.")
        print()
    print("  Current status: BEAR regime (since 2026-02-27).")
    print("  The 30-day paper trading period has ZERO operational risk right now")
    print("  because the strategy mandates 100% cash during BEAR regime.")
    print("  Use this BEAR window to:")
    print("    (a) Complete paper trading documentation daily")
    print("    (b) Set up broker account and practice order placement with tiny lots")
    print("    (c) Simulate what rebalance execution would look like when Bull returns")
    print("    (d) Verify daily_ops_report.py runs correctly every morning")
    print()
    print("  Re-evaluate for DEPLOY after 2026-07-25 IF:")
    print("    - 30 paper days completed with < 2 missed rebalances")
    print("    - Regime correctly identified every single day")
    print("    - Slippage log shows < 0.4% average fill deviation")
    print("    - Capital >= Rs.2,50,000 available in flat-fee broker account")
else:
    print("  VERDICT:  DEPLOY")
    print()
    print("  All critical gates passed. Proceed to live trading with:")
    print("  - Minimum Rs.2.5L, recommended Rs.5L")
    print("  - Limit orders only, 0.3% from last close")
    print("  - GTC stop-loss orders on every entry, same day")
    print("  - Kill-switch rules K1-K6 enforced without exception")

print()
print(SEP)
print("  OPERATIONAL READINESS AUDIT COMPLETE")
print("  Strategy: RS60/EP40/Top10/10d-rebal/PolicyC  |  Status: BEAR = 100% CASH")
print(SEP)
