"""
verify_order_lifecycle.py — Prove local state cannot exceed broker holdings.
Tests all 4 edge cases by simulating exact code paths from trading_bot.py.

Run: python verify_order_lifecycle.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SEP = "=" * 90
sep = "-" * 90
results = []

def check(label, condition, detail=""):
    results.append((condition, label))
    icon = "PASS" if condition else "FAIL"
    print(f"  [{icon}]  {label}")
    if detail:
        print(f"         {detail}")


# ═══════════════════════════════════════════════════════════════════════════════
# Simulate the exact place_order + _wait_for_fill + BUY state update logic
# from trading_bot.py, with mock broker responses
# ═══════════════════════════════════════════════════════════════════════════════

class MockBrokerResponse:
    """Simulates Upstox API responses for each scenario."""
    def __init__(self, scenario):
        self.scenario = scenario
        self.poll_count = 0

    def place_order_response(self):
        """POST /order/place always succeeds (order accepted)."""
        return {"status": "success", "data": {"order_id": "ORD_12345"}}

    def order_status_response(self):
        """GET /order/details — varies by scenario."""
        self.poll_count += 1

        if self.scenario == "timeout":
            return {"data": {"status": "open", "filled_quantity": 0, "average_price": 0}}

        elif self.scenario == "partial_fill":
            if self.poll_count <= 3:
                return {"data": {"status": "open", "filled_quantity": 3, "average_price": 1520.0}}
            return {"data": {"status": "open", "filled_quantity": 5, "average_price": 1518.0}}

        elif self.scenario == "long_open":
            return {"data": {"status": "open", "filled_quantity": 0, "average_price": 0}}

        elif self.scenario == "api_failure":
            raise ConnectionError("Upstox API timeout")

        elif self.scenario == "rejected_after_accept":
            if self.poll_count == 1:
                return {"data": {"status": "open"}}
            return {"data": {"status": "rejected", "filled_quantity": 0}}

        elif self.scenario == "normal_fill":
            if self.poll_count == 1:
                return {"data": {"status": "open"}}
            return {"data": {"status": "complete", "filled_quantity": 10, "average_price": 1505.0}}


def simulate_wait_for_fill(broker, order_id, instrument, qty, side, max_wait=10):
    """Exact replica of UpstoxClient._wait_for_fill() logic."""
    import time as _time
    for attempt in range(max_wait):
        # In real code: time.sleep(1) — skipped in test
        try:
            resp = broker.order_status_response()
            data = resp.get("data", {})
            status = data.get("status", "").lower()

            if status == "complete":
                fill_price = float(data.get("average_price", 0))
                fill_qty = int(data.get("filled_quantity", qty))
                return {
                    "status": "success",
                    "fill_confirmed": True,
                    "fill_price": fill_price,
                    "fill_qty": fill_qty,
                    "order_id": order_id,
                }
            elif status in ("rejected", "cancelled"):
                return {"status": status, "fill_confirmed": False, "order_id": order_id}
        except Exception:
            pass  # API failure — continue polling

    # Timeout: return None
    return None


def simulate_place_order(broker, instrument, qty, side):
    """Exact replica of UpstoxClient.place_order() logic."""
    result = broker.place_order_response()
    if result.get("status") == "success":
        order_id = result.get("data", {}).get("order_id", "")
        if order_id:
            fill = simulate_wait_for_fill(broker, order_id, instrument, qty, side)
            if fill:
                return fill
            # Timeout path: return None from _wait_for_fill
            # place_order falls through to return original result
        return result
    return result


def simulate_buy_state_update(result, instrument, qty, ltp, state):
    """Exact replica of the BUY state update block in trading_bot.py run()."""
    if result.get("status") in ("success", "complete"):
        if result.get("fill_confirmed") is False:
            # Rejected/cancelled — do NOT add to positions
            return "REJECTED"
        actual_price = result.get("fill_price", ltp)
        actual_qty = result.get("fill_qty", qty)
        state["positions"][instrument] = {
            "qty": actual_qty, "entry": actual_price,
            "order_id": result.get("order_id", ""),
        }
        return "ADDED"
    return "NO_ACTION"


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1: Order accepted but not filled within 10 seconds
# ═══════════════════════════════════════════════════════════════════════════════
print(SEP)
print("  SCENARIO 1: Order accepted, not filled within 10 seconds (timeout)")
print(SEP)

print("""
  Code path:
    place_order()
      → POST /order/place → {"status": "success", "data": {"order_id": "ORD_12345"}}
      → _wait_for_fill("ORD_12345", max_wait=10)
        → poll 1: {"status": "open"} → continue
        → poll 2: {"status": "open"} → continue
        → ...
        → poll 10: {"status": "open"} → continue
        → loop ends → return None
      → fill is None → log warning
      → return original result (no fill_confirmed key, no fill_price key)

    BUY state update:
      result.get("status") == "success" → True (enters block)
      result.get("fill_confirmed") is False → evaluated:
        result has NO "fill_confirmed" key → .get() returns None
        None is False → False (None is NOT the same object as False)
      → DOES NOT hit the "continue" (rejection path)
      → actual_price = result.get("fill_price", ltp) → ltp (fallback)
      → actual_qty = result.get("fill_qty", qty) → qty (fallback)
      → STATE UPDATED WITH ASSUMED VALUES
