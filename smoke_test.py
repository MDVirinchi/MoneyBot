"""
smoke_test.py — End-to-end test of the live trading path.

Run before every commit:

    python smoke_test.py          # exit 0 = pass, 1 = fail

WHY THIS EXISTS
---------------
test_critical_bugs.py reported 37/37 passing while daily_ops_report.main()
raised UnboundLocalError on every single invocation for roughly two months.
It passed because it inspects source text ("lock exists in code") instead of
executing anything. No test in the repo called main(), execute_today() or
run_monitor().

That bug fired 100% of the time, in every regime, needing no market data and
no broker. One real call to main() would have caught it instantly.

So this file has exactly one rule: CALL THE REAL ENTRY POINTS. Assertions
about source text belong somewhere else.

Market data is stubbed, so this is offline and takes about a second. That is
deliberate — a test that needs the network is a test that gets skipped.
"""

import io
import json
import os
import shutil
import sys
import types
import contextlib
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

_passed, _failed = 0, 0


def check(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}" + (f"\n          -> {detail}" if detail else ""))


def section(title):
    print(f"\n{title}\n" + "-" * len(title))


# ── Synthetic market data ────────────────────────────────────────────────────
# Shaped like yfinance output: MultiIndex columns of (field, ticker).

def _bars(n):
    return pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)


