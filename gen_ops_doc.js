const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, BorderStyle, WidthType,
  ShadingType, HeadingLevel, PageNumber
} = require('docx');
const fs = require('fs');

const CONTENT_W = 9360;
const COL1 = 2880, COL2 = 3240, COL3 = 3240;
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const hdrBorder = { style: BorderStyle.SINGLE, size: 1, color: "999999" };
const hdrBorders = { top: hdrBorder, bottom: hdrBorder, left: hdrBorder, right: hdrBorder };

function cell(text, opts = {}) {
  return new TableCell({
    borders: opts.header ? hdrBorders : borders,
    width: { size: opts.width || 4680, type: WidthType.DXA },
    shading: { fill: opts.fill || (opts.header ? "2E4057" : "FFFFFF"), type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({
        text,
        bold: opts.bold || opts.header || false,
        color: opts.header ? "FFFFFF" : "000000",
        font: "Arial",
        size: 20
      })]
    })]
  });
}

function twoColRow(f, d, fw = 3000, dw = 6360) {
  return new TableRow({ children: [cell(f, { width: fw }), cell(d, { width: dw })] });
}

function threeColRow(a, b, c, aw = COL1, bw = COL2, cw = COL3, fill = "FFFFFF") {
  return new TableRow({ children: [cell(a, { width: aw, fill }), cell(b, { width: bw, fill }), cell(c, { width: cw, fill })] });
}

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text, font: "Arial", size: 32, bold: true, color: "2E4057" })] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text, font: "Arial", size: 26, bold: true, color: "2E4057" })] });
}
function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text, font: "Arial", size: 22, bold: true, color: "4A6FA5" })] });
}
function p(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Arial", size: 20, bold: opts.bold || false, italics: opts.italic || false, color: opts.color || "000000" })]
  });
}
function bullet(runs) {
  if (typeof runs === 'string') runs = [{ text: runs }];
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: runs.map(r => new TextRun({ font: "Arial", size: 20, ...r }))
  });
}
function numbered(runs, ref = "numbers1") {
  if (typeof runs === 'string') runs = [{ text: runs }];
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    children: runs.map(r => new TextRun({ font: "Arial", size: 20, ...r }))
  });
}
function checkbox(text, bold = false) {
  const parts = [];
  if (bold) {
    const match = text.match(/^(.*?)(\*\*(.+?)\*\*)(.*?)$/);
    if (match) {
      if (match[1]) parts.push(new TextRun({ text: match[1], font: "Arial", size: 20 }));
      parts.push(new TextRun({ text: match[3], font: "Arial", size: 20, bold: true }));
      if (match[4]) parts.push(new TextRun({ text: match[4], font: "Arial", size: 20 }));
    } else {
      parts.push(new TextRun({ text, font: "Arial", size: 20 }));
    }
  } else {
    parts.push(new TextRun({ text, font: "Arial", size: 20 }));
  }
  return new Paragraph({
    numbering: { reference: "checkboxes", level: 0 },
    children: parts
  });
}
function mono(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Courier New", size: 18, color: "333333" })],
    indent: { left: 720 }
  });
}
function blank() { return new Paragraph({ children: [new TextRun("")] }); }

function twoColTable(rows, col1w = 3000, col2w = 6360) {
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [col1w, col2w],
    rows
  });
}
function threeColTable(rows, aw = COL1, bw = COL2, cw = COL3) {
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [aw, bw, cw],
    rows
  });
}

function twoColHeader(a, b, aw = 3000, bw = 6360) {
  return new TableRow({ children: [cell(a, { header: true, width: aw }), cell(b, { header: true, width: bw })] });
}
function threeColHeader(a, b, c, aw = COL1, bw = COL2, cw = COL3) {
  return new TableRow({ children: [cell(a, { header: true, width: aw }), cell(b, { header: true, width: bw }), cell(c, { header: true, width: cw })] });
}

function logTable(headers, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  const hRow = new TableRow({ children: headers.map((h, i) => cell(h, { header: true, width: widths[i] })) });
  const dRows = rows.map(r => new TableRow({ children: r.map((v, i) => cell(v, { width: widths[i] })) }));
  return new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: widths, rows: [hRow, ...dRows] });
}

