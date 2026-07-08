# MoneyBot Live Operations Manual
## RS=60% / EP=40% | Policy C | Top-10 | Rebal 10d | SL 10%
**Status: FROZEN. Do not modify any parameter without a full re-validation cycle.**
Generated: 2026-06-14

---

## 1. DAILY CHECKLIST
*Every trading day. Complete before 9:10 AM. Takes ~5 minutes.*

### 1A. Regime Check (mandatory)
- [ ] Download yesterday's Nifty 50 closing price
- [ ] Recompute 50-DMA (50-bar rolling average of closes)
- [ ] Recompute 200-DMA (200-bar rolling average of closes)
- [ ] Classify regime:
  - **Bull** = Nifty > 200DMA AND 50DMA > 200DMA
  - **Flat** = Nifty > 200DMA AND 50DMA <= 200DMA
  - **Bear** = Nifty < 200DMA
- [ ] Log: Date | Nifty close | 50DMA | 200DMA | Regime

### 1B. Bear Regime Actions
- [ ] If regime = **Bear** AND positions are open -> place market sell orders for ALL positions at 9:15 AM open
- [ ] If regime = **Bear** AND no positions -> do nothing. Hold cash. Skip to step 1E.
- [ ] Record regime exit in trade log with date, price, reason = "Regime:Bear"

### 1C. Stop-Loss Check (Bull/Flat only)
For each open position:
- [ ] Retrieve entry price (cost basis recorded at fill)
- [ ] Compute SL level = entry_price x 0.90
- [ ] Retrieve yesterday's closing price for each position
- [ ] If close <= SL level -> mark for exit at today's 9:15 AM open
- [ ] Place market sell order for any SL-triggered positions
- [ ] Record exit in trade log: Date | Symbol | Entry | Exit | Reason=SL | P&L

### 1D. Check for open orders from previous day
- [ ] Confirm all yesterday's orders filled
- [ ] If any order is pending/partial -> resolve manually before placing new orders
- [ ] Record actual fill prices in position log (not the order price)

### 1E. End-of-day logging
- [ ] Log portfolio value (cash + market value of all positions at close)
- [ ] Log each position: Symbol | Qty | Entry price | Current price | Unrealised P&L | Days held
- [ ] Confirm no duplicate positions in the same stock

---

## 2. REBALANCE-DAY CHECKLIST
*Every 10th trading day from the last rebalance. Runs after Daily Checklist completes.*

### 2A. Pre-rebalance gate
- [ ] Confirm today is rebalance day (count 10 trading days from last rebalance date)
- [ ] Confirm regime is **Bull** or **Flat**. If **Bear** -> skip rebalance entirely. Log "Rebal skipped: Bear regime".
- [ ] Confirm no pending unresolved orders from Daily Checklist

### 2B. Data download
- [ ] Download closing prices for all 134 stocks from yesterday
- [ ] Download Nifty 50 closing price from yesterday
- [ ] Verify data: count stocks with valid closes. Expect 130-134.
- [ ] Flag any stock showing price = 0 or missing data. Exclude it from scoring for this rebalance only.

### 2C. Factor computation
**RS Factor (for each stock):**
- [ ] Compute 63-day return: (close_today / close_63days_ago) - 1
- [ ] Compute Nifty 63-day return: same calculation on Nifty index
- [ ] RS_raw = stock_return - nifty_return (excess return, in %)
- [ ] Run final_validation.py or deployment_verification.py to generate scores automatically

**EP Factor (for each stock):**
- [ ] Scan the last 63 trading days for each stock
- [ ] Flag any day where: daily_return > 2% AND volume > 1.5x (63-day average volume)
- [ ] EP_raw = maximum flagged daily return found (0 if none found)

**Ranking:**
- [ ] Percentile-rank RS_raw across all 134 stocks (rank 1 = lowest, 134 = highest, normalise to 0-100)
- [ ] Percentile-rank EP_raw across all 134 stocks (same method)
- [ ] Composite = 0.60 x RS_percentile + 0.40 x EP_percentile
- [ ] Sort descending. Top 10 = target portfolio for next 10 days.

