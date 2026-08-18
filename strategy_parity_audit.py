"""
strategy_parity_audit.py
========================
Strategy Parity Audit: final_validation.py vs daily_ops_report.py

Compares ranking output on 10 historical OOS rebalance dates.
Measures: top-10 membership match, rank correlation, score correlation.
Identifies every code-level divergence between the two engines.

Run:  python strategy_parity_audit.py
Out:  parity_audit_results.json  (machine-readable)
      parity_audit_report.txt    (human-readable)
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import yfinance as yf
import pandas as pd
import numpy as np
import json, time, os
from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# FROZEN STRATEGY CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
W_RS        = 0.60
W_EP        = 0.40
TOP_N       = 10
RS_WINDOW   = 63
EP_WINDOW   = 63
EP_RET_MIN  = 0.02
EP_VOL_MULT = 1.5

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

# 10 historical OOS rebalance dates (~10-trading-day intervals from 2025)
AUDIT_DATES = [
    "2025-01-10", "2025-01-24", "2025-02-07", "2025-02-21",
    "2025-03-07", "2025-03-21", "2025-04-04", "2025-04-17",
    "2025-05-02", "2025-05-16",
]

# ─────────────────────────────────────────────────────────────────────────────
# DATA DOWNLOAD  (5-year history, single pass)
# ─────────────────────────────────────────────────────────────────────────────
SEP = "=" * 80

lines = []  # collects all output for the .txt report
def out(s=""):
    print(s)
    lines.append(s)

out(SEP)
out("MONEYBOT RS60/EP40 — STRATEGY PARITY AUDIT")
out(f"Run date: {date.today()}")
out("Comparing: final_validation.py (FV)  vs  daily_ops_report.py (OPS)")
out(SEP)

out("\n[PHASE 1] Downloading 5-year data for all 136 stocks + Nifty (~10 min)...")

price_data = {}
valid = []
for i, (ticker, sym) in enumerate(STOCKS):
    try:
        df = yf.Ticker(ticker).history(period='5y', interval='1d', auto_adjust=True)
        if not df.empty:
            d = {str(ts.date()): {'close': float(r['Close']),
                                   'vol':   float(r.get('Volume', 0) or 0)}
                 for ts, r in df.iterrows()}
            if len(d) >= 300:
                price_data[sym] = d
                valid.append(sym)
    except Exception:
        pass
    time.sleep(0.15)
    if (i + 1) % 20 == 0:
        out(f"  {i+1}/{len(STOCKS)} downloaded, {len(valid)} valid so far...")

out(f"\n  Universe loaded: {len(valid)} / {len(STOCKS)} stocks with 300+ days")

nifty_raw = {}
try:
    df = yf.Ticker('^NSEI').history(period='5y', interval='1d', auto_adjust=True)
    nifty_raw = {str(ts.date()): float(r['Close']) for ts, r in df.iterrows()}
except Exception as e:
    out(f"  ERROR fetching Nifty: {e}")

all_dates = sorted(nifty_raw.keys())
out(f"  Nifty: {all_dates[0]} to {all_dates[-1]}  ({len(all_dates)} trading days)")


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE A — final_validation.py ranking logic (REFERENCE)
# ─────────────────────────────────────────────────────────────────────────────
def fv_rank(target_date_str):
    """
    Exact replication of final_validation.py: get_raw() + composite().
    Returns list of (sym, composite, rs_raw, ep_raw, rs_pct, ep_pct) sorted desc.
    """
    # Snap to nearest available date
    candidates = [d for d in all_dates if d <= target_date_str]
    if not candidates:
        return []
    snap = candidates[-1]
    gi = all_dates.index(snap)
    if gi < 72:
        return []

    dn  = all_dates[gi]
    nc  = nifty_raw.get(dn)
    np_ = nifty_raw.get(all_dates[gi - 63]) if gi >= 63 else None

    raw_rs = {}
    raw_ep = {}

    for sym in valid:
        c = price_data[sym]
        sd = [d for d in all_dates[max(0, gi - 74):gi + 1] if d in c]
        if len(sd) < 50:
            continue

        # RS — exact FV code (line 191-199 of final_validation.py)
        if nc and np_:
            cn = c.get(dn, {}).get('close')
            cp = c.get(all_dates[gi - 63], {}).get('close')
            if cn and cp:
                raw_rs[sym] = (cn / cp - 1) * 100 - (nc / np_ - 1) * 100

        # EP — exact FV code (lines 200-208)
        ed = sd[-63:]
        evols = [c[d]['vol'] for d in ed if c[d]['vol'] > 0]  # excludes zeros
        av = sum(evols) / len(evols) if evols else 0
        ep = 0.0
        for j in range(1, len(ed)):
            cj  = c.get(ed[j])
            cjm = c.get(ed[j - 1])
            if not (cj and cjm and cjm['close'] > 0):
                continue
            dr = cj['close'] / cjm['close'] - 1
            if dr > 0.02 and av > 0 and cj['vol'] > 1.5 * av:
                ep = max(ep, dr * 100)
        raw_ep[sym] = ep

    # Percentile rank — exact FV code (pr() function lines 217-219)
    def pr(d):
        items = sorted(d.items(), key=lambda x: x[1])
        n = len(items)
        return {s: (r + 1) / n * 100 for r, (s, _) in enumerate(items)}

    rnks = {}
    if raw_rs: rnks['rs'] = pr(raw_rs)
    if raw_ep: rnks['ep'] = pr(raw_ep)
    if not rnks:
        return []

    active = list(rnks.keys())
    tw     = sum({'rs': W_RS, 'ep': W_EP}[f] for f in active)
    syms   = set.intersection(*[set(rnks[f].keys()) for f in active])

    scored = {}
    for s in syms:
        comp = sum({'rs': W_RS, 'ep': W_EP}[f] * rnks[f][s] for f in active) / tw
        scored[s] = {
            'composite': comp,
            'rs_pct':    rnks['rs'].get(s, 0),
            'ep_pct':    rnks['ep'].get(s, 0),
            'rs_raw':    raw_rs.get(s, 0),
            'ep_raw':    raw_ep.get(s, 0),
        }

    ranked = sorted(scored.items(), key=lambda x: -x[1]['composite'])
    return [(sym, v['composite'], v['rs_raw'], v['ep_raw'], v['rs_pct'], v['ep_pct'])
            for sym, v in ranked]


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE B — daily_ops_report.py logic, AS CODED (period="100d")
# ─────────────────────────────────────────────────────────────────────────────
def ops_rank_as_coded(target_date_str):
    """
    Replicates daily_ops_report.py fetch_and_score() exactly as written.
    Simulates period='100d' by taking only the last 71 trading days of data
    up to target_date (100 calendar days × 5/7 ≈ 71 trading days).
    Returns (ranked_list, n_skipped, n_scored).
    """
    candidates = [d for d in all_dates if d <= target_date_str]
    if not candidates:
        return [], 0, 0
    snap = candidates[-1]
    gi   = all_dates.index(snap)

    # Simulate period="100d": ~71 trading days
    WINDOW = 71
    window_dates = set(all_dates[max(0, gi - WINDOW + 1):gi + 1])

    # Nifty Series for this window
    nifty_s = pd.Series(
        {d: nifty_raw[d] for d in window_dates if d in nifty_raw}
    )
    nifty_s.index = pd.to_datetime(nifty_s.index)
    nifty_s = nifty_s.sort_index()

    results = []
    n_skipped = 0

    for sym in valid:
        c = price_data[sym]
        stock_dates = sorted(d for d in window_dates if d in c)
        if not stock_dates:
            n_skipped += 1
            continue

        px  = pd.Series([c[d]['close'] for d in stock_dates],
                        index=pd.to_datetime(stock_dates))
        vol = pd.Series([c[d]['vol']   for d in stock_dates],
                        index=pd.to_datetime(stock_dates))

        # OPS minimum bar check — line 124 of daily_ops_report.py
        # RS_WINDOW + 10 = 73.  Window gives 71 bars → FAILS for every stock.
        if len(px) < RS_WINDOW + 10:
            n_skipped += 1
            continue

        # RS — OPS code (lines 129-136)
        px_arr    = px.values
        nifty_arr = nifty_s.reindex(px.index, method="ffill").values
        if len(px_arr) < RS_WINDOW + 1 or np.isnan(nifty_arr[-1]) or nifty_arr[-RS_WINDOW-1] == 0:
            n_skipped += 1
            continue
        stock_ret = px_arr[-1] / px_arr[-RS_WINDOW-1] - 1
        nifty_ret = float(nifty_arr[-1]) / float(nifty_arr[-RS_WINDOW-1]) - 1
        rs_raw    = (stock_ret - nifty_ret) * 100

        # EP — OPS code (lines 139-150); uses np.nanmean (includes zeros)
        if len(vol) < EP_WINDOW:
            n_skipped += 1
            continue
        px_ep  = px.tail(EP_WINDOW).values
        vol_ep = vol.tail(EP_WINDOW).values
        avg_vol = np.nanmean(vol_ep)   # D2: includes zero-volume days
        ep_raw  = 0.0
        for i in range(1, len(px_ep)):
            if px_ep[i-1] <= 0: continue
            day_ret = px_ep[i] / px_ep[i-1] - 1
            if day_ret > EP_RET_MIN and vol_ep[i] > EP_VOL_MULT * avg_vol:
                ep_raw = max(ep_raw, day_ret * 100)

        results.append({'symbol': sym, 'rs_raw': rs_raw, 'ep_raw': ep_raw})

    if not results:
        return [], n_skipped, 0

    df = pd.DataFrame(results)
    df['rs_pct']    = df['rs_raw'].rank(pct=True) * 100
    df['ep_pct']    = df['ep_raw'].rank(pct=True) * 100
    df['composite'] = W_RS * df['rs_pct'] + W_EP * df['ep_pct']
    df = df.sort_values('composite', ascending=False).reset_index(drop=True)

    ranked = [(r['symbol'], r['composite'], r['rs_raw'], r['ep_raw'],
               r['rs_pct'], r['ep_pct']) for _, r in df.iterrows()]
    return ranked, n_skipped, len(results)


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE C — daily_ops_report.py with D1 fixed (period="200d")
#            and D2 fixed (exclude zero-volume days from EP avg)
# ─────────────────────────────────────────────────────────────────────────────
def ops_rank_fixed(target_date_str):
    """
    OPS engine with both critical fixes applied:
      F1: period='200d' (143 trading days instead of 71)
      F2: exclude zero-volume days from EP average volume
    Returns (ranked_list, n_skipped, n_scored).
    """
    candidates = [d for d in all_dates if d <= target_date_str]
    if not candidates:
        return [], 0, 0
    snap = candidates[-1]
    gi   = all_dates.index(snap)

    # F1: simulate period="200d" → ~143 trading days
    WINDOW = 143
    window_dates = set(all_dates[max(0, gi - WINDOW + 1):gi + 1])

    nifty_s = pd.Series(
        {d: nifty_raw[d] for d in window_dates if d in nifty_raw}
    )
    nifty_s.index = pd.to_datetime(nifty_s.index)
    nifty_s = nifty_s.sort_index()

    results = []
    n_skipped = 0

    for sym in valid:
        c = price_data[sym]
        stock_dates = sorted(d for d in window_dates if d in c)
        if not stock_dates:
            n_skipped += 1
            continue

        px  = pd.Series([c[d]['close'] for d in stock_dates],
                        index=pd.to_datetime(stock_dates))
        vol = pd.Series([c[d]['vol']   for d in stock_dates],
                        index=pd.to_datetime(stock_dates))

        if len(px) < RS_WINDOW + 10:
            n_skipped += 1
            continue

        px_arr    = px.values
        nifty_arr = nifty_s.reindex(px.index, method="ffill").values
        if len(px_arr) < RS_WINDOW + 1 or np.isnan(nifty_arr[-1]) or nifty_arr[-RS_WINDOW-1] == 0:
            n_skipped += 1
            continue
        stock_ret = px_arr[-1] / px_arr[-RS_WINDOW-1] - 1
        nifty_ret = float(nifty_arr[-1]) / float(nifty_arr[-RS_WINDOW-1]) - 1
        rs_raw    = (stock_ret - nifty_ret) * 100

        if len(vol) < EP_WINDOW:
            n_skipped += 1
            continue
        px_ep  = px.tail(EP_WINDOW).values
        vol_ep = vol.tail(EP_WINDOW).values

        # F2: exclude zero-volume days from average (matches FV)
        vol_nz  = vol_ep[vol_ep > 0]
        avg_vol = float(np.mean(vol_nz)) if len(vol_nz) > 0 else 0.0

        ep_raw = 0.0
        for i in range(1, len(px_ep)):
            if px_ep[i-1] <= 0: continue
            day_ret = px_ep[i] / px_ep[i-1] - 1
            if day_ret > EP_RET_MIN and avg_vol > 0 and vol_ep[i] > EP_VOL_MULT * avg_vol:
                ep_raw = max(ep_raw, day_ret * 100)

        results.append({'symbol': sym, 'rs_raw': rs_raw, 'ep_raw': ep_raw})

    if not results:
        return [], n_skipped, 0

    df = pd.DataFrame(results)
    df['rs_pct']    = df['rs_raw'].rank(pct=True) * 100
    df['ep_pct']    = df['ep_raw'].rank(pct=True) * 100
    df['composite'] = W_RS * df['rs_pct'] + W_EP * df['ep_pct']
    df = df.sort_values('composite', ascending=False).reset_index(drop=True)

    ranked = [(r['symbol'], r['composite'], r['rs_raw'], r['ep_raw'],
               r['rs_pct'], r['ep_pct']) for _, r in df.iterrows()]
    return ranked, n_skipped, len(results)


# ─────────────────────────────────────────────────────────────────────────────
# SPEARMAN RANK CORRELATION helper
# ─────────────────────────────────────────────────────────────────────────────
def spearman(list_a, list_b):
    """Spearman correlation over the common top-10 intersection."""
    set_a = {s: i for i, s in enumerate(list_a[:TOP_N])}
    set_b = {s: i for i, s in enumerate(list_b[:TOP_N])}
    common = [s for s in list_a[:TOP_N] if s in set_b]
    if len(common) < 3:
        return float('nan')
    n = len(common)
    d_sq = sum((set_a[s] - set_b[s]) ** 2 for s in common)
    return 1 - 6 * d_sq / (n * (n * n - 1))


# ─────────────────────────────────────────────────────────────────────────────
# RUN AUDIT ON 10 DATES
# ─────────────────────────────────────────────────────────────────────────────
out("\n[PHASE 2] Running parity audit on 10 historical OOS dates...")
out("  FV  = final_validation.py engine (reference)")
out("  OPS = daily_ops_report.py as-coded (period='100d')")
out("  FIX = daily_ops_report.py with F1+F2 applied (period='200d', EP vol fixed)")
out("")

audit_rows = []

for audit_date in AUDIT_DATES:
    out(f"\n  ── {audit_date} " + "─" * 50)

    fv_result = fv_rank(audit_date)
    fv_top10  = [s for s, *_ in fv_result[:TOP_N]]
    fv_n      = len(fv_result)
    out(f"  FV  scored={fv_n:>3}  top-10: {', '.join(fv_top10) if fv_top10 else '[empty]'}")

    ops_result, ops_skip, ops_scored = ops_rank_as_coded(audit_date)
    ops_top10 = [s for s, *_ in ops_result[:TOP_N]]
    out(f"  OPS scored={ops_scored:>3}  skip={ops_skip:>3}  top-10: {', '.join(ops_top10) if ops_top10 else '[EMPTY — D1 failure]'}")

    fix_result, fix_skip, fix_scored = ops_rank_fixed(audit_date)
    fix_top10 = [s for s, *_ in fix_result[:TOP_N]]
    out(f"  FIX scored={fix_scored:>3}  skip={fix_skip:>3}  top-10: {', '.join(fix_top10) if fix_top10 else '[empty]'}")

    fv_set  = set(fv_top10)
    ops_set = set(ops_top10)
    fix_set = set(fix_top10)

    match_ops = len(fv_set & ops_set) / TOP_N * 100 if fv_top10 else 0.0
    match_fix = len(fv_set & fix_set) / TOP_N * 100 if fv_top10 else 0.0
    spr_ops   = spearman(fv_top10, ops_top10)
    spr_fix   = spearman(fv_top10, fix_top10)

    only_fv  = sorted(fv_set  - fix_set)
    only_fix = sorted(fix_set - fv_set)

    out(f"  Match OPS(as-coded): {match_ops:.0f}%   Match FIX: {match_fix:.0f}%")
    out(f"  Spearman OPS: {spr_ops:.3f}   Spearman FIX: {spr_fix:.3f}")
    if only_fv or only_fix:
        out(f"  FV only : {', '.join(only_fv) if only_fv else '—'}")
        out(f"  FIX only: {', '.join(only_fix) if only_fix else '—'}")

    audit_rows.append({
        'date':       audit_date,
        'fv_n':       fv_n,
        'fv_top10':   fv_top10,
        'ops_scored': ops_scored,
        'ops_skip':   ops_skip,
        'ops_top10':  ops_top10,
        'fix_scored': fix_scored,
        'fix_skip':   fix_skip,
        'fix_top10':  fix_top10,
        'match_ops':  match_ops,
        'match_fix':  match_fix,
        'spr_ops':    spr_ops,
        'spr_fix':    spr_fix,
        'only_fv':    only_fv,
        'only_fix':   only_fix,
    })


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY TABLE
# ─────────────────────────────────────────────────────────────────────────────
out("\n\n" + SEP)
out("DATE-BY-DATE COMPARISON TABLE")
out(SEP)
hdr = f"{'Date':<12} {'FV_N':>5} {'OPS_N':>6} {'OPS_Skip':>9} {'Match_OPS':>10} {'Match_FIX':>10} {'Spr_OPS':>9} {'Spr_FIX':>9}"
out(hdr)
out("-" * 75)

match_ops_vals, match_fix_vals, spr_ops_vals, spr_fix_vals = [], [], [], []

for r in audit_rows:
    spr_ops_str = f"{r['spr_ops']:>9.3f}" if not (isinstance(r['spr_ops'], float) and r['spr_ops'] != r['spr_ops']) else "       nan"
    spr_fix_str = f"{r['spr_fix']:>9.3f}" if not (isinstance(r['spr_fix'], float) and r['spr_fix'] != r['spr_fix']) else "       nan"
    out(f"{r['date']:<12} {r['fv_n']:>5} {r['ops_scored']:>6} {r['ops_skip']:>9} "
        f"{r['match_ops']:>9.0f}% {r['match_fix']:>9.0f}% "
        f"{spr_ops_str} {spr_fix_str}")
    match_ops_vals.append(r['match_ops'])
    match_fix_vals.append(r['match_fix'])
    if not (isinstance(r['spr_ops'], float) and r['spr_ops'] != r['spr_ops']):
        spr_ops_vals.append(r['spr_ops'])
    if not (isinstance(r['spr_fix'], float) and r['spr_fix'] != r['spr_fix']):
        spr_fix_vals.append(r['spr_fix'])

out("-" * 75)
avg_match_ops = sum(match_ops_vals) / len(match_ops_vals)
avg_match_fix = sum(match_fix_vals) / len(match_fix_vals)
avg_spr_ops   = sum(spr_ops_vals) / len(spr_ops_vals) if spr_ops_vals else float('nan')
avg_spr_fix   = sum(spr_fix_vals) / len(spr_fix_vals) if spr_fix_vals else float('nan')

out(f"{'AVERAGE':<12} {'':>5} {'':>6} {'':>9} "
    f"{avg_match_ops:>9.0f}% {avg_match_fix:>9.0f}% "
    f"{avg_spr_ops:>9.3f} {avg_spr_fix:>9.3f}")
out(f"\n  PASS threshold: membership ≥95%, Spearman ≥0.85")


# ─────────────────────────────────────────────────────────────────────────────
# DISCREPANCY CATALOGUE
# ─────────────────────────────────────────────────────────────────────────────
out("\n\n" + SEP)
out("DISCREPANCY CATALOGUE — STATIC CODE ANALYSIS")
out(SEP)

discrepancies = [
    {
        "id":       "D1",
        "severity": "CRITICAL",
        "category": "data_period",
        "fv_code":  "yf.Ticker(ticker).history(period='5y')  [line 138]",
        "ops_code": "yf.download(tickers, period='100d')     [line 103]",
        "detail":   (
            "period='100d' = 100 calendar days = ~71 trading days. "
            "Minimum bar check (line 124): RS_WINDOW + 10 = 73. "
            "71 < 73 → ALL stocks fail the check → candidate list is empty. "
            "This defect has been invisible because fetch_and_score() is only "
            "called in Bull/Flat regime (line 289). The system has been in "
            "Bear regime since before paper trading started. "
            "This will fail on the first non-Bear day."
        ),
        "impact":   "Candidate list = empty. Top-10 membership match = 0%.",
        "fix":      "Change period='100d' to period='200d' in fetch_and_score() line 103.",
    },
    {
        "id":       "D2",
        "severity": "MODERATE",
        "category": "ep_volume_average",
        "fv_code":  "evols=[vol for vol in ed if vol>0]; av=mean(evols)  [lines 201-202]",
        "ops_code": "avg_vol = np.nanmean(vol_ep)                        [line 144]",
        "detail":   (
            "FV excludes zero-volume days before computing the average. "
            "OPS uses np.nanmean which includes zero entries (NaN excluded, "
            "zeros included). Lower avg_vol in OPS → more days satisfy "
            "vol[i] > 1.5 × avg_vol → higher EP scores → different ranking. "
            "Effect is small for large-cap stocks (rare zero-volume days) "
            "but non-zero: corporate action days, trading halts, and yfinance "
            "data gaps can produce 0-volume entries. Over a 63-day window, "
            "1-2 zero-volume days lower avg_vol by ~2-5%, inflating EP scores."
        ),
        "impact":   "Systematic EP score inflation. Estimated 1-3 rank position shifts.",
        "fix":      "Replace np.nanmean(vol_ep) with mean of vol_ep[vol_ep > 0].",
    },
    {
        "id":       "D3",
        "severity": "MODERATE",
        "category": "rs_date_anchor",
        "fv_code":  "cp = c.get(all_dates[gi-63], {}).get('close')  [line 198]",
        "ops_code": "stock_ret = px_arr[-1] / px_arr[-RS_WINDOW-1] - 1  [line 134]",
        "detail":   (
            "FV anchors the RS lookback to all_dates[gi-63]: the date exactly "
            "63 positions back in the GLOBAL Nifty date list. If the stock "
            "has no data on that exact date, cp=None and the stock is SKIPPED "
            "from RS (excluded from composite). "
            "OPS uses px_arr[-64]: 63 bars back in the STOCK's own date array. "
            "If the stock's date array has gaps, -64 maps to a DIFFERENT actual "
            "date. The stock is still included (not skipped). "
            "Diverges for stocks with trading suspensions or yfinance data gaps."
        ),
        "impact":   "0-2 stocks may differ between FV and OPS top-10 per rebalance date.",
        "fix":      "Verification only: log the actual date at px_arr[-64] and confirm "
                    "it matches all_dates[gi-63] for each scored stock.",
    },
    {
        "id":       "D4",
        "severity": "NEGLIGIBLE",
        "category": "percentile_ties",
        "fv_code":  "(r+1)/n*100 over stable-sorted list  [lines 217-219]",
        "ops_code": "rank(pct=True) * 100, method='average'  [lines 163-165]",
        "detail":   (
            "FV assigns adjacent (not averaged) ranks to tied values. "
            "OPS averages ranks of tied values. "
            "Floating-point RS and EP values are virtually never identical. "
            "Impact in practice: zero."
        ),
        "impact":   "Negligible.",
        "fix":      "None required.",
    },
    {
        "id":       "D5",
        "severity": "MINOR",
        "category": "missing_rs_stock_inclusion",
        "fv_code":  "if cn and cp: raw_rs[sym]=...  else: sym absent from RS  [line 199]",
        "ops_code": "stock is included regardless if bars >= 73  [line 124]",
        "detail":   (
            "When a stock has no data on all_dates[gi-63], FV silently "
            "drops it from RS. Since composite requires RS∩EP intersection "
            "(line 225), the stock is excluded from the composite ranking. "
            "OPS includes the stock using its nearest available bar. "
            "Stocks present in OPS ranking but absent from FV ranking (due "
            "to D5) contribute to membership divergence beyond what D2/D3 cause."
        ),
        "impact":   "0-1 stocks may appear in OPS top-10 but not FV top-10.",
        "fix":      "Add explicit check: if the date at px_arr[-64] differs from "
                    "the expected Nifty-calendar anchor by >1 day, skip the stock's RS.",
    },
]

for d in discrepancies:
    out(f"\n  [{d['id']}] {d['severity']} — {d['category']}")
    out(f"  FV  : {d['fv_code']}")
    out(f"  OPS : {d['ops_code']}")
    out(f"  Detail: {d['detail']}")
    out(f"  Impact: {d['impact']}")
    out(f"  Fix   : {d['fix']}")


# ─────────────────────────────────────────────────────────────────────────────
# RECOMMENDED CODE FIXES
# ─────────────────────────────────────────────────────────────────────────────
out("\n\n" + SEP)
out("RECOMMENDED FIXES FOR daily_ops_report.py")
out(SEP)

out("""
  [F1] Fix D1 — data period (REQUIRED)
  File   : daily_ops_report.py, line 103
  Change :
    BEFORE:  raw = yf.download(tickers, period="100d", ...)
    AFTER :  raw = yf.download(tickers, period="200d", ...)
  Why    : 200 calendar days = ~143 trading days. Comfortably covers RS_WINDOW(63)
           + EP_WINDOW(63) + the 10-bar safety margin in the minimum check (73).

  [F2] Fix D2 — EP average volume (REQUIRED for parity)
  File   : daily_ops_report.py, lines 144-145 inside fetch_and_score()
  Change :
    BEFORE:  avg_vol = np.nanmean(vol_ep)
    AFTER :  vol_nz  = vol_ep[vol_ep > 0]
             avg_vol = float(np.mean(vol_nz)) if len(vol_nz) > 0 else 0.0
  Why    : Matches FV's zero-volume exclusion. Prevents lower avg_vol from
           inflating EP scores relative to the backtest.

  [F3] Verify D3 — RS date alignment (RECOMMENDED)
  File   : daily_ops_report.py, inside fetch_and_score() after computing px_arr
  Add    : (inside the per-stock loop, after the nifty alignment fail check)
             anchor_date = str(px.index[-RS_WINDOW-1].date())
             # Expected: should be within 1 trading day of 63 Nifty days ago
             # (No code change needed; log the date for one-time verification)
  Why    : Confirms that px_arr[-64] lands on the same actual date as
           all_dates[gi-63]. For large-cap NSE stocks, this should always hold.