const doc = new Document({
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers1", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers2", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers3", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers4", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers5", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers6", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers7", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers8", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers9", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers10", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "checkboxes", levels: [{ level: 0, format: LevelFormat.BULLET, text: "□", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "2E4057" },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "2E4057" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Arial", color: "4A6FA5" },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
    ]
  },
  sections: [{
    properties: {
      page: { size: { width: 12240, height: 15840 }, margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 } }
    },
    headers: {
      default: new Header({ children: [
        new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E4057", space: 1 } },
          children: [new TextRun({ text: "MoneyBot Live Operations Manual  |  RS=60% / EP=40%  |  STRATEGY FROZEN", font: "Arial", size: 18, color: "666666" })]
        })
      ]})
    },
    footers: {
      default: new Footer({ children: [
        new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 } },
          children: [
            new TextRun({ text: "Confidential  |  Page ", font: "Arial", size: 16, color: "888888" }),
            new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "888888" }),
            new TextRun({ text: " of ", font: "Arial", size: 16, color: "888888" }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], font: "Arial", size: 16, color: "888888" }),
          ]
        })
      ]})
    },
    children: [
      // ── COVER ──
      new Paragraph({ spacing: { before: 1440, after: 240 }, children: [new TextRun({ text: "MoneyBot", font: "Arial", size: 64, bold: true, color: "2E4057" })] }),
      new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "Live Operations Manual", font: "Arial", size: 40, color: "4A6FA5" })] }),
      new Paragraph({ spacing: { after: 480 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E4057", space: 1 } }, children: [new TextRun({ text: "RS=60% / EP=40%  |  Policy C  |  Top-10  |  Rebal 10d  |  SL 10%", font: "Arial", size: 24, color: "666666" })] }),
      blank(),
      new Paragraph({ children: [new TextRun({ text: "STATUS: STRATEGY FROZEN", font: "Arial", size: 28, bold: true, color: "C0392B" })] }),
      new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "Do not modify any parameter without a full re-validation cycle.", font: "Arial", size: 22, color: "555555" })] }),
      new Paragraph({ children: [new TextRun({ text: "Generated: 2026-06-14", font: "Arial", size: 20, color: "888888" })] }),
      blank(),

      // Status box
      new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        columnWidths: [3120, 6240],
        rows: [
          new TableRow({ children: [
            cell("CURRENT REGIME", { header: true, width: 3120 }),
            new TableCell({ borders, width: { size: 6240, type: WidthType.DXA }, shading: { fill: "FFF3CD", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "BEAR  —  Nifty 23,623 < 200DMA 24,921  |  HOLD CASH. Do not deploy.", font: "Arial", size: 20, bold: true, color: "856404" })] })] })
          ]}),
          new TableRow({ children: [
            cell("RE-ENTRY TRIGGER", { width: 3120 }),
            cell("Nifty must close above 24,921 (200DMA). Run final_validation.py on that day for fresh candidate list.", { width: 6240 })
          ]}),
          new TableRow({ children: [
            cell("VALIDATED OOS PERFORMANCE", { width: 3120 }),
            cell("PF 1.349  |  CAGR +5.7%  |  Sharpe 0.507  |  MaxDD 13.8%  |  Alpha +5.2%/yr vs Nifty", { width: 6240 })
          ]}),
        ]
      }),

      // PAGE BREAK -> Section 1
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),

      // ── 1. DAILY CHECKLIST ──
      h1("1. Daily Checklist"),
      p("Every trading day. Complete before 9:10 AM IST. Takes ~5 minutes.", { italic: true }),
      blank(),

      h3("1A. Regime Check (mandatory)"),
      checkbox("Download yesterday's Nifty 50 closing price"),
      checkbox("Recompute 50-DMA: rolling average of last 50 closes"),
      checkbox("Recompute 200-DMA: rolling average of last 200 closes"),
      checkbox("Classify regime:"),
      p("        Bull = Nifty > 200DMA AND 50DMA > 200DMA", { bold: false }),
      p("        Flat = Nifty > 200DMA AND 50DMA <= 200DMA", { bold: false }),
      p("        Bear = Nifty < 200DMA", { bold: false }),
      checkbox("Log: Date | Nifty close | 50DMA | 200DMA | Regime"),
      blank(),

      h3("1B. Bear Regime Actions"),
      checkbox("If Bear AND positions are open: place market sell orders for ALL positions at 9:15 AM open"),
      checkbox("If Bear AND no positions: do nothing, hold cash, skip to step 1E"),
      checkbox("Record regime exit: date, price, reason = Regime:Bear"),
      blank(),

      h3("1C. Stop-Loss Check (Bull/Flat only)"),
      p("For each open position:"),
      checkbox("Retrieve entry price (cost basis recorded at fill)"),
      checkbox("Compute SL level = entry_price x 0.90"),
      checkbox("Retrieve yesterday's closing price for each position"),
      checkbox("If close <= SL level: mark for exit at today's 9:15 AM open"),
      checkbox("Place market sell order for any SL-triggered positions"),
      checkbox("Record exit in trade log: Date | Symbol | Entry | Exit | Reason=SL | P&L"),
      blank(),

      h3("1D. Order Confirmation"),
      checkbox("Confirm all yesterday's orders filled"),
      checkbox("If any order is pending or partial: resolve manually before placing new orders"),
      checkbox("Record actual fill prices in position log (not the order price)"),
      blank(),

      h3("1E. End-of-Day Logging"),
      checkbox("Log portfolio value (cash + market value of all positions at close)"),
      checkbox("Log each position: Symbol | Qty | Entry price | Current price | Unrealised P&L | Days held"),
      checkbox("Confirm no duplicate positions in the same stock"),
      blank(),

      h3("Daily Log Format"),
      twoColTable([
        twoColHeader("Field", "Description", 3000, 6360),
        twoColRow("Date", "Trading date"),
        twoColRow("Nifty Close", "Previous close used for regime calculation"),
        twoColRow("50DMA", "Current value"),
        twoColRow("200DMA", "Current value"),
        twoColRow("Regime", "Bull / Flat / Bear"),
        twoColRow("Portfolio Value", "Cash + mark-to-market of all positions"),
        twoColRow("Cash", "Free cash"),
        twoColRow("SL Exits Today", "Symbols exited on SL (empty if none)"),
        twoColRow("Regime Exits", "Y/N — did regime change force liquidation today"),
        twoColRow("Notes", "Any anomalies, manual interventions"),
      ], 3000, 6360),

      // ── 2. REBALANCE-DAY ──
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),
      h1("2. Rebalance-Day Checklist"),
      p("Every 10th trading day from the last rebalance. Run after Daily Checklist completes.", { italic: true }),
      blank(),

      h3("2A. Pre-Rebalance Gate"),
      checkbox("Confirm today is rebalance day (count 10 trading days from last rebalance)"),
      checkbox("Confirm regime is Bull or Flat — if Bear, skip entirely. Log: Rebal skipped: Bear regime."),
      checkbox("Confirm no pending unresolved orders from Daily Checklist"),
      blank(),

      h3("2B. Data Download"),
      checkbox("Download closing prices for all 134 stocks from yesterday"),
      checkbox("Download Nifty 50 closing price from yesterday"),
      checkbox("Verify data: count stocks with valid closes. Expect 130-134."),
      checkbox("Flag any stock with price = 0 or missing. Exclude from scoring this rebalance only."),
      blank(),

      h3("2C. Factor Computation"),
      p("RS Factor (for each stock):", { bold: true }),
      checkbox("63-day return: (close_today / close_63days_ago) - 1"),
      checkbox("Nifty 63-day return: same calculation on Nifty index"),
      checkbox("RS_raw = stock_return - nifty_return (excess return, in %)"),
      checkbox("Run final_validation.py or deployment_verification.py to generate scores automatically"),
      blank(),
      p("EP Factor (for each stock):", { bold: true }),
      checkbox("Scan the last 63 trading days for each stock"),
      checkbox("Flag any day where: daily_return > 2% AND volume > 1.5x (63-day average volume)"),
      checkbox("EP_raw = maximum flagged daily return found (0 if none found)"),
      blank(),
      p("Ranking:", { bold: true }),
      checkbox("Percentile-rank RS_raw across all 134 stocks (0-100 scale)"),
      checkbox("Percentile-rank EP_raw across all 134 stocks (same method)"),
      checkbox("Composite = 0.60 x RS_percentile + 0.40 x EP_percentile"),
      checkbox("Sort descending. Top 10 = target portfolio for next 10 days."),
      blank(),

      h3("2D. Determine Trades"),
      checkbox("EXITS: Stocks in current holdings but NOT in new top-10 → sell at tomorrow's open"),
      checkbox("ENTRIES: Stocks in new top-10 but NOT currently held → buy at tomorrow's open"),
      checkbox("HOLDS: Stocks in both current and new top-10 → no action"),
      blank(),

      h3("2E. Position Sizing"),
      checkbox("Available cash = current_cash - Rs.25,000 buffer (keep as reserve)"),
      checkbox("Per-position allocation = min(available_cash / N_new entries, Rs.50,000)"),
      checkbox("Shares to buy = floor(allocation / open_price_estimate)"),
      p("        Use yesterday's close as proxy for tomorrow's open, adjusted down 0.5% for slippage"),
      checkbox("Verify total outlay <= available cash"),
      blank(),

      h3("2F. Order Placement (9:15 AM tomorrow)"),
      checkbox("Place all EXIT orders first (market CNC sell)"),
      checkbox("Wait 2 minutes"),
      checkbox("Place all ENTRY orders (market CNC buy)"),
      checkbox("Do NOT use limit orders — slippage model assumes market fills"),
      checkbox("Record all order IDs"),
      blank(),

      h3("2G. Post-Fill Update"),
      checkbox("Record actual fill prices for all new entries"),
      checkbox("Update position log with new cost basis (actual fill price, not order price)"),
      checkbox("Set new SL levels = fill_price x 0.90 for each new entry"),
      checkbox("Record new rebalance date (today = Day 0, next rebalance = Day 10)"),
      checkbox("Log: Rebal # | Date | Stocks exited | Stocks entered | Stocks held | Cash before | Cash after"),

      // ── 3. WEEKLY REVIEW ──
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),
      h1("3. Weekly Review Checklist"),
      p("Every Friday evening. Takes ~15 minutes.", { italic: true }),
      blank(),

      h3("3A. Performance Snapshot"),
      checkbox("Portfolio value at Friday close vs. last Friday close"),
      checkbox("Week P&L (Rs. and %)"),
      checkbox("Nifty 50 weekly return (benchmark)"),
      checkbox("Running 4-week P&L"),
      checkbox("Current drawdown from peak equity"),
      blank(),

      h3("3B. Position Review"),
      checkbox("List all open positions: days held, entry price, current price, unrealised P&L %"),
      checkbox("Flag any position with unrealised loss > 7% (approaching SL territory — monitor closely)"),
      checkbox("Flag any position held > 25 trading days (check if SL should have triggered)"),
      checkbox("Confirm SL levels are correct for each position (= entry x 0.90)"),
      blank(),

      h3("3C. Regime Status"),
      checkbox("Current regime: Bull / Flat / Bear"),
      checkbox("How many days in current regime?"),
      checkbox("If Bear: confirm fully in cash. If not, investigate immediately."),
      checkbox("Distance to regime change: how far is Nifty from 200DMA?"),
      blank(),

      h3("3D. Data Quality"),
      checkbox("Did any stock fail to return data this week?"),
      checkbox("Were any corporate actions (splits, bonuses, mergers) announced for held stocks?"),
      p("        If yes: adjust cost basis for splits/bonuses. Remove merged stocks from universe."),
      checkbox("Any exchange trading halts this week?"),

      // ── 4. MONTHLY REVIEW ──
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),
      h1("4. Monthly Review Checklist"),
      p("Last trading day of each month. Takes ~45 minutes.", { italic: true }),
      blank(),

      h3("4A. Performance vs Benchmark"),
      checkbox("Monthly return: strategy vs Nifty"),
      checkbox("Rolling 3-month return: strategy vs Nifty"),
      checkbox("Rolling 6-month return: strategy vs Nifty"),
      checkbox("Year-to-date return: strategy vs Nifty"),
      checkbox("Annualised return since live start"),
      checkbox("Sharpe ratio (rolling 3-month)"),
      checkbox("Maximum drawdown since live start"),
      blank(),

      h3("4B. Trade Quality Analysis"),
      checkbox("Total trades this month"),
      checkbox("Win rate this month"),
      checkbox("Average win % and average loss %"),
      checkbox("Profit factor this month (gross wins / gross losses)"),
      checkbox("Average hold period (days)"),
      checkbox("SL-triggered exits: count and average loss"),
      checkbox("Rebalance exits: count and average return"),
      blank(),

      h3("4C. Cost Analysis"),
      checkbox("Total brokerage paid"),
      checkbox("Total STT paid"),
      checkbox("Total slippage (compare order price to fill price)"),
      checkbox("Total cost as % of capital — compare to budget of 0.4% round-trip per trade"),
      blank(),

      h3("4D. Factor Health Check (observe only — do NOT change parameters)"),
      checkbox("Run final_validation.py to generate current top-10 candidate list"),
      checkbox("Observe sector composition of current top-10 vs universe"),
      checkbox("Is Finance still the dominant sector in top-10?"),
      p("        If yes: expected, no action.  If a completely different sector dominates (>40%): note and monitor 2 more months."),
      blank(),

      h3("4E. Red Flag Assessment"),
      p("Raise a red flag if ANY of the following:", { bold: true }),
      checkbox("3-month profit factor < 0.90"),
      checkbox("Strategy trailing Nifty by > 5% over rolling 3 months"),
      checkbox("Drawdown > 15% from peak"),
      checkbox("More than 3 SL-triggered exits in a single rebalance period"),
      blank(),
      p("If red flag raised:", { bold: true }),
      bullet("Do NOT change strategy parameters."),
      bullet("Run deployment_verification.py on the most recent 2 years of data."),
      bullet("Fresh OOS PF > 1.10: strategy intact. Continue. Log the flag and resolution."),
      bullet("Fresh OOS PF < 1.05: pause trading. Escalate to full review."),
      blank(),

      h3("Monthly Performance Metrics"),
      threeColTable([
        threeColHeader("Metric", "Target", "Red Flag Level"),
        threeColRow("Monthly Return", "> Nifty", "Trailing Nifty >3% for 3 consecutive months"),
        threeColRow("Rolling 3M PF", "> 1.00", "< 0.90"),
        threeColRow("Rolling 3M Sharpe", "> 0.20", "< 0.00"),
        threeColRow("Max Drawdown", "< 15%", "> 20% (auto-shutdown)"),
        threeColRow("Win Rate", "~46%", "< 35% for 2 months"),
        threeColRow("Avg Win / Avg Loss", "> 1.0", "< 0.80"),
        threeColRow("Monthly Costs (% capital)", "< 0.5%", "> 1.0%"),
        threeColRow("Slippage per trade", "< 0.3%", "> 0.5% (review cost model)"),
      ]),

      // ── 5. PAPER TRADING ──
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),
      h1("5. Paper-Trading Workflow"),
      p("Run for 30 full trading days (3 rebalance cycles) before committing real capital.", { italic: true }),
      blank(),

      h3("Setup"),
      checkbox("Open a dedicated spreadsheet: MoneyBot Paper Trading Log"),
      checkbox("Set paper capital = Rs.5,00,000 (same as live)"),
      checkbox("Set start date. Paper trading ends exactly 30 trading days later."),
      checkbox("Run final_validation.py on Day 0. Record the top-10 candidate list and today's regime."),
      blank(),

      h3("Daily Paper-Trade Execution"),
      checkbox("Follow the Daily Checklist exactly as written"),
      checkbox("Record what orders you would place and at what price"),
      checkbox("At 9:15 AM, note the actual market open price for each stock"),
      checkbox("Record fill price: yesterday's close x 1.002 for buys, x 0.998 for sells (simulates 0.2% slippage)"),
      checkbox("Track paper P&L daily"),
      blank(),

      h3("Slippage Measurement"),
      checkbox("For each rebalance, record the actual 9:15 AM opening price for each stock traded"),
      checkbox("Compare actual open to your simulated fill"),
      checkbox("Track: actual slippage = abs(actual_open - prev_close) / prev_close"),
      checkbox("After 3 rebalances, compute average actual slippage"),
      checkbox("If average slippage > 0.4%: update the cost model before deploying real capital"),
      blank(),

      h3("Paper-Trading Pass Criteria"),
      p("After 30 days, confirm all of the following before going live:"),
      checkbox("Workflow executable in under 10 minutes daily"),
      checkbox("No data availability issues"),
      checkbox("Actual slippage below 0.4% per trade on average"),
      checkbox("Regime correctly classified on every day"),
      checkbox("SL levels correctly tracked for every position"),
      blank(),
      p("If all pass: proceed to small-capital deployment."),
      p("If any fail: fix the process issue and run another 30-day paper cycle."),

      // ── 6. SMALL CAPITAL ──
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),
      h1("6. Small-Capital Deployment Workflow"),
      blank(),

      new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        columnWidths: [2340, 2340, 2340, 2340],
        rows: [
          new TableRow({ children: [
            cell("Phase", { header: true, width: 2340 }),
            cell("Capital", { header: true, width: 2340 }),
            cell("Per Position", { header: true, width: 2340 }),
            cell("Stocks", { header: true, width: 2340 }),
          ]}),
          new TableRow({ children: [
            cell("Phase 1 (Day 1-60)", { width: 2340 }),
            cell("Rs.1,00,000", { width: 2340 }),
            cell("Rs.10,000", { width: 2340 }),
            cell("Top-5 only", { width: 2340 }),
          ]}),
          new TableRow({ children: [
            cell("Phase 2 (Day 61-120)", { width: 2340 }),
            cell("Rs.2,50,000", { width: 2340 }),
            cell("Rs.25,000", { width: 2340 }),
            cell("Top-10", { width: 2340 }),
          ]}),
          new TableRow({ children: [
            cell("Phase 3 (Day 121+)", { width: 2340 }),
            cell("Rs.5,00,000", { width: 2340 }),
            cell("Rs.50,000", { width: 2340 }),
            cell("Top-10 (full strategy)", { width: 2340 }),
          ]}),
        ]
      }),
      blank(),
      new Paragraph({ children: [new TextRun({ text: "IMPORTANT: ", font: "Arial", size: 20, bold: true, color: "C0392B" }), new TextRun({ text: "At Rs.1,00,000, brokerage = Rs.20 per trade = 0.2% of position. This doubles brokerage drag. Effective round-trip cost rises to ~0.8%. The strategy edge breaks at 0.6%. Phase 1 is execution validation only, not profit-seeking. Minimum meaningful deployment is Rs.2,00,000.", font: "Arial", size: 20 })] }),
      blank(),

      h3("Phase 1 Exit Criteria (all must pass)"),
      checkbox("6 completed rebalances (60 trading days)"),
      checkbox("No execution failures or data errors"),
      checkbox("Actual slippage confirmed below 0.4% per trade on average"),
      checkbox("Portfolio P&L directionally consistent with backtest"),
      blank(),

      h3("Capital Scaling Rules"),
      bullet("Never scale up during a drawdown period (drawdown > 10% from local peak)"),
      bullet("Never scale up if in Bear regime"),
      bullet("Never scale up following an unresolved red flag"),
      bullet("Only scale on a rebalance day, never mid-period"),

      // ── 7. FAILURE SCENARIOS ──
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),
      h1("7. Failure Scenarios and Recovery Procedures"),
      blank(),

      h3("F1: Data Download Failure"),
      p("Symptom: yfinance returns no data or partial data for many stocks.  Severity: Medium."),
      numbered("Retry download after 30 minutes.", "numbers1"),
      numbered("If still failing: skip today's rebalance. Do not trade on bad data.", "numbers1"),
      numbered("Hold all current positions. Apply SL check manually using yesterday's confirmed closes.", "numbers1"),
      numbered("Retry next trading day. Log the skip with reason.", "numbers1"),
      blank(),

      h3("F2: Broker Order Placement Failure"),
      p("Symptom: Orders not appearing in broker order book, or connection timeout.  Severity: High."),
      numbered("Do NOT retry automatically. Log in to Zerodha Kite manually.", "numbers2"),
      numbered("Verify order status in the broker interface.", "numbers2"),
      numbered("If not placed: place manually via Kite app before 9:30 AM.", "numbers2"),
      numbered("If duplicate: cancel duplicates immediately.", "numbers2"),
      numbered("Record all manual interventions with timestamp.", "numbers2"),
      numbered("Do not resume algorithmic trading until connection is confirmed stable.", "numbers2"),
      blank(),

      h3("F3: Gap-Down Open Past Stop-Loss"),
      p("Symptom: Stock opens significantly below SL level (e.g., SL=180, opens at 155).  Severity: Medium."),
      numbered("Accept the fill at whatever the market open price is. Do NOT hold hoping for recovery.", "numbers3"),
      numbered("Record actual fill vs SL level as gap-down slippage separately.", "numbers3"),
      numbered("If gap-downs occur more than 3 times in 60 days: revisit slippage assumption in a re-validation run.", "numbers3"),
      blank(),

      h3("F4: Regime Misclassification"),
      p("Symptom: Realised you classified regime incorrectly on a previous day."),
      p("If Bear classified as Bull (invested when should be in cash):", { bold: true }),
      bullet("Exit all positions at next open. This takes priority over rebalance logic."),
      bullet("Do not attempt to make back the days in Bear regime."),
      p("If Bull classified as Bear (in cash when should be invested):", { bold: true }),
      bullet("Wait until next scheduled rebalance to re-enter. Do not chase."),
      bullet("Log the error and root cause."),
      blank(),

      h3("F5: Corporate Action on Held Stock"),
      p("For splits / bonus issues:", { bold: true }),
      bullet("Adjust cost basis: new_cost_basis = old_cost_basis / split_ratio"),
      bullet("Adjust quantity: new_qty = old_qty x split_ratio"),
      bullet("Adjust SL level = new_cost_basis x 0.90. No trading action required."),
      p("For merger / delisting:", { bold: true }),
      bullet("Exit position at market at the next open after announcement."),
      bullet("Remove the stock from the STOCKS universe list."),
      p("For rights issue:", { bold: true }),
      bullet("Do not subscribe. Treat as a non-event. SL check will handle any price impact."),
      blank(),

      h3("F6: Portfolio Drawdown > 20% from Peak  [CRITICAL]"),
      new Paragraph({ children: [new TextRun({ text: "Trigger: Peak portfolio value declines by more than 20%.  Severity: CRITICAL.", font: "Arial", size: 20, bold: true, color: "C0392B" })] }),
      numbered("Exit all positions at next open. No exceptions.", "numbers4"),
      numbered("Stop all trading for 30 calendar days.", "numbers4"),
      numbered("During the pause: run deployment_verification.py on the most recent data.", "numbers4"),
      numbered("Fresh OOS PF > 1.10: resume after 30 days.", "numbers4"),
      numbered("Fresh OOS PF < 1.05: do not resume without a full re-validation study.", "numbers4"),
      numbered("Do not shorten the 30-day pause even if the market recovers.", "numbers4"),
      blank(),

      h3("F7: Three Consecutive Losing Rebalances"),
      p("Definition: Three consecutive 10-day periods with negative P&L.  Severity: Medium."),
      numbered("Do NOT stop trading. Three losing rebalances is within normal variance.", "numbers5"),
      numbered("Run a mini health check: compute rolling 30-day PF from trade log.", "numbers5"),
      numbered("Rolling PF > 0.85: continue normally. Log the flag.", "numbers5"),
      numbered("Rolling PF < 0.85: raise a red flag. Run deployment_verification.py.", "numbers5"),
      numbered("Strategy parameters must not change based solely on a losing streak.", "numbers5"),
      blank(),

      h3("F8: Exchange / Market-Wide Circuit Breaker"),
      p("Trigger: SEBI-mandated market halt.  Severity: High but external."),
      numbered("Do not place any orders during a market-wide halt.", "numbers6"),
      numbered("Wait for normal trading to resume.", "numbers6"),
      numbered("On the next trading day: re-run Daily Checklist from the beginning.", "numbers6"),
      numbered("SL and regime checks take priority.", "numbers6"),

      // ── 8. LOGS ──
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),
      h1("8. Required Logs and Metrics"),
      blank(),

      h2("Log 1: Daily Operations Log"),
      p("One row per trading day."),
      blank(),
      logTable(
        ["Field", "Description"],
        [
          ["Date", "Trading date"],
          ["Nifty Close", "Previous close used for regime calculation"],
          ["50DMA", "Current value"],
          ["200DMA", "Current value"],
          ["Regime", "Bull / Flat / Bear"],
          ["Portfolio Value", "Cash + mark-to-market of all positions"],
          ["Cash", "Free cash"],
          ["Invested", "Total in positions"],
          ["SL Exits Today", "Symbols exited on SL (empty if none)"],
          ["Regime Exits Today", "Y/N — did regime change force liquidation"],
          ["Notes", "Any anomalies, manual interventions"],
        ],
        [2880, 6480]
      ),
      blank(),

      h2("Log 2: Position Log"),
      p("Current state of all open positions. Updated daily."),
      blank(),
      logTable(
        ["Field", "Description"],
        [
          ["Symbol", "Stock ticker"],
          ["Entry Date", "Date bought"],
          ["Entry Price", "Actual fill price"],
          ["Qty", "Number of shares"],
          ["SL Level", "Entry x 0.90 (fixed at entry, never trail)"],
          ["Current Price", "Latest close"],
          ["Unrealised P&L", "(Current - Entry) x Qty"],
          ["Unrealised P&L %", "(Current / Entry - 1) x 100"],
          ["Days Held", "Trading days since entry"],
        ],
        [2880, 6480]
      ),
      blank(),

      h2("Log 3: Trade Log"),
      p("One row per completed trade (exit only)."),
      blank(),
      logTable(
        ["Field", "Description"],
        [
          ["Trade #", "Sequential ID"],
          ["Symbol", "Stock ticker"],
          ["Entry Date", "Date bought"],
          ["Exit Date", "Date sold"],
          ["Entry Price", "Actual buy fill"],
          ["Exit Price", "Actual sell fill"],
          ["Qty", "Shares"],
          ["Gross P&L", "(Exit - Entry) x Qty"],
          ["Costs", "Brokerage + STT + Exchange (both legs)"],
          ["Net P&L", "Gross P&L - Costs"],
          ["Return %", "(Exit / Entry - 1) x 100"],
          ["Exit Reason", "SL / Rebalance / Regime / EoP"],
          ["Hold Days", "Trading days"],
        ],
        [2880, 6480]
      ),
      blank(),

      h2("Log 4: Rebalance Log"),
      p("One row per rebalance event."),
      blank(),
      logTable(
        ["Field", "Description"],
        [
          ["Rebal #", "Sequential ID"],
          ["Date", "Rebalance day"],
          ["Regime", "Regime at rebalance"],
          ["Top-10 Selected", "Comma-separated symbols and composite scores"],
          ["Exits", "Symbols sold"],
          ["Entries", "Symbols bought"],
          ["Holds", "Unchanged positions"],
          ["Cash Before", ""],
          ["Cash After", ""],
          ["Skipped", "Y/N (Bear regime = rebal skipped)"],
        ],
        [2880, 6480]
      ),
      blank(),

      h2("Log 5: Slippage Tracker"),
      p("One row per buy or sell order. Target: average slippage <= 0.25%. Review cost model if average exceeds 0.40% over 60 trades."),
      blank(),
      logTable(
        ["Field", "Description"],
        [
          ["Date", "Order date"],
          ["Symbol", "Stock ticker"],
          ["Side", "Buy / Sell"],
          ["Prev Close", "Yesterday's close"],
          ["Actual Fill", "Actual execution price"],
          ["Slippage %", "abs(Fill - Prev Close) / Prev Close x 100"],
          ["Modelled", "0.20%"],
          ["Excess", "Actual - Modelled"],
        ],
        [2880, 6480]
      ),

      // ── QUICK REFERENCE CARD ──
      new Paragraph({ pageBreakBefore: true, children: [new TextRun("")] }),
      h1("Quick Reference Card"),
      p("Print and keep at desk.", { italic: true }),
      blank(),

      new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        columnWidths: [2880, 6480],
        rows: [
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 9360, type: WidthType.DXA }, columnSpan: 2,
              shading: { fill: "2E4057", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "STRATEGY (FROZEN)", font: "Arial", size: 22, bold: true, color: "FFFFFF" })] })] })
          ]}),
          twoColRow("Weights", "RS=60%, EP=40%"),
          twoColRow("Universe", "134 NSE stocks"),
          twoColRow("Portfolio", "Top-10 equal weight"),
          twoColRow("Rebalance", "Every 10 trading days"),
          twoColRow("Stop-Loss", "10% below entry price (check each morning)"),
          twoColRow("Regime", "Bull+Flat = trade  |  Bear = 100% cash"),
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 9360, type: WidthType.DXA }, columnSpan: 2,
              shading: { fill: "2E4057", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "REGIME RULES", font: "Arial", size: 22, bold: true, color: "FFFFFF" })] })] })
          ]}),
          twoColRow("Bull", "Nifty > 200DMA AND 50DMA > 200DMA  →  Full portfolio"),
          twoColRow("Flat", "Nifty > 200DMA AND 50DMA <= 200DMA  →  Full portfolio"),
          twoColRow("Bear", "Nifty < 200DMA  →  100% cash"),
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 9360, type: WidthType.DXA }, columnSpan: 2,
              shading: { fill: "2E4057", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "MORNING ROUTINE (before 9:10 AM)", font: "Arial", size: 22, bold: true, color: "FFFFFF" })] })] })
          ]}),
          twoColRow("Step 1", "Nifty close → classify regime"),
          twoColRow("Step 2", "If Bear: exit all → STOP"),
          twoColRow("Step 3", "SL check: close <= entry x 0.90 → exit at open"),
          twoColRow("Step 4", "Confirm all orders filled from prior day"),
          twoColRow("Step 5", "Log portfolio value"),
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 9360, type: WidthType.DXA }, columnSpan: 2,
              shading: { fill: "2E4057", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "EMERGENCY SHUTDOWN", font: "Arial", size: 22, bold: true, color: "FFFFFF" })] })] })
          ]}),
          twoColRow("Drawdown > 20%", "EXIT ALL → 30-day pause → re-validate"),
          twoColRow("3 losing rebalances", "Health check only. Do NOT stop automatically."),
          twoColRow("Data failure", "Skip rebalance, hold positions, retry next day"),
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 9360, type: WidthType.DXA }, columnSpan: 2,
              shading: { fill: "FFF3CD", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "CURRENT STATE (2026-06-14)  —  BEAR REGIME", font: "Arial", size: 22, bold: true, color: "856404" })] })] })
          ]}),
          twoColRow("Action", "HOLD CASH. Do not enter any positions."),
          twoColRow("Re-entry", "When Nifty closes above 24,921 (200DMA)"),
          twoColRow("Candidates", "Run final_validation.py on first Bull/Flat day"),
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 9360, type: WidthType.DXA }, columnSpan: 2,
              shading: { fill: "E8F5E9", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "VALIDATED OOS PERFORMANCE (Policy C)", font: "Arial", size: 22, bold: true, color: "2E7D32" })] })] })
          ]}),
          twoColRow("Profit Factor", "1.349"),
          twoColRow("CAGR", "+5.7%"),
          twoColRow("Sharpe", "0.507"),
          twoColRow("Max Drawdown", "13.8%"),
          twoColRow("Alpha vs Nifty", "+5.2% / year"),
        ]
      }),
      blank(),
      new Paragraph({ spacing: { before: 240 }, border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 } }, children: [new TextRun({ text: "End of Live Operations Manual. Version 1.0. Strategy parameters frozen 2026-06-14. Next scheduled review: 90 days after live start, or when a red flag is raised.", font: "Arial", size: 18, italics: true, color: "888888" })] }),
    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("C:\\Users\\rushi\\Downloads\\moneybot\\MoneyBot_Live_Operations.docx", buf);
  console.log("Done");
});