### 2D. Determine trades
- [ ] List current holdings (from position log)
- [ ] EXITS: Stocks in current holdings but NOT in new top-10 -> sell at tomorrow's open
- [ ] ENTRIES: Stocks in new top-10 but NOT currently held -> buy at tomorrow's open
- [ ] HOLDS: Stocks in both current and new top-10 -> no action

### 2E. Position sizing
- [ ] Count number of new entries (N_new)
- [ ] Available cash = current_cash - buffer (keep Rs.25,000 cash reserve)
- [ ] Per-position allocation = min(available_cash / N_new, Rs.50,000)
- [ ] Shares to buy = floor(allocation / open_price_estimate)
  - Use yesterday's close as proxy for tomorrow's open
  - Adjust down by 0.5% for expected slippage
- [ ] Verify total outlay <= available cash

### 2F. Order placement (at 9:15 AM tomorrow)
- [ ] Place all EXIT orders first (market CNC sell)
- [ ] Wait 2 minutes
- [ ] Place all ENTRY orders (market CNC buy)
- [ ] Do NOT use limit orders -- slippage model assumes market fills
- [ ] Record all order IDs

### 2G. Post-fill update
- [ ] Record actual fill prices for all new entries
- [ ] Update position log with new cost basis (actual fill price, not order price)
- [ ] Set new SL levels = fill_price x 0.90 for each new entry
- [ ] Record new rebalance date (today = Day 0, next rebalance = Day 10)
- [ ] Log: Rebal # | Date | Stocks exited | Stocks entered | Stocks held | Cash before | Cash after

---

## 3. WEEKLY REVIEW CHECKLIST
*Every Friday evening. Takes ~15 minutes.*

### 3A. Performance snapshot
- [ ] Portfolio value at Friday close vs. last Friday close
- [ ] Week P&L (Rs. and %)
- [ ] Compare to Nifty 50 weekly return (benchmark)
- [ ] Running 4-week P&L
- [ ] Current drawdown from peak equity

### 3B. Position review
- [ ] List all open positions with: days held, entry price, current price, unrealised P&L %
- [ ] Flag any position with unrealised loss > 7% (approaching SL territory)
- [ ] Flag any position held > 25 trading days (unusually long hold -- check if SL should have triggered)
- [ ] Confirm SL levels are correct for each position (= entry x 0.90)

### 3C. Regime status
- [ ] Current regime: Bull / Flat / Bear
- [ ] How many days in current regime?
- [ ] If Bear: confirm fully in cash. If not, investigate.
- [ ] Distance to regime change: how far is Nifty from 200DMA?

### 3D. Data quality
- [ ] Did any stock fail to return data this week?
- [ ] Were any corporate actions (splits, bonuses, mergers) announced for held stocks?
  - If yes: adjust cost basis for splits/bonuses. Remove merged stocks from universe temporarily.
- [ ] Any exchange trading halts this week?

---

## 4. MONTHLY REVIEW CHECKLIST
*Last trading day of each month. Takes ~45 minutes.*

### 4A. Performance vs benchmark
- [ ] Monthly return (strategy vs Nifty)
- [ ] Rolling 3-month return (strategy vs Nifty)
- [ ] Rolling 6-month return (strategy vs Nifty)
- [ ] Year-to-date return (strategy vs Nifty)
- [ ] Annualised return since live start
- [ ] Sharpe ratio (rolling 3-month)
- [ ] Maximum drawdown since live start

### 4B. Trade quality analysis
- [ ] Total trades this month
- [ ] Win rate this month
- [ ] Average win % and average loss %
- [ ] Profit factor this month (gross wins / gross losses)
- [ ] Average hold period (days)
- [ ] SL-triggered exits: count and average loss
- [ ] Rebalance exits: count and average return

### 4C. Cost analysis
- [ ] Total brokerage paid
- [ ] Total STT paid
- [ ] Total slippage (estimated: compare order price to fill price)
- [ ] Total cost as % of capital
- [ ] Compare to modelled cost budget (0.4% round-trip per trade)

### 4D. Factor health check (observe only, do NOT change parameters)
- [ ] Run final_validation.py to generate current top-10 candidate list
- [ ] Observe sector composition of current top-10 vs universe
- [ ] Is Finance still the dominant sector in top-10? If a completely different sector dominates (>40%): note it, monitor 2 more months before concern.

