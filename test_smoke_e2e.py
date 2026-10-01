"""
test_smoke_e2e.py — End-to-end smoke test for the live trading path.

Runs the REAL entry points (daily_ops_report.main, execution_engine.validate_orders)
against synthetic data. No network, no broker, no credentials.

This exists because test_critical_bugs.py reported 37/37 passing while
daily_ops_report.main() raised UnboundLocalError on every single invocation --
those checks grep source text, they never execute the code. One actual call to
main() would have caught it instantly. That bug blocked every ops log from
2026-07-22 onward, which in turn stopped all trading.

Run before every change:
    python test_smoke_e2e.py

Exit code 0 = pass, 1 = fail.
"""

import sys
import os
import json
import types
import shutil
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent.resolve()
os.chdir(HERE)

_passed, _failed = 0, 0


def check(label, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}" + (f"\n          {detail}" if detail else ""))


# ── Synthetic market data ────────────────────────────────────────────────────

def _nifty(trend, n=260):
    """Nifty close series. 'bull' ends above its 200-DMA, 'bear' below."""
    idx = pd.bdate_range(end=pd.Timestamp(date.today()), periods=n)
    vals = (np.linspace(20000, 26000, n) if trend == "bull"
            else np.linspace(26000, 20000, n))
    return pd.DataFrame({"Close": vals}, index=idx)


def _stocks(symbols, n=200, price=300.0):
    """MultiIndex OHLCV frame shaped like a multi-ticker yfinance download.
    Prices are kept low so qty > 0 and the buy path actually produces orders."""
    idx = pd.bdate_range(end=pd.Timestamp(date.today()), periods=n)
    tickers = [s + ".NS" for s in symbols]
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    data = {}
    for i, t in enumerate(tickers):
        # Staggered uptrends so composite scores differ and ranking is exercised
        drift = 1.0 + (i % 7) * 0.05
        close = np.linspace(price, price * drift, n)
        close[-5] *= 1.04          # a >2% surge day to light up the EP factor
        vol = np.full(n, 1_000_000.0)
        vol[-5] = 5_000_000.0      # with >1.5x volume confirmation
        data[("Close", t)] = close
        data[("Volume", t)] = vol
    return pd.DataFrame(data, index=idx, columns=cols)


def _patch_yf(ops, nifty_trend, stock_frame):
    """Point yfinance at synthetic data. ^NSEI and the universe differ."""
    def fake_download(tickers, *a, **k):
        if isinstance(tickers, str) and tickers == "^NSEI":
            return _nifty(nifty_trend)
        return stock_frame
    ops.yf.download = fake_download


# ── Protect any real ops log ─────────────────────────────────────────────────

OPS_LOG = HERE / f"ops_log_{date.today()}.json"
BACKUP = HERE / f"ops_log_{date.today()}.json.smoketest-backup"


def preserve_real_ops_log():
    if OPS_LOG.exists():
        shutil.copy2(OPS_LOG, BACKUP)


def restore_real_ops_log():
    if BACKUP.exists():
        shutil.move(str(BACKUP), str(OPS_LOG))
    elif OPS_LOG.exists():
        OPS_LOG.unlink()  # only the test wrote it


def run_main_capturing(ops):
    """Call the real main(), swallowing its stdout. Returns (ok, error)."""
    import io
    buf, real = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        ops.main()
        return True, None
    except Exception as e:
        import traceback
        return False, traceback.format_exc()
    finally:
        sys.stdout = real


REQUIRED_KEYS = {"report_date", "data_date", "nifty", "dma50", "dma200", "regime",
                 "tradeable", "action", "rebalance_due", "candidates", "buys",
                 "sells", "sl_hits", "regime_exits"}


# ── Tests ────────────────────────────────────────────────────────────────────

