"""
slippage_tracker.py — Live slippage measurement framework.
Captures actual fill prices from Upstox order history and compares
against the backtest's 0.2% slippage assumption.

Designed to answer: "Does live execution behave like the backtest?"

Usage:
  python slippage_tracker.py               (fetch today's fills, compute slippage)
  python slippage_tracker.py --report      (aggregate report across all recorded fills)
  python slippage_tracker.py --simulate    (simulate with trading_state.json data)

The tracker saves every fill to slippage_data.json for ongoing analysis.
After 50+ fills, the report can statistically compare actual vs assumed slippage.
"""

import json
import sys
import logging
import statistics
from datetime import datetime, date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SLIPPAGE] %(message)s",
    handlers=[
        logging.FileHandler("slippage_tracker.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

SLIPPAGE_FILE = Path("slippage_data.json")
ASSUMED_SLIP = 0.002  # 0.2% each side — backtest assumption


def load_data():
    if SLIPPAGE_FILE.exists():
        try:
            return json.loads(SLIPPAGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"fills": [], "summary": {}}


def save_data(data):
    SLIPPAGE_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def fetch_order_history():
    """Fetch today's completed orders from Upstox."""
    try:
        import config
        import requests
        headers = {
            "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}",
            "Accept": "application/json"
        }
        r = requests.get(
            "https://api.upstox.com/v2/order/get-order-book",
            headers=headers, timeout=10
        )
        data = r.json()
        if data.get("status") == "success":
            orders = data.get("data", [])
            completed = [o for o in orders if o.get("status", "").lower() == "complete"]
            return completed
        else:
            log.warning(f"Order book API returned: {data.get('status')}")
            return None
    except Exception as e:
        log.warning(f"Order book API failed: {e}")
        return None


def record_fill(order):
    """Extract slippage data from a completed order."""
    instrument = order.get("instrument_token", "")
    symbol = instrument.split("|")[-1] if instrument else order.get("trading_symbol", "?")
    side = order.get("transaction_type", "").upper()
    order_price = float(order.get("price", 0))  # limit price (0 for market)
    fill_price = float(order.get("average_price", 0))
    qty = int(order.get("filled_quantity", 0))
    order_time = order.get("order_timestamp", "")
    fill_time = order.get("exchange_timestamp", "")

    if fill_price <= 0 or qty <= 0:
        return None

    # For market orders, we compare fill vs the LTP at order time
    # Since we don't have exact LTP, use trigger_price or order_price as reference
    # For a more accurate measure, we'd need to capture LTP at signal time
    ref_price = float(order.get("trigger_price", 0)) or order_price or fill_price

    if ref_price > 0 and ref_price != fill_price:
        if side == "BUY":
            actual_slip = (fill_price - ref_price) / ref_price
        else:
            actual_slip = (ref_price - fill_price) / ref_price
    else:
        actual_slip = 0.0

    return {
        "date": str(date.today()),
        "symbol": symbol,
        "instrument": instrument,
        "side": side,
        "qty": qty,
        "ref_price": round(ref_price, 2),
        "fill_price": round(fill_price, 2),
        "actual_slip_pct": round(actual_slip * 100, 4),
        "assumed_slip_pct": round(ASSUMED_SLIP * 100, 4),
        "slip_vs_assumed": round((actual_slip - ASSUMED_SLIP) * 100, 4),
        "order_time": order_time,
        "fill_time": fill_time,
        "order_id": order.get("order_id", ""),
    }


def fetch_and_record():
    """Fetch today's fills and record slippage data."""
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  LIVE SLIPPAGE TRACKER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(sep)

    orders = fetch_order_history()
    if orders is None:
        print("\n  Could not fetch order history. Token may be expired.")
        print("  Use --simulate to test with existing trading_state.json data.\n")
        return

    data = load_data()
    existing_ids = {f.get("order_id") for f in data["fills"]}
    new_fills = 0

    for order in orders:
        oid = order.get("order_id", "")
        if oid in existing_ids:
            continue
        fill = record_fill(order)
        if fill:
            data["fills"].append(fill)
            new_fills += 1
            print(f"  NEW: {fill['side']} {fill['qty']}x {fill['symbol']} "
                  f"ref={fill['ref_price']:.2f} fill={fill['fill_price']:.2f} "
                  f"slip={fill['actual_slip_pct']:+.4f}%")

    if new_fills == 0:
        print("\n  No new completed orders found today.")
    else:
        print(f"\n  Recorded {new_fills} new fill(s).")

    save_data(data)
    print(f"  Total fills in database: {len(data['fills'])}")
    print(sep)


def generate_report():
    """Aggregate slippage report across all recorded fills."""
    sep = "=" * 70

    data = load_data()
    fills = data["fills"]

    print(f"\n{sep}")
    print(f"  SLIPPAGE ANALYSIS REPORT")
    print(f"  Fills recorded: {len(fills)}")
    print(f"  Backtest assumption: {ASSUMED_SLIP*100:.2f}% each side")
    print(sep)

    if len(fills) < 5:
        print(f"\n  Not enough data for analysis (need at least 5 fills, have {len(fills)}).")
        print(f"  Keep running the tracker after each trading day.\n")
        return

    buy_slips = [f["actual_slip_pct"] for f in fills if f["side"] == "BUY"]
    sell_slips = [f["actual_slip_pct"] for f in fills if f["side"] == "SELL"]
    all_slips = [f["actual_slip_pct"] for f in fills]

    print(f"\n  {'Metric':<35} {'All':>10} {'BUY':>10} {'SELL':>10}")
    print(f"  {'-'*65}")
    print(f"  {'Count':<35} {len(all_slips):>10} {len(buy_slips):>10} {len(sell_slips):>10}")

    if all_slips:
        print(f"  {'Mean slippage %':<35} {statistics.mean(all_slips):>+10.4f} "
              f"{statistics.mean(buy_slips):>+10.4f} " if buy_slips else "", end="")
        print(f"{statistics.mean(sell_slips):>+10.4f}" if sell_slips else "")

        print(f"  {'Median slippage %':<35} {statistics.median(all_slips):>+10.4f}")
        if len(all_slips) > 1:
            print(f"  {'Stdev slippage %':<35} {statistics.stdev(all_slips):>10.4f}")
        print(f"  {'Max adverse slippage %':<35} {max(all_slips):>+10.4f}")
        print(f"  {'Min (best) slippage %':<35} {min(all_slips):>+10.4f}")
        print(f"  {'Assumed (backtest) %':<35} {ASSUMED_SLIP*100:>+10.4f}")

        mean_actual = statistics.mean(all_slips) / 100
        print(f"\n  {'COMPARISON':}")
        print(f"  {'Assumed slippage':<35} {ASSUMED_SLIP*100:>10.4f}%")
        print(f"  {'Actual mean slippage':<35} {statistics.mean(all_slips):>10.4f}%")
        diff = statistics.mean(all_slips) - ASSUMED_SLIP * 100
        print(f"  {'Difference':<35} {diff:>+10.4f}%")

        if diff > 0.05:
            print(f"\n  WARNING: Actual slippage is {diff:.4f}% HIGHER than backtest assumption.")
            print(f"  This means live performance will be WORSE than backtested.")
            print(f"  Consider increasing slippage assumption to {statistics.mean(all_slips):.3f}%")
        elif diff < -0.05:
            print(f"\n  GOOD: Actual slippage is {abs(diff):.4f}% LOWER than backtest assumption.")
            print(f"  Live performance should be BETTER than backtested.")
        else:
            print(f"\n  Actual slippage is within 0.05% of assumption. Backtest is realistic.")

        # Fills exceeding 2x assumed slippage
        extreme = [f for f in fills if f["actual_slip_pct"] > ASSUMED_SLIP * 100 * 2]
        if extreme:
            print(f"\n  EXTREME SLIPPAGE EVENTS (>{ASSUMED_SLIP*200:.2f}%):")
            for f in extreme[:10]:
                print(f"    {f['date']} {f['side']} {f['symbol']} "
                      f"slip={f['actual_slip_pct']:+.4f}% qty={f['qty']}")

    # Statistical confidence
    if len(all_slips) >= 30:
        se = statistics.stdev(all_slips) / (len(all_slips) ** 0.5)
        mean = statistics.mean(all_slips)
        ci_lo = mean - 1.96 * se
        ci_hi = mean + 1.96 * se
        print(f"\n  95% confidence interval: [{ci_lo:+.4f}%, {ci_hi:+.4f}%]")
        print(f"  Sample size: {len(all_slips)} (sufficient for statistical inference)")
    elif len(all_slips) >= 10:
        print(f"\n  Sample size: {len(all_slips)} (preliminary — need 30+ for confidence interval)")
    else:
        print(f"\n  Sample size: {len(all_slips)} (too small for statistical inference)")

    print(sep)


def simulate_from_state():
    """Use trading_state.json trades to simulate slippage recording."""
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  SLIPPAGE SIMULATION (from trading_state.json)")
    print(sep)

    state_file = Path("trading_state.json")
    if not state_file.exists():
        print("  No trading_state.json found.")
        return

    state = json.loads(state_file.read_text(encoding="utf-8"))
    trades = state.get("trades", [])

    if not trades:
        print("  No completed trades in trading_state.json.")
        print("  System B has never placed a live trade.")
        print(f"\n  To get real slippage data:")
        print(f"    1. Refresh Upstox token in config.py")
        print(f"    2. Let System B run for at least 1 trading day")
        print(f"    3. Run: python slippage_tracker.py")
        print(sep)
        return

    data = load_data()
    for t in trades:
        fill = {
            "date": t.get("time", "")[:10],
            "symbol": t.get("symbol", "?"),
            "side": "SELL" if "exit" in t else "BUY",
            "qty": t.get("qty", 0),
            "ref_price": t.get("entry", 0),
            "fill_price": t.get("exit", t.get("entry", 0)),
            "actual_slip_pct": 0.0,
            "assumed_slip_pct": ASSUMED_SLIP * 100,
            "order_id": f"sim_{t.get('time', '')}",
        }
        data["fills"].append(fill)

    save_data(data)
    print(f"  Recorded {len(trades)} simulated fills from trading_state.json")
    print(sep)


if __name__ == "__main__":
    if "--report" in sys.argv:
        generate_report()
    elif "--simulate" in sys.argv:
        simulate_from_state()
    else:
        fetch_and_record()
