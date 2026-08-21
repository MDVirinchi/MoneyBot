# MoneyBot — Authoritative System Specification
**Version:** v1.3.1 | **Last updated:** 2026-08-21 | **Status:** Paper-trading validation

> This is the single source of truth. All other documents, comments, and configs
> must agree with this file. When in doubt, this wins.

---

## Strategy (FROZEN — do not modify during paper-trading period)

| Parameter | Value | File |
|-----------|-------|------|
| RS weight (W_RS) | 60% | `daily_ops_report.py` |
| EP weight (W_EP) | 40% | `daily_ops_report.py` |
| RS window | 63 bars (≈ 3 months) | `daily_ops_report.py` |
| EP window | 63 bars | `daily_ops_report.py` |
| EP minimum return | 2% (EP_RET_MIN) | `daily_ops_report.py` |
| EP volume multiplier | 1.5× avg volume | `daily_ops_report.py` |
| Top-N selections | 10 stocks | `daily_ops_report.py` |
| Stop-loss | 10% from fill price | `daily_ops_report.py`, `execution_engine.py` |
| Rebalance cadence | Every 10 trading days | `daily_ops_report.py` |
| Paper start date | 2026-06-16 | `daily_ops_report.py` |

### RS Factor
63-day excess return vs Nifty 50:
```
stock_ret  = (price_now / price_63d_ago) - 1
nifty_ret  = (nifty_now / nifty_63d_ago) - 1
rs_raw     = (stock_ret - nifty_ret) × 100
```

### EP Factor
Maximum single-day surge in last 63 bars where:
- Day return > 2%  AND  volume > 1.5× 63-day average volume
- Zero-volume days excluded from average
- `ep_raw = max qualifying day_return × 100`

### Composite Score
```
composite = 0.60 × rs_percentile + 0.40 × ep_percentile
```
(Cross-sectional percentile rank 0–100 within the universe)

---

## Regime Filter — Policy-C

| Condition | Regime | Action |
|-----------|--------|--------|
| Nifty close < 200-DMA | BEAR | 100% cash. Zero new entries. |
| Nifty > 200-DMA AND 50-DMA > 200-DMA | BULL | Trade normally. |
| Nifty > 200-DMA AND 50-DMA ≤ 200-DMA | FLAT | Trade normally. |

Signal is **daily close only** — intraday crosses do not trigger regime change.

---

## Stock Filter

50-DMA trend filter applied before Top-N selection:
- Stock's close must be above its own 50-bar MA
- Stocks below their 50-DMA are excluded from Top-N eligibility
- This does NOT change RS/EP weights

---

## Universe

136 NSE stocks (defined in `daily_ops_report.py → STOCKS`). Do not modify.
All tickers are `.NS` suffix for yfinance.

---

## Capital Configuration

| Variable | Value | Description |
|----------|-------|-------------|
| `PAPER_CAPITAL` | ₹5,000 | Paper-sim display only. Fingerprint-locked. Do not change. |
| `PER_POS` | ₹500 | Paper-sim per-position. Fingerprint-locked. Do not change. |
| `LIVE_CAPITAL` | ₹11,500 | Actual Upstox funded balance. Update when balance changes. |
| `LIVE_PER_POS` | ₹1,150 | `LIVE_CAPITAL ÷ TOP_N`. Auto-computed. |

**To update live capital:** change only `LIVE_CAPITAL` in `daily_ops_report.py`.
`LIVE_PER_POS` re-computes automatically. Update `strategy_fingerprint._FROZEN["LIVE_CAPITAL"]`
and `_FROZEN["LIVE_PER_POS"]` to match, then commit.

---

## Execution Timing

| Time (IST) | Action |
|------------|--------|
| 9:05 AM | Cron fires `auto_daily.py` |
| 9:05–9:14 | `daily_ops_report.py` runs (regime, candidates, ops_log) |
| 9:14 AM | `execution_engine.py` — place buy/sell orders at market |
| 9:15–15:30 | SL monitor every 5 minutes |
| 15:30+ | Post-market audit, Telegram notification |

---

## Execution Platform

- **Development / testing:** Windows (laptop)
- **Production:** Samsung Galaxy S25 FE → Termux → Ubuntu proot-distro
- **Python version (production):** Ubuntu system Python 3.x (has glibc pandas)
- **Start command:** `python3 ~/token_input.py` (opens web UI at localhost:8877)
- **Env var required:** `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python`

---

## Mode: Paper Trading

The bot is in **paper-trading validation mode**. All execution calls are live
(real Upstox API calls), but the goal is to build evidence, not returns.

**Do NOT change strategy parameters** (`W_RS`, `W_EP`, `TOP_N`, `SL_PCT`,
`RS_WINDOW`, `EP_WINDOW`, `EP_RET_MIN`, `EP_VOL_MULT`, rebalance cadence)
until the paper-trading period is complete and results are reviewed.

The `strategy_fingerprint.py` enforces this: any drift in frozen parameters
halts the bot before execution.

---

## What "No Trade" Means

The daily ops report now produces a **candidate pipeline summary** explaining
exactly why no trade occurred:

1. BEAR regime → blocked at Policy-C (waiting for Nifty > 200-DMA close)
2. Non-rebalance day → monitoring only
3. All candidates filtered by 50-DMA → no eligible stocks
4. LIVE_PER_POS too small for candidate prices → qty=0 (update `LIVE_CAPITAL`)

---

## Files and Responsibilities

| File | Purpose |
|------|---------|
| `daily_ops_report.py` | Regime, scoring, candidate list, ops_log JSON |
| `execution_engine.py` | Read ops_log → place orders → SL monitor |
| `auto_daily.py` | Orchestrator: runs all steps in sequence |
| `strategy_fingerprint.py` | Immutable strategy hash — halts on drift |
| `config.py` | Upstox credentials — **never commit, never share** |
| `token_input.py` | Web UI on phone to enter daily access token |
| `execution_state.json` | Open positions, trades, PnL |
| `ops_log_YYYY-MM-DD.json` | Today's regime + candidate + order plan |
| `auto_daily.log` | Full daily run log |

---

## Security Rules

- `config.py` must NEVER be committed to git (it's in `.gitignore`)
- Upstox access token expires daily — paste fresh token via web UI each morning
- API Key and API Secret are saved once by `token_input.py`
- If credentials leak: rotate immediately at Upstox developer portal