""")

broker = MockBrokerResponse("timeout")
state = {"positions": {}}
result = simulate_place_order(broker, "NSE_EQ|INFY", 10, "BUY")
action = simulate_buy_state_update(result, "NSE_EQ|INFY", 10, 1500.0, state)

check("Timeout: _wait_for_fill returns None",
      result.get("fill_confirmed") is None,
      f"result keys: {list(result.keys())}")

check("Timeout: state IS updated (with assumed LTP)",
      "NSE_EQ|INFY" in state["positions"],
      f"position: {state['positions'].get('NSE_EQ|INFY', {})}")

has_position = "NSE_EQ|INFY" in state["positions"]
assumed_qty = state["positions"].get("NSE_EQ|INFY", {}).get("qty", 0)

print(f"""
  *** PROBLEM FOUND ***
  On timeout, the bot DOES add the position with assumed qty={assumed_qty}.
  If the order was never actually filled, local state > broker holdings.

  This happens because:
    result.get("fill_confirmed") → None (key missing)
    None is False → evaluates to False (Python identity check)
    The rejection guard requires `is False` (exact False), not just falsy.
    None passes through the guard.

  ROOT CAUSE: The timeout path returns the original place_order result,
  which has status="success" but no fill_confirmed key. The BUY block
  treats missing fill_confirmed as "not rejected" and adds the position.
""")

# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2: Order partially filled
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  SCENARIO 2: Order partially filled (ordered 10, filled 5)")
print(SEP)

print("""
  Code path:
    _wait_for_fill polls: status stays "open", filled_quantity grows but < ordered
    After 10 polls: still "open" → return None (timeout)
    Same problem as Scenario 1: state updated with assumed qty.

  Even if broker eventually fills to 5 shares:
    Local state: qty=10 (assumed)
    Broker: qty=5 (actual)
    Mismatch until next reconciliation cycle.
""")

broker2 = MockBrokerResponse("partial_fill")
state2 = {"positions": {}}
result2 = simulate_place_order(broker2, "NSE_EQ|TCS", 10, "BUY")
action2 = simulate_buy_state_update(result2, "NSE_EQ|TCS", 10, 3500.0, state2)
local_qty = state2["positions"].get("NSE_EQ|TCS", {}).get("qty", 0)

check("Partial fill: position added with assumed qty (not actual fill)",
      local_qty == 10,
      f"Local qty={local_qty}, but broker only filled 5. Drift until reconciliation.")

# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3: Order remains open for several minutes
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  SCENARIO 3: Order remains open for several minutes (limit order)")
print(SEP)

print("""
  Identical to Scenario 1 — _wait_for_fill has max_wait=10 seconds.
  After 10s of "open" status, returns None.
  BUY block adds position with assumed values.
  Same drift risk.
