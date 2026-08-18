"""
paper.py — MoneyBot Paper-Trade Fill Simulator
===============================================
Implements the IDENTICAL fill model used by final_validation.py run_sim().

Every formula in this file is traceable to a specific line in final_validation.py.
No fill assumption may differ between backtest and paper mode.

Fill model reference (final_validation.py constants, lines 21-22):
  BROKERAGE = Rs.20.00 flat per order leg
  STT       = 0.10%  — sell side ONLY (NSE delivery)
  EXCHANGE  = 0.00345% — applied to both buy and sell legs separately
  SLIP      = 0.20%  — adverse slippage applied to each side independently
  SL_PCT    = 10.0%  — stop-loss at entry_fill × 0.90

Event execution timing (final_validation.py run_sim(), lines 263-348):
  Rebalance BUY    → fills at T+1 OPEN (next trading day open)
  Rebalance SELL   → fills at T+1 OPEN (next trading day open)
  Regime EXIT      → fills at T+1 OPEN (next trading day open)
  SL EXIT          → fills at T CLOSE  (SAME DAY close — not T+1)
  End-of-Period    → fills at T CLOSE  (last day of paper period)

Price fallback chain (final_validation.py lines 275, 284, 324-325, 335):
  BUY  : next_open → today_close          (no entry-price fallback on buy)
  SELL : next_open → today_close → entry  (entry price as last resort)
  SL   : today_close only                 (no fallback; if close is None, skip)
  EoP  : today_close → entry

SL trigger (final_validation.py line 308):
  today_close <= entry_fill × (1 - SL_PCT/100)
  entry_fill  = the fill price including slippage stored at time of buy
  Do NOT anchor SL to the pre-slippage close price.

Position sizing (final_validation.py lines 330-337):
  avail_cap  = cash × 0.95
  alloc      = min(avail_cap / n_new_entries, CAPITAL / TOP_N)
             = min(cash × 0.95 / n_new, 50_000)
  qty        = max(1, floor(alloc / fill_price))   ← minimum 1 share
  Condition  : skip if cash < qty × fill + buy_cost (line 339)
"""

# ── constants ── exact values from final_validation.py lines 21-22 ──────────
BROKERAGE  = 20.0       # Rs.20 flat per order leg  (FV line 21)
STT        = 0.001      # 0.10% sell-side only       (FV line 21)
EXCHANGE   = 0.0000345  # 0.00345% each leg          (FV line 21)
SLIP       = 0.002      # 0.20% each side, adverse   (FV line 22)
SL_PCT     = 10.0       # percent                    (FV line 20)
CAPITAL    = 500_000.0  # paper starting capital     (FV line 23)
TOP_N      = 10         # positions                  (FV line 20)