def nifty_frame(direction, n=400):
    """direction: 'bull' (above both MAs), 'bear' (below 200DMA), 'flat'."""
    idx = _bars(n)
    if direction == "bull":
        close = np.linspace(18000, 25000, n)            # steady uptrend
    elif direction == "bear":
        close = np.linspace(28000, 22000, n)            # steady downtrend
    else:
        # FLAT needs price > 200DMA while 50DMA is still <= 200DMA. That means
        # a long high plateau (lifting the 200DMA), a deep dip (dragging the
        # 50DMA down), then a sharp recovery at the very end.
        close = np.concatenate([
            np.full(n - 200, 26000.0),
            np.full(150, 26000.0),          # plateau -> high 200DMA
            np.full(45, 20000.0),           # dip     -> low 50DMA
            np.linspace(21000, 27000, 5),   # recovery-> close above 200DMA
        ])
    df = pd.DataFrame({("Close", "^NSEI"): close,
                       ("Volume", "^NSEI"): np.full(n, 1e6)}, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def stock_frame(symbols, n=200, seed=7):
    """Varied trends + a volume spike so RS and EP both produce a spread."""
    idx = _bars(n)
    rng = np.random.default_rng(seed)
    data = {}
    for i, sym in enumerate(symbols):
        t = sym + ".NS"
        drift = (i % 11 - 4) / 2200.0                   # some up, some down
        rets = rng.normal(drift, 0.011, n)
        rets[-20] = 0.045                               # EP-qualifying surge
        close = 100.0 * (1 + i % 40) * np.cumprod(1 + rets)
        vol = np.full(n, 1_000_000.0)
        vol[-20] = 5_000_000.0                          # volume confirms surge
        data[("Close", t)] = close
        data[("Volume", t)] = vol
    df = pd.DataFrame(data, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def make_downloader(direction, stocks, fail=False):
    def _download(tickers, *a, **kw):
        if fail:
            return pd.DataFrame()
        tl = [tickers] if isinstance(tickers, str) else list(tickers)
        if tl == ["^NSEI"]:
            return nifty_frame(direction)
        return stock_frame(stocks)
    return _download


# ── Harness ──────────────────────────────────────────────────────────────────
# daily_ops_report rewrites sys.stdout at import time and needs a real stream
# with .buffer, so it must be imported before any output capture.

import daily_ops_report as ops  # noqa: E402

_cfg = types.ModuleType("config")
_cfg.UPSTOX_ACCESS_TOKEN = "smoke-test-token"
sys.modules.setdefault("config", _cfg)
_tj = types.ModuleType("trade_journal")
_tj.record_trade = lambda **kw: None
sys.modules.setdefault("trade_journal", _tj)

import execution_engine as ee  # noqa: E402
ee.load_frozen_symbols = lambda: set()

OPS_LOG = HERE / f"ops_log_{date.today()}.json"
BACKUP = HERE / f"ops_log_{date.today()}.json.smokebak"


def run_main(direction, fail=False):
    """Call the real main() with stubbed data. Returns (error, ops_log_dict)."""
    real_dl = ops.yf.download
    ops.yf.download = make_downloader(direction, ops.STOCKS, fail=fail)
    if OPS_LOG.exists():
        OPS_LOG.unlink()
    err = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ops.main()
    except Exception as e:
        import traceback
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"
    finally:
        ops.yf.download = real_dl
    log = None
    if OPS_LOG.exists():
        try:
            log = json.loads(OPS_LOG.read_text(encoding="utf-8"))
        except Exception as e:
            err = err or f"ops log unreadable: {e}"
    return err, log


REQUIRED_KEYS = ["report_date", "data_date", "nifty", "dma50", "dma200",
                 "regime", "tradeable", "action", "rebalance_due",
                 "candidates", "buys", "sells"]


def test_ops_report():
    section("1. daily_ops_report.main() — the path that was crashing")

    for direction, expect in [("bull", "BULL"), ("bear", "BEAR"), ("flat", "FLAT")]:
        err, log = run_main(direction)
        check(f"main() completes in {expect} regime", err is None, err)
        check(f"{expect}: ops log written", log is not None,
              "execution_engine reads this file; no file means no trading")
        if log:
            missing = [k for k in REQUIRED_KEYS if k not in log]
            check(f"{expect}: ops log has all required keys", not missing,
                  f"missing: {missing}")
            check(f"{expect}: regime classified correctly",
                  log.get("regime") == expect,
                  f"got {log.get('regime')}, expected {expect}")
            # execution_engine.pre_market_health_check rejects nifty<=0
            check(f"{expect}: nifty/dma200 pass the health-check gate",
                  log.get("nifty", 0) > 0 and log.get("dma200", 0) > 0,
                  f"nifty={log.get('nifty')} dma200={log.get('dma200')}")

    # Total data failure must degrade to BEAR, not raise.
    err, log = run_main("bull", fail=True)
    check("main() survives total data failure", err is None, err)
    check("data failure: still writes an ops log", log is not None)
    if log:
        check("data failure: degrades to BEAR (never trades blind)",
              log.get("regime") == "BEAR", f"got {log.get('regime')}")


def test_candidates():
    section("2. Stock selection produces a usable target list")
    err, log = run_main("bull")
    if err or not log:
        check("BULL run available for candidate checks", False, err)
        return
    cands = log.get("candidates", [])
    check("candidates generated in BULL", len(cands) > 0)
    check(f"candidate count <= TOP_N ({ops.TOP_N})", len(cands) <= ops.TOP_N,
          f"got {len(cands)}")
    if cands:
        check("candidates carry symbol + composite",
              all("symbol" in c and "composite" in c for c in cands))
        comps = [c["composite"] for c in cands]
        check("candidates ranked by composite descending",
              comps == sorted(comps, reverse=True), f"{comps}")


def test_validate_orders():
    section("3. execution_engine.validate_orders() — rotation + safety")

    def pos(sym, qty=5, entry=1000.0):
        return {"qty": qty, "entry": entry, "plain": sym,
                "sl_price": entry * (1 - ee.SL_PCT)}

    held = ["RELIANCE", "TCS", "INFY"]

    def state():
        return {"positions": {f"NSE_EQ|{s}": pos(s) for s in held},
                "trades": [], "pnl": 0}

    cands = lambda syms: [{"symbol": s} for s in syms]
    mkbuy = lambda syms: [{"symbol": s, "qty": 1, "alloc_rs": 1000,
                           "sl_price": 900} for s in syms]

    # The engine's logger owns a StreamHandler bound to the real stdout at
    # import, so redirect_stdout cannot silence it. Disable the logger instead.
    ee.log.disabled = True

    def vo(regime, rebalance, candidates, buys, cash=0.0):
        return ee.validate_orders(
            {"regime": regime, "rebalance_due": rebalance,
             "candidates": cands(candidates), "buys": mkbuy(buys)},
            state(), cash)

    try:
        # Rotation: TCS drops out, HDFCBANK comes in
        b, s, e = vo("BULL", True, ["RELIANCE", "INFY", "HDFCBANK"],
                     ["RELIANCE", "INFY", "HDFCBANK"])
        sold = {x["symbol"] for x in s}
        check("rebalance sells the name that left Top-N", sold == {"TCS"}, f"{sold}")
        check("rebalance keeps names still in Top-N", "RELIANCE" not in sold)
        check("rebalance buys the new name",
              {x["symbol"] for x in b} == {"HDFCBANK"}, f"{[x['symbol'] for x in b]}")
        check("buys validated against sell proceeds, not idle cash", len(b) > 0,
              "a fully-deployed portfolio must still be able to rotate")

        # The dangerous one: rebalance due but scoring failed.
        b, s, e = vo("BULL", True, [], [])
        check("empty candidates does NOT liquidate the portfolio", len(s) == 0,
              f"would have sold {len(s)} position(s) on a data blip")
        check("empty candidates records an error", len(e) > 0)

        # BEAR exits everything.
        b, s, e = vo("BEAR", False, [], [])
        check("BEAR liquidates all positions", len(s) == len(held), f"{len(s)}")
        check("BEAR places no buys", len(b) == 0)

        # Non-rebalance day is a no-op.
        b, s, e = vo("BULL", False, ["HDFCBANK"], ["HDFCBANK"])
        check("non-rebalance day places no orders", not b and not s)

        # No churn when nothing changed.
        b, s, e = vo("BULL", True, held, held)
        check("unchanged Top-N causes no churn", not b and not s,
              f"buys={len(b)} sells={len(s)}")
    finally:
        ee.log.disabled = False


def test_invariants():
    section("4. Cross-module invariants")
    check("SL_PCT matches across modules", ops.SL_PCT == ee.SL_PCT,
          f"ops={ops.SL_PCT} exec={ee.SL_PCT}")
    check("LIVE_PER_POS = LIVE_CAPITAL / TOP_N",
          ops.LIVE_PER_POS == ops.LIVE_CAPITAL // ops.TOP_N)
    check("RS and EP weights sum to 1.0", abs(ops.W_RS + ops.W_EP - 1.0) < 1e-9)

    try:
        import strategy_fingerprint as fp
        fp.assert_frozen()
        check("strategy fingerprint not drifted", True)
        check("fingerprint covers the declared universe size",
              fp._FROZEN.get("UNIVERSE_SIZE") == len(ops.STOCKS),
              f"_FROZEN says {fp._FROZEN.get('UNIVERSE_SIZE')}, "
              f"STOCKS has {len(ops.STOCKS)} — silent universe drift")
    except ValueError as e:
        check("strategy fingerprint not drifted", False, str(e)[:200])
    except ImportError:
        pass


def main():
    print("=" * 68)
    print("  MONEYBOT SMOKE TEST — runs the real entry points, offline")
    print("=" * 68)

    restore = False
    if OPS_LOG.exists():
        shutil.copy2(OPS_LOG, BACKUP)
        restore = True

    try:
        test_ops_report()
        test_candidates()
        test_validate_orders()
        test_invariants()
    finally:
        if OPS_LOG.exists():
            OPS_LOG.unlink()
        if restore:
            shutil.move(str(BACKUP), str(OPS_LOG))

    total = _passed + _failed
    print("\n" + "=" * 68)
    print(f"  {_passed}/{total} checks passed")
    if _failed:
        print(f"  {_failed} FAILED — do not deploy")
    else:
        print("  Live path runs end to end. Safe to deploy.")
    print("=" * 68)
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
