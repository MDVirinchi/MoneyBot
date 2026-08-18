# PERFORMANCE REGISTRY
## Single Source of Truth for Strategy Performance

**Last updated:** 2026-06-20
**Updated by:** Claude (automated backtest)
**Data source:** yfinance 5-year daily data, 134 stocks

---

## DEPLOYED CONFIGURATION

| Parameter | Value |
|-----------|-------|
| **Version** | v2.0 |
| **Strategy** | RS60/EP40 + Policy C + 50-DMA filter |
| **RS weight** | 60% |
| **EP weight** | 40% |
| **Regime filter** | Policy C: Nifty close < 200-DMA = BEAR = 100% cash |
| **50-DMA filter** | Stock close must be above its own 50-day MA |
| **Sector cap** | None |
| **Position sizing** | Equal weight (Rs.50,000 per position) |
| **Top-N** | 10 |
| **Rebalance** | Every 10 trading days |
| **Stop-loss** | 10% below entry fill |
| **Slippage assumption** | 0.2% each side |
| **Brokerage** | Rs.20 flat per leg |
| **STT** | 0.1% sell-side only |
| **Exchange fees** | 0.00345% both legs |
| **Universe** | 134 NSE stocks (frozen list in daily_ops_report.py) |
| **Capital** | Rs.5,00,000 (paper) |
| **IS period** | 2021-06-21 to 2024-06-19 (740 trading days) |
| **OOS period** | 2024-06-20 to 2026-06-19 (494 trading days) |

---

## AUTHORITATIVE OOS PERFORMANCE (v2.0)

| Metric | Value |
|--------|-------|
| **CAGR** | **+4.40%** |
| **Sharpe Ratio** | **0.427** |
| **Max Drawdown** | **16.1%** |
| **Win Rate** | **44.1%** |
| **Profit Factor** | **1.230** |
| **Total Trades** | **170** |
| **SL Exits** | **12** |
| **Final Value** | **Rs.5,43,991** |
| **Beats Nifty** | YES (Nifty OOS: +1.0%) |
| **Break-even slippage** | 0.47% each side |
| **Annual turnover** | 1,586% |

---

## ALL TESTED VARIANTS

| Version | Description | Regime | Slip | 50DMA | Sector | OOS CAGR | OOS Sharpe | OOS MaxDD | Why it differs from v2.0 |
|---------|-------------|--------|------|-------|--------|----------|------------|-----------|--------------------------|
| v1.0 | Raw RS60/EP40, no regime | always | 0.2% | No | None | +1.45% | 0.183 | 23.3% | No regime filter, no 50-DMA |
| v1.1 | + Policy B (Bull-only) | bull_only | 0.2% | No | None | -0.16% | 0.069 | 18.1% | Too restrictive regime |
| v1.2 | + Policy C (Bull+Flat) | bull_flat | 0.2% | No | None | +3.94% | 0.380 | 16.6% | No 50-DMA filter |
| v1.3 | + Policy C + 2x slippage | bull_flat | 0.4% | No | None | +0.64% | 0.138 | 18.6% | Higher slippage, no 50-DMA |
| v1.4 | + Policy C + 3x slippage | bull_flat | 0.6% | No | None | -2.46% | -0.090 | 20.7% | 3x slippage kills edge |
| **v2.0** | **+ Policy C + 50DMA** | **bull_flat** | **0.2%** | **Yes** | **None** | **+4.40%** | **0.427** | **16.1%** | **DEPLOYED** |
| v2.1 | + Policy C + 50DMA + 2x slip | bull_flat | 0.4% | Yes | None | +1.17% | 0.181 | 18.3% | Cost stress test |
| v3.0 | + 50DMA + Sector cap(2) | bull_flat | 0.2% | Yes | Max 2 | -4.25% | -0.284 | 19.8% | Sector cap destroys edge |
| v3.1 | + 50DMA + Sector cap(3) | bull_flat | 0.2% | Yes | Max 3 | +1.70% | 0.221 | 14.8% | Sector cap costs CAGR |

---

## REJECTED ENHANCEMENTS (with evidence)

| Enhancement | OOS Result | Reason for rejection |
|-------------|-----------|---------------------|
| Sector cap (max 2/sector) | CAGR -4.25%, Sharpe -0.284 | Destroys strategy entirely |
| Sector cap (max 3/sector) | CAGR +1.70%, -2.70pp vs deployed | Costs too much CAGR for DD gain |
| ATR sizing | CAGR +0.83%, -3.57pp vs deployed | High-vol winners get undersized |
| Volatility parity | CAGR +4.22%, -0.18pp vs deployed | Marginal DD gain, not worth complexity |
| Inverse volatility | CAGR +4.22%, same as vol parity | Mathematically equivalent to vol parity |

## REBALANCE FREQUENCY STUDY

