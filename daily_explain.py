"""
daily_explain.py — "Why did MoneyBot do what it did today?"

Reads today's ops_log, execution_state, broker_audit_log and prints
a plain-English explanation of every decision the bot made.
No interpretation needed — every trade, skip, and hold is documented.

Usage:
  python daily_explain.py              # explain today
  python daily_explain.py 2026-07-01   # explain a specific date
  python daily_explain.py --confidence # also print confidence score
"""

import json
import sys
import os
from datetime import date, datetime
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── Confidence score ──────────────────────────────────────────────────────────

def confidence_score():
    """
    Returns a dict of component scores (0-100) and an overall score.
    Any component below 50 should block trading.
    """
    scores = {}
    reasons = {}

    # Market data: did we get today's ops log?
    today_ops = Path(f"ops_log_{date.today()}.json")
    if today_ops.exists():
        try:
            ops = json.loads(today_ops.read_text(encoding="utf-8"))
            staleness = ops.get("data_staleness_days", 0)
            if staleness == 0:
                scores["market_data"] = 100
            elif staleness <= 1:
                scores["market_data"] = 85
                reasons["market_data"] = f"Data is {staleness} day(s) old"
            else:
                scores["market_data"] = max(0, 100 - staleness * 20)
                reasons["market_data"] = f"Data is {staleness} days old — stale"
        except Exception:
            scores["market_data"] = 0
            reasons["market_data"] = "Ops log could not be parsed"
    else:
        scores["market_data"] = 0
        reasons["market_data"] = "No ops log for today"

    # Broker: last audit result
    audit_log = Path("broker_audit_log.json")
    if audit_log.exists():
        try:
            history = json.loads(audit_log.read_text(encoding="utf-8"))
            if history:
                latest = history[-1]
                if latest.get("status") == "CLEAN":
                    scores["broker"] = 100
                elif latest.get("status") == "SKIPPED":
                    scores["broker"] = 60
                    reasons["broker"] = f"Last audit SKIPPED ({latest.get('date', '?')})"
                else:
                    n_miss = len(latest.get("mismatches", []))
                    scores["broker"] = max(0, 100 - n_miss * 25)
                    reasons["broker"] = f"{n_miss} mismatch(es) in last audit ({latest.get('date', '?')})"
            else:
                scores["broker"] = 50
                reasons["broker"] = "No audit history"
        except Exception:
            scores["broker"] = 50
            reasons["broker"] = "Audit log could not be read"
    else:
        scores["broker"] = 50
        reasons["broker"] = "No broker audit log"

    # State: is execution_state.json intact?
    state_file = Path("execution_state.json")
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            scores["state"] = 100
        except Exception:
            scores["state"] = 0
            reasons["state"] = "execution_state.json is corrupt"
    else:
        scores["state"] = 90
        reasons["state"] = "No state file (fresh start)"

    # Invariants
    try:
        from invariant_checker import check_all_invariants
        report = check_all_invariants()
        n_crit = len(report.critical)
        n_high = len(report.high)
        if n_crit > 0:
            scores["invariants"] = 0
            reasons["invariants"] = f"{n_crit} CRITICAL violation(s)"
        elif n_high > 0:
            scores["invariants"] = max(50, 100 - n_high * 15)
            reasons["invariants"] = f"{n_high} HIGH violation(s)"
        else:
            scores["invariants"] = 100
    except Exception as e:
        scores["invariants"] = 75
        reasons["invariants"] = f"Could not run invariant checker: {e}"

    # Config / token
    try:
        import config
        token = getattr(config, "UPSTOX_ACCESS_TOKEN", "")
        if len(token) > 100 and token.count(".") >= 2:
            # Decode JWT expiry
            import base64, json as _json, time
            try:
                payload = token.split(".")[1]
                payload += "=" * (4 - len(payload) % 4)
                data = _json.loads(base64.b64decode(payload))
                exp = data.get("exp", 0)
                remaining = exp - time.time()
                if remaining > 3600:
                    scores["config"] = 100
                elif remaining > 0:
                    scores["config"] = 70
                    reasons["config"] = f"Token expires in {int(remaining/60)} min"
                else:
                    scores["config"] = 0
                    reasons["config"] = "Token has EXPIRED"
            except Exception:
                scores["config"] = 85
                reasons["config"] = "Token present but expiry could not be decoded"
        else:
            scores["config"] = 0
            reasons["config"] = "Token missing or malformed"
    except Exception:
        scores["config"] = 0
        reasons["config"] = "config.py failed to import"

    # Logs writable
    try:
        with open("auto_daily.log", "a", encoding="utf-8"):
            pass
        scores["logs"] = 100
    except Exception:
        scores["logs"] = 0
        reasons["logs"] = "Log file not writable"

    # Overall: weighted minimum
    weights = {"market_data": 3, "broker": 2, "state": 2,
               "invariants": 3, "config": 3, "logs": 1}
    total_weight = sum(weights.values())
    overall = sum(scores.get(k, 0) * w for k, w in weights.items()) / total_weight

    return {
        "components": scores,
        "reasons": reasons,
        "overall": round(overall, 1),
        "safe_to_trade": overall >= 80 and scores.get("invariants", 0) > 0 and scores.get("config", 0) > 0,
    }