### 4E. Red flag assessment
Raise a red flag if ANY of the following:
- [ ] 3-month profit factor < 0.90
- [ ] Strategy trailing Nifty by > 5% over rolling 3 months
- [ ] Drawdown > 15% from peak
- [ ] More than 3 SL-triggered exits in a single rebalance period

**If red flag raised:**
- Do NOT change strategy parameters.
- Run deployment_verification.py on the most recent 2 years of data.
- If fresh OOS PF > 1.10: strategy intact. Continue. Log the flag and resolution.
- If fresh OOS PF < 1.05: pause trading. Escalate to full review.

---

## 5. PAPER-TRADING WORKFLOW
*Run for 30 full trading days (3 rebalance cycles) before committing real capital.*

### Setup
- [ ] Open a dedicated spreadsheet: "MoneyBot Paper Trading Log"
- [ ] Set paper capital = Rs.5,00,000 (same as live)
- [ ] Set start date. Paper trading ends exactly 30 trading days later.
- [ ] Run final_validation.py on day 0. Record the top-10 candidate list and regime.

### Daily paper-trade execution
- [ ] Follow the Daily Checklist exactly as written
- [ ] Record what orders you would place and at what price
- [ ] At 9:15 AM, note the actual market open price for each stock
- [ ] Record the fill price as: yesterday close x 1.002 for buys, x 0.998 for sells (simulates 0.2% slippage)
- [ ] Track paper P&L daily

### Slippage measurement
- [ ] For each rebalance, record the actual 9:15 AM opening price for each stock traded
- [ ] Compare actual open to your simulated fill
- [ ] Track: actual slippage = abs(actual_open - prev_close) / prev_close
- [ ] After 3 rebalances, compute average actual slippage
- [ ] If average slippage > 0.4%: update the cost model before deploying real capital

### Paper-trading pass criteria
After 30 days, confirm all of the following:
- [ ] Workflow executable in under 10 minutes daily
- [ ] No data availability issues
- [ ] Actual slippage below 0.4% per trade on average
- [ ] Regime correctly classified on every day
- [ ] SL levels correctly tracked for every position

If all pass -> proceed to small-capital deployment.
If any fail -> fix the process issue and run another 30-day paper cycle.

---

## 6. SMALL-CAPITAL DEPLOYMENT WORKFLOW

### Phase 1: Minimum deployment (Day 1-60)
**Capital: Rs.1,00,000. Per position: Rs.10,000. Top-5 stocks only.**

NOTE: At Rs.10,000 per position, brokerage = Rs.20 = 0.2% of trade. This doubles brokerage drag vs the validated model. Effective cost per round-trip rises to ~0.8% all-in. The strategy edge breaks at 0.6% cost. Phase 1 is validation of execution, not profit-seeking. Minimum meaningful deployment for profit is Rs.2,00,000.

- [ ] Confirm regime is Bull or Flat before starting
- [ ] On first rebalance day: buy top-5 stocks by composite score only
- [ ] Follow Daily, Rebalance, Weekly checklists exactly
- [ ] Track actual fill slippage vs model for every trade

Phase 1 exit criteria (all must pass):
- [ ] 6 completed rebalances (60 trading days)
- [ ] No execution failures or data errors
- [ ] Actual slippage confirmed below 0.4% per trade on average

### Phase 2: Half capital (Day 61-120)
**Capital: Rs.2,50,000. Per position: Rs.25,000. Top-10 stocks.**

- [ ] Scale up on next rebalance day after Phase 1 pass
- [ ] Same workflow -- only size changes
- [ ] 3-month rolling PF must be > 0.90 to proceed to Phase 3

### Phase 3: Full capital (Day 121+)
**Capital: Rs.5,00,000. Per position: Rs.50,000. Top-10 stocks.**

- [ ] Scale on next rebalance day after Phase 2 pass
- [ ] Monthly review becomes mandatory

### Capital scaling rules
- Never scale up during a drawdown period (drawdown > 10% from local peak)
- Never scale up if in Bear regime
- Never scale up following an unresolved red flag
- Only scale on a rebalance day, never mid-period

---

## 7. FAILURE SCENARIOS AND RECOVERY PROCEDURES