def test_ops_report():
    import daily_ops_report as ops
    print("\n[1] daily_ops_report.main() — the path that was crashing")

    # Swap functions back by hand rather than importlib.reload(): the module
    # reassigns sys.stdout at import time, so reloading it closes the real
    # stdout buffer and every later print() dies.
    _orig_regime, _orig_fetch = ops.get_regime, ops.fetch_and_score

    # --- BEAR with healthy data ---
    OPS_LOG.unlink(missing_ok=True)
    _patch_yf(ops, "bear", _stocks(ops.STOCKS[:20]))
    ok, err = run_main_capturing(ops)
    check("BEAR: main() completes", ok, (err or "")[-400:])
    check("BEAR: ops log written", OPS_LOG.exists())
    if OPS_LOG.exists():
        d = json.loads(OPS_LOG.read_text(encoding="utf-8"))
        check("BEAR: schema complete", REQUIRED_KEYS <= set(d),
              f"missing: {REQUIRED_KEYS - set(d)}")
        check("BEAR: regime == BEAR", d.get("regime") == "BEAR", f"got {d.get('regime')}")
        check("BEAR: no buys", d.get("buys") == [])
        check("BEAR: nifty > 0 (passes exec health gate)", d.get("nifty", 0) > 0)

    # --- BULL with healthy data: candidates and buys must appear ---
    OPS_LOG.unlink(missing_ok=True)
    _patch_yf(ops, "bull", _stocks(ops.STOCKS[:20]))
    ok, err = run_main_capturing(ops)
    check("BULL: main() completes", ok, (err or "")[-400:])
    if OPS_LOG.exists():
        d = json.loads(OPS_LOG.read_text(encoding="utf-8"))
        check("BULL: regime is BULL/FLAT", d.get("regime") in ("BULL", "FLAT"),
              f"got {d.get('regime')}")
        check("BULL: candidates produced", len(d.get("candidates", [])) > 0)
        check("BULL: candidates ranked by composite",
              [c["composite"] for c in d["candidates"]]
              == sorted([c["composite"] for c in d["candidates"]], reverse=True))

    # --- Regression: the exact no-data case that caused ZeroDivisionError ---
    OPS_LOG.unlink(missing_ok=True)
    ops.get_regime = lambda: {"date": date.today(), "close": 0, "dma50": 0,
                              "dma200": 0, "regime": "BEAR", "tradeable": False,
                              "data_error": True}
    ok, err = run_main_capturing(ops)
    check("No-data: main() survives close=0 (was ZeroDivisionError)", ok,
          (err or "")[-400:])
    check("No-data: ops log still written", OPS_LOG.exists())

    # --- Regression: empty universe must not crash the candidate path ---
    OPS_LOG.unlink(missing_ok=True)
    ops.get_regime = _orig_regime
    _patch_yf(ops, "bull", _stocks(ops.STOCKS[:20]))
    ops.fetch_and_score = lambda n: (pd.DataFrame(), [(s, "no data") for s in ops.STOCKS])
    ok, err = run_main_capturing(ops)
    check("Empty universe: main() survives (was KeyError/IndexError)", ok,
          (err or "")[-400:])
    check("Empty universe: ops log still written with no buys",
          OPS_LOG.exists()
          and json.loads(OPS_LOG.read_text(encoding="utf-8")).get("buys") == [])
    ops.fetch_and_score = _orig_fetch