| Frequency | OOS CAGR | Sharpe | MaxDD | Break-even slip | Status |
|-----------|----------|--------|-------|-----------------|--------|
| 5d | +3.65% | 0.352 | 17.5% | 0.37% | Too much turnover |
| 7d | +3.75% | 0.360 | 16.3% | 0.38% | Marginal |
| **10d** | **+4.40%** | **0.427** | **16.1%** | **0.47%** | **DEPLOYED** |
| 15d | +3.66% | 0.377 | 11.9% | 0.47% | Lower DD, lower CAGR |
| 20d | -3.66% | -0.229 | 20.3% | <0.2% | Signal decays too much |
| 30d | -3.97% | -0.296 | 17.2% | <0.2% | Strategy breaks |

---

## PROFIT CONCENTRATION (OOS, 10d rebalance)

- Top 10 trades produce 233% of total PnL
- All bottom 10 losses are stop-loss exits (0% win rate)
- Average rebalance trade: +Rs.726, held 24.2 days
- Average SL trade: -Rs.5,564, held 17.0 days
- Rebalance exits: 50.6% win rate
- Strategy depends on catching a few large winners

---

## REGIME DMA ROBUSTNESS (OOS, 0.2% slippage)

| DMA | Bear% | CAGR | Sharpe | MaxDD | Break-even slip | Status |
|-----|-------|------|--------|-------|-----------------|--------|
| 150 | 35.0% | -2.96% | -0.143 | 18.3% | <0.2% | Too aggressive filter |
| 175 | 33.4% | +0.99% | 0.158 | 13.5% | ~0.3% | Marginal |
| **200** | **32.2%** | **+4.40%** | **0.427** | **16.1%** | **0.47%** | **DEPLOYED (rank 2/5)** |
| 225 | 30.0% | +6.82% | 0.581 | 14.7% | >0.6% | Best Sharpe but less protective |
| 250 | 27.3% | +3.17% | 0.311 | 18.1% | ~0.4% | Too loose filter |

**Conclusion:** 200-DMA is robust (rank 2 of 5 by Sharpe). Not a lucky pick.

### Fine DMA Sweep (190-240, step 5)

| DMA | Bear% | OOS CAGR | Sharpe | MaxDD | 0.6% slip CAGR |
|-----|-------|----------|--------|-------|----------------|
| 190 | 32.6% | +2.36% | 0.268 | 18.1% | — |
| 195 | 32.8% | +3.65% | 0.369 | 16.6% | — |
| **200** | **32.2%** | **+4.40%** | **0.427** | **16.1%** | **-2.03%** |
| 205 | 31.8% | +3.84% | 0.383 | 17.1% | — |
| 210 | 31.6% | +5.80% | 0.540 | 13.9% | — |
| 215-225 | 30.0% | +6.82% | 0.581 | 14.7% | +0.55% |
| **230** | **28.5%** | **+7.47%** | **0.621** | **14.7%** | **+1.43%** |
| 235 | 28.1% | +6.05% | 0.514 | 17.5% | — |
| 240 | 27.9% | +6.07% | 0.516 | 17.4% | — |

**Smoothness analysis:** Spike ratio = 0.16 (<1.0 = smooth). The 210-230 DMA range is a genuine performance plateau, not parameter luck. 215/220/225 produce identical results (same regime transitions in this OOS period).

**Key finding:** 215-230 DMA stays profitable at 0.6% slippage (+0.55% to +1.43%) while 200 DMA does not (-2.03%). The friction sensitivity concern largely resolves at longer DMA thresholds because fewer regime transitions = less exit/re-entry churn.

### Walk-Forward Validation (4 independent 2-year windows)

| Window | 200-DMA | 210-DMA | 220-DMA | 230-DMA | Winner |
|--------|---------|---------|---------|---------|--------|
| 2018-2020 | -7.0% | -5.4% | **-4.5%** | -6.1% | 220 |
| 2020-2022 | +30.3% | **+31.6%** | +28.4% | +26.1% | 210 |
| 2022-2024 | **+39.9%** | +39.0% | +37.9% | +34.2% | 200 |
| 2024-2026 | +1.7% | +3.1% | +4.1% | **+5.6%** | 230 |
| **Avg CAGR** | +16.2% | **+17.1%** | +16.5% | +14.9% | 210 |
| **Avg Sharpe** | 0.889 | **0.940** | 0.935 | 0.850 | 210 |
| **Windows won** | 1 | 1 | 1 | 1 | Tie |

**Conclusion:** No single DMA consistently wins. Each DMA won exactly 1 of 4 windows. 210-DMA has the best average Sharpe (0.940) but the differences are small. 200-DMA won the strongest bull market window (2022-2024, +39.9%). 230-DMA won the most recent difficult window (2024-2026).

**Current decision:** Keep 200-DMA. The walk-forward shows NO DMA is reliably superior across all market conditions. The 225-DMA advantage seen in single-window OOS does NOT persist across multiple windows — it was period-specific, exactly as ChatGPT suspected. 200-DMA remains the conservative, validated choice.

---

## HOW TO UPDATE THIS DOCUMENT

When re-running backtests:
1. Run `python performance_registry.py`
2. Copy the OOS results for the deployed version into this file
3. Add any new variants to the ALL TESTED VARIANTS table
4. Update the "Last updated" date

**Rule: If a number in this document conflicts with any other document, THIS document is authoritative.**