# ── Explainability report ─────────────────────────────────────────────────────

def explain(target_date: date = None):
    target = target_date or date.today()
    ops_path = Path(f"ops_log_{target}.json")

    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  WHY MONEYBOT DID WHAT IT DID — {target}")
    print(sep)

    if not ops_path.exists():
        print(f"\n  No ops log found for {target}.")
        print(f"  Either the bot didn't run, it was a weekend/holiday,")
        print(f"  or the ops report failed.")
        print(sep)
        return

    try:
        ops = json.loads(ops_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"\n  Ops log exists but could not be parsed: {e}")
        print(sep)
        return

    # ── Regime ──────────────────────────────────────────────────────────────
    regime    = ops.get("regime", "UNKNOWN")
    nifty     = ops.get("nifty", 0)
    dma200    = ops.get("dma200", 0)
    dma50     = ops.get("dma50", 0)
    tradeable = ops.get("tradeable", False)

    print(f"\n  REGIME:  {regime}")
    if nifty and dma200:
        direction = "ABOVE" if nifty > dma200 else "BELOW"
        print(f"  Reason:  Nifty ({nifty:,.0f}) is {direction} 200-DMA ({dma200:,.0f})")
        if dma50:
            trend = "ABOVE" if dma50 > dma200 else "BELOW"
            print(f"           50-DMA ({dma50:,.0f}) is {trend} 200-DMA — "
                  f"{'uptrend' if dma50 > dma200 else 'downtrend'} confirmed")
    if not tradeable:
        print(f"  Result:  POLICY-C ACTIVE → All buys blocked. Cash is king.")

    # ── Rebalance ───────────────────────────────────────────────────────────
    rebal_due   = ops.get("rebalance_due", False)
    days_to_reb = ops.get("days_to_rebal", "?")
    print(f"\n  REBALANCE DUE: {'YES' if rebal_due else 'NO'}")
    if not rebal_due and days_to_reb not in (0, "?"):
        print(f"  Reason:  {days_to_reb} trading day(s) remaining in current 10-day cycle")

    # ── Signal generation ────────────────────────────────────────────────────
    candidates  = ops.get("candidates", [])
    n_universe  = ops.get("universe_size", len(ops.get("skipped", [])) + len(candidates))
    skipped     = ops.get("skipped", [])

    print(f"\n  SIGNAL GENERATION:")
    print(f"  Universe:   {n_universe} stocks screened")

    if regime == "BEAR":
        print(f"  Candidates: 0 (regime filter blocked all analysis)")
    else:
        print(f"  Candidates: {len(candidates)} passed all filters into Top-10")
        if skipped:
            by_reason = {}
            for sym, reason in skipped:
                by_reason.setdefault(reason, []).append(sym)
            print(f"  Skipped:    {len(skipped)} stocks excluded")
            for reason, syms in sorted(by_reason.items(), key=lambda x: -len(x[1])):
                print(f"    → {len(syms):>3} stocks: {reason}")
                if len(syms) <= 4:
                    print(f"             ({', '.join(syms)})")

    # ── Top-10 candidates ────────────────────────────────────────────────────
    if candidates:
        print(f"\n  TOP-{len(candidates)} CANDIDATES (ranked by RS60/EP40 composite):")
        print(f"  {'#':>3}  {'Symbol':<14} {'Composite':>10} {'RS%':>8} {'EP%':>8} {'Price':>10} {'SL':>10}")
        print(f"  {'─'*60}")
        for i, c in enumerate(candidates[:10], 1):
            print(f"  {i:>3}  {c.get('symbol','?'):<14} "
                  f"{c.get('composite', 0):>10.1f} "
                  f"{c.get('rs_pct', 0):>8.1f} "
                  f"{c.get('ep_pct', 0):>8.1f} "
                  f"Rs.{c.get('price', 0):>7,.0f} "
                  f"Rs.{c.get('sl_price', 0):>7,.0f}")

    # ── Orders ───────────────────────────────────────────────────────────────
    buys  = ops.get("buys", [])
    sells = ops.get("sells", [])
    sl_hits      = ops.get("sl_hits", [])
    regime_exits = ops.get("regime_exits", [])

    print(f"\n  ORDERS:")

    if not tradeable:
        print(f"  → 0 buys placed. Reason: BEAR regime (Policy-C blocks all buying)")
    elif not rebal_due:
        print(f"  → 0 buys placed. Reason: Not a rebalance day")
    elif not buys:
        print(f"  → 0 buys placed. Reason: All Top-10 stocks already held, or insufficient cash")
    else:
        print(f"  → {len(buys)} buy order(s) generated:")
        for b in buys:
            print(f"     BUY  {b.get('qty',0)}x {b.get('symbol','?')} "
                  f"@ ~Rs.{b.get('price', b.get('sim_fill',0)):,.0f} "
                  f"(alloc Rs.{b.get('alloc_rs',0):,.0f}, SL Rs.{b.get('sl_price',0):,.0f})")

    if sells:
        print(f"  → {len(sells)} sell order(s) generated (rebalance exits):")
        for s in sells:
            print(f"     SELL {s.get('qty',0)}x {s.get('symbol','?')} — {s.get('reason','exit')}")

    if sl_hits:
        print(f"  → {len(sl_hits)} stop-loss exit(s):")
        for s in sl_hits:
            print(f"     SL   {s.get('symbol','?')} @ Rs.{s.get('exit_price',0):,.0f} "
                  f"(entry Rs.{s.get('entry',0):,.0f}, PnL Rs.{s.get('pnl',0):+,.0f})")

    if regime_exits:
        print(f"  → {len(regime_exits)} regime exit(s) (BEAR signal, sold everything):")
        for r in regime_exits:
            print(f"     EXIT {r.get('symbol','?')} — Policy-C BEAR exit")

    if not buys and not sells and not sl_hits and not regime_exits:
        print(f"  → No orders. Bot held existing positions unchanged.")

    # ── Current positions (from execution_state) ─────────────────────────────
    state_file = Path("execution_state.json")
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            positions = state.get("positions", {})
            pnl       = state.get("pnl", 0)
            if positions:
                print(f"\n  CURRENT POSITIONS ({len(positions)} open):")
                print(f"  {'Symbol':<14} {'Qty':>5} {'Entry':>12} {'SL':>12} {'Since'}")
                print(f"  {'─'*55}")
                for inst, pos in positions.items():
                    sym   = pos.get("plain", inst.split("|")[-1])
                    since = pos.get("time", "")[:10]
                    print(f"  {sym:<14} {pos.get('qty',0):>5} "
                          f"Rs.{pos.get('entry',0):>9,.0f} "
                          f"Rs.{pos.get('sl_price',0):>9,.0f}  {since}")
            else:
                print(f"\n  CURRENT POSITIONS: 0 (fully in cash)")

            print(f"\n  CUMULATIVE PnL:  Rs.{pnl:+,.2f}  (gross, excl. brokerage)")
        except Exception:
            pass

    # ── Summary sentence ─────────────────────────────────────────────────────
    print(f"\n  SUMMARY:")
    if regime == "BEAR":
        print(f"  MoneyBot held 100% cash today. Policy-C blocked all trades")
        print(f"  because Nifty is below its 200-day moving average.")
    elif not rebal_due:
        print(f"  MoneyBot held existing positions. No rebalance was due.")
        if sl_hits:
            print(f"  {len(sl_hits)} stop-loss(es) fired and positions were exited.")
    else:
        n_bought = len([b for b in buys if b])
        n_sold   = len([s for s in sells if s]) + len(sl_hits)
        print(f"  MoneyBot rebalanced: {n_bought} buy(s), {n_sold} sell(s).")

    print(sep)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    show_confidence = "--confidence" in sys.argv
    target = None
    for arg in sys.argv[1:]:
        if arg.startswith("20") and len(arg) == 10:
            try:
                target = date.fromisoformat(arg)
            except ValueError:
                print(f"Invalid date: {arg}. Use YYYY-MM-DD.")
                sys.exit(1)

    explain(target)

    if show_confidence or not target:
        score = confidence_score()
        sep = "=" * 65
        print(f"\n{sep}")
        print(f"  MONEYBOT CONFIDENCE SCORE — {date.today()}")
        print(sep)
        print()
        components = [
            ("Market Data",  "market_data"),
            ("Config/Token", "config"),
            ("Invariants",   "invariants"),
            ("Broker Audit", "broker"),
            ("State File",   "state"),
            ("Logs",         "logs"),
        ]
        for label, key in components:
            pct   = score["components"].get(key, 0)
            bar   = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            note  = score["reasons"].get(key, "")
            warn  = "  ⚠" if pct < 80 else ""
            print(f"  {label:<14} {bar} {pct:>3}%{warn}")
            if note:
                print(f"               {note}")

        overall = score["overall"]
        safe    = score["safe_to_trade"]
        verdict = "SAFE TO TRADE" if safe else "DO NOT TRADE"

        print()
        print(f"  {'─'*55}")
        print(f"  Overall          {overall:.1f}%   →  {verdict}")
        print(sep)

        if not safe:
            sys.exit(1)