def test_execution_validation():
    # Stub credentials + journal so the module imports with no secrets present
    sys.modules.setdefault("config", types.ModuleType("config"))
    sys.modules["config"].UPSTOX_ACCESS_TOKEN = "smoke-test-not-a-real-token"
    tj = types.ModuleType("trade_journal")
    tj.record_trade = lambda **k: None
    sys.modules.setdefault("trade_journal", tj)

    import execution_engine as ee
    ee.load_frozen_symbols = lambda: set()
    print("\n[2] execution_engine.validate_orders() — order planning")

    def state(syms):
        return {"positions": {f"NSE_EQ|{s}": {"qty": 5, "entry": 1000.0, "plain": s,
                                              "sl_price": 900.0} for s in syms},
                "trades": [], "pnl": 0}

    cands = lambda s: [{"symbol": x} for x in s]
    mkbuy = lambda s: [{"symbol": x, "qty": 1, "alloc_rs": 1000, "sl_price": 900}
                       for x in s]
    held = ["RELIANCE", "TCS", "INFY"]

    # Rotation: TCS drops out of the target, HDFCBANK enters
    b, s, e = ee.validate_orders(
        {"regime": "BULL", "rebalance_due": True,
         "candidates": cands(["RELIANCE", "INFY", "HDFCBANK"]),
         "buys": mkbuy(["RELIANCE", "INFY", "HDFCBANK"])}, state(held), 0.0)
    check("Rebalance: drops the name that left Top-N",
          [x["symbol"] for x in s] == ["TCS"], f"got {[x['symbol'] for x in s]}")
    check("Rebalance: buys only the new name",
          [x["symbol"] for x in b] == ["HDFCBANK"], f"got {[x['symbol'] for x in b]}")
    check("Rebalance: sells carry an instrument key (execute_sells needs it)",
          all("instrument" in x for x in s))

    # The dangerous one: rebalance due but scoring failed
    b, s, e = ee.validate_orders(
        {"regime": "BULL", "rebalance_due": True, "candidates": [], "buys": []},
        state(held), 0.0)
    check("SAFETY: empty candidates does NOT liquidate the portfolio",
          s == [], f"would have sold {[x['symbol'] for x in s]}")
    check("SAFETY: the refusal is recorded as an error", len(e) > 0)

    # No rebalance due -> monitoring only
    b, s, e = ee.validate_orders(
        {"regime": "BULL", "rebalance_due": False,
         "candidates": cands(["HDFCBANK"]), "buys": mkbuy(["HDFCBANK"])},
        state(held), 999_999)
    check("Non-rebalance day: no orders", (b, s) == ([], []))

    # BEAR -> exit everything
    b, s, e = ee.validate_orders(
        {"regime": "BEAR", "rebalance_due": False, "candidates": [], "buys": []},
        state(held), 0.0)
    check("BEAR: exits all positions", len(s) == len(held))
    check("BEAR: places no buys", b == [])

    # Unchanged target -> no churn
    b, s, e = ee.validate_orders(
        {"regime": "BULL", "rebalance_due": True, "candidates": cands(held),
         "buys": mkbuy(held)}, state(held), 999_999)
    check("Stable Top-N: no needless turnover", (b, s) == ([], []))


def test_invariants():
    import daily_ops_report as ops
    import execution_engine as ee
    print("\n[3] Cross-module invariants")

    check("SL_PCT matches across modules (silent divergence = wrong stops)",
          ops.SL_PCT == ee.SL_PCT, f"ops={ops.SL_PCT} exec={ee.SL_PCT}")
    check("LIVE_PER_POS == LIVE_CAPITAL // TOP_N",
          ops.LIVE_PER_POS == ops.LIVE_CAPITAL // ops.TOP_N)
    check("Factor weights sum to 1.0", abs(ops.W_RS + ops.W_EP - 1.0) < 1e-9)

    try:
        import strategy_fingerprint as fp
        fp.assert_frozen()
        check("Strategy fingerprint: no parameter drift", True)
        check("Universe size matches the frozen value",
              len(ops.STOCKS) == fp._FROZEN["UNIVERSE_SIZE"],
              f"STOCKS={len(ops.STOCKS)} frozen={fp._FROZEN['UNIVERSE_SIZE']} "
              f"(assert_frozen does not check this)")
    except ValueError as e:
        check("Strategy fingerprint: no parameter drift", False, str(e)[:300])
    except ImportError:
        pass


def main():
    print("=" * 70)
    print("  MONEYBOT END-TO-END SMOKE TEST")
    print("  Executes the real entry points. No network, no broker, no orders.")
    print("=" * 70)

    preserve_real_ops_log()
    try:
        test_ops_report()
        test_execution_validation()
        test_invariants()
    finally:
        restore_real_ops_log()

    total = _passed + _failed
    print("\n" + "=" * 70)
    print(f"  RESULT: {_passed}/{total} passed")
    if _failed:
        print(f"  {_failed} FAILED — do not deploy until these are green.")
    else:
        print("  The live path runs end to end and writes a valid ops log.")
    print("=" * 70)
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