### F1: Data download failure
Symptom: yfinance returns no data or partial data for many stocks.
Action:
1. Retry download after 30 minutes.
2. If still failing: skip today's rebalance if it is a rebalance day. Do not trade on bad data.
3. Hold all current positions. Apply SL check manually using yesterday's confirmed closes.
4. Retry next trading day. Log the skip with reason.

### F2: Broker order placement failure
Symptom: Orders not appearing in broker order book, or connection timeout.
Action:
1. Do NOT retry automatically. Log in to Zerodha Kite manually.
2. Verify order status in the broker interface.
3. If order was not placed: place manually via Kite app before 9:30 AM.
4. If order was placed but duplicate: cancel duplicates immediately.
5. Record all manual interventions with timestamp and reason.
6. Do not continue algorithmic trading until connection is confirmed stable.

### F3: Gap-down open past stop-loss
Symptom: Stock opens significantly below SL level (e.g., SL=180, opens at 155).
Action:
1. Accept the fill at whatever the market open price is. Do NOT hold hoping for recovery.
2. Record actual fill vs SL level as "gap-down slippage" separately.
3. Do not adjust the SL model based on one event. If gap-downs occur more than 3 times in 60 days, revisit slippage assumption.

### F4: Regime misclassification
Symptom: Realised you classified regime incorrectly on a previous day.
Action:
- If Bear classified as Bull (invested when should be in cash): exit all positions at next open. Do not attempt to recover missed cash days.
- If Bull classified as Bear (in cash when should be invested): wait until next scheduled rebalance to re-enter. Do not chase.
- Log the error and root cause.

### F5: Corporate action on held stock
For splits/bonus:
1. Adjust cost basis: new_cost_basis = old_cost_basis / split_ratio
2. Adjust quantity: new_qty = old_qty x split_ratio
3. Adjust SL level = new_cost_basis x 0.90. No trading action required.

For merger/delisting:
1. Exit the position at market at the next open after announcement.
2. Remove the stock from the STOCKS universe list.

For rights issue:
1. Do not subscribe. Treat as a non-event. SL check will handle any price impact naturally.

### F6: Portfolio drawdown > 20% from peak
Action:
1. Exit all positions at next open. No exceptions.
2. Stop all trading for 30 calendar days.
3. During the 30-day pause: run deployment_verification.py on the most recent data.
4. If fresh OOS PF > 1.10: resume after 30 days.
5. If fresh OOS PF < 1.05: do not resume without a full re-validation study.
6. Do not shorten the 30-day pause even if the market recovers.

### F7: Three consecutive losing rebalances
Action:
1. Do NOT stop trading. Three losing rebalances is within normal variance for this strategy.
2. Run a mini health check: compute rolling 30-day PF from trade log.
3. If rolling PF > 0.85: continue normally. Log the flag.
4. If rolling PF < 0.85: raise a red flag. Run deployment_verification.py.
5. Strategy parameters must not change based solely on a losing streak.

### F8: Exchange/market-wide circuit breaker
Action:
1. Do not place any orders during a market-wide halt.
2. Wait for normal trading to resume.
3. On the next trading day: re-run Daily Checklist from the beginning.
4. SL and regime checks take priority.

---

## 8. REQUIRED LOGS AND METRICS

### Log 1: Daily Operations Log
One row per trading day.

Field              | Description
Date               | Trading date
Nifty Close        | Previous close used for regime calculation
50DMA              | Current value
200DMA             | Current value
Regime             | Bull / Flat / Bear
Portfolio Value    | Cash + mark-to-market of all positions
Cash               | Free cash
Invested           | Total in positions
SL Exits Today     | Symbols exited on SL (empty if none)
Regime Exits Today | Y/N -- did regime change force liquidation
Notes              | Any anomalies, manual interventions

### Log 2: Position Log
Current state of all open positions. Updated daily.

Field           | Description
Symbol          | Stock ticker
Entry Date      | Date bought
Entry Price     | Actual fill price
Qty             | Number of shares
SL Level        | Entry x 0.90 (fixed at entry, never trail)
Current Price   | Latest close
Unrealised P&L  | (Current - Entry) x Qty
Unrealised P&L% | (Current / Entry - 1) x 100
Days Held       | Trading days since entry

### Log 3: Trade Log
One row per completed trade (exit only).

