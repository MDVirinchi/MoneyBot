"""
MoneyBot RS60/EP40 Paper Trading Package
30-trading-day operational workbook
"""
import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.styles.numbers import FORMAT_PERCENTAGE_00
from datetime import date, timedelta
import os

OUT = r"C:\Users\rushi\Downloads\moneybot\MoneyBot_PaperTrading_Package.xlsx"

try:
    import config as _cfg
    _CAP = int(getattr(_cfg, "TRADING_CAPITAL_INR", 5_000))
except Exception:
    _CAP = 5_000

# ── colour palette ──────────────────────────────────────────────────────────
NAVY     = "1F3864"
BLUE2    = "2E4057"
LTBLUE   = "D6E4F0"
LTBLUE2  = "EBF5FB"
YELLOW   = "FFF9C4"
GREEN_H  = "E8F5E9"
GREEN_D  = "2E7D32"
RED_H    = "FDECEA"
RED_D    = "C0392B"
ORANGE_H = "FFF3CD"
ORANGE_D = "856404"
GREY_H   = "F2F3F4"
GREY_D   = "7F8C8D"
WHITE    = "FFFFFF"
BLACK    = "000000"
BLUE_IN  = "0000FF"   # hardcoded inputs
FORMULA  = "000000"   # formula cells
XSHEET   = "2E7D32"   # cross-sheet links

# ── style helpers ────────────────────────────────────────────────────────────
def font(bold=False, size=10, color=BLACK, italic=False, name="Arial"):
    return Font(name=name, bold=bold, size=size, color=color, italic=italic)

def fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def border_thin(sides="all"):
    s = Side(style="thin", color="CCCCCC")
    n = Side(style=None)
    if sides == "all":
        return Border(left=s, right=s, top=s, bottom=s)
    if sides == "bottom":
        return Border(bottom=Side(style="medium", color="999999"))
    if sides == "thick_bottom":
        return Border(bottom=Side(style="thick", color=NAVY))
    return Border()

def align(h="left", v="center", wrap=False):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

def hdr_cell(ws, row, col, text, bg=NAVY, fg=WHITE, bold=True, size=10,
             h="center", colspan=1, rowspan=1, wrap=False):
    c = ws.cell(row=row, column=col, value=text)
    c.font = font(bold=bold, size=size, color=fg)
    c.fill = fill(bg)
    c.alignment = align(h=h, v="center", wrap=wrap)
    c.border = border_thin()
    if colspan > 1 or rowspan > 1:
        ws.merge_cells(start_row=row, start_column=col,
                       end_row=row+rowspan-1, end_column=col+colspan-1)
    return c

def data_cell(ws, row, col, value="", color=BLACK, bg=WHITE, bold=False,
              fmt=None, h="left", wrap=False, border=True):
    c = ws.cell(row=row, column=col, value=value)
    c.font = font(bold=bold, color=color)
    c.fill = fill(bg)
    c.alignment = align(h=h, v="center", wrap=wrap)
    if border:
        c.border = border_thin()
    if fmt:
        c.number_format = fmt
    return c

def input_cell(ws, row, col, value="", fmt=None, bg=YELLOW, h="center"):
    c = ws.cell(row=row, column=col, value=value)
    c.font = font(color=BLUE_IN, bold=True)
    c.fill = fill(bg)
    c.alignment = align(h=h, v="center")
    c.border = border_thin()
    if fmt:
        c.number_format = fmt
    return c

def formula_cell(ws, row, col, formula, fmt=None, bg=WHITE, h="right"):
    c = ws.cell(row=row, column=col, value=formula)
    c.font = font(color=FORMULA)
    c.fill = fill(bg)
    c.alignment = align(h=h, v="center")
    c.border = border_thin()
    if fmt:
        c.number_format = fmt
    return c

def xsheet_cell(ws, row, col, formula, fmt=None, bg=WHITE, h="right"):
    c = ws.cell(row=row, column=col, value=formula)
    c.font = font(color=XSHEET)
    c.fill = fill(bg)
    c.alignment = align(h=h, v="center")
    c.border = border_thin()
    if fmt:
        c.number_format = fmt
    return c

def section_title(ws, row, col, text, ncols, bg=BLUE2):
    hdr_cell(ws, row, col, text, bg=bg, bold=True, size=11, colspan=ncols)

def freeze(ws, row, col):
    ws.freeze_panes = ws.cell(row=row, column=col)

# ── trading day calendar ─────────────────────────────────────────────────────
def trading_days(start: date, n: int):
    """Return n weekdays starting from start."""
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days

START_DATE = date(2026, 6, 16)
TDAYS = trading_days(START_DATE, 30)
REBAL_DAYS = {TDAYS[9], TDAYS[19], TDAYS[29]}   # day 10, 20, 30

# ── number formats ───────────────────────────────────────────────────────────
FMT_DATE    = "DD-MMM-YYYY"
FMT_INT     = '#,##0'
FMT_RS      = u'₹#,##0.00'
FMT_RS0     = u'₹#,##0'
FMT_PCT1    = '0.0%'
FMT_PCT2    = '0.00%'
FMT_2DP     = '0.00'
FMT_4DP     = '0.0000'

# ════════════════════════════════════════════════════════════════════════════
wb = openpyxl.Workbook()

# ─── 1. INSTRUCTIONS ────────────────────────────────────────────────────────
ws_i = wb.active
ws_i.title = "INSTRUCTIONS"

