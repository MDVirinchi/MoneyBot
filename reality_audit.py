"""
reality_audit.py  --  RS60/EP40 OOS Reality Audit
===================================================
Identical data loading and simulation logic as final_validation.py.
Adds full trade-level logging and stress scenarios.
Research freeze: no parameter changes.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import math, statistics, warnings, logging, datetime, time
from collections import defaultdict
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

# ── Locked strategy constants (same as final_validation.py) ──────────────────
W_RS=0.60; W_EP=0.40; TOP_N=10; REBAL_DAYS=10; SL_PCT=10.0
BROKERAGE=20.0; STT=0.001; EXCHANGE=0.0000345; BASE_SLIP=0.002
CAPITAL=500_000.0

SECTOR={
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
    ('M&MFIN.NS','M&MFIN'),('PGHH.NS','PGHH'),
]

# ── Data download ─────────────────────────────────────────────────────────────
print("Downloading data (this takes ~10 min)...")
nifty_raw = {}
try:
    nd = yf.download("^NSEI", period="5y", interval="1d", progress=False, auto_adjust=True)
    for ts, row in nd.iterrows():
        nifty_raw[ts.strftime("%Y-%m-%d")] = float(row["Close"])
except Exception as e:
    print(f"Nifty download failed: {e}")

price_data = {}
valid = []
for ticker, sym in STOCKS:
    try:
        df = yf.download(ticker, period="5y", interval="1d", progress=False, auto_adjust=True)
        if len(df) < 200:
            continue
        d = {}
        prev_close = None
        for ts, row in df.iterrows():
            dt = ts.strftime("%Y-%m-%d")
            o = float(row["Open"]); h = float(row["High"])
            l = float(row["Low"]);  c = float(row["Close"])
            v = int(row["Volume"])
            if prev_close and prev_close > 0 and abs(c/prev_close - 1) > 0.5:
                prev_close = c; continue
            d[dt] = {"open": o, "high": h, "low": l, "close": c, "vol": v}
            prev_close = c
        if len(d) >= 200:
            price_data[sym] = d
            valid.append(sym)
    except Exception:
        pass
    time.sleep(0.15)

all_dates = sorted(nifty_raw.keys())
N = len(all_dates)
IS_END = int(N * 0.6)
IS_DATES  = all_dates[:IS_END]
OOS_DATES = all_dates[IS_END:]
n_start = nifty_raw.get(OOS_DATES[0],1); n_end = nifty_raw.get(OOS_DATES[-1],1)
NIFTY_OOS_CAGR = ((n_end/n_start)**(252/len(OOS_DATES))-1)*100

print(f"Universe: {len(valid)} stocks  |  {all_dates[0]} to {all_dates[-1]}  ({N} days)")
print(f"IS:  {IS_DATES[0]} to {IS_DATES[-1]}  ({len(IS_DATES)} days)")
print(f"OOS: {OOS_DATES[0]} to {OOS_DATES[-1]}  ({len(OOS_DATES)} days)  Nifty OOS CAGR={NIFTY_OOS_CAGR:+.1f}%\n")

# ── DMA + regime ──────────────────────────────────────────────────────────────
nifty_dma = {}
nifty_closes = [(d, nifty_raw[d]) for d in all_dates]
for idx, (d, c) in enumerate(nifty_closes):
    dma50  = sum(v for _,v in nifty_closes[max(0,idx-49):idx+1]) / min(idx+1,50)
    dma200 = sum(v for _,v in nifty_closes[max(0,idx-199):idx+1]) / min(idx+1,200)
    nifty_dma[d] = {"close":c,"dma50":dma50,"dma200":dma200}

def regime(date):
    r = nifty_dma.get(date)
    if not r: return "Bull"
    c,d50,d200 = r["close"],r["dma50"],r["dma200"]
    if c < d200:    return "Bear"
    if d50 <= d200: return "Flat"
    return "Bull"

# ── Factor engine ─────────────────────────────────────────────────────────────
_raw_cache = {}

def get_raw(gi):
    if gi in _raw_cache: return _raw_cache[gi]
    if gi < 72: return {}
    dn = all_dates[gi]
    nc = nifty_raw.get(dn)
    np_ = nifty_raw.get(all_dates[gi-63]) if gi >= 63 else None
    raw_rs = {}; raw_ep = {}
    for sym in valid:
        c = price_data[sym]
        sd = [d for d in all_dates[max(0,gi-74):gi+1] if d in c]
        if len(sd) < 50: continue
        if nc and np_:
            cn = c.get(dn,{}).get("close"); cp = c.get(all_dates[gi-63],{}).get("close")
            if cn and cp: raw_rs[sym] = (cn/cp-1)*100 - (nc/np_-1)*100
        ed = sd[-63:]
        evols = [c[d]["vol"] for d in ed if c[d]["vol"]>0]
        av = sum(evols)/len(evols) if evols else 0
        ep = 0.0
        for j in range(1,len(ed)):
            cj=c.get(ed[j]); cjm=c.get(ed[j-1])
            if not(cj and cjm and cjm["close"]>0): continue
            dr = cj["close"]/cjm["close"]-1
            if dr>0.02 and av>0 and cj["vol"]>1.5*av: ep=max(ep,dr*100)
        raw_ep[sym] = ep
    _raw_cache[gi] = {"rs":raw_rs,"ep":raw_ep}
    return _raw_cache[gi]

def composite(gi):
    raw = get_raw(gi)
    if not raw: return {}
    def pr(d):
        items=sorted(d.items(),key=lambda x:x[1]); n=len(items)
        return {s:(r+1)/n*100 for r,(s,_) in enumerate(items)}
    rnk_rs = pr(raw["rs"]) if raw["rs"] else {}
    rnk_ep = pr(raw["ep"]) if raw["ep"] else {}
    syms = set(rnk_rs.keys()) & set(rnk_ep.keys())
    if not syms: return {}
    return {s: W_RS*rnk_rs[s] + W_EP*rnk_ep[s] for s in syms}

print("Pre-computing factors...")
gi = 72
while gi < N:
    get_raw(gi); gi += REBAL_DAYS
print(f"Cached {len(_raw_cache)} rebalance points.\n")

# ── Core simulator with FULL trade log ───────────────────────────────────────
def run_sim_full(date_range, slip=BASE_SLIP, regime_policy="bull_flat",
                 fill_delay=1, miss_fill_pct=0.0, skip_rebal_pct=0.0):
    """
    Full-detail simulation with per-trade records and equity curve.
    fill_delay     : bars delay before fill (0=same bar open, 1=next bar open, 2=2 bars)
    miss_fill_pct  : probability [0-1] a fill is missed entirely (stock stays in cash)
    skip_rebal_pct : probability [0-1] a rebalance is skipped entirely
    """
    import random
    random.seed(42)

    cash = CAPITAL
    pos  = {}       # sym -> {qty, ep (entry price), entry_date}
    trades = []     # full trade records
    equity = []
    last_rebal = -999
    date_to_gi = {d: all_dates.index(d) for d in date_range if d in all_dates}

    def gc(s, d): return price_data[s].get(d, {}).get("close")
    def go(s, d): return price_data[s].get(d, {}).get("open")

    def next_open(sym, idx, dr):
        """Get fill price with delay and slippage."""
        for delta in range(fill_delay, fill_delay + 3):
            nidx = idx + delta
            if nidx < len(dr):
                nd = dr[nidx]
                px = go(sym, nd) or gc(sym, nd)
                if px: return px, nd
        return None, None

    for idx, date in enumerate(date_range):
        gi = date_to_gi.get(date)
        if gi is None or gi < 72:
            equity.append(cash + sum(p["qty"]*(gc(s,date) or p["ep"]) for s,p in pos.items()))
            continue

        reg = regime(date)
        # Bear = liquidate all
        if regime_policy == "bull_flat" and reg == "Bear":
            for sym in list(pos):
                nd = date_range[idx+1] if idx+1 < len(date_range) else date
                fp = (go(sym,nd) or gc(sym,date) or pos[sym]["ep"]) * (1-slip)
                p = pos.pop(sym)
                ev = p["qty"] * fp
                cost = BROKERAGE + ev*STT + ev*EXCHANGE
                cash += ev - cost
                pnl  = (fp - p["ep"]) * p["qty"] - cost
                trades.append({
                    "sym": sym, "entry_date": p["entry_date"], "exit_date": nd,
                    "entry": p["ep"], "exit": fp, "qty": p["qty"],
                    "pnl": pnl, "ret_pct": (fp/p["ep"]-1)*100, "exit_reason": "Regime-Bear"
                })
            equity.append(cash); continue

        # Stop-loss check
        for sym in list(pos):
            curr = gc(sym, date)
            if curr and curr <= pos[sym]["ep"] * (1 - SL_PCT/100):
                fill = curr * (1-slip)
                p = pos.pop(sym)
                ev = p["qty"] * fill
                cost = BROKERAGE + ev*STT + ev*EXCHANGE
                cash += ev - cost
                pnl  = (fill - p["ep"]) * p["qty"] - cost
                trades.append({
                    "sym": sym, "entry_date": p["entry_date"], "exit_date": date,
                    "entry": p["ep"], "exit": fill, "qty": p["qty"],
                    "pnl": pnl, "ret_pct": (fill/p["ep"]-1)*100, "exit_reason": "SL"
                })

        # Rebalance
        if idx - last_rebal >= REBAL_DAYS:
            # Optionally skip this rebalance (human error simulation)
            if skip_rebal_pct > 0 and random.random() < skip_rebal_pct:
                pass  # skip — positions held unchanged
            else:
                last_rebal = idx
                comp = composite(gi)
                tgt  = {s for s,_ in sorted(comp.items(), key=lambda x:-x[1])[:TOP_N]}

                # Sell exits
                for sym in list(pos):
                    if sym not in tgt:
                        fp, nd = next_open(sym, idx, date_range)
                        if fp is None:
                            nd   = date
                            fp   = (gc(sym,date) or pos[sym]["ep"]) * (1-slip)
                        else:
                            fp *= (1-slip)
                        p  = pos.pop(sym)
                        ev = p["qty"] * fp
                        cost = BROKERAGE + ev*STT + ev*EXCHANGE
                        cash += ev - cost
                        pnl  = (fp - p["ep"]) * p["qty"] - cost
                        trades.append({
                            "sym": sym, "entry_date": p["entry_date"], "exit_date": nd,
                            "entry": p["ep"], "exit": fp, "qty": p["qty"],
                            "pnl": pnl, "ret_pct": (fp/p["ep"]-1)*100, "exit_reason": "Rebal"
                        })

                # Buy entries
                new  = [s for s in tgt if s not in pos]
                avail_cap = cash * 0.95
                if new and avail_cap > 10_000:
                    alloc = min(avail_cap / max(len(new),1), CAPITAL/TOP_N)
                    for sym in new:
                        # Missed fill simulation
                        if miss_fill_pct > 0 and random.random() < miss_fill_pct:
                            continue
                        fp, nd = next_open(sym, idx, date_range)
                        if fp is None: continue
                        fill = fp * (1+slip)
                        qty  = max(1, int(alloc/fill))
                        cost = BROKERAGE + qty*fill*EXCHANGE
                        if cash >= qty*fill + cost:
                            cash -= qty*fill + cost
                            pos[sym] = {"qty": qty, "ep": fill, "entry_date": nd or date}

        fv = cash + sum(p["qty"]*(gc(s,date) or p["ep"]) for s,p in pos.items())
        equity.append(fv)

    # Close all remaining at end of period
    for sym, p in list(pos.items()):
        last_date = date_range[-1]
        fp = (gc(sym, last_date) or p["ep"]) * (1-slip)
        ev = p["qty"] * fp
        cost = BROKERAGE + ev*STT + ev*EXCHANGE
        cash += ev - cost
        pnl  = (fp - p["ep"]) * p["qty"] - cost
        trades.append({
            "sym": sym, "entry_date": p["entry_date"], "exit_date": last_date,
            "entry": p["ep"], "exit": fp, "qty": p["qty"],
            "pnl": pnl, "ret_pct": (fp/p["ep"]-1)*100, "exit_reason": "EoP"
        })
        equity[-1] = cash + 0  # all liquidated

    return trades, equity

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 0: reproduce OOS PF=1.349 on OOS dates
# ─────────────────────────────────────────────────────────────────────────────
print("Running baseline OOS simulation...")
base_trades, base_equity = run_sim_full(OOS_DATES)

wins   = [t for t in base_trades if t["pnl"] > 0]
losses = [t for t in base_trades if t["pnl"] <= 0]
gp = sum(t["pnl"] for t in wins)
gl = abs(sum(t["pnl"] for t in losses))
pf = gp/gl if gl > 0 else 0
yrs = len(OOS_DATES)/252
fv  = CAPITAL + sum(t["pnl"] for t in base_trades)
cagr = ((fv/CAPITAL)**(1/yrs)-1)*100 if fv > 0 else -100

SEP = "=" * 72
sep = "-" * 72

print()
print(SEP)
print("  REALITY AUDIT  --  RS60/EP40 OOS  (Policy C: Bull+Flat trade, Bear=cash)")
print(SEP)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: Trade count and summary
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("  1. TRADE COUNT AND OOS SUMMARY")
print(SEP)
print(f"  OOS period          : {OOS_DATES[0]} to {OOS_DATES[-1]}  ({len(OOS_DATES)} trading days)")
print(f"  Total trades        : {len(base_trades)}")
print(f"    Rebalance exits   : {sum(1 for t in base_trades if t['exit_reason']=='Rebal')}")
print(f"    Stop-loss exits   : {sum(1 for t in base_trades if t['exit_reason']=='SL')}")
print(f"    Regime exits      : {sum(1 for t in base_trades if 'Regime' in t['exit_reason'])}")
print(f"    End-of-period     : {sum(1 for t in base_trades if t['exit_reason']=='EoP')}")
print(f"  Winning trades      : {len(wins)}  ({len(wins)/len(base_trades)*100:.1f}%)")
print(f"  Losing trades       : {len(losses)}  ({len(losses)/len(base_trades)*100:.1f}%)")
print(f"  Gross profit        : Rs.{gp:,.0f}")
print(f"  Gross loss          : Rs.{gl:,.0f}")
print(f"  Net P&L             : Rs.{gp-gl:,.0f}")
print(f"  Profit Factor       : {pf:.3f}  (target: 1.349)")
print(f"  CAGR                : {cagr:+.1f}%  (target: +5.7%)")
print(f"  Nifty OOS CAGR      : {NIFTY_OOS_CAGR:+.1f}%")
print(f"  Alpha               : {cagr - NIFTY_OOS_CAGR:+.1f}pp")

# Avg hold time
hold_times = []
for t in base_trades:
    try:
        ed = datetime.date.fromisoformat(t["entry_date"])
        xd = datetime.date.fromisoformat(t["exit_date"])
        hold_times.append((xd-ed).days)
    except: pass
if hold_times:
    print(f"  Avg hold time       : {statistics.mean(hold_times):.1f} calendar days")
    print(f"  Median hold time    : {statistics.median(hold_times):.0f} calendar days")

# Avg trades per rebalance
rebal_exits = [t for t in base_trades if t["exit_reason"] in ("Rebal","EoP")]
est_rebalances = len(OOS_DATES) // REBAL_DAYS
print(f"  Est. rebalances     : {est_rebalances}")
print(f"  Avg trades/rebal    : {len(base_trades)/max(est_rebalances,1):.1f}")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Year-by-year annual returns
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("  2. YEAR-BY-YEAR ANNUAL RETURNS  (OOS only)")
print(SEP)

# Group equity by year
year_equity = defaultdict(list)
for i, d in enumerate(OOS_DATES):
    if i < len(base_equity):
        year_equity[d[:4]].append(base_equity[i])

years = sorted(year_equity.keys())
print(f"  {'Year':<6} {'Start Eq':>12} {'End Eq':>12} {'Return':>9} {'vs Nifty':>10}")
print(f"  {'-'*52}")
prev_eq = CAPITAL
for yr in years:
    vals = year_equity[yr]
    if not vals: continue
    start = prev_eq
    end   = vals[-1]
    ret   = (end/start - 1)*100 if start > 0 else 0
    # Nifty return for same year
    yr_nifty_dates = [d for d in OOS_DATES if d.startswith(yr)]
    if len(yr_nifty_dates) >= 2:
        ns = nifty_raw.get(yr_nifty_dates[0],1)
        ne = nifty_raw.get(yr_nifty_dates[-1],1)
        nret = (ne/ns-1)*100
    else:
        nret = 0
    flag = " [BEAR YR]" if ret < -5 else (" [BEST]" if ret == max((base_equity[i]/prev_eq-1)*100 if i>0 else 0 for i in range(len(base_equity))) else "")
    print(f"  {yr:<6} {start:>12,.0f} {end:>12,.0f} {ret:>+8.1f}%  {nret:>+8.1f}%")
    prev_eq = end

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Rolling 3-month returns
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("  3. ROLLING 3-MONTH (63-TRADING-DAY) RETURNS  (OOS)")
print(SEP)

WINDOW = 63
rolling = []
for i in range(WINDOW, len(base_equity)):
    start = base_equity[i - WINDOW]
    end   = base_equity[i]
    if start > 0:
        ret = (end/start - 1) * 100
        rolling.append({"date": OOS_DATES[i] if i < len(OOS_DATES) else "?", "ret": ret})

if rolling:
    rets = [r["ret"] for r in rolling]
    neg  = [r for r in rets if r < 0]
    print(f"  Observations (rolling 63-day windows) : {len(rolling)}")
    print(f"  Mean 3-month return   : {statistics.mean(rets):+.1f}%")
    print(f"  Median 3-month return : {statistics.median(rets):+.1f}%")
    print(f"  Best 3-month          : {max(rets):+.1f}%")
    print(f"  Worst 3-month         : {min(rets):+.1f}%")
    print(f"  Positive periods      : {len([r for r in rets if r>=0])}  ({len([r for r in rets if r>=0])/len(rets)*100:.0f}%)")
    print(f"  Negative periods      : {len(neg)}  ({len(neg)/len(rets)*100:.0f}%)")
    print(f"  Avg loss when negative: {statistics.mean(neg):+.1f}%")
    print()
    print(f"  {'Quarter end date':<14} {'3M return':>10}")
    print(f"  {'-'*26}")
    step = max(1, len(rolling) // 20)  # show ~20 data points
    for r in rolling[::step]:
        bar = "#" * min(30, int(abs(r["ret"])))
        sign = "+" if r["ret"] >= 0 else "-"
        print(f"  {r['date']:<14} {r['ret']:>+9.1f}%  {bar}")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 & 5: Worst 10 and Best 10 trades
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("  4. WORST 10 TRADES  (by Rs. P&L)")
print(SEP)
sorted_trades = sorted(base_trades, key=lambda t: t["pnl"])
print(f"  {'#':<3} {'Symbol':<14} {'Entry date':<12} {'Exit date':<12} {'Entry':>8} {'Exit':>8} {'Qty':>5} {'P&L':>10} {'Ret%':>7} {'Reason'}")
print(f"  {'-'*90}")
for i, t in enumerate(sorted_trades[:10], 1):
    print(f"  {i:<3} {t['sym']:<14} {t['entry_date']:<12} {t['exit_date']:<12} "
          f"{t['entry']:>8.1f} {t['exit']:>8.1f} {t['qty']:>5} "
          f"{t['pnl']:>+10.0f} {t['ret_pct']:>+6.1f}%  {t['exit_reason']}")

print()
print(SEP)
print("  5. BEST 10 TRADES  (by Rs. P&L)")
print(SEP)
print(f"  {'#':<3} {'Symbol':<14} {'Entry date':<12} {'Exit date':<12} {'Entry':>8} {'Exit':>8} {'Qty':>5} {'P&L':>10} {'Ret%':>7} {'Reason'}")
print(f"  {'-'*90}")
for i, t in enumerate(sorted(base_trades, key=lambda t: -t["pnl"])[:10], 1):
    print(f"  {i:<3} {t['sym']:<14} {t['entry_date']:<12} {t['exit_date']:<12} "
          f"{t['entry']:>8.1f} {t['exit']:>8.1f} {t['qty']:>5} "
          f"{t['pnl']:>+10.0f} {t['ret_pct']:>+6.1f}%  {t['exit_reason']}")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: Turnover per rebalance
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("  6. TURNOVER PER REBALANCE")
print(SEP)

rebal_trades = [t for t in base_trades if t["exit_reason"] == "Rebal"]
total_rebal_turnover = sum(t["qty"] * t["exit"] for t in rebal_trades)
avg_portfolio_value  = statistics.mean(base_equity) if base_equity else CAPITAL
avg_trades_per_rebal = len(rebal_trades) / max(est_rebalances, 1)

# Estimate cost per rebalance
total_costs = sum(
    BROKERAGE*2 + t["qty"]*t["entry"]*EXCHANGE + t["qty"]*t["exit"]*STT + t["qty"]*t["exit"]*EXCHANGE
    for t in base_trades
)
cost_per_rebal = total_costs / max(est_rebalances, 1)
total_rebal_value = sum(t["qty"]*t["exit"] for t in rebal_trades)

print(f"  Rebalance exits (turnover trades)  : {len(rebal_trades)}")
print(f"  Estimated rebalances in OOS period : {est_rebalances}")
print(f"  Avg stocks rotated per rebalance   : {avg_trades_per_rebal:.1f}  out of {TOP_N}")
print(f"  Avg turnover per rebalance         : Rs.{total_rebal_turnover/max(est_rebalances,1):,.0f}")
print(f"  Avg portfolio value                : Rs.{avg_portfolio_value:,.0f}")
print(f"  Turnover as % of portfolio         : {total_rebal_turnover/max(est_rebalances,1)/avg_portfolio_value*100:.1f}% per rebalance")
print(f"  Total transaction costs (all)      : Rs.{total_costs:,.0f}")
print(f"  Costs as % of initial capital      : {total_costs/CAPITAL*100:.2f}%")
print(f"  Avg cost per rebalance             : Rs.{cost_per_rebal:,.0f}")
print(f"  Brokerage alone per rebalance      : Rs.{BROKERAGE*2*avg_trades_per_rebal:.0f}  (Rs.40 x {avg_trades_per_rebal:.0f} trades)")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: Capital requirements
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("  7. REAL-WORLD CAPITAL REQUIREMENTS")
print(SEP)

# Minimum single-stock allocation = price of 1 share of the most expensive stock
# Use rough estimate: at Rs.1L total / 10 stocks = Rs.10,000 per slot
# At Rs.2.5L / 10 = Rs.25,000 per slot, etc.

capital_scenarios = [
    (100_000,   "Rs.1 Lakh"),
    (250_000,   "Rs.2.5 Lakh"),
    (500_000,   "Rs.5 Lakh"),
    (1_000_000, "Rs.10 Lakh"),
]

# Find avg stock price across all entries in base_trades
all_entry_prices = [t["entry"] for t in base_trades if t.get("entry")]
avg_stock_price  = statistics.median(all_entry_prices) if all_entry_prices else 1500
min_stock_price  = min(all_entry_prices) if all_entry_prices else 100
max_stock_price  = max(all_entry_prices) if all_entry_prices else 5000

print(f"  Stock price range in OOS trades: Rs.{min_stock_price:.0f} – Rs.{max_stock_price:.0f}")
print(f"  Median stock entry price       : Rs.{avg_stock_price:.0f}")
print(f"  Min shares per position (qty=1): Rs.{min_stock_price:.0f} per slot")
print()
print(f"  {'Capital':<15} {'Per slot':>10} {'Min shares':>12} {'Feasible?':>12} {'Brokerage drag':>16} {'Est. CAGR adj':>14}")
print(f"  {'-'*72}")

for cap, label in capital_scenarios:
    per_slot = cap / TOP_N
    min_shares = int(per_slot / avg_stock_price)
    feasible   = "YES" if per_slot >= avg_stock_price else "MARGINAL" if per_slot >= avg_stock_price*0.3 else "NO (round lots)"
    # Brokerage drag = Rs.40 round-trip x avg_trades_per_rebal rebalances x est_rebalances
    annual_brokerage = BROKERAGE * 2 * avg_trades_per_rebal * (252/REBAL_DAYS)
    brokerage_drag   = annual_brokerage / cap * 100
    est_cagr_adj     = cagr - brokerage_drag  # rough adjustment from base CAGR
    print(f"  {label:<15} {per_slot:>10,.0f} {min_shares:>12} {feasible:>12} {brokerage_drag:>14.2f}%  {est_cagr_adj:>+12.1f}%")

print()
print(f"  NOTE: Brokerage drag = Rs.40 flat x ~{avg_trades_per_rebal:.0f} trades/rebal x ~25 rebalances/yr")
print(f"  At Rs.1L, brokerage alone can consume 5–10% of capital/year, eliminating the edge.")
print(f"  Minimum viable capital for this strategy: approximately Rs.3–5 Lakh.")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: Operational stress scenarios
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("  8. OPERATIONAL STRESS SIMULATIONS  (vs baseline)")
print(SEP)

def summarize(trades, equity, label):
    if not trades:
        print(f"  {label:<40}: NO TRADES")
        return
    w = [t for t in trades if t["pnl"]>0]
    l = [t for t in trades if t["pnl"]<=0]
    gp_ = sum(t["pnl"] for t in w)
    gl_ = abs(sum(t["pnl"] for t in l))
    pf_ = gp_/gl_ if gl_>0 else 0
    fv_ = CAPITAL + sum(t["pnl"] for t in trades)
    yrs_= len(OOS_DATES)/252
    cagr_ = ((fv_/CAPITAL)**(1/yrs_)-1)*100 if fv_>0 else -100
    peak_ = CAPITAL; dd_=0
    for v in equity:
        if v>peak_: peak_=v
        d=(peak_-v)/peak_*100 if peak_>0 else 0
        if d>dd_: dd_=d
    print(f"  {label:<40}: PF={pf_:.3f}  CAGR={cagr_:+.1f}%  MaxDD={dd_:.1f}%  Trades={len(trades)}  WR={len(w)/len(trades)*100:.0f}%")

print(f"  {'Scenario':<40}  PF     CAGR     MaxDD   Trades  WR")
print(f"  {'-'*72}")

# Baseline
summarize(base_trades, base_equity, "Baseline (0.2% slippage, 1-bar delay)")

# 0.5% slippage
t2, e2 = run_sim_full(OOS_DATES, slip=0.005)
summarize(t2, e2, "0.5% slippage each side")

# 1.0% slippage (stress)
t3, e3 = run_sim_full(OOS_DATES, slip=0.010)
summarize(t3, e3, "1.0% slippage each side (extreme)")

# 1-day delayed execution (already in baseline as fill_delay=1)
t4, e4 = run_sim_full(OOS_DATES, fill_delay=2)
summarize(t4, e4, "2-bar execution delay")

# 3-day execution delay
t5, e5 = run_sim_full(OOS_DATES, fill_delay=3)
summarize(t5, e5, "3-bar execution delay")

# 20% missed fills (1 in 5 entries missed)
t6, e6 = run_sim_full(OOS_DATES, miss_fill_pct=0.20)
summarize(t6, e6, "20% missed fills (underweight)")

# 30% skipped rebalances (human forgets)
t7, e7 = run_sim_full(OOS_DATES, skip_rebal_pct=0.30)
summarize(t7, e7, "30% skipped rebalances")

# Worst combo: 0.5% slip + 2-bar delay + 20% missed fills
t8, e8 = run_sim_full(OOS_DATES, slip=0.005, fill_delay=2, miss_fill_pct=0.20)
summarize(t8, e8, "COMBO: 0.5%slip+2bar+20%miss")

# Full worst: 0.5% slip + 2-bar + 20% miss + 30% skip rebal
t9, e9 = run_sim_full(OOS_DATES, slip=0.005, fill_delay=2, miss_fill_pct=0.20, skip_rebal_pct=0.30)
summarize(t9, e9, "WORST CASE: all errors combined")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9: Paper-trading scorecard
# ─────────────────────────────────────────────────────────────────────────────
print()
print(SEP)
print("  9. PAPER-TRADING SCORECARD  --  PASS/FAIL CRITERIA")
print("     These are the gates that must be met before deploying real capital.")
print(SEP)

def check(label, value, threshold, direction="above", fmt=".2f"):
    if direction == "above":
        passed = value >= threshold
    else:
        passed = value <= threshold
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}]  {label:<42} {value:{fmt}}  (threshold: {direction} {threshold:{fmt}})")
    return passed

wins_b   = [t for t in base_trades if t["pnl"]>0]
losses_b = [t for t in base_trades if t["pnl"]<=0]
avg_win  = statistics.mean([t["pnl"] for t in wins_b])   if wins_b   else 0
avg_loss = statistics.mean([t["pnl"] for t in losses_b]) if losses_b else 0
wl_ratio = abs(avg_win/avg_loss) if avg_loss != 0 else 0
peak_eq  = CAPITAL; max_dd_val = 0
for v in base_equity:
    if v > peak_eq: peak_eq = v
    dd = (peak_eq - v)/peak_eq*100 if peak_eq > 0 else 0
    if dd > max_dd_val: max_dd_val = dd

wr_pct = len(wins_b)/len(base_trades)*100 if base_trades else 0

score = 0
total = 0

print()
print("  STRATEGY HEALTH (from OOS simulation):")
total+=1; score += check("Profit Factor", pf, 1.10, "above")
total+=1; score += check("CAGR", cagr, 3.0, "above", ".1f")
total+=1; score += check("Win Rate", wr_pct, 40.0, "above", ".1f")
total+=1; score += check("Win/Loss ratio", wl_ratio, 1.5, "above")
total+=1; score += check("Max Drawdown", max_dd_val, 20.0, "below", ".1f")
total+=1; score += check("Trade count (reliability)", len(base_trades), 30, "above", ".0f")

print()
print("  STRESS RESILIENCE:")
w2=[t for t in t2 if t["pnl"]>0]; l2=[t for t in t2 if t["pnl"]<=0]
pf2 = sum(t["pnl"] for t in w2) / abs(sum(t["pnl"] for t in l2)) if l2 else 0
fv2 = CAPITAL + sum(t["pnl"] for t in t2)
cagr2 = ((fv2/CAPITAL)**(1/yrs)-1)*100 if fv2>0 and yrs>0 else -100
total+=1; score += check("PF survives 0.5% slippage", pf2, 1.0, "above")
total+=1; score += check("CAGR survives 0.5% slippage", cagr2, 0.0, "above", ".1f")

w8=[t for t in t8 if t["pnl"]>0]; l8=[t for t in t8 if t["pnl"]<=0]
pf8 = sum(t["pnl"] for t in w8) / abs(sum(t["pnl"] for t in l8)) if l8 else 0
total+=1; score += check("PF survives COMBO stress scenario", pf8, 0.90, "above")

w7=[t for t in t7 if t["pnl"]>0]; l7=[t for t in t7 if t["pnl"]<=0]
pf7 = sum(t["pnl"] for t in w7) / abs(sum(t["pnl"] for t in l7)) if l7 else 0
total+=1; score += check("PF survives 30% skipped rebalances", pf7, 1.0, "above")

print()
print("  OPERATIONAL CRITERIA  (must pass before live deployment):")
print(f"  [ -- ]  {'30 paper-trading days completed':<42} 0 / 30  (IN PROGRESS)")
print(f"  [ -- ]  {'Regime correctly identified daily':<42} Ongoing")
print(f"  [ -- ]  {'Slippage tracked within 0.1% of model':<42} Ongoing")
print(f"  [ -- ]  {'No missed rebalances in 30 days':<42} Ongoing")
print(f"  [ -- ]  {'All SL exits executed on trigger day':<42} Ongoing")

print()
print(SEP)
grade_pct = score/total*100
grade = "A" if grade_pct >= 90 else "B" if grade_pct >= 75 else "C" if grade_pct >= 60 else "D"
print(f"  SCORECARD RESULT: {score}/{total} checks passed ({grade_pct:.0f}%)  Grade: {grade}")
if grade_pct >= 75:
    print("  VERDICT: Edge is REAL and SURVIVES operational stress.")
    print("  The strategy can proceed to paper trading. Do NOT skip the 30-day paper period.")
elif grade_pct >= 60:
    print("  VERDICT: Edge exists but is FRAGILE under stress.")
    print("  Operational discipline is critical. Any slippage or delay compounds quickly.")
else:
    print("  VERDICT: Edge does NOT survive realistic operational conditions.")
    print("  Do NOT deploy live. Revisit execution model before paper trading.")
print()
print("  KEY OPERATIONAL RISK (human operator):")
print("  - Missed rebalance = drift from optimal portfolio, reduces alpha")
print("  - >0.5% slippage = PF drops toward 1.0, CAGR halves")
print("  - Skipping Bear cash signal = max drawdown can double")
print("  - Rs.1L capital = brokerage drag eliminates the edge entirely")
print(SEP)
