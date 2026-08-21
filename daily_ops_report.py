"""
MoneyBot RS60/EP40 — Daily Operations Report
Generates: regime classification, candidate list (if tradeable), slippage baseline,
           and full ops log entry matching the paper trading workbook workflow.

Strategy FROZEN: RS=60%, EP=40%, Top-10, Rebal 10d, SL 10%, Policy C
Research freeze in effect. No parameter changes.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import json
import os
from datetime import date, datetime, timedelta

warnings.filterwarnings('ignore')

# ── Strategy constants (FROZEN) ─────────────────────────────────────────────
W_RS        = 0.60
W_EP        = 0.40
TOP_N       = 10
SL_PCT      = 0.10
RS_WINDOW   = 63   # bars
EP_WINDOW   = 63   # bars
EP_RET_MIN  = 0.02
EP_VOL_MULT = 1.5
PAPER_CAPITAL = 5_000   # paper-sim display only — DO NOT change (fingerprint locked)
PER_POS       = 500     # paper-sim display only — DO NOT change (fingerprint locked)
SLIP_MODEL    = 0.002   # 0.20% each way

# ── Live execution capital (update when Upstox balance changes) ───────────────
# LIVE_CAPITAL drives actual order sizing in the ops_log buys list.
# Change this when you fund/withdraw from Upstox — it is NOT a strategy parameter.
LIVE_CAPITAL  = 11_500
LIVE_PER_POS  = LIVE_CAPITAL // TOP_N   # = 1_150 per position

# AUTHORITATIVE universe from final_validation.py (136 stocks).
# Must match the backtest exactly — do not modify.
STOCKS = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN",
    "HCLTECH","WIPRO","AXISBANK","KOTAKBANK","TECHM","MARUTI",
    "TITAN","BAJFINANCE","ITC","HINDUNILVR","BHARTIARTL",
    "ASIANPAINT","SUNPHARMA","DRREDDY","CIPLA","POWERGRID",
    "NTPC","COALINDIA","ONGC","BPCL","ULTRACEMCO","GRASIM",
    "ADANIENT","ADANIPORTS","BAJAJFINSV","EICHERMOT",
    "TATACONSUM","BRITANNIA","APOLLOHOSP","JSWSTEEL",
    "TATASTEEL","HINDALCO","LT","NESTLEIND","PIDILITIND",
    "HAVELLS","DIVISLAB","TORNTPHARM","MUTHOOTFIN",
    "INDUSINDBK","BANDHANBNK","FEDERALBNK","ESCORTS",
    "BALKRISIND","TATAPOWER","M&M","HEROMOTOCO","BAJAJ-AUTO",
    "BOSCHLTD","SIEMENS","ABB","CUMMINSIND","VOLTAS",
    "BERGEPAINT","KANSAINER","DABUR","MARICO","COLPAL",
    "GODREJCP","EMAMILTD","PGHH","LUPIN","AUROPHARMA",
    "BIOCON","ALKEM","PFIZER","LICHSGFIN","M&MFIN","CHOLAFIN",
    "PFC","RECLTD","IRFC","SAIL","NMDC","VEDL",
    "IGL","MGL","GUJGASLTD","INDIGO","SBILIFE","HDFCLIFE",
    "NAUKRI","IRCTC","TORNTPOWER","TATAELXSI",
    "MPHASIS","LTTS","COFORGE","PERSISTENT","OFSS",
    "TRENT","DMART","IDFCFIRSTB","AUBANK",
    "POLYCAB","KEI","APLAPOLLO","DEEPAKNTR",
    "RBLBANK","TATAMOTORS","WHIRLPOOL","PAGEIND",
    "VBL","TVSMOTOR","ASHOKLEY","MOTHERSON","BHARATFORG",
    "EXIDEIND","CESC","NHPC","RVNL","MANAPPURAM",
    "KPITTECH","CYIENT","NAVINFLUOR","PIIND",
    "METROPOLIS","MAXHEALTH","PNBHOUSING","CANFINHOME",
    "CDSL","MCX","ANGELONE","RAMCOCEM","JKCEMENT",
    "DALBHARAT","SUNDARMFIN","ZENSARTECH","ASTRAL",
    "MCDOWELL-N",
]

def nse(t): return t + ".NS"

# ── 1. FETCH NIFTY & CLASSIFY REGIME ────────────────────────────────────────
def get_regime():
    # FIX: 220 calendar days ~ 152 trading days -- not enough for 200-bar SMA.
    # 400d gives ~275 trading days, safely covering the 200-bar requirement.
    data = yf.download("^NSEI", period="400d", interval="1d",
                       progress=False, auto_adjust=True)
    # FIX: yfinance returns MultiIndex DataFrame for single tickers.
    # data["Close"] is a 1-column DataFrame; squeeze() converts to Series.
    close = data["Close"].squeeze().dropna()

    # ── DATA INTEGRITY GATE ──────────────────────────────────────────────
    # Validates: freshness, completeness, no NaN before computing regime.
    # If any check fails, returns a safe BEAR regime (100% cash).
    if len(close) < 200:
        print(f"  DATA ERROR: Only {len(close)} Nifty bars (need 200). Defaulting to BEAR.")
        return {"date": date.today(), "close": 0, "dma50": 0, "dma200": 0,
                "regime": "BEAR", "tradeable": False, "data_error": True}

    last_date = close.index[-1].date()
    staleness = (date.today() - last_date).days
    if staleness > 5:
        print(f"  DATA ERROR: Nifty data is {staleness} days stale (last: {last_date}). Defaulting to BEAR.")
        return {"date": last_date, "close": float(close.iloc[-1]), "dma50": 0, "dma200": 0,
                "regime": "BEAR", "tradeable": False, "data_error": True}

    last_close = float(close.iloc[-1])
    dma50  = float(close.tail(50).mean())
    dma200 = float(close.tail(200).mean())

    if np.isnan(last_close) or np.isnan(dma50) or np.isnan(dma200):
        print(f"  DATA ERROR: NaN detected in Nifty data. Defaulting to BEAR.")
        return {"date": last_date, "close": last_close, "dma50": dma50, "dma200": dma200,
                "regime": "BEAR", "tradeable": False, "data_error": True}

    if last_close <= 0 or dma200 <= 0:
        print(f"  DATA ERROR: Invalid prices (close={last_close}, dma200={dma200}). Defaulting to BEAR.")
        return {"date": last_date, "close": last_close, "dma50": dma50, "dma200": dma200,
                "regime": "BEAR", "tradeable": False, "data_error": True}

    if last_close < dma200:
        regime = "BEAR"
    elif dma50 > dma200:
        regime = "BULL"
    else:
        regime = "FLAT"
    return {
        "date": last_date,
        "close": last_close,
        "dma50": dma50,
        "dma200": dma200,
        "regime": regime,
        "tradeable": regime in ("BULL", "FLAT"),
    }

# ── 2. FETCH STOCK DATA & COMPUTE FACTORS ───────────────────────────────────
def fetch_and_score(nifty_closes):
    tickers = [nse(s) for s in STOCKS]
    # FIX D1: period="100d" = ~71 calendar-day trading sessions, which is below
    # the RS_WINDOW+10=73 bar minimum and would cause all stocks to be skipped.
    # period="200d" = ~143 trading sessions, safely above all window requirements.
    raw = yf.download(tickers, period="200d", interval="1d",
                      progress=False, auto_adjust=True)

    price_df  = raw["Close"] if "Close" in raw.columns else raw.xs("Close", axis=1, level=0)
    volume_df = raw["Volume"] if "Volume" in raw.columns else raw.xs("Volume", axis=1, level=0)

    # FIX: nifty_closes may be a 1-col DataFrame from yfinance MultiIndex download.
    # Convert to 1-D Series so .reindex().values produces a 1-D array, not (n,1) array.
    if isinstance(nifty_closes, pd.DataFrame):
        nifty_closes = nifty_closes.squeeze()

    results = []
    skipped = []

    for sym in STOCKS:
        ticker = nse(sym)
        if ticker not in price_df.columns:
            skipped.append((sym, "no data"))
            continue
        px = price_df[ticker].dropna()
        vol = volume_df[ticker].dropna()
        if len(px) < RS_WINDOW + 10:
            skipped.append((sym, f"only {len(px)} bars"))
            continue

        # RS factor
        px_arr = px.values
        nifty_arr = nifty_closes.reindex(px.index, method="ffill").values  # now 1-D
        if len(px_arr) < RS_WINDOW + 1 or np.isnan(nifty_arr[-1]) or nifty_arr[-RS_WINDOW-1] == 0:
            skipped.append((sym, "nifty alignment fail"))
            continue
        stock_ret  = px_arr[-1] / px_arr[-RS_WINDOW-1] - 1
        nifty_ret  = float(nifty_arr[-1]) / float(nifty_arr[-RS_WINDOW-1]) - 1
        rs_raw = (stock_ret - nifty_ret) * 100

        # EP factor
        if len(vol) < EP_WINDOW:
            skipped.append((sym, "vol too short"))
            continue
        px_ep  = px.tail(EP_WINDOW).values
        vol_ep = vol.tail(EP_WINDOW).values
        # FIX D2: final_validation.py excludes zero-volume days before averaging
        # (line 201: evols=[vol for vol>0]). np.nanmean() includes zeros, which
        # lowers avg_vol, inflates EP scores, and diverges from the backtest engine.
        vol_ep_nz = vol_ep[vol_ep > 0]
        avg_vol   = float(np.mean(vol_ep_nz)) if len(vol_ep_nz) > 0 else 0.0
        ep_raw = 0.0
        for i in range(1, len(px_ep)):
            if px_ep[i-1] <= 0: continue
            day_ret = px_ep[i] / px_ep[i-1] - 1
            if day_ret > EP_RET_MIN and vol_ep[i] > EP_VOL_MULT * avg_vol:
                ep_raw = max(ep_raw, day_ret * 100)

        # 50-DMA trend filter: stock's close must be above its own 50-bar MA
        dma50_stock = float(np.mean(px_arr[-50:])) if len(px_arr) >= 50 else float(px_arr[-1])
        above_50dma = float(px_arr[-1]) > dma50_stock

        results.append({
            "symbol":      sym,
            "price":       round(float(px_arr[-1]), 2),
            "rs_raw":      round(rs_raw, 4),
            "ep_raw":      round(ep_raw, 4),
            "above_50dma": above_50dma,
            "dma50_stock": round(dma50_stock, 2),
        })

    df = pd.DataFrame(results)
    if df.empty:
        return df, skipped

    # Cross-sectional percentile rank (0-100)
    df["rs_pct"] = df["rs_raw"].rank(pct=True) * 100
    df["ep_pct"] = df["ep_raw"].rank(pct=True) * 100
    df["composite"] = W_RS * df["rs_pct"] + W_EP * df["ep_pct"]
    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    return df, skipped

# ── 3. SLIPPAGE MODEL ────────────────────────────────────────────────────────
def slippage_baseline(top10_df, per_pos=None):
    if per_pos is None:
        per_pos = LIVE_PER_POS
    rows = []
    for _, r in top10_df.iterrows():
        buy_price   = r["price"]
        sim_fill    = buy_price * (1 + SLIP_MODEL)
        qty         = int(per_pos / sim_fill)
        actual_cost = sim_fill * qty
        brokerage   = 20                               # Rs.20 flat each way
        exchange    = 0.0000345 * actual_cost * 2     # both legs
        sl_level    = buy_price * (1 - SL_PCT)
        rows.append({
            "symbol":       r["symbol"],
            "last_close":   buy_price,
            "sim_buy_fill": round(sim_fill, 2),
            "qty":          qty,
            "allocation":   round(actual_cost, 2),
            "sl_level":     round(sl_level, 2),
            "brokerage_rt": round(brokerage * 2, 2),
            "stt_est":      round(0.001 * sim_fill * qty, 2),
            "exchange_fee": round(exchange, 2),
            "total_cost":   round(brokerage*2 + 0.001*sim_fill*qty + exchange, 2),
            "slip_pct_model": f"{SLIP_MODEL*100:.2f}%",
        })
    return pd.DataFrame(rows)

# ── 4. MAIN REPORT ───────────────────────────────────────────────────────────
def main():
    report_date = date.today()
    paper_start = date(2026, 6, 16)
    sep = "=" * 70

    # ── REBALANCE COUNTER ────────────────────────────────────────────────────
    # Rebalance day 1 = 2024-06-13 (first OOS trading day in backtest).
    # Every 10th TRADING day from that anchor. We approximate using calendar
    # days: 10 trading days ~ 14 calendar days. We count from paper_start
    # (2026-06-16) as day 0 of paper trading. A rebalance is due when
    # (calendar days since paper_start) is a multiple of 14 (+/- 1 day
    # tolerance to absorb weekends).  Operator must confirm with the actual
    # trading-day count in the Excel workbook.
    days_since_paper_start = (report_date - paper_start).days
    if days_since_paper_start < 0:
        paper_day_num   = 0
        rebal_due       = False
        days_to_rebal   = (paper_start - report_date).days
    else:
        paper_day_num   = days_since_paper_start + 1
        # Count actual weekdays (Mon-Fri) between paper_start and report_date.
        # The 5/7 approximation incorrectly fires on calendar day 1 (int(1*5/7)=0).
        _cur = paper_start + timedelta(days=1)
        trading_days_elapsed = 0
        while _cur <= report_date:
            if _cur.weekday() < 5:
                trading_days_elapsed += 1
            _cur += timedelta(days=1)
        rebal_due       = trading_days_elapsed > 0 and (trading_days_elapsed % 10) == 0
        days_to_rebal   = 10 - (trading_days_elapsed % 10) if not rebal_due else 0

    print(sep)
    print("MONEYBOT RS60/EP40 - DAILY OPERATIONS REPORT")
    print(f"Report generated : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Paper trading    : Day {paper_day_num} (started {paper_start})")
    print(f"REBALANCE DUE    : {'*** YES *** - CHECK TOP-10 BEFORE 9:20 AM' if rebal_due else f'NO  (approx {days_to_rebal} trading days away)'}")
    print(f"Strategy frozen  : RS={W_RS*100:.0f}% / EP={W_EP*100:.0f}% / "
          f"Top-{TOP_N} / Rebal-10d / SL-{SL_PCT*100:.0f}% / Policy-C")
    print(sep)

    # ── REGIME ──────────────────────────────────────────────────────────────
    print("\n[1] REGIME CLASSIFICATION")
    print("-" * 40)
    reg = get_regime()
    print(f"  Last data date : {reg['date']}")
    print(f"  Nifty close    : {reg['close']:>10,.2f}")
    print(f"  50-DMA         : {reg['dma50']:>10,.2f}")
    print(f"  200-DMA        : {reg['dma200']:>10,.2f}")
    print(f"  50DMA > 200DMA : {'YES' if reg['dma50']>reg['dma200'] else 'NO'}")
    print(f"  Nifty > 200DMA : {'YES' if reg['close']>reg['dma200'] else 'NO'}")
    print(f"  REGIME         : *** {reg['regime']} ***")
    print()
    print(f"  ┌─ REGIME DECISION BLOCK ──────────────────────────────────────────┐")
    print(f"  │  Nifty Close   {reg['close']:>10,.2f}                                    │")
    print(f"  │  50-DMA        {reg['dma50']:>10,.2f}                                    │")
    print(f"  │  200-DMA       {reg['dma200']:>10,.2f}                                    │")
    print(f"  │  Price > 200DMA  {'YES ✓' if reg['close'] > reg['dma200'] else 'NO ✗ ':<6}  Gap: {abs(reg['dma200']-reg['close']):>7,.0f} pts   │")
    print(f"  │  50DMA > 200DMA  {'YES ✓' if reg['dma50'] > reg['dma200'] else 'NO ✗ ':<6}  Gap: {abs(reg['dma200']-reg['dma50']):>7,.0f} pts   │")
    print(f"  │  Policy-C Rule   {'BULL/FLAT → trade' if reg['regime'] != 'BEAR' else 'BEAR → 100% CASH, NO BUY':<35}│")
    print(f"  │  BUYING BLOCKED  {'NO' if reg['regime'] != 'BEAR' else 'YES — waiting for Nifty > {:.0f} (200DMA)'.format(reg['dma200']):<35}│")
    print(f"  └───────────────────────────────────────────────────────────────────┘")

    # Populated inside BULL/FLAT branch; stay empty in BEAR so JSON log can reference them
    top10   = pd.DataFrame()
    slip_df = pd.DataFrame()

    if reg["regime"] == "BEAR":
        print("\n  Policy C: BEAR regime detected.")
        print("  ACTION   : HOLD CASH. No positions. No trades.")
        print(f"  Paper portfolio value: Rs.{PAPER_CAPITAL:,} (100% cash)")
        print(f"  Re-entry trigger: Nifty must close above {reg['dma200']:,.0f} (200DMA)")
        print(f"  Current gap to 200DMA: {reg['dma200']-reg['close']:,.0f} points "
              f"({(reg['dma200']/reg['close']-1)*100:.1f}% above current)")

        print("\n[2] CANDIDATE LIST")
        print("-" * 40)
        print("  NOT GENERATED — Bear regime. No entries permitted.")
        print("  Candidate list will be generated on first Bull/Flat day.")

        print("\n[3] POSITION LOG")
        print("-" * 40)
        print("  Open positions : 0")
        print("  Invested       : Rs.0")
        print(f"  Cash           : Rs.{PAPER_CAPITAL:,}")

        print("\n[4] SLIPPAGE TRACKER")
        print("-" * 40)
        print("  No orders placed. No slippage data.")

        print("\n[5] DEVIATION FLAGS")
        print("-" * 40)
        print("  No deviation. Bear regime expected per backtest OOS period.")
        print("  OOS data shows 31% of days in Bear regime — consistent.")

        print("\n[6] WORKBOOK UPDATE INSTRUCTIONS")
        print("-" * 40)
        print(f"  Daily_Ops_Log  : Enter row for Day {paper_day_num} ({report_date})")
        print(f"    C (Nifty)   = {reg['close']:,.0f}")
        print(f"    D (50DMA)   = {reg['dma50']:,.0f}")
        print(f"    E (200DMA)  = {reg['dma200']:,.0f}")
        print("    F (50>200?) = NO   [auto-formula]")
        print("    G (Regime)  = BEAR [auto-formula]")
        print(f"    H (Port Val)= {PAPER_CAPITAL}")
        print(f"    I (Daily PL)= —{' (first day)' if paper_day_num <= 1 else ''}")
        print("    J (SL Exits)= [blank]")
        print("    K (Reg Exit)= —")
        print(f"    L (Rebal?)  = {'*** YES ***' if rebal_due else '—'}")
        print(f"    M (Notes)   = Paper trading Day {paper_day_num}. Bear regime. 100% cash.")

        _print_bear_watch(reg)

    else:
        # Bull or Flat: generate candidate list
        print(f"  Policy C: {reg['regime']} regime — PROCEED TO RANK.")

        print("\n[2] FETCHING STOCK DATA & COMPUTING RS60/EP40 SCORES")
        print("-" * 40)
        nifty_data = yf.download("^NSEI", period="100d", interval="1d",
                                 progress=False, auto_adjust=True)
        # FIX: squeeze() converts 1-col DataFrame to Series for alignment math
        nifty_closes = nifty_data["Close"].squeeze().dropna()

        df, skipped = fetch_and_score(nifty_closes)

        print(f"  Universe loaded  : {len(STOCKS)} stocks")
        print(f"  Successfully scored: {len(df)}")
        print(f"  Skipped (data)   : {len(skipped)}")
        if skipped:
            for s, reason in skipped[:5]:
                print(f"    {s}: {reason}")

        # Apply 50-DMA trend filter BEFORE selecting Top-N.
        # Stocks with high RS/EP but close < 50-DMA are already rolling over;
        # removing them reduces momentum-crash risk without changing RS/EP weights.
        df_pass = df[df["above_50dma"]].reset_index(drop=True)
        df_fail = df[~df["above_50dma"]]
        top10   = df_pass.head(TOP_N).copy()
        if not df_fail.empty:
            print(f"\n  [TREND FILTER] 50-DMA excluded {len(df_fail)} stock(s) from Top-{TOP_N} eligibility:")
            for _, r in df_fail.head(5).iterrows():
                print(f"    {r['symbol']:<14} close={r['price']:>9,.2f}  50DMA={r['dma50_stock']:>9,.2f}  EXCLUDED")
        if len(top10) < TOP_N:
            print(f"  WARNING: Only {len(top10)} stocks passed 50-DMA filter (wanted {TOP_N}).")

        print("\n[3] TOP-10 CANDIDATE LIST (RS=60% / EP=40% + 50-DMA FILTER)")
        print("-" * 78)
        print(f"  {'Rank':<5} {'Symbol':<14} {'Price':>8} {'50DMA':>8} "
              f"{'RS_raw':>8} {'EP_raw':>8} {'RS_pct':>8} {'EP_pct':>8} {'Composite':>10}")
        print("  " + "-"*76)
        for rank_i, (_, row) in enumerate(top10.iterrows(), start=1):
            print(f"  {rank_i:<5} {row['symbol']:<14} {row['price']:>8,.2f} {row['dma50_stock']:>8,.2f} "
                  f"{row['rs_raw']:>8.2f} {row['ep_raw']:>8.2f} "
                  f"{row['rs_pct']:>8.1f} {row['ep_pct']:>8.1f} "
                  f"{row['composite']:>10.2f}")

        print("\n[4] POSITION SIZING & SLIPPAGE BASELINE")
        print("-" * 70)
        slip_df = slippage_baseline(top10)
        total_alloc = 0
        print(f"  {'Symbol':<14} {'Close':>8} {'SimFill':>8} {'Qty':>6} "
              f"{'Alloc(Rs)':>11} {'SL Level':>10} {'Est.Cost(Rs)':>13}")
        print("  " + "-"*72)
        for _, r in slip_df.iterrows():
            print(f"  {r['symbol']:<14} {r['last_close']:>8,.2f} "
                  f"{r['sim_buy_fill']:>8,.2f} {r['qty']:>6} "
                  f"{r['allocation']:>11,.0f} {r['sl_level']:>10,.2f} "
                  f"{r['total_cost']:>13,.2f}")
            total_alloc += r['allocation']

        cash_remaining = PAPER_CAPITAL - total_alloc
        print(f"  {'TOTAL':>56} {total_alloc:>11,.0f}")
        print(f"  Cash remaining after fills: Rs.{cash_remaining:,.0f}")
        print(f"\n  Slippage model assumption: {SLIP_MODEL*100:.2f}% each way")
        print(f"  Record ACTUAL 9:15 AM open prices in Slippage_Tracker sheet.")
        print(f"  Flag any stock where actual fill deviates > 0.40% from prev close.")

        print("\n[5] DEVIATION FLAGS vs BACKTEST EXPECTATIONS")
        print("-" * 40)
        _check_deviations(top10, reg, df)

        print("\n[6] WORKBOOK UPDATE INSTRUCTIONS")
        print("-" * 40)
        print("  Daily_Ops_Log — fill today's row:")
        print(f"    C (Nifty)   = {reg['close']:,.0f}")
        print(f"    D (50DMA)   = {reg['dma50']:,.0f}")
        print(f"    E (200DMA)  = {reg['dma200']:,.0f}")
        print(f"    G (Regime)  = {reg['regime']}  [auto]")
        print(f"    H (Port Val)= {PAPER_CAPITAL} (pre-fill)")
        print("  Position_Log — add one row per entry after 9:15 AM fills:")
        for _, r in slip_df.iterrows():
            print(f"    {r['symbol']}: fill at actual open, qty {r['qty']}, SL={r['sl_level']:,.2f}")
        print("  Slippage_Tracker — log every buy order with prev close vs actual fill.")
        print("  Rebalance_Log  — log today as Rebal #1 after fills confirmed.")

    # ── WHY NO TRADE? — Pipeline transparency report ─────────────────────────
    print("\n[X] WHY NO TRADE? — CANDIDATE PIPELINE SUMMARY")
    print("-" * 55)
    universe_size   = len(STOCKS)
    scored_count    = len(top10) + (len(df) - len(top10) if not top10.empty and not df.empty else 0) if not top10.empty else 0
    # Reconstruct full scored df from fetch_and_score if available (only in BULL/FLAT)
    _df_full = df if not top10.empty else pd.DataFrame()
    _passed_dma = len(_df_full[_df_full["above_50dma"]]) if not _df_full.empty else 0
    _top_n      = len(top10)
    _buys_gen   = len(buys) if rebal_due else 0
    _blocked_cap = sum(1 for b in buys if b.get("qty", 0) == 0) if buys else 0
    _orders_out  = sum(1 for b in buys if b.get("qty", 1) > 0) if buys else 0

    _regime_ok  = reg["regime"] != "BEAR"
    _rebal_ok   = rebal_due

    print(f"  Universe (total stocks tracked) : {universe_size}")
    if _df_full.empty:
        print(f"  Data fetched & scored          : — (BEAR regime, skipped)")
    else:
        print(f"  Data fetched & scored          : {len(_df_full)}")
        print(f"  Passed 50-DMA filter           : {_passed_dma}")
        print(f"  Top-{TOP_N} selected                : {_top_n}")
    print(f"  Regime allows entry            : {'YES' if _regime_ok else 'NO  ← BLOCKED HERE (Policy-C BEAR)'}")
    print(f"  Rebalance due today            : {'YES' if _rebal_ok else f'NO  ← BLOCKED HERE (next rebal in ~{days_to_rebal} trading days)'}")
    print(f"  BUY orders generated           : {_buys_gen}")
    if _buys_gen > 0:
        print(f"  Orders with qty > 0            : {_orders_out}")
        print(f"  Orders rejected (qty=0, price  : {_blocked_cap}")
        print(f"       exceeds LIVE_PER_POS={LIVE_PER_POS})")
    print(f"  Orders submitted to broker     : {'0 (dry-run/paper)' if _orders_out == 0 else str(_orders_out)}")
    if not _regime_ok:
        gap = reg['dma200'] - reg['close']
        print(f"\n  *** Entry will resume when Nifty reclaims {reg['dma200']:,.0f} (200DMA).")
        print(f"  *** Current gap: {gap:,.0f} pts ({gap/reg['close']*100:.1f}% away).")
    elif not _rebal_ok:
        print(f"\n  *** Regime is {reg['regime']} — next entry window in ~{days_to_rebal} trading days.")

    print("\n" + sep)
    print("REPORT COMPLETE. No strategy parameters modified.")
    print(f"Next report: next trading day morning before 9:10 AM IST")
    print(sep)

    # Save JSON log — paper_runner.py reads all keys below
    candidates = [
        {"symbol": r["symbol"], "price": r["price"],
         "composite": round(r["composite"], 2),
         "rs_pct": round(r["rs_pct"], 1), "ep_pct": round(r["ep_pct"], 1)}
        for _, r in top10.iterrows()
    ] if not top10.empty else []

    buys = [
        {"symbol": r["symbol"], "alloc_rs": round(r["allocation"], 0),
         "qty": r["qty"], "sl_price": r["sl_level"]}
        for _, r in slip_df.iterrows()
    ] if (not slip_df.empty and rebal_due) else []

    log_data = {
        "report_date":   str(report_date),
        "data_date":     str(reg["date"]),
        "nifty":         reg["close"],
        "dma50":         reg["dma50"],
        "dma200":        reg["dma200"],
        "regime":        reg["regime"],
        "tradeable":     reg["tradeable"],
        "action":        "CASH" if reg["regime"] == "BEAR" else "ENTER",
        "rebalance_due": rebal_due,
        "candidates":    candidates,
        "buys":          buys,
        "sells":         [],  # operator fills from workbook; no live portfolio state here
        "sl_hits":       [],  # operator fills from workbook; computed from position log
        "regime_exits":  [],  # operator fills from workbook; triggered on BEAR transition
    }
    log_path = os.path.join(os.path.dirname(__file__),
                            f"ops_log_{report_date}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)
    print(f"\nJSON log saved: {log_path}")


def _print_bear_watch(reg):
    print("\n[7] BEAR REGIME WATCH")
    print("-" * 40)
    gap = reg['dma200'] - reg['close']
    pct = gap / reg['close'] * 100
    print(f"  Nifty needs to rise {gap:,.0f} pts ({pct:.1f}%) to reclaim 200DMA")
    print(f"  50DMA gap to 200DMA: {reg['dma200']-reg['dma50']:,.0f} pts")
    print("  Monitor daily. Enter when BOTH:")
    print(f"    - Nifty close > {reg['dma200']:,.0f}  (200DMA)")
    print("    - Regime formula in Daily_Ops_Log shows BULL or FLAT")
    print("  DO NOT enter on intraday crosses — signal is CLOSE only.")


def _check_deviations(top10, reg, full_df):
    flags = []

    # Check sector concentration (Finance dominance expected from backtest)
    finance_stocks = {"HDFCBANK","ICICIBANK","AXISBANK","KOTAKBANK","BAJFINANCE",
                      "BAJAJFINSV","SBILIFE","HDFCLIFE","ANGELONE","PNBHOUSING",
                      "IDFCFIRSTB","BANDHANBNK","AUBANK","FEDERALBNK","CHOLAFIN",
                      "MUTHOOTFIN","PNB","BANKBARODA","CANBK","RBLBANK","INDUSINDBK"}
    top10_syms = set(top10["symbol"])
    fin_count = len(top10_syms & finance_stocks)
    if fin_count < 2:
        flags.append(f"WARNING: Only {fin_count} Finance stocks in Top-10. "
                     "Backtest showed Finance dominance (34.9% of D1). "
                     "Monitor — may indicate regime shift.")
    else:
        print(f"  Finance stocks in Top-10: {fin_count}  "
              f"[OK — backtest expected ~3-4]")

    # Check IT exposure (should be near neutral)
    it_stocks = {"INFY","TCS","WIPRO","HCLTECH","TECHM","LTIM","MPHASIS",
                 "COFORGE","LTTS","OFSS"}
    it_count = len(top10_syms & it_stocks)
    print(f"  IT stocks in Top-10     : {it_count}  "
          f"[backtest: ~1-2 expected, near-neutral]")

    # Check composite score spread
    top_score  = float(top10["composite"].iloc[0])
    tenth_score = float(top10["composite"].iloc[-1])
    spread = top_score - tenth_score
    print(f"  Composite score spread  : {top_score:.1f} (rank 1) to "
          f"{tenth_score:.1f} (rank 10), spread={spread:.1f}")
    if spread < 10:
        flags.append(f"INFO: Low composite spread ({spread:.1f} pts). "
                     "Top-10 stocks are tightly bunched — turnover may be elevated.")

    # Check RS of rank-1 stock
    rs1 = float(top10["rs_raw"].iloc[0])
    if rs1 < 0:
        flags.append(f"INFO: Rank-1 stock has negative RS ({rs1:.2f}). "
                     "In Bear regime this can happen — not a strategy deviation.")

    # Universe coverage
    coverage = len(full_df) / len(STOCKS) * 100
    if coverage < 80:
        flags.append(f"WARNING: Only {coverage:.0f}% of universe scored "
                     f"({len(full_df)}/{len(STOCKS)}). "
                     "Check data availability for missing stocks.")
    else:
        print(f"  Universe coverage       : {coverage:.0f}%  "
              f"({len(full_df)}/{len(STOCKS)} stocks scored)  [OK]")

    if flags:
        print()
        for f in flags:
            print(f"  *** {f}")
    else:
        print("  No deviations flagged.")


if __name__ == "__main__":
    main()