def build_instructions(ws):
    ws.column_dimensions['A'].width = 26
    ws.column_dimensions['B'].width = 70
    ws.sheet_view.showGridLines = False

    # Title block
    c = ws.merge_cells("A1:B1")
    t = ws['A1']
    t.value = "MoneyBot RS60/EP40  —  Paper Trading Package"
    t.font = Font(name="Arial", bold=True, size=18, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 36

    ws.merge_cells("A2:B2")
    s = ws['A2']
    s.value = "30-Trading-Day Operational Workbook  |  Strategy FROZEN  |  Generated 2026-06-15"
    s.font = font(italic=True, color=GREY_D, size=10)
    s.fill = fill(LTBLUE)
    s.alignment = align(h="center")
    ws.row_dimensions[2].height = 18

    # Strategy params box
    params = [
        ("STRATEGY PARAMETERS (FROZEN)", "", BLUE2, WHITE),
        ("RS Weight", "60%", LTBLUE, BLACK),
        ("EP Weight", "40%", LTBLUE, BLACK),
        ("Universe", "134 NSE stocks", LTBLUE, BLACK),
        ("Portfolio size", "Top 10 by composite score", LTBLUE, BLACK),
        ("Rebalance cadence", "Every 10 trading days", LTBLUE, BLACK),
        ("Stop-loss", "10% below entry price — checked every morning", LTBLUE, BLACK),
        ("Regime filter", "Policy C: Bull+Flat = trade  |  Bear = 100% cash", LTBLUE, BLACK),
        ("Paper capital", "Rs.5,00,000 (Rs.50,000 per position)", LTBLUE, BLACK),
        ("Paper start date", "2026-06-16", LTBLUE, BLACK),
        ("Paper end date", "2026-07-27 (30 trading days)", LTBLUE, BLACK),
    ]
    r = 4
    for label, val, bg, fg in params:
        if val == "":
            ws.merge_cells(f"A{r}:B{r}")
            c = ws[f'A{r}']
            c.value = label
            c.font = font(bold=True, size=11, color=fg)
            c.fill = fill(bg)
            c.alignment = align(h="center")
            c.border = border_thin()
        else:
            ws[f'A{r}'].value = label
            ws[f'A{r}'].font = font(bold=True, color=BLACK)
            ws[f'A{r}'].fill = fill(bg)
            ws[f'A{r}'].border = border_thin()
            ws[f'B{r}'].value = val
            ws[f'B{r}'].font = font(color=BLUE_IN, bold=True)
            ws[f'B{r}'].fill = fill(bg)
            ws[f'B{r}'].border = border_thin()
        r += 1

    r += 1
    # Regime rules
    regime = [
        ("REGIME RULES (Policy C)", "", BLUE2, WHITE),
        ("Bull", "Nifty > 200DMA  AND  50DMA > 200DMA  →  Hold/Enter positions", GREEN_H, GREEN_D),
        ("Flat", "Nifty > 200DMA  AND  50DMA ≤ 200DMA  →  Hold/Enter positions", GREEN_H, GREEN_D),
        ("Bear", "Nifty < 200DMA  →  Exit ALL positions. 100% cash. Skip rebalance.", RED_H, RED_D),
    ]
    for label, val, bg, fg in regime:
        if val == "":
            ws.merge_cells(f"A{r}:B{r}")
            c = ws[f'A{r}']
            c.value = label
            c.font = font(bold=True, size=11, color=fg)
            c.fill = fill(bg)
            c.alignment = align(h="center")
            c.border = border_thin()
        else:
            ws[f'A{r}'].value = label
            ws[f'A{r}'].font = font(bold=True, color=fg)
            ws[f'A{r}'].fill = fill(bg)
            ws[f'A{r}'].border = border_thin()
            ws[f'B{r}'].value = val
            ws[f'B{r}'].font = font(color=fg)
            ws[f'B{r}'].fill = fill(bg)
            ws[f'B{r}'].border = border_thin()
        r += 1

    r += 1
    # Sheet guide
    sheets = [
        ("SHEET GUIDE", "", BLUE2, WHITE),
        ("1. INSTRUCTIONS", "This sheet — strategy params, color codes, sheet guide", LTBLUE2, BLACK),
        ("2. Daily_Ops_Log", "PRIMARY daily sheet. Enter Nifty data every morning. Regime auto-classifies.", LTBLUE2, BLACK),
        ("3. Position_Log", "Track all open positions. Enter fills. SL levels auto-calculate.", LTBLUE2, BLACK),
        ("4. Trade_Log", "Record every completed trade (exit). P&L and return auto-calculate.", LTBLUE2, BLACK),
        ("5. Rebalance_Log", "One row per rebalance event (Days 10, 20, 30 of paper period).", LTBLUE2, BLACK),
        ("6. Monthly_Dashboard", "Pulls live metrics from Trade Log. No manual entry needed.", LTBLUE2, BLACK),
        ("7. Slippage_Tracker", "Compare simulated vs actual fills. Slippage auto-calculates.", LTBLUE2, BLACK),
        ("8. Daily_Checklist", "Print this. 10-minute morning routine. Tick boxes.", LTBLUE2, BLACK),
        ("9. Rebalance_Checklist", "Print this. Use on every 10th trading day.", LTBLUE2, BLACK),
        ("10. Emergency_Card", "Print this. One page. What to do when things break.", LTBLUE2, BLACK),
    ]
    for label, val, bg, fg in sheets:
        if val == "":
            ws.merge_cells(f"A{r}:B{r}")
            c = ws[f'A{r}']
            c.value = label
            c.font = font(bold=True, size=11, color=fg)
            c.fill = fill(bg)
            c.alignment = align(h="center")
            c.border = border_thin()
        else:
            ws[f'A{r}'].value = label
            ws[f'A{r}'].font = font(bold=True, color=BLUE2)
            ws[f'A{r}'].fill = fill(bg)
            ws[f'A{r}'].border = border_thin()
            ws[f'B{r}'].value = val
            ws[f'B{r}'].font = font(color=BLACK)
            ws[f'B{r}'].fill = fill(bg)
            ws[f'B{r}'].border = border_thin()
        r += 1

    r += 1
    # Colour key
    ck = [
        ("COLOUR CODE KEY", "", BLUE2, WHITE),
        ("Blue bold text", "Hardcoded input — enter this value yourself", YELLOW, BLUE_IN),
        ("Black text", "Formula — calculated automatically", WHITE, BLACK),
        ("Green text", "Cross-sheet link — pulls from another tab", WHITE, XSHEET),
        ("Yellow background", "Cell requires user input every day/rebalance", YELLOW, BLACK),
        ("Green background", "Bull/Flat regime — OK to trade", GREEN_H, GREEN_D),
        ("Red background", "Bear regime — cash only", RED_H, RED_D),
        ("Orange background", "Warning / attention required", ORANGE_H, ORANGE_D),
    ]
    for label, val, bg, fg in ck:
        if val == "":
            ws.merge_cells(f"A{r}:B{r}")
            c = ws[f'A{r}']
            c.value = label
            c.font = font(bold=True, size=11, color=fg)
            c.fill = fill(bg)
            c.alignment = align(h="center")
            c.border = border_thin()
        else:
            ws[f'A{r}'].value = label
            ws[f'A{r}'].font = font(bold=True, color=fg)
            ws[f'A{r}'].fill = fill(bg)
            ws[f'A{r}'].border = border_thin()
            ws[f'B{r}'].value = val
            ws[f'B{r}'].font = font(color=fg)
            ws[f'B{r}'].fill = fill(bg)
            ws[f'B{r}'].border = border_thin()
        r += 1

build_instructions(ws_i)

# ─── 2. DAILY OPS LOG ────────────────────────────────────────────────────────
ws_d = wb.create_sheet("Daily_Ops_Log")

def build_daily_ops(ws):
    ws.sheet_view.showGridLines = False
    # Col widths
    widths = [4, 13, 10, 10, 10, 10, 12, 12, 11, 22, 20, 20, 30]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Title
    ws.merge_cells("A1:M1")
    t = ws['A1']
    t.value = "DAILY OPERATIONS LOG  —  MoneyBot RS60/EP40  |  Paper Trading 2026-06-16 to 2026-07-27"
    t.font = font(bold=True, size=13, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:M2")
    s = ws['A2']
    s.value = ("Enter YELLOW cells every morning before 9:10 AM. "
               "Regime auto-classifies. Rebalance days highlighted in blue.")
    s.font = font(italic=True, size=9, color=GREY_D)
    s.fill = fill(LTBLUE2)
    s.alignment = align(h="center")

    # Column headers row 3
    headers = ["#", "Date", "Nifty\nClose", "50-DMA\n(enter)", "200-DMA\n(enter)",
               "50>200?", "Regime", "Portfolio\nValue (Rs)", "Daily\nP&L (Rs)",
               "SL Exits\n(symbols)", "Regime\nExit?", "Rebalance\nDay?", "Notes"]
    cols_fmt = [None, FMT_DATE, FMT_INT, FMT_INT, FMT_INT,
                None, None, FMT_RS0, FMT_RS0, None, None, None, None]
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = font(bold=True, size=9, color=WHITE)
        c.fill = fill(BLUE2)
        c.alignment = align(h="center", v="center", wrap=True)
        c.border = border_thin()
    ws.row_dimensions[3].height = 32

    # Data rows
    for idx, d in enumerate(TDAYS):
        r = idx + 4
        is_rebal = d in REBAL_DAYS
        row_bg = LTBLUE if is_rebal else (GREY_H if idx % 2 == 1 else WHITE)

        # Col A: row number
        data_cell(ws, r, 1, idx+1, h="center", bg=row_bg, bold=is_rebal)
        # Col B: date
        c = ws.cell(row=r, column=2, value=d)
        c.font = font(bold=is_rebal, color=BLUE2 if is_rebal else BLACK)
        c.fill = fill(row_bg)
        c.alignment = align(h="center")
        c.border = border_thin()
        c.number_format = FMT_DATE
        # Col C: Nifty close — INPUT
        input_cell(ws, r, 3, fmt=FMT_INT)
        # Col D: 50DMA — INPUT
        input_cell(ws, r, 4, fmt=FMT_INT)
        # Col E: 200DMA — INPUT
        input_cell(ws, r, 5, fmt=FMT_INT)
        # Col F: 50>200? formula
        fc = ws.cell(row=r, column=6,
                     value=f'=IF(D{r}=""," ",IF(D{r}>E{r},"YES","NO"))')
        fc.font = font(color=FORMULA)
        fc.fill = fill(row_bg)
        fc.alignment = align(h="center")
        fc.border = border_thin()
        # Col G: Regime formula
        rc = ws.cell(row=r, column=7,
                     value=(f'=IF(C{r}="","—",'
                            f'IF(C{r}<E{r},"BEAR",'
                            f'IF(D{r}>E{r},"BULL","FLAT")))'))
        rc.font = font(bold=True, color=FORMULA)
        rc.fill = fill(row_bg)
        rc.alignment = align(h="center")
        rc.border = border_thin()
        # Col H: Portfolio value — INPUT
        pv_bg = YELLOW if idx == 0 else YELLOW
        input_cell(ws, r, 8, value=(_CAP if idx == 0 else ""),
                   fmt=FMT_RS0)
        # Col I: Daily P&L — formula vs previous
        if idx == 0:
            data_cell(ws, r, 9, value="—", h="center", bg=row_bg)
        else:
            formula_cell(ws, r, 9,
                         f'=IF(H{r}="","",H{r}-H{r-1})',
                         fmt=FMT_RS0, bg=row_bg)
        # Col J: SL exits — INPUT text
        c = ws.cell(row=r, column=10, value="")
        c.fill = fill(YELLOW)
        c.border = border_thin()
        c.font = font(color=BLUE_IN)
        # Col K: Regime exit — INPUT
        dv_k = DataValidation(type="list", formula1='"YES,NO,—"', allow_blank=True)
        ws.add_data_validation(dv_k)
        kc = input_cell(ws, r, 11, value="—", h="center")
        dv_k.add(kc)
        # Col L: Rebalance day?
        lc = ws.cell(row=r, column=12,
                     value="REBAL" if is_rebal else "—")
        lc.font = font(bold=is_rebal, color=WHITE if is_rebal else GREY_D)
        lc.fill = fill(BLUE2 if is_rebal else row_bg)
        lc.alignment = align(h="center")
        lc.border = border_thin()
        # Col M: Notes — INPUT
        nc = ws.cell(row=r, column=13, value="")
        nc.fill = fill(YELLOW)
        nc.border = border_thin()
        nc.font = font(color=BLUE_IN)

    # Freeze panes: row 4, col 3
    freeze(ws, 4, 3)

    # Summary below data
    last_r = 4 + 30 + 2
    ws.merge_cells(f"A{last_r}:M{last_r}")
    s = ws[f'A{last_r}']
    s.value = ("CURRENT REGIME (2026-06-15):  BEAR  —  Nifty 23,623 < 200DMA 24,921  "
               "Hold cash. Do not enter positions until Nifty reclaims 200DMA.")
    s.font = font(bold=True, color=RED_D, size=10)
    s.fill = fill(RED_H)
    s.alignment = align(h="center")
    s.border = border_thin()

build_daily_ops(ws_d)

# ─── 3. POSITION LOG ────────────────────────────────────────────────────────
ws_p = wb.create_sheet("Position_Log")

def build_position_log(ws):
    ws.sheet_view.showGridLines = False
    widths = [14, 13, 10, 8, 10, 10, 10, 11, 11, 11, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.merge_cells("A1:K1")
    t = ws['A1']
    t.value = "POSITION LOG  —  Open Positions  |  Updated daily after market close"
    t.font = font(bold=True, size=13, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:K2")
    s = ws['A2']
    s.value = ("Enter Symbol, Entry Date, Entry Price, Qty in YELLOW. "
               "SL Level, P&L, and Days Held auto-calculate. "
               "Remove row when position is closed (record it in Trade Log first).")
    s.font = font(italic=True, size=9, color=GREY_D)
    s.fill = fill(LTBLUE2)
    s.alignment = align(h="center", wrap=True)
    ws.row_dimensions[2].height = 20

    hdrs = ["Symbol", "Entry\nDate", "Entry\nPrice (Rs)", "Qty\n(shares)", "SL Level\n(auto)",
            "Current\nClose (Rs)", "Unreal.\nP&L (Rs)", "Unreal.\nP&L %",
            "Days\nHeld", "Allocation\n(Rs)", "Status"]
    for ci, h in enumerate(hdrs, 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = font(bold=True, size=9, color=WHITE)
        c.fill = fill(BLUE2)
        c.alignment = align(h="center", v="center", wrap=True)
        c.border = border_thin()
    ws.row_dimensions[3].height = 32

    # 10 position rows
    for i in range(10):
        r = i + 4
        bg = GREY_H if i % 2 == 1 else WHITE
        # A: Symbol
        input_cell(ws, r, 1, h="center")
        # B: Entry date
        c = ws.cell(row=r, column=2)
        c.fill = fill(YELLOW)
        c.font = font(color=BLUE_IN, bold=True)
        c.alignment = align(h="center")
        c.border = border_thin()
        c.number_format = FMT_DATE
        # C: Entry price
        input_cell(ws, r, 3, fmt=FMT_RS, h="right")
        # D: Qty
        input_cell(ws, r, 4, fmt=FMT_INT, h="center")
        # E: SL level = entry * 0.90 (formula)
        formula_cell(ws, r, 5, f'=IF(C{r}="","",C{r}*0.90)', fmt=FMT_RS, bg=LTBLUE2)
        # F: Current close — INPUT daily
        input_cell(ws, r, 6, fmt=FMT_RS, h="right")
        # G: Unrealised P&L
        formula_cell(ws, r, 7,
                     f'=IF(OR(C{r}="",D{r}="",F{r}=""),"",(F{r}-C{r})*D{r})',
                     fmt=FMT_RS0)
        # H: Unrealised P&L %
        formula_cell(ws, r, 8,
                     f'=IF(OR(C{r}="",F{r}=""),"",F{r}/C{r}-1)',
                     fmt=FMT_PCT2)
        # I: Days held (formula: today-entry — during paper trading user can enter date)
        formula_cell(ws, r, 9,
                     f'=IF(B{r}="","",TODAY()-B{r})',
                     fmt=FMT_INT, h="center")
        # J: Allocation
        formula_cell(ws, r, 10,
                     f'=IF(OR(C{r}="",D{r}=""),"",C{r}*D{r})',
                     fmt=FMT_RS0)
        # K: Status — SL warning
        formula_cell(ws, r, 11,
                     f'=IF(C{r}="","",IF(F{r}="","Awaiting price",'
                     f'IF(F{r}<=E{r},"*** SL TRIGGERED ***",'
                     f'IF(F{r}/C{r}-1<-0.07,"APPROACHING SL","OPEN"))))',
                     bg=bg, h="center")

    # Summary
    sr = 15
    ws.merge_cells(f"A{sr}:K{sr}")
    ws[f'A{sr}'].value = "POSITION SUMMARY"
    ws[f'A{sr}'].font = font(bold=True, color=WHITE)
    ws[f'A{sr}'].fill = fill(BLUE2)
    ws[f'A{sr}'].alignment = align(h="center")
    ws[f'A{sr}'].border = border_thin()

    srows = [
        ("Total open positions", f'=COUNTA(A4:A13)', FMT_INT),
        ("Total invested (Rs)", f'=IFERROR(SUMPRODUCT((C4:C13<>"")*C4:C13*D4:D13),0)', FMT_RS0),
        ("Total unrealised P&L (Rs)", f'=IFERROR(SUM(G4:G13),0)', FMT_RS0),
        ("Positions approaching SL (loss >7%)", f'=COUNTIF(K4:K13,"APPROACHING SL")', FMT_INT),
        ("Positions SL triggered", f'=COUNTIF(K4:K13,"*** SL TRIGGERED ***")', FMT_INT),
    ]
    for j, (lbl, frm, fmt) in enumerate(srows):
        r = sr + 1 + j
        data_cell(ws, r, 1, lbl, bold=True, bg=LTBLUE2, h="left")
        ws.merge_cells(f"A{r}:B{r}")
        formula_cell(ws, r, 3, frm, fmt=fmt, bg=WHITE, h="right")
        for ci in range(4, 12):
            ws.cell(row=r, column=ci).border = border_thin()

    freeze(ws, 4, 1)

build_position_log(ws_p)

# ─── 4. TRADE LOG ────────────────────────────────────────────────────────────
ws_t = wb.create_sheet("Trade_Log")

def build_trade_log(ws):
    ws.sheet_view.showGridLines = False
    widths = [5, 12, 12, 12, 11, 11, 8, 11, 11, 11, 10, 11, 14, 8]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.merge_cells("A1:N1")
    t = ws['A1']
    t.value = "TRADE LOG  —  Completed Trades  |  One row per exit"
    t.font = font(bold=True, size=13, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:N2")
    s = ws['A2']
    s.value = ("Enter YELLOW cells when a position is closed. "
               "Gross P&L, Net P&L, Return %, and Hold Days auto-calculate. "
               "Costs = Brokerage (Rs.20 each way) + STT 0.1% on sell side + Exchange fee 0.00345%.")
    s.font = font(italic=True, size=9, color=GREY_D)
    s.fill = fill(LTBLUE2)
    s.alignment = align(h="center", wrap=True)
    ws.row_dimensions[2].height = 24

    hdrs = ["#", "Symbol", "Entry\nDate", "Exit\nDate", "Entry\nPrice (Rs)",
            "Exit\nPrice (Rs)", "Qty", "Gross\nP&L (Rs)", "Total\nCosts (Rs)",
            "Net\nP&L (Rs)", "Return\n%", "Hold\nDays", "Exit\nReason", "Win?"]
    for ci, h in enumerate(hdrs, 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = font(bold=True, size=9, color=WHITE)
        c.fill = fill(BLUE2)
        c.alignment = align(h="center", v="center", wrap=True)
        c.border = border_thin()
    ws.row_dimensions[3].height = 32

    # 30 trade rows
    for i in range(30):
        r = i + 4
        bg = GREY_H if i % 2 == 1 else WHITE
        # A: trade number
        formula_cell(ws, r, 1, f'=IF(B{r}="","",ROW()-3)', fmt=FMT_INT, bg=bg, h="center")
        # B: symbol
        input_cell(ws, r, 2, h="center")
        # C: entry date
        c = ws.cell(row=r, column=3)
        c.fill = fill(YELLOW)
        c.font = font(color=BLUE_IN, bold=True)
        c.alignment = align(h="center")
        c.border = border_thin()
        c.number_format = FMT_DATE
        # D: exit date
        c = ws.cell(row=r, column=4)
        c.fill = fill(YELLOW)
        c.font = font(color=BLUE_IN, bold=True)
        c.alignment = align(h="center")
        c.border = border_thin()
        c.number_format = FMT_DATE
        # E: entry price
        input_cell(ws, r, 5, fmt=FMT_RS, h="right")
        # F: exit price
        input_cell(ws, r, 6, fmt=FMT_RS, h="right")
        # G: qty
        input_cell(ws, r, 7, fmt=FMT_INT, h="center")
        # H: Gross P&L = (exit-entry)*qty
        formula_cell(ws, r, 8,
                     f'=IF(OR(E{r}="",F{r}="",G{r}=""),"",(F{r}-E{r})*G{r})',
                     fmt=FMT_RS0, bg=bg)
        # I: Costs = 2*20 + STT(0.001*exit*qty) + exchange(0.0000345*2*entry*qty)
        formula_cell(ws, r, 9,
                     f'=IF(OR(E{r}="",F{r}="",G{r}=""),"",40+0.001*F{r}*G{r}+0.0000345*(E{r}+F{r})*G{r})',
                     fmt=FMT_RS0, bg=bg)
        # J: Net P&L
        formula_cell(ws, r, 10,
                     f'=IF(H{r}="","",H{r}-I{r})',
                     fmt=FMT_RS0, bg=bg)
        # K: Return %
        formula_cell(ws, r, 11,
                     f'=IF(OR(E{r}="",F{r}=""),"",F{r}/E{r}-1)',
                     fmt=FMT_PCT2, bg=bg)
        # L: Hold days
        formula_cell(ws, r, 12,
                     f'=IF(OR(C{r}="",D{r}=""),"",D{r}-C{r})',
                     fmt=FMT_INT, bg=bg, h="center")
        # M: Exit reason — dropdown
        dv = DataValidation(type="list",
                            formula1='"SL,Rebalance,Regime,EoP"',
                            allow_blank=True)
        ws.add_data_validation(dv)
        mc = input_cell(ws, r, 13, h="center")
        dv.add(mc)
        # N: Win?
        formula_cell(ws, r, 14,
                     f'=IF(J{r}="","",IF(J{r}>0,"WIN","LOSS"))',
                     bg=bg, h="center")

    # Summary block
    sr = 35
    ws.merge_cells(f"A{sr}:N{sr}")
    ws[f'A{sr}'].value = "TRADE SUMMARY (auto-updates)"
    ws[f'A{sr}'].font = font(bold=True, color=WHITE)
    ws[f'A{sr}'].fill = fill(BLUE2)
    ws[f'A{sr}'].alignment = align(h="center")
    ws[f'A{sr}'].border = border_thin()

    sumrows = [
        ("Total trades", f'=COUNTA(B4:B33)', FMT_INT),
        ("Winning trades", f'=COUNTIF(N4:N33,"WIN")', FMT_INT),
        ("Losing trades", f'=COUNTIF(N4:N33,"LOSS")', FMT_INT),
        ("Win rate", f'=IFERROR(B{sr+2}/B{sr+1},"")', FMT_PCT1),
        ("Total gross P&L (Rs)", f'=IFERROR(SUM(H4:H33),"")', FMT_RS0),
        ("Total costs (Rs)", f'=IFERROR(SUM(I4:I33),"")', FMT_RS0),
        ("Total net P&L (Rs)", f'=IFERROR(SUM(J4:J33),"")', FMT_RS0),
        ("Gross wins (Rs)", f'=IFERROR(SUMIF(H4:H33,">"&0,H4:H33),"")', FMT_RS0),
        ("Gross losses (Rs)", f'=IFERROR(SUMIF(H4:H33,"<"&0,H4:H33),"")', FMT_RS0),
        ("Profit Factor", f'=IFERROR(B{sr+8}/ABS(B{sr+9}),"")', FMT_2DP),
        ("Average win % (per trade)", f'=IFERROR(AVERAGEIF(N4:N33,"WIN",K4:K33),"")', FMT_PCT2),
        ("Average loss % (per trade)", f'=IFERROR(AVERAGEIF(N4:N33,"LOSS",K4:K33),"")', FMT_PCT2),
        ("Average hold days", f'=IFERROR(AVERAGE(L4:L33),"")', FMT_2DP),
        ("Exits by SL", f'=COUNTIF(M4:M33,"SL")', FMT_INT),
        ("Exits by Rebalance", f'=COUNTIF(M4:M33,"Rebalance")', FMT_INT),
        ("Exits by Regime", f'=COUNTIF(M4:M33,"Regime")', FMT_INT),
    ]
    for j, (lbl, frm, fmt) in enumerate(sumrows):
        r = sr + 1 + j
        bg2 = LTBLUE2 if j % 2 == 0 else WHITE
        data_cell(ws, r, 1, lbl, bold=True, bg=bg2, h="left")
        ws.merge_cells(f"A{r}:A{r}")
        formula_cell(ws, r, 2, frm, fmt=fmt, bg=bg2, h="right")
        for ci in range(3, 15):
            ws.cell(row=r, column=ci).border = border_thin()

    freeze(ws, 4, 2)

build_trade_log(ws_t)

# ─── 5. REBALANCE LOG ────────────────────────────────────────────────────────
ws_rb = wb.create_sheet("Rebalance_Log")

def build_rebalance_log(ws):
    ws.sheet_view.showGridLines = False
    widths = [4, 13, 8, 8, 40, 40, 40, 11, 11, 8]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.merge_cells("A1:J1")
    t = ws['A1']
    t.value = "REBALANCE LOG  —  One row per rebalance event"
    t.font = font(bold=True, size=13, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:J2")
    s = ws['A2']
    s.value = ("Paper trading has 3 rebalance days: Day 10 (2026-06-27), "
               "Day 20 (2026-07-10), Day 30 (2026-07-24). "
               "Enter Exits, Entries, and Holds as comma-separated symbols.")
    s.font = font(italic=True, size=9, color=GREY_D)
    s.fill = fill(LTBLUE2)
    s.alignment = align(h="center", wrap=True)
    ws.row_dimensions[2].height = 20

    hdrs = ["#", "Date", "Regime", "Skipped?", "Top-10 Selected\n(symbol : score)",
            "Exits\n(comma-separated)", "Entries\n(comma-separated)",
            "Cash Before\n(Rs)", "Cash After\n(Rs)", "Turnover\n(%)"]
    for ci, h in enumerate(hdrs, 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = font(bold=True, size=9, color=WHITE)
        c.fill = fill(BLUE2)
        c.alignment = align(h="center", v="center", wrap=True)
        c.border = border_thin()
    ws.row_dimensions[3].height = 40

    rebal_dates = [TDAYS[9], TDAYS[19], TDAYS[29]]
    rebal_labels = ["Day 10", "Day 20", "Day 30"]

    for i, (rd, lbl) in enumerate(zip(rebal_dates, rebal_labels)):
        r = i + 4
        bg = LTBLUE if i % 2 == 0 else WHITE
        data_cell(ws, r, 1, i+1, h="center", bg=bg, bold=True)
        c = ws.cell(row=r, column=2, value=rd)
        c.font = font(bold=True, color=BLUE2)
        c.fill = fill(bg)
        c.alignment = align(h="center")
        c.border = border_thin()
        c.number_format = FMT_DATE
        # Regime — dropdown
        dv = DataValidation(type="list", formula1='"BULL,FLAT,BEAR"', allow_blank=True)
        ws.add_data_validation(dv)
        rc = input_cell(ws, r, 3, h="center")
        dv.add(rc)
        # Skipped?
        dv2 = DataValidation(type="list", formula1='"YES,NO"', allow_blank=True)
        ws.add_data_validation(dv2)
        sc = input_cell(ws, r, 4, value="NO", h="center")
        dv2.add(sc)
        # Top-10 selected — large text INPUT
        for ci in range(5, 10):
            c = ws.cell(row=r, column=ci)
            c.fill = fill(YELLOW)
            c.font = font(color=BLUE_IN)
            c.alignment = align(h="left", v="center", wrap=True)
            c.border = border_thin()
        # Cash cols
        for ci in [8, 9]:
            c = ws.cell(row=r, column=ci)
            c.fill = fill(YELLOW)
            c.font = font(color=BLUE_IN, bold=True)
            c.alignment = align(h="right")
            c.border = border_thin()
            c.number_format = FMT_RS0
        # Turnover — manual input
        input_cell(ws, r, 10, fmt=FMT_PCT1, h="center")
        ws.row_dimensions[r].height = 80

    # Notes below
    nr = 8
    ws.merge_cells(f"A{nr}:J{nr}")
    nc = ws[f'A{nr}']
    nc.value = ("HOW TO RECORD A REBALANCE: "
                "(1) Enter regime. (2) If Bear, set Skipped=YES and stop. "
                "(3) Run final_validation.py — paste the top-10 symbols+scores in col E. "
                "(4) List stocks you sold in col F (not in new top-10). "
                "(5) List stocks you bought in col G (new in top-10). "
                "(6) Enter cash balance before/after fills. "
                "(7) Estimate turnover = (shares sold + shares bought) / (2 x total shares) x 100.")
    nc.font = font(italic=True, size=9, color=BLUE2)
    nc.fill = fill(LTBLUE2)
    nc.alignment = align(h="left", wrap=True)
    nc.border = border_thin()
    ws.row_dimensions[nr].height = 60

build_rebalance_log(ws_rb)

# ─── 6. MONTHLY DASHBOARD ───────────────────────────────────────────────────
ws_dash = wb.create_sheet("Monthly_Dashboard")

def build_dashboard(ws):
    ws.sheet_view.showGridLines = False
    widths = [32, 20, 20, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.merge_cells("A1:D1")
    t = ws['A1']
    t.value = "MONTHLY PERFORMANCE DASHBOARD  —  MoneyBot RS60/EP40"
    t.font = font(bold=True, size=14, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:D2")
    s = ws['A2']
    s.value = ("Pulls live from Trade_Log and Daily_Ops_Log. "
               "Enter the Nifty benchmark return in yellow. All other cells are formulas.")
    s.font = font(italic=True, size=9, color=GREY_D)
    s.fill = fill(LTBLUE2)
    s.alignment = align(h="center")

    sections = [
        ("PORTFOLIO PERFORMANCE", [
            ("Paper Start Capital (Rs)", f"={_CAP}", FMT_RS0, "hardcode"),
            ("Current Portfolio Value (Rs)", f"=IF(COUNTA(Daily_Ops_Log!H4:H33)>0,LOOKUP(2,1/(Daily_Ops_Log!H4:H33<>\"\"),Daily_Ops_Log!H4:H33),{_CAP})", FMT_RS0, "formula"),
            ("Total Net P&L (Rs)", "=IFERROR(SUM(Trade_Log!J4:J33),0)", FMT_RS0, "xsheet"),
            ("Period Return %", "=IFERROR((B6-B5)/B5,0)", FMT_PCT2, "formula"),
            ("Nifty Period Return % (enter)", "", FMT_PCT2, "input"),
            ("Alpha vs Nifty (pp)", "=IF(B8=\"\",\"\",B7-B8)", FMT_PCT2, "formula"),
        ]),
        ("TRADE QUALITY", [
            ("Total trades completed", "=IFERROR(Trade_Log!B36,0)", FMT_INT, "xsheet"),
            ("Winning trades", "=IFERROR(Trade_Log!B37,0)", FMT_INT, "xsheet"),
            ("Losing trades", "=IFERROR(Trade_Log!B38,0)", FMT_INT, "xsheet"),
            ("Win rate %", "=IFERROR(Trade_Log!B39,0)", FMT_PCT1, "xsheet"),
            ("Profit Factor", "=IFERROR(Trade_Log!B45,\"\")", FMT_2DP, "xsheet"),
            ("Average win %", "=IFERROR(Trade_Log!B46,\"\")", FMT_PCT2, "xsheet"),
            ("Average loss %", "=IFERROR(Trade_Log!B47,\"\")", FMT_PCT2, "xsheet"),
            ("Average hold days", "=IFERROR(Trade_Log!B48,\"\")", FMT_2DP, "xsheet"),
        ]),
        ("COST ANALYSIS", [
            ("Total costs paid (Rs)", "=IFERROR(SUM(Trade_Log!I4:I33),0)", FMT_RS0, "xsheet"),
            ("Costs as % of start capital", "=IFERROR(B27/B5,0)", FMT_PCT2, "formula"),
            ("Avg slippage per trade (enter)", "", FMT_PCT2, "input"),
        ]),
        ("REGIME BREAKDOWN (30 days)", [
            ("Days in BULL regime", f'=COUNTIF(Daily_Ops_Log!G4:G33,"BULL")', FMT_INT, "xsheet"),
            ("Days in FLAT regime", f'=COUNTIF(Daily_Ops_Log!G4:G33,"FLAT")', FMT_INT, "xsheet"),
            ("Days in BEAR regime", f'=COUNTIF(Daily_Ops_Log!G4:G33,"BEAR")', FMT_INT, "xsheet"),
            ("% of days in cash (Bear)", "=IFERROR(B35/30,0)", FMT_PCT1, "formula"),
        ]),
        ("RED FLAG THRESHOLDS", [
            ("Profit Factor >= 0.90?", '=IF(B22="","Awaiting data",IF(B22>=0.9,"OK — PF "&TEXT(B22,"0.00"),"⚠ RED FLAG — PF "&TEXT(B22,"0.00")))', None, "formula"),
            ("Trailing Nifty by < 5%?", '=IF(OR(B7="",B8=""),"Awaiting data",IF(B7-B8>=-0.05,"OK — Alpha "&TEXT((B7-B8)*100,"0.0")&"pp","⚠ RED FLAG — Alpha "&TEXT((B7-B8)*100,"0.0")&"pp"))', None, "formula"),
            ("Drawdown < 20%?", f'=IF(B6={_CAP},"No trades yet",IF((B6-{_CAP})/{_CAP}>-0.2,"OK — DD "&TEXT(MIN(0,(B6-{_CAP})/{_CAP})*-1,"0.0%"),"⚠ RED FLAG — SUSPEND TRADING"))', None, "formula"),
        ]),
    ]

    r = 4
    for sec_title, rows in sections:
        ws.merge_cells(f"A{r}:D{r}")
        hc = ws[f'A{r}']
        hc.value = sec_title
        hc.font = font(bold=True, size=11, color=WHITE)
        hc.fill = fill(BLUE2)
        hc.alignment = align(h="left")
        hc.border = border_thin()
        r += 1
        for lbl, frm, fmt, kind in rows:
            bg = GREY_H if r % 2 == 0 else WHITE
            data_cell(ws, r, 1, lbl, bold=True, bg=bg)
            if kind == "input":
                ic = input_cell(ws, r, 2, fmt=fmt, h="right")
                for ci in [3, 4]:
                    ws.cell(row=r, column=ci).border = border_thin()
                    ws.cell(row=r, column=ci).fill = fill(bg)
            elif kind == "hardcode":
                c = data_cell(ws, r, 2, frm if frm != "" else "", bg=bg, h="right")
                if fmt: c.number_format = fmt
                c.value = _CAP
                c.font = font(color=BLUE_IN, bold=True)
                for ci in [3, 4]:
                    ws.cell(row=r, column=ci).border = border_thin()
                    ws.cell(row=r, column=ci).fill = fill(bg)
            else:
                color = XSHEET if kind == "xsheet" else FORMULA
                c = ws.cell(row=r, column=2, value=frm)
                c.font = font(color=color)
                c.fill = fill(bg)
                c.alignment = align(h="right")
                c.border = border_thin()
                if fmt: c.number_format = fmt
                for ci in [3, 4]:
                    ws.cell(row=r, column=ci).border = border_thin()
                    ws.cell(row=r, column=ci).fill = fill(bg)
            r += 1
        r += 1

    # Benchmarks note
    ws.merge_cells(f"A{r}:D{r}")
    nc = ws[f'A{r}']
    nc.value = ("VALIDATED BACKTEST BENCHMARKS (OOS, Policy C):  "
                "PF 1.349  |  CAGR +5.7%  |  Sharpe 0.507  |  MaxDD 13.8%  |  "
                "Win Rate 45.2%  |  Alpha +5.2%/yr vs Nifty")
    nc.font = font(bold=True, size=9, color=GREEN_D)
    nc.fill = fill(GREEN_H)
    nc.alignment = align(h="center", wrap=True)
    nc.border = border_thin()
    ws.row_dimensions[r].height = 30

build_dashboard(ws_dash)

# ─── 7. SLIPPAGE TRACKER ────────────────────────────────────────────────────
ws_sl = wb.create_sheet("Slippage_Tracker")

def build_slippage(ws):
    ws.sheet_view.showGridLines = False
    widths = [5, 12, 8, 10, 11, 11, 10, 11, 9, 9]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.merge_cells("A1:J1")
    t = ws['A1']
    t.value = "SLIPPAGE TRACKER  —  Compare simulated vs actual fills"
    t.font = font(bold=True, size=13, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:J2")
    s = ws['A2']
    s.value = ("For each order placed, enter the previous close and actual fill price. "
               "Slippage auto-calculates. Target: average slippage < 0.40%. "
               "Model assumption: 0.20%.")
    s.font = font(italic=True, size=9, color=GREY_D)
    s.fill = fill(LTBLUE2)
    s.alignment = align(h="center", wrap=True)
    ws.row_dimensions[2].height = 20

    hdrs = ["#", "Date", "Symbol", "Side", "Prev Close\n(Rs)", "Actual Fill\n(Rs)",
            "Qty", "Trade Value\n(Rs)", "Slippage\n%", "vs Model\n(0.20%)"]
    for ci, h in enumerate(hdrs, 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = font(bold=True, size=9, color=WHITE)
        c.fill = fill(BLUE2)
        c.alignment = align(h="center", v="center", wrap=True)
        c.border = border_thin()
    ws.row_dimensions[3].height = 32

    for i in range(40):
        r = i + 4
        bg = GREY_H if i % 2 == 1 else WHITE
        formula_cell(ws, r, 1, f'=IF(B{r}="","",ROW()-3)', fmt=FMT_INT, bg=bg, h="center")
        c = ws.cell(row=r, column=2)
        c.fill = fill(YELLOW); c.font = font(color=BLUE_IN, bold=True)
        c.alignment = align(h="center"); c.border = border_thin()
        c.number_format = FMT_DATE
        input_cell(ws, r, 3, h="center")
        dv = DataValidation(type="list", formula1='"BUY,SELL"', allow_blank=True)
        ws.add_data_validation(dv)
        sc = input_cell(ws, r, 4, h="center"); dv.add(sc)
        input_cell(ws, r, 5, fmt=FMT_RS, h="right")
        input_cell(ws, r, 6, fmt=FMT_RS, h="right")
        input_cell(ws, r, 7, fmt=FMT_INT, h="center")
        formula_cell(ws, r, 8, f'=IF(OR(E{r}="",G{r}=""),"",E{r}*G{r})', fmt=FMT_RS0, bg=bg)
        formula_cell(ws, r, 9, f'=IF(OR(E{r}="",F{r}=""),"",ABS(F{r}/E{r}-1))', fmt=FMT_PCT2, bg=bg)
        formula_cell(ws, r, 10, f'=IF(I{r}="","",I{r}-0.002)', fmt=FMT_PCT2, bg=bg)

    sr = 45
    ws.merge_cells(f"A{sr}:J{sr}")
    ws[f'A{sr}'].value = "SLIPPAGE SUMMARY"
    ws[f'A{sr}'].font = font(bold=True, color=WHITE)
    ws[f'A{sr}'].fill = fill(BLUE2)
    ws[f'A{sr}'].alignment = align(h="center")
    ws[f'A{sr}'].border = border_thin()

    sumrows2 = [
        ("Total orders tracked", f'=COUNTA(B4:B43)', FMT_INT),
        ("Average actual slippage %", f'=IFERROR(AVERAGE(I4:I43),"")', FMT_PCT2),
        ("Maximum slippage % (single order)", f'=IFERROR(MAX(I4:I43),"")', FMT_PCT2),
        ("Orders with slippage > 0.40%", f'=COUNTIF(I4:I43,">"&0.004)', FMT_INT),
        ("Model assumption", "0.20%", FMT_PCT2, "hardcode"),
        ("Average excess over model", f'=IFERROR(AVERAGE(J4:J43),"")', FMT_PCT2),
        ("STATUS", f'=IF(B{sr+2}="","Awaiting data",IF(B{sr+2}<=0.004,"OK — avg slippage within model","⚠ REVIEW — avg slippage exceeds model"))', None),
    ]
    for j, row_data in enumerate(sumrows2):
        r = sr + 1 + j
        bg2 = LTBLUE2 if j % 2 == 0 else WHITE
        lbl = row_data[0]
        frm = row_data[1]
        fmt = row_data[2] if len(row_data) > 2 else None
        kind = row_data[3] if len(row_data) > 3 else "formula"
        data_cell(ws, r, 1, lbl, bold=True, bg=bg2, h="left")
        ws.merge_cells(f"A{r}:B{r}")
        if kind == "hardcode":
            c = ws.cell(row=r, column=3, value=0.002)
            c.font = font(color=BLUE_IN, bold=True)
            c.fill = fill(bg2)
            c.alignment = align(h="right")
            c.border = border_thin()
            if fmt: c.number_format = fmt
        else:
            c = ws.cell(row=r, column=3, value=frm)
            c.font = font(color=FORMULA)
            c.fill = fill(bg2)
            c.alignment = align(h="right")
            c.border = border_thin()
            if fmt: c.number_format = fmt
        for ci in range(4, 11):
            ws.cell(row=r, column=ci).border = border_thin()
            ws.cell(row=r, column=ci).fill = fill(bg2)

    freeze(ws, 4, 3)

build_slippage(ws_sl)

# ─── 8. DAILY CHECKLIST ─────────────────────────────────────────────────────
ws_dc = wb.create_sheet("Daily_Checklist")

def build_daily_checklist(ws):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 60
    ws.column_dimensions['C'].width = 20

    ws.merge_cells("A1:C1")
    t = ws['A1']
    t.value = "DAILY OPERATOR CHECKLIST  —  Target: Under 10 minutes  |  Before 9:10 AM"
    t.font = font(bold=True, size=13, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:C2")
    s = ws['A2']
    s.value = "Strategy: RS=60% / EP=40% / Top-10 / Rebal 10d / SL 10% / Policy C"
    s.font = font(italic=True, bold=True, size=10, color=BLUE2)
    s.fill = fill(LTBLUE2)
    s.alignment = align(h="center")

    steps = [
        # (section_title, [(tick, step_text, time_note)])
        ("STEP 1 — REGIME CHECK  (~2 min)", [
            ("☐", "Open NSE website or yfinance. Get yesterday's Nifty 50 close.", ""),
            ("☐", "Calculate 50-DMA (or read from script). Enter in Daily_Ops_Log col D.", ""),
            ("☐", "Calculate 200-DMA (or read from script). Enter in Daily_Ops_Log col E.", ""),
            ("☐", "Read regime from col G (auto-classifies):  BULL / FLAT / BEAR", ""),
            ("☐", "Log: Date | Nifty | 50DMA | 200DMA | Regime", ""),
        ]),
        ("STEP 2 — BEAR GATE  (~1 min)", [
            ("☐", "If BEAR AND open positions exist → place market SELL orders for ALL positions at 9:15 AM open. Record in Trade Log with Exit Reason = Regime.", "CRITICAL"),
            ("☐", "If BEAR AND no positions → hold cash. Skip to Step 5.", ""),
            ("☐", "If BULL or FLAT → proceed to Step 3.", ""),
        ]),
        ("STEP 3 — STOP-LOSS CHECK  (~3 min)", [
            ("☐", "Open Position_Log. Update col F (Current Close) for every open position.", ""),
            ("☐", "Check col K (Status). Look for *** SL TRIGGERED *** or APPROACHING SL.", ""),
            ("☐", "If SL triggered: place market SELL order for that position at 9:15 AM open.", ""),
            ("☐", "Record SL exits in Trade Log. Exit Reason = SL.", ""),
            ("☐", "Record symbol in Daily_Ops_Log col J (SL Exits Today).", ""),
        ]),
        ("STEP 4 — ORDER CONFIRMATION  (~2 min)", [
            ("☐", "Confirm all orders from yesterday are filled in broker platform.", ""),
            ("☐", "If any order is pending or partial: resolve manually. Do not place new orders.", ""),
            ("☐", "Record actual fill prices in Position_Log (not order price).", ""),
        ]),
        ("STEP 5 — REBALANCE CHECK  (~1 min)", [
            ("☐", "Check Daily_Ops_Log col L. Is today marked REBAL?", ""),
            ("☐", "If YES and regime is BULL/FLAT → run full Rebalance Checklist (separate sheet).", ""),
            ("☐", "If YES and regime is BEAR → skip rebalance. Log in Rebalance_Log as Skipped=YES.", ""),
            ("☐", "If NO → no further action needed today.", ""),
        ]),
        ("STEP 6 — END-OF-DAY LOG  (~1 min)", [
            ("☐", "Enter portfolio value in Daily_Ops_Log col H (cash + positions at close).", ""),
            ("☐", "Confirm col I shows daily P&L (auto-calculates from previous row).", ""),
            ("☐", "Add any notes in col M (data issues, manual interventions, anomalies).", ""),
        ]),
    ]

    r = 4
    for sec, items in steps:
        ws.merge_cells(f"A{r}:C{r}")
        hc = ws[f'A{r}']
        hc.value = sec
        hc.font = font(bold=True, size=10, color=WHITE)
        hc.fill = fill(BLUE2)
        hc.alignment = align(h="left")
        hc.border = border_thin()
        ws.row_dimensions[r].height = 18
        r += 1
        for tick, text, note in items:
            bg = RED_H if note == "CRITICAL" else (ORANGE_H if note == "WARNING" else (GREY_H if r % 2 == 0 else WHITE))
            tc = ws.cell(row=r, column=1, value=tick)
            tc.font = font(size=12, bold=True, color=NAVY)
            tc.fill = fill(bg)
            tc.alignment = align(h="center")
            tc.border = border_thin()
            bc = ws.cell(row=r, column=2, value=text)
            bc.font = font(size=10, color=RED_D if note == "CRITICAL" else BLACK, bold=(note == "CRITICAL"))
            bc.fill = fill(bg)
            bc.alignment = align(h="left", wrap=True)
            bc.border = border_thin()
            nc2 = ws.cell(row=r, column=3, value=note)
            nc2.font = font(size=9, color=RED_D if note == "CRITICAL" else GREY_D, bold=(note=="CRITICAL"))
            nc2.fill = fill(bg)
            nc2.alignment = align(h="center")
            nc2.border = border_thin()
            ws.row_dimensions[r].height = 22
            r += 1
        r += 1

    # Quick regime reminder at bottom
    ws.merge_cells(f"A{r}:C{r}")
    regime_note = ws[f'A{r}']
    regime_note.value = ("REGIME RULES:  BULL = Nifty>200DMA AND 50DMA>200DMA  |  "
                         "FLAT = Nifty>200DMA AND 50DMA≤200DMA  |  "
                         "BEAR = Nifty<200DMA  →  CASH ONLY")
    regime_note.font = font(bold=True, size=9, color=BLUE2)
    regime_note.fill = fill(LTBLUE)
    regime_note.alignment = align(h="center", wrap=True)
    regime_note.border = border_thin()
    ws.row_dimensions[r].height = 28

build_daily_checklist(ws_dc)

# ─── 9. REBALANCE CHECKLIST ─────────────────────────────────────────────────
ws_rc = wb.create_sheet("Rebalance_Checklist")

def build_rebalance_checklist(ws):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 62
    ws.column_dimensions['C'].width = 18

    ws.merge_cells("A1:C1")
    t = ws['A1']
    t.value = "REBALANCE-DAY CHECKLIST  —  Every 10th trading day from last rebalance"
    t.font = font(bold=True, size=13, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:C2")
    s = ws['A2']
    s.value = ("Paper trading rebalance days: 2026-06-27 (Day 10)  |  "
               "2026-07-10 (Day 20)  |  2026-07-24 (Day 30)")
    s.font = font(italic=True, bold=True, size=10, color=BLUE2)
    s.fill = fill(LTBLUE2)
    s.alignment = align(h="center")

    steps_rb = [
        ("PRE-REBALANCE GATE", [
            ("☐", "Run Daily Checklist first (steps 1–4). Confirm regime before proceeding.", "Do first"),
            ("☐", "If BEAR regime → do NOT rebalance. Log Rebalance_Log: Skipped=YES. STOP.", "CRITICAL"),
            ("☐", "If BULL or FLAT → continue below.", ""),
        ]),
        ("DATA DOWNLOAD  (~3 min)", [
            ("☐", "Run final_validation.py (or download 134 stock closes from yfinance).", ""),
            ("☐", "Verify data: confirm 130+ stocks returned valid closes.", ""),
            ("☐", "Flag any stock with price = 0 or missing — exclude from ranking this cycle.", ""),
        ]),
        ("FACTOR COMPUTATION  (auto via script)", [
            ("☐", "Script computes RS_raw = (stock 63d return) - (Nifty 63d return) for each stock.", ""),
            ("☐", "Script computes EP_raw = max gap-day return >2% with volume >1.5x avg in 63d.", ""),
            ("☐", "Script percentile-ranks both factors (0-100). Composite = 0.60×RS + 0.40×EP.", ""),
            ("☐", "Read the top-10 stocks from script output. Paste into Rebalance_Log col E.", ""),
        ]),
        ("DETERMINE TRADES  (~2 min)", [
            ("☐", "List current holdings from Position_Log.", ""),
            ("☐", "EXITS: stocks in current holdings NOT in new top-10 → queue sell.", ""),
            ("☐", "ENTRIES: stocks in new top-10 NOT currently held → queue buy.", ""),
            ("☐", "HOLDS: stocks in both → no action.", ""),
            ("☐", "Record exits and entries in Rebalance_Log cols F and G.", ""),
        ]),
        ("POSITION SIZING  (~2 min)", [
            ("☐", "Available cash = current cash - Rs.25,000 buffer.", ""),
            ("☐", "Per-position allocation = min(available_cash ÷ N_new_entries,  Rs.50,000).", ""),
            ("☐", "Shares to buy = floor(allocation ÷ yesterday's close).", ""),
            ("☐", "Verify total outlay ≤ available cash before placing orders.", ""),
        ]),
        ("ORDER PLACEMENT  (9:15 AM tomorrow)", [
            ("☐", "Place all EXIT (sell) orders first — market CNC.", ""),
            ("☐", "Wait 2 minutes.", ""),
            ("☐", "Place all ENTRY (buy) orders — market CNC.", "DO NOT use limit orders"),
            ("☐", "Record all order IDs.", ""),
        ]),
        ("POST-FILL UPDATE  (~3 min after 9:30 AM)", [
            ("☐", "Confirm all orders filled in broker platform.", ""),
            ("☐", "Record actual fill prices in Position_Log (new cost basis).", ""),
            ("☐", "Update SL level for each new entry: fill_price × 0.90 (auto-calculates).", ""),
            ("☐", "Add completed trade records to Trade_Log for each exit.", ""),
            ("☐", "Record actual fill prices in Slippage_Tracker for every buy and sell.", ""),
            ("☐", "Update Rebalance_Log: Cash Before, Cash After, Turnover %.", ""),
            ("☐", "Set next rebalance date = today + 10 trading days.", ""),
        ]),
    ]

    r = 4
    for sec, items in steps_rb:
        ws.merge_cells(f"A{r}:C{r}")
        hc = ws[f'A{r}']
        hc.value = sec
        hc.font = font(bold=True, size=10, color=WHITE)
        hc.fill = fill(BLUE2)
        hc.alignment = align(h="left")
        hc.border = border_thin()
        ws.row_dimensions[r].height = 18
        r += 1
        for tick, text, note in items:
            bg = RED_H if note == "CRITICAL" else (ORANGE_H if "DO NOT" in note else (GREY_H if r % 2 == 0 else WHITE))
            tc = ws.cell(row=r, column=1, value=tick)
            tc.font = font(size=12, bold=True, color=NAVY)
            tc.fill = fill(bg)
            tc.alignment = align(h="center")
            tc.border = border_thin()
            bc = ws.cell(row=r, column=2, value=text)
            bc.font = font(size=10, color=RED_D if note == "CRITICAL" else BLACK, bold=(note == "CRITICAL"))
            bc.fill = fill(bg)
            bc.alignment = align(h="left", wrap=True)
            bc.border = border_thin()
            nc2 = ws.cell(row=r, column=3, value=note)
            nc2.font = font(size=9, color=RED_D if note == "CRITICAL" else ORANGE_D if "DO NOT" in note else GREY_D)
            nc2.fill = fill(bg)
            nc2.alignment = align(h="center", wrap=True)
            nc2.border = border_thin()
            ws.row_dimensions[r].height = 22
            r += 1
        r += 1

build_rebalance_checklist(ws_rc)

# ─── 10. EMERGENCY CARD ─────────────────────────────────────────────────────
ws_e = wb.create_sheet("Emergency_Card")

def build_emergency(ws):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 58

    ws.merge_cells("A1:B1")
    t = ws['A1']
    t.value = "WHAT TO DO IF SOMETHING BREAKS  —  MoneyBot RS60/EP40"
    t.font = font(bold=True, size=14, color=WHITE)
    t.fill = fill(NAVY)
    t.alignment = align(h="center", v="center")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:B2")
    s = ws['A2']
    s.value = "Print this page and keep it at your desk. Strategy is FROZEN — do not change any parameter."
    s.font = font(bold=True, size=10, color=RED_D)
    s.fill = fill(RED_H)
    s.alignment = align(h="center")

    scenarios = [
        ("DATA DOWNLOAD FAILS\n(yfinance returns no data)", RED_H, RED_D,
         "1. Retry after 30 min.\n"
         "2. If still failing — SKIP rebalance (if rebal day). Do not trade on bad data.\n"
         "3. Apply SL check manually using yesterday's prices (check NSEIndia.com).\n"
         "4. Log the skip. Resume tomorrow."),
        ("BROKER ORDER NOT PLACED\n(order missing from platform)", ORANGE_H, ORANGE_D,
         "1. Do NOT retry automatically.\n"
         "2. Log in to Zerodha Kite manually.\n"
         "3. Verify order status. If not placed: place manually before 9:30 AM.\n"
         "4. If duplicate exists: cancel duplicates immediately.\n"
         "5. Record all manual actions with timestamp."),
        ("STOCK OPENS BELOW SL\n(gap-down past stop-loss)", ORANGE_H, ORANGE_D,
         "1. Accept the fill at the market open price. Do NOT hold hoping for recovery.\n"
         "2. Record actual fill vs SL level as gap-down slippage.\n"
         "3. No action on SL model unless this happens >3 times in 60 days."),
        ("REGIME CLASSIFIED WRONG\n(you entered wrong DMA values)", ORANGE_H, ORANGE_D,
         "Bear→Bull error (invested when should be in cash):\n"
         "  → Exit ALL positions at next open. Do not make back Bear regime days.\n"
         "Bull→Bear error (in cash when should be invested):\n"
         "  → Wait until next rebalance. Do not chase missed entry.\n"
         "  → Log the error and root cause."),
        ("CORPORATE ACTION\n(split, bonus, merger, delisting)", LTBLUE, BLUE2,
         "Split / Bonus: Adjust cost basis (new = old ÷ ratio). Adjust qty and SL.\n"
         "Merger / Delisting: Exit at next open. Remove from universe list.\n"
         "Rights issue: Do not subscribe. SL check handles price impact."),
        ("PORTFOLIO DOWN >20% FROM PEAK\n[CRITICAL — AUTO-SHUTDOWN TRIGGER]", RED_H, RED_D,
         "1. EXIT ALL positions at next open. No exceptions.\n"
         "2. Stop all trading for 30 calendar days.\n"
         "3. During pause: run deployment_verification.py on latest 2-year data.\n"
         "   → Fresh OOS PF >1.10: resume after 30 days.\n"
         "   → Fresh OOS PF <1.05: do NOT resume. Full re-validation required.\n"
         "4. Do not shorten the 30-day pause even if market recovers."),
        ("3 CONSECUTIVE LOSING REBALANCES", ORANGE_H, ORANGE_D,
         "1. Do NOT stop trading. This is within normal variance.\n"
         "2. Compute rolling 30-day PF from Trade_Log.\n"
         "   → PF >0.85: continue. Log the flag.\n"
         "   → PF <0.85: raise red flag. Run deployment_verification.py.\n"
         "3. Do NOT change strategy parameters based on a losing streak."),
        ("MARKET-WIDE CIRCUIT BREAKER\n(SEBI halts trading)", LTBLUE, BLUE2,
         "1. Do not place any orders during market halt.\n"
         "2. Wait for normal trading to resume.\n"
         "3. On next trading day: run full Daily Checklist from Step 1.\n"
         "4. SL and regime checks take priority over everything else."),
    ]

    r = 4
    for title, bg, fg, action in scenarios:
        # Title cell
        tc = ws.cell(row=r, column=1, value=title)
        tc.font = font(bold=True, size=10, color=fg)
        tc.fill = fill(bg)
        tc.alignment = align(h="left", v="center", wrap=True)
        tc.border = border_thin()
        # Action cell
        ac = ws.cell(row=r, column=2, value=action)
        ac.font = font(size=10, color=BLACK)
        ac.fill = fill(bg)
        ac.alignment = align(h="left", v="center", wrap=True)
        ac.border = border_thin()
        ws.row_dimensions[r].height = max(60, action.count('\n') * 18 + 20)
        r += 1

    # Permanent rules
    ws.merge_cells(f"A{r}:B{r}")
    pr = ws[f'A{r}']
    pr.value = "PERMANENT RULES — NEVER VIOLATE"
    pr.font = font(bold=True, size=11, color=WHITE)
    pr.fill = fill(RED_D)
    pr.alignment = align(h="center")
    pr.border = border_thin()
    ws.row_dimensions[r].height = 20
    r += 1

    rules = [
        "Do NOT trade in Bear regime (Nifty < 200DMA).",
        "Do NOT change RS/EP weights, Top-N, SL%, or rebalance cadence without full re-validation.",
        "Do NOT use limit orders — strategy is modelled on market fills.",
        "Do NOT trade on bad or stale data — skip the day and log it.",
        "Do NOT reduce the 30-day suspension after a >20% drawdown.",
    ]
    for rule in rules:
        c1 = ws.cell(row=r, column=1, value="⛔")
        c1.font = font(bold=True, size=12, color=RED_D)
        c1.fill = fill(RED_H)
        c1.alignment = align(h="center")
        c1.border = border_thin()
        c2 = ws.cell(row=r, column=2, value=rule)
        c2.font = font(bold=True, size=10, color=RED_D)
        c2.fill = fill(RED_H)
        c2.alignment = align(h="left", wrap=True)
        c2.border = border_thin()
        ws.row_dimensions[r].height = 22
        r += 1

    r += 1
    # Quick ref
    ws.merge_cells(f"A{r}:B{r}")
    qr = ws[f'A{r}']
    qr.value = (
        "STRATEGY FROZEN:  RS=60% | EP=40% | Top-10 | Rebal 10d | SL 10% | Policy C  "
        "||  CURRENT STATE (Jun 2026): BEAR — hold cash — re-entry when Nifty > 200DMA  "
        "||  VALIDATED OOS: PF 1.349 | CAGR +5.7% | Sharpe 0.507 | MaxDD 13.8%"
    )
    qr.font = font(bold=True, size=9, color=GREEN_D)
    qr.fill = fill(GREEN_H)
    qr.alignment = align(h="center", wrap=True)
    qr.border = border_thin()
    ws.row_dimensions[r].height = 36

build_emergency(ws_e)

# ─── Save ────────────────────────────────────────────────────────────────────
wb.save(OUT)
print(f"Saved: {OUT}")