""")


# ─────────────────────────────────────────────────────────────────────────────
# FINAL VERDICT
# ─────────────────────────────────────────────────────────────────────────────
out("\n" + SEP)
out("FINAL VERDICT")
out(SEP)

ops_fail = avg_match_ops < 95
fix_pass = avg_match_fix >= 95 and avg_spr_fix >= 0.85

out(f"""
  OPS as-coded (period='100d'):
    Membership match : {avg_match_ops:.0f}%  [threshold: ≥95%]
    Spearman         : {avg_spr_ops:.3f}  [threshold: ≥0.85]
    Verdict          : {'FAIL' if ops_fail else 'PASS'}

  OPS with F1+F2 applied (period='200d', EP vol fix):
    Membership match : {avg_match_fix:.0f}%  [threshold: ≥95%]
    Spearman         : {avg_spr_fix:.3f}  [threshold: ≥0.85]
    Verdict          : {'PASS' if fix_pass else 'FAIL — investigate D3/D5 further'}

  ROOT CAUSE (D1):
    daily_ops_report.py fetch_and_score() uses period='100d' (~71 trading days).
    The minimum bar filter requires 73. 71 < 73 → all stocks skipped.
    fetch_and_score() has never been called in production (system has been
    in Bear regime throughout). This is a latent defect that will produce
    an empty candidate list on the first Bull or Flat trading day.

  ACTION REQUIRED BEFORE PAPER TRADING CAN BEGIN:
    1. Apply F1 (change period to '200d')      — fixes D1, the guaranteed failure
    2. Apply F2 (zero-vol exclusion in EP)      — fixes D2, aligns EP scoring
    3. Re-run this audit script                 — confirm ≥95% match after fixes
    4. Only proceed to paper trading after PASS
""")

out(SEP)
out("AUDIT COMPLETE")
out(SEP)

# ─────────────────────────────────────────────────────────────────────────────
# SAVE OUTPUTS
# ─────────────────────────────────────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))

# JSON results
json_out = {
    'audit_date': str(date.today()),
    'statistics': {
        'avg_match_ops_as_coded': avg_match_ops,
        'avg_match_ops_fixed':    avg_match_fix,
        'avg_spearman_as_coded':  avg_spr_ops,
        'avg_spearman_fixed':     avg_spr_fix,
    },
    'dates': audit_rows,
    'discrepancies': [{'id': d['id'], 'severity': d['severity'],
                       'category': d['category']} for d in discrepancies],
}
json_path = os.path.join(script_dir, 'parity_audit_results.json')
with open(json_path, 'w') as f:
    json.dump(json_out, f, indent=2, default=str)
out(f"\nJSON saved : {json_path}")

# Text report
txt_path = os.path.join(script_dir, 'parity_audit_report.txt')
with open(txt_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
out(f"Text saved : {txt_path}")