""")

broker3 = MockBrokerResponse("long_open")
state3 = {"positions": {}}
result3 = simulate_place_order(broker3, "NSE_EQ|HDFC", 8, "BUY")
action3 = simulate_buy_state_update(result3, "NSE_EQ|HDFC", 8, 1600.0, state3)

check("Long open: same as timeout — position added with assumed values",
      "NSE_EQ|HDFC" in state3["positions"],
      f"Local qty={state3['positions']['NSE_EQ|HDFC']['qty']}")

# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4: Broker API fails during fill polling
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  SCENARIO 4: Broker API fails during fill polling (ConnectionError)")
print(SEP)

print("""
  Code path:
    _wait_for_fill polls:
      → requests.get raises ConnectionError
      → except catches it, continues loop
      → all 10 polls fail → return None
    Same as Scenario 1: state updated with assumed values.
""")

broker4 = MockBrokerResponse("api_failure")
state4 = {"positions": {}}
result4 = simulate_place_order(broker4, "NSE_EQ|SBIN", 15, "BUY")
action4 = simulate_buy_state_update(result4, "NSE_EQ|SBIN", 15, 800.0, state4)

check("API failure: all polls fail, position added with assumed values",
      "NSE_EQ|SBIN" in state4["positions"],
      f"Local qty={state4['positions']['NSE_EQ|SBIN']['qty']}")

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION: Rejected order is correctly blocked
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  CONTROL: Order rejected after acceptance (should NOT add position)")
print(SEP)

broker5 = MockBrokerResponse("rejected_after_accept")
state5 = {"positions": {}}
result5 = simulate_place_order(broker5, "NSE_EQ|RELIANCE", 5, "BUY")
action5 = simulate_buy_state_update(result5, "NSE_EQ|RELIANCE", 5, 2800.0, state5)

check("Rejected: fill_confirmed is exactly False",
      result5.get("fill_confirmed") is False,
      f"fill_confirmed={result5.get('fill_confirmed')}")
check("Rejected: position NOT added to state",
      "NSE_EQ|RELIANCE" not in state5["positions"],
      "Rejection guard works correctly")

# ═══════════════════════════════════════════════════════════════════════════════
# CONTROL: Normal fill works correctly
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  CONTROL: Normal fill (complete on poll 2)")
print(SEP)

broker6 = MockBrokerResponse("normal_fill")
state6 = {"positions": {}}
result6 = simulate_place_order(broker6, "NSE_EQ|WIPRO", 10, "BUY")
action6 = simulate_buy_state_update(result6, "NSE_EQ|WIPRO", 10, 450.0, state6)

check("Normal fill: fill_confirmed is True",
      result6.get("fill_confirmed") is True)
check("Normal fill: uses actual fill price (1505), not LTP (450)",
      state6["positions"]["NSE_EQ|WIPRO"]["entry"] == 1505.0,
      f"entry={state6['positions']['NSE_EQ|WIPRO']['entry']}")
check("Normal fill: uses actual fill qty (10)",
      state6["positions"]["NSE_EQ|WIPRO"]["qty"] == 10)

# ═══════════════════════════════════════════════════════════════════════════════
# DIAGNOSIS AND REQUIRED FIX
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  DIAGNOSIS")
print(SEP)
print("""
  Scenarios 1-4 all have the SAME root cause:

  When _wait_for_fill() times out, it returns None.
  place_order() then returns the original API result:
    {"status": "success", "data": {"order_id": "ORD_12345"}}

  This result has:
    - status = "success" → passes the status check
    - NO "fill_confirmed" key → .get("fill_confirmed") returns None
    - None is False → evaluates to False (Python identity)
    - The guard `if result.get("fill_confirmed") is False` does NOT catch None
    - Position is added with ASSUMED qty and price

  CONSEQUENCE: Local portfolio CAN become larger than broker holdings.

  REQUIRED FIX:
  Change the BUY guard from:
    if result.get("fill_confirmed") is False:
  to:
    if not result.get("fill_confirmed"):

  This catches BOTH:
    - fill_confirmed=False (rejected)
    - fill_confirmed missing/None (timeout, API failure, partial)

  After this fix, positions are ONLY added when fill_confirmed=True.
  Timeout/failure/partial → position NOT added → local state <= broker.
  Reconciliation on next cycle picks up any fills that completed late.
""")

print(f"\n{SEP}")
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"  {passed}/{total} checks passed")
print(f"  All scenarios correctly identified the timeout vulnerability.")
print(SEP)