Field        | Description
Trade #      | Sequential ID
Symbol       | Stock ticker
Entry Date   | Date bought
Exit Date    | Date sold
Entry Price  | Actual buy fill
Exit Price   | Actual sell fill
Qty          | Shares
Gross P&L    | (Exit - Entry) x Qty
Costs        | Brokerage + STT + Exchange (both legs)
Net P&L      | Gross P&L - Costs
Return %     | (Exit / Entry - 1) x 100
Exit Reason  | SL / Rebalance / Regime / EoP
Hold Days    | Trading days

### Log 4: Rebalance Log
One row per rebalance event.

Field                 | Description
Rebal #               | Sequential ID
Date                  | Rebalance day
Regime                | Regime at rebalance
Top-10 Selected       | Comma-separated symbols and composite scores
Exits                 | Symbols sold
Entries               | Symbols bought
Holds                 | Unchanged positions
Cash Before           |
Cash After            |
Skipped               | Y/N (Bear regime = skipped)

### Log 5: Monthly Performance Metrics

Metric                    | Target         | Red Flag Level
Monthly Return            | > Nifty        | Trailing Nifty >3% for 3 consecutive months
Rolling 3M PF             | > 1.00         | < 0.90
Rolling 3M Sharpe         | > 0.20         | < 0.00
Max Drawdown              | < 15%          | > 20% (auto-shutdown)
Win Rate                  | ~46%           | < 35% for 2 months
Avg Win / Avg Loss        | > 1.0          | < 0.80
Monthly Costs (% capital) | < 0.5%         | > 1.0%
Slippage per trade        | < 0.3%         | > 0.5% (review cost model)

### Log 6: Slippage Tracker
One row per buy or sell order.

Field       | Description
Date        | Order date
Symbol      |
Side        | Buy / Sell
Prev Close  | Yesterday's close
Actual Fill | Actual execution price
Slippage %  | abs(Fill - Prev Close) / Prev Close x 100
Modelled    | 0.20%
Excess      | Actual - Modelled

Target: Average actual slippage <= 0.25%. Review cost model if average exceeds 0.40% over 60 trades.

---

## QUICK REFERENCE CARD

STRATEGY (FROZEN)
  Weights     : RS=60%, EP=40%
  Universe    : 134 NSE stocks
  Portfolio   : Top-10 equal weight
  Rebalance   : Every 10 trading days
  Stop-loss   : 10% below entry price (check each morning)
  Regime      : Bull+Flat=trade, Bear=100% cash

REGIME RULES
  Bull  : Nifty > 200DMA AND 50DMA > 200DMA  -> Full portfolio
  Flat  : Nifty > 200DMA AND 50DMA <= 200DMA -> Full portfolio
  Bear  : Nifty < 200DMA                      -> 100% cash

MORNING ROUTINE (before 9:10 AM)
  1. Nifty close -> classify regime
  2. If Bear: exit all -> STOP
  3. SL check: close <= entry x 0.90 -> exit at open
  4. Confirm all orders filled from prior day
  5. Log portfolio value

REBALANCE DAY (every 10th trading day)
  1. Regime = Bull/Flat? If not -> skip
  2. Download 134 stock closes
  3. Compute RS + EP -> rank -> top 10
  4. Exit stocks NOT in top 10
  5. Enter stocks IN top 10 not held
  6. All orders at 9:15 AM market open (exits first, entries 2 min later)

EMERGENCY SHUTDOWN
  Drawdown > 20% from peak -> EXIT ALL -> 30-day pause
  3 losing rebalances -> health check only, do NOT stop automatically
  Data failure -> skip rebalance, hold positions, retry next day

CURRENT STATE (2026-06-14)
  Regime      : BEAR
  Action      : HOLD CASH. Do not enter.
  Re-entry    : When Nifty closes above 200DMA (was 24,921 on Jun 12)
  Candidates  : Run final_validation.py on first Bull/Flat day to get fresh list

VALIDATED STRATEGY PERFORMANCE (OOS, Policy C)
  Profit Factor : 1.349
  CAGR          : +5.7%
  Sharpe        : 0.507
  Max Drawdown  : 13.8%
  Nifty CAGR    : +0.5%
  Alpha         : +5.2% / year

---
End of Live Operations Manual. Version 1.0. Strategy parameters frozen 2026-06-14.
Next scheduled review: 90 days after live start, or when a red flag is raised.