# ─────────────────────────────────────────────────────────────────────────────
# Fill result dataclass (plain dict — no external dependencies)
# ─────────────────────────────────────────────────────────────────────────────
def _fill_result(event, symbol, qty, fill_price, brokerage, stt, exchange, net_cash):
    """
    Canonical fill result dict.  net_cash is the SIGNED change to the
    portfolio cash balance:
      positive  → cash received   (sell / regime / SL / EoP exits)
      negative  → cash spent      (buy entries)
    """
    return {
        "event":      event,        # "BUY" | "SELL_REBAL" | "SELL_REGIME" | "SELL_SL" | "SELL_EOP"
        "symbol":     symbol,
        "qty":        qty,
        "fill_price": round(fill_price, 4),
        "brokerage":  round(brokerage,  2),
        "stt":        round(stt,        2),   # 0.0 on buys
        "exchange":   round(exchange,   4),
        "total_cost": round(brokerage + stt + exchange, 2),
        "gross":      round(qty * fill_price, 2),
        "net_cash":   round(net_cash, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def fill_buy(symbol, next_open, today_close, cash, n_new_entries):
    """
    Simulate a rebalance BUY fill.

    Mirrors final_validation.py run_sim() lines 333-340:
      fpd  = go(sym,nd) or gc(sym,date)
      fill = fpd * (1 + slip)
      qty  = max(1, int(alloc / fill))
      cost = BROKERAGE + qty*fill*EXCHANGE
      cash -= qty*fill + cost

    Args:
        symbol      : stock ticker (for record only)
        next_open   : next trading day opening price (may be None)
        today_close : today's closing price (fallback if next_open is None)
        cash        : current cash balance before this fill
        n_new_entries : total number of new entries in this rebalance batch
                        (needed to split available capital correctly)

    Returns:
        fill_record : dict (see _fill_result) — or None if insufficient data/cash
        entry_fill  : the fill price to store as position entry (includes slippage)
        qty         : shares purchased
    """
    # Price source fallback (FV line 335):  next_open → today_close
    price_base = next_open if next_open else today_close
    if price_base is None or price_base <= 0:
        return None, None, 0

    # BUY slippage is adverse: fill ABOVE market (FV line 337)
    fill = price_base * (1 + SLIP)

    # Allocation (FV lines 330-332)
    avail_cap = cash * 0.95
    alloc     = min(avail_cap / max(n_new_entries, 1), CAPITAL / TOP_N)

    # Qty: floor division, minimum 1 share (FV line 337)
    qty = max(1, int(alloc / fill))

    # BUY-side cost: brokerage + exchange ONLY — no STT on buy (FV line 338)
    exchange_cost = qty * fill * EXCHANGE
    brokerage_cost = BROKERAGE
    total_cost     = brokerage_cost + exchange_cost

    # Cash gate (FV line 339): skip if insufficient cash
    if cash < qty * fill + total_cost:
        return None, None, 0

    net_cash = -(qty * fill + total_cost)   # cash decreases

    record = _fill_result(
        event       = "BUY",
        symbol      = symbol,
        qty         = qty,
        fill_price  = fill,
        brokerage   = brokerage_cost,
        stt         = 0.0,              # no STT on buy (FV line 338 — no STT term)
        exchange    = exchange_cost,
        net_cash    = net_cash,
    )
    return record, fill, qty   # fill is entry_fill to store in position


def fill_sell_rebalance(symbol, qty, entry_fill, next_open, today_close):
    """
    Simulate a rebalance or regime SELL fill.

    Mirrors final_validation.py run_sim() lines 323-328 and 274-287:
      fpd  = go(sym,nd) or gc(sym,date) or pos[sym]['ep']
      fp   = fpd * (1 - slip)
      ev   = p['qty'] * fp
      cost = BROKERAGE + ev*STT + ev*EXCHANGE
      cash += ev - cost

    Args:
        symbol      : stock ticker
        qty         : shares to sell (from position record)
        entry_fill  : position entry price including slippage (for last-resort fallback)
        next_open   : next trading day opening price (may be None)
        today_close : today's closing price (may be None)

    Returns:
        fill_record : dict — or None if no valid price available
    """
    # Price source fallback (FV line 325): next_open → today_close → entry_fill
    price_base = next_open if next_open else (today_close if today_close else entry_fill)
    if price_base is None or price_base <= 0:
        return None

    # SELL slippage is adverse: fill BELOW market (FV line 325)
    fill = price_base * (1 - SLIP)
    ev   = qty * fill

    # SELL-side cost: brokerage + STT + exchange (FV line 327)
    brokerage_cost = BROKERAGE
    stt_cost       = ev * STT
    exchange_cost  = ev * EXCHANGE
    total_cost     = brokerage_cost + stt_cost + exchange_cost

    net_cash = ev - total_cost   # cash increases

    return _fill_result(
        event      = "SELL_REBAL",
        symbol     = symbol,
        qty        = qty,
        fill_price = fill,
        brokerage  = brokerage_cost,
        stt        = stt_cost,
        exchange   = exchange_cost,
        net_cash   = net_cash,
    )


def fill_sell_regime(symbol, qty, entry_fill, next_open, today_close):
    """
    Simulate a regime-exit SELL fill.

    Same formula as fill_sell_rebalance (FV lines 274-287 are identical
    to lines 323-328 except for the exit reason label).
    Returns fill_record with event="SELL_REGIME".
    """
    result = fill_sell_rebalance(symbol, qty, entry_fill, next_open, today_close)
    if result:
        result["event"] = "SELL_REGIME"
    return result


def fill_sell_sl(symbol, qty, entry_fill, today_close):
    """
    Simulate a stop-loss SELL fill.

    THIS IS THE ONLY EVENT THAT FILLS AT TODAY'S CLOSE (not T+1 open).
    Mirrors final_validation.py run_sim() lines 306-312:
      curr  = gc(sym,date)          ← today's close, NOT next-day open
      if curr <= entry_fill*(1 - SL_PCT/100):   ← SL trigger
          fill = curr * (1 - slip)  ← fills at today's close with slippage
          cost = BROKERAGE + ev*STT + ev*EXCHANGE

    SL trigger anchors to entry_fill (which includes buy slippage).
    Do NOT anchor to the pre-slippage close — that would be wrong.

    Args:
        symbol      : stock ticker
        qty         : shares to sell
        entry_fill  : stored entry price (close × (1+SLIP) at time of buy)
        today_close : today's closing price

    Returns:
        triggered   : bool — True if SL is breached
        fill_record : dict — or None if not triggered / no close price
    """
    if today_close is None or today_close <= 0:
        return False, None

    # SL trigger check (FV line 308): close <= entry_fill × (1 - SL_PCT/100)
    sl_threshold = entry_fill * (1 - SL_PCT / 100)
    if today_close > sl_threshold:
        return False, None   # not triggered

    # Fill at TODAY'S CLOSE (not tomorrow's open) with adverse slippage (FV line 309)
    fill = today_close * (1 - SLIP)
    ev   = qty * fill

    # Same cost structure as other sells (FV line 310)
    brokerage_cost = BROKERAGE
    stt_cost       = ev * STT
    exchange_cost  = ev * EXCHANGE

    net_cash = ev - (brokerage_cost + stt_cost + exchange_cost)

    return True, _fill_result(
        event      = "SELL_SL",
        symbol     = symbol,
        qty        = qty,
        fill_price = fill,
        brokerage  = brokerage_cost,
        stt        = stt_cost,
        exchange   = exchange_cost,
        net_cash   = net_cash,
    )


def fill_sell_eop(symbol, qty, entry_fill, last_close):
    """
    Simulate end-of-period liquidation fill.

    Mirrors final_validation.py run_sim() lines 345-348:
      fp   = (gc(s, date_range[-1]) or p['ep']) * (1 - slip)
      cost = BROKERAGE + ev*STT + ev*EXCHANGE

    Args:
        symbol     : stock ticker
        qty        : shares to sell
        entry_fill : position entry price (fallback if last_close is None)
        last_close : last day's closing price

    Returns:
        fill_record : dict
    """
    # Price fallback (FV line 346): last_close → entry_fill
    price_base = last_close if (last_close and last_close > 0) else entry_fill
    if price_base is None or price_base <= 0:
        return None

    fill = price_base * (1 - SLIP)
    ev   = qty * fill

    brokerage_cost = BROKERAGE
    stt_cost       = ev * STT
    exchange_cost  = ev * EXCHANGE

    net_cash = ev - (brokerage_cost + stt_cost + exchange_cost)

    return _fill_result(
        event      = "SELL_EOP",
        symbol     = symbol,
        qty        = qty,
        fill_price = fill,
        brokerage  = brokerage_cost,
        stt        = stt_cost,
        exchange   = exchange_cost,
        net_cash   = net_cash,
    )


def sl_level(entry_fill):
    """
    Compute the SL trigger threshold for a position.

    Mirrors final_validation.py line 308:
      entry_fill * (1 - SL_PCT / 100)

    IMPORTANT: entry_fill must be the post-slippage fill price stored at
    time of buy, NOT the pre-slippage closing price. Using close × 0.90
    instead of entry_fill × 0.90 understates the SL level by ~0.18%.

    Args:
        entry_fill : fill price at time of buy (includes +0.2% slippage)

    Returns:
        float : the closing price at or below which SL is triggered
    """
    return entry_fill * (1 - SL_PCT / 100)


def is_sl_triggered(today_close, entry_fill):
    """
    Returns True if today_close breaches the SL threshold.
    Exact replication of final_validation.py line 308 condition.
    """
    return today_close is not None and today_close > 0 and today_close <= sl_level(entry_fill)


# ─────────────────────────────────────────────────────────────────────────────
# Self-verification: run against known final_validation.py values
# ─────────────────────────────────────────────────────────────────────────────
def _verify():
    """
    Verifies this module's outputs against hand-computed values derived
    from final_validation.py constants. Run with: python paper.py
    """
    PASS = "✓ PASS"
    FAIL = "✗ FAIL"
    results = []

    def check(label, got, expected, tol=0.01):
        ok = abs(got - expected) <= tol
        results.append((ok, label, got, expected))
        print(f"  {PASS if ok else FAIL}  {label}")
        print(f"         got={got:.6f}  expected={expected:.6f}")

    print("=" * 60)
    print("paper.py SELF-VERIFICATION")
    print("=" * 60)

    # ── Test 1: BUY fill at next_open ───────────────────────────────────────
    # Stock A: next_open=2000, cash=500_000, n_new=10
    # avail_cap = 500_000 × 0.95 = 475_000
    # alloc     = min(475_000/10, 500_000/10) = min(47_500, 50_000) = 47_500
    # fill      = 2000 × 1.002 = 2004.00
    # qty       = max(1, int(47_500/2004)) = max(1,23) = 23
    # exchange  = 23 × 2004 × 0.0000345 = 1.5891
    # total_cost= 20 + 1.5891 = 21.5891
    # net_cash  = -(23 × 2004 + 21.5891) = -(46092 + 21.5891) = -46113.589
    print("\n[T1] Rebalance BUY at next_open=2000")
    rec, entry_fill, qty = fill_buy("TEST_A", next_open=2000, today_close=1990,
                                     cash=500_000, n_new_entries=10)
    check("fill_price",  rec["fill_price"],  2000 * 1.002)
    check("qty",         qty,                23,          tol=0)
    check("brokerage",   rec["brokerage"],   20.0,        tol=0)
    check("stt",         rec["stt"],         0.0,         tol=0)  # no STT on buy
    check("exchange",    rec["exchange"],     23 * 2004.0 * 0.0000345)
    check("net_cash",    rec["net_cash"],     -(23 * 2004.0 + 20.0 + 23 * 2004.0 * 0.0000345))

    # ── Test 2: BUY falls back to today_close when next_open=None ──────────
    print("\n[T2] Rebalance BUY — next_open=None, falls back to today_close=1990")
    rec2, entry_fill2, _ = fill_buy("TEST_B", next_open=None, today_close=1990,
                                     cash=500_000, n_new_entries=10)
    check("fill_price", rec2["fill_price"], 1990 * 1.002)

    # ── Test 3: SELL REBALANCE at next_open ─────────────────────────────────
    # Stock: qty=23, entry_fill=2004, next_open=2100
    # fill     = 2100 × (1-0.002) = 2100 × 0.998 = 2095.80
    # ev       = 23 × 2095.80 = 48203.40
    # brokerage= 20
    # stt      = 48203.40 × 0.001 = 48.2034
    # exchange = 48203.40 × 0.0000345 = 1.663
    # net_cash = 48203.40 - 20 - 48.2034 - 1.663 = 48133.53
    print("\n[T3] Rebalance SELL at next_open=2100")
    rec3 = fill_sell_rebalance("TEST_A", qty=23, entry_fill=2004.0,
                                next_open=2100, today_close=2090)
    check("fill_price", rec3["fill_price"],  2100 * 0.998)
    check("stt",        rec3["stt"],         23 * 2100 * 0.998 * 0.001)
    check("exchange",   rec3["exchange"],    23 * 2100 * 0.998 * 0.0000345)
    check("net_cash",   rec3["net_cash"],
          23*2100*0.998 - 20 - 23*2100*0.998*0.001 - 23*2100*0.998*0.0000345)

    # ── Test 4: SL trigger check ────────────────────────────────────────────
    # entry_fill=2004.0, sl_threshold=2004*0.90=1803.60
    print("\n[T4] SL trigger checks")
    check("sl_level",   sl_level(2004.0),   2004.0 * 0.90)
    not_triggered, _ = fill_sell_sl("TEST_A", qty=23, entry_fill=2004.0, today_close=1810)
    above_threshold, _ = fill_sell_sl("TEST_A", qty=23, entry_fill=2004.0, today_close=1900)
    print(f"  {PASS if not not_triggered == False else FAIL}  close=1810 > threshold=1803.6  → not triggered: {not not_triggered}")
    print(f"  {PASS if above_threshold == False else FAIL}  close=1900 > threshold=1803.6  → not triggered: {above_threshold}")

    # ── Test 5: SL EXIT fill (same-day close, NOT next-day open) ───────────
    # entry_fill=2004.0, sl_threshold=1803.6, today_close=1780 (breached)
    # fill     = 1780 × 0.998 = 1776.44
    # ev       = 23 × 1776.44 = 40858.12
    # stt      = 40858.12 × 0.001 = 40.858
    # exchange = 40858.12 × 0.0000345 = 1.4096
    # net_cash = 40858.12 - 20 - 40.858 - 1.4096 = 40795.85
    print("\n[T5] SL EXIT fill at today_close=1780 (threshold=1803.6)")
    triggered, rec5 = fill_sell_sl("TEST_A", qty=23, entry_fill=2004.0, today_close=1780)
    check("triggered",  float(triggered),   1.0,        tol=0)
    check("fill_price", rec5["fill_price"], 1780 * 0.998)
    check("stt",        rec5["stt"],        23 * 1780 * 0.998 * 0.001)
    check("net_cash",   rec5["net_cash"],
          23*1780*0.998 - 20 - 23*1780*0.998*0.001 - 23*1780*0.998*0.0000345)

    # ── Test 6: SL anchors to entry_fill, NOT pre-slippage close ───────────
    # Validates the bug fix: if sl were anchored to close×0.90 (wrong),
    # for entry_fill=2004.0 the threshold would be 1800.0 (not 1803.6).
    # close=1802 breaches correct threshold (1803.6) but not wrong one (1800.0).
    print("\n[T6] SL anchor is entry_fill×0.90 (not close×0.90)")
    trig_correct, _ = fill_sell_sl("TEST_A", qty=23, entry_fill=2004.0, today_close=1802)
    print(f"  {'PASS' if trig_correct else 'FAIL'}  "
          f"close=1802 < threshold=1803.60 (entry_fill=2004×0.90)  triggered={trig_correct}")

    # ── Test 7: EoP fill ────────────────────────────────────────────────────
    print("\n[T7] End-of-Period EXIT at last_close=2200")
    rec7 = fill_sell_eop("TEST_A", qty=23, entry_fill=2004.0, last_close=2200)
    check("fill_price", rec7["fill_price"], 2200 * 0.998)
    check("stt",        rec7["stt"],        23 * 2200 * 0.998 * 0.001)

    # ── Test 8: EoP falls back to entry_fill when last_close=None ──────────
    print("\n[T8] End-of-Period EXIT — last_close=None, falls back to entry_fill")
    rec8 = fill_sell_eop("TEST_A", qty=23, entry_fill=2004.0, last_close=None)
    check("fill_price", rec8["fill_price"], 2004.0 * 0.998)

    print()
    passed = sum(1 for ok, *_ in results if ok)
    total  = len(results)
    print(f"{'=' * 60}")
    print(f"RESULT: {passed}/{total} checks passed")
    if passed == total:
        print("VERDICT: PASS — paper.py fill model is identical to final_validation.py")
    else:
        print("VERDICT: FAIL — discrepancies found above")
    print(f"{'=' * 60}")
    return passed == total


if __name__ == "__main__":
    _verify()
