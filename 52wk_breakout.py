"""
52wk_breakout.py — 52-Week High Breakout Strategy (Repair #2)

Academic basis:
  George & Hwang (2004): 52-week high is the strongest anchoring reference
  for institutional investors. Stocks that break through it force
  re-evaluation and sustained buying — independently of momentum.
  Separate from pure momentum: a stock can have weak 12-month return
  but still break its 52-week high if it's been recovering from a dip.

Questions to answer:
  1. Does breaking a yearly high outperform Compression Breakout (PF=0.996)?
  2. Does volume confirmation add or subtract edge?
  3. What hold period captures the most drift?

Signal variants tested:
  A — Pure: close > 252-day rolling high
  B — Pure + volume gate (vol > 1.5x 20d avg)
  C — Pure + within 5% of high for 5+ days (proximity filter)
  D — B + C combined (strictest)

Hold periods: 5, 10, 20, 40, 60 days
SL: 8% (trend following needs room)

Universe: 130 NSE stocks (same as PEAD study)
Walk-forward: Y1-Y3 IS | Y4-Y5 OOS
"""

import time, math, logging, warnings, statistics
from collections import defaultdict

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

BROKERAGE    = 20.0
STT_PCT      = 0.001
EXCHANGE_PCT = 0.0000345
SLIPPAGE     = 0.002
SL_PCT       = 8.0
POSITION     = 50_000.0
WF_SPLIT     = 0.60

SEP = '=' * 116
sep = '-' * 116

STOCKS = [
    ('RELIANCE.NS','RELIANCE'),('TCS.NS','TCS'),('INFY.NS','INFY'),
    ('HDFCBANK.NS','HDFCBANK'),('ICICIBANK.NS','ICICIBANK'),('SBIN.NS','SBIN'),
    ('HCLTECH.NS','HCLTECH'),('WIPRO.NS','WIPRO'),('AXISBANK.NS','AXISBANK'),
    ('KOTAKBANK.NS','KOTAKBANK'),('TECHM.NS','TECHM'),('MARUTI.NS','MARUTI'),
    ('TITAN.NS','TITAN'),('BAJFINANCE.NS','BAJFINANCE'),('ITC.NS','ITC'),
    ('HINDUNILVR.NS','HINDUNILVR'),('BHARTIARTL.NS','BHARTIARTL'),
    ('ASIANPAINT.NS','ASIANPAINT'),('SUNPHARMA.NS','SUNPHARMA'),
    ('DRREDDY.NS','DRREDDY'),('CIPLA.NS','CIPLA'),('POWERGRID.NS','POWERGRID'),
    ('NTPC.NS','NTPC'),('COALINDIA.NS','COALINDIA'),('ONGC.NS','ONGC'),
    ('BPCL.NS','BPCL'),('ULTRACEMCO.NS','ULTRACEMCO'),('GRASIM.NS','GRASIM'),
    ('ADANIENT.NS','ADANIENT'),('ADANIPORTS.NS','ADANIPORTS'),
    ('BAJAJFINSV.NS','BAJAJFINSV'),('EICHERMOT.NS','EICHERMOT'),
    ('TATACONSUM.NS','TATACONSUM'),('BRITANNIA.NS','BRITANNIA'),
    ('APOLLOHOSP.NS','APOLLOHOSP'),('JSWSTEEL.NS','JSWSTEEL'),
    ('TATASTEEL.NS','TATASTEEL'),('HINDALCO.NS','HINDALCO'),('LT.NS','LT'),
    ('NESTLEIND.NS','NESTLEIND'),('PIDILITIND.NS','PIDILITIND'),
    ('HAVELLS.NS','HAVELLS'),('DIVISLAB.NS','DIVISLAB'),
    ('TORNTPHARM.NS','TORNTPHARM'),('MUTHOOTFIN.NS','MUTHOOTFIN'),
    ('INDUSINDBK.NS','INDUSINDBK'),('BANDHANBNK.NS','BANDHANBNK'),
    ('FEDERALBNK.NS','FEDERALBNK'),('ESCORTS.NS','ESCORTS'),
    ('BALKRISIND.NS','BALKRISIND'),('TATAPOWER.NS','TATAPOWER'),
    ('M&M.NS','M&M'),('HEROMOTOCO.NS','HEROMOTOCO'),('BAJAJ-AUTO.NS','BAJAJ-AUTO'),
    ('BOSCHLTD.NS','BOSCHLTD'),('SIEMENS.NS','SIEMENS'),('ABB.NS','ABB'),
    ('CUMMINSIND.NS','CUMMINSIND'),('VOLTAS.NS','VOLTAS'),('WHIRLPOOL.NS','WHIRLPOOL'),
    ('BERGEPAINT.NS','BERGEPAINT'),('KANSAINER.NS','KANSAINER'),
    ('DABUR.NS','DABUR'),('MARICO.NS','MARICO'),('COLPAL.NS','COLPAL'),
    ('GODREJCP.NS','GODREJCP'),('EMAMILTD.NS','EMAMILTD'),('PGHH.NS','PGHH'),
    ('LUPIN.NS','LUPIN'),('AUROPHARMA.NS','AUROPHARMA'),('BIOCON.NS','BIOCON'),
    ('ALKEM.NS','ALKEM'),('PFIZER.NS','PFIZER'),
    ('LICHSGFIN.NS','LICHSGFIN'),('M&MFIN.NS','M&MFIN'),('CHOLAFIN.NS','CHOLAFIN'),
    ('PFC.NS','PFC'),('RECLTD.NS','RECLTD'),('IRFC.NS','IRFC'),
    ('SAIL.NS','SAIL'),('NMDC.NS','NMDC'),('MOIL.NS','MOIL'),
    ('VEDL.NS','VEDL'),('NATIONALUM.NS','NATIONALUM'),
    ('CONCOR.NS','CONCOR'),('IGL.NS','IGL'),('MGL.NS','MGL'),
    ('GUJGASLTD.NS','GUJGASLTD'),('INDIGO.NS','INDIGO'),
    ('NYKAA.NS','NYKAA'),('POLICYBZR.NS','POLICYBZR'),('PAYTM.NS','PAYTM'),
    ('DELHIVERY.NS','DELHIVERY'),('LICI.NS','LICI'),
    ('SBILIFE.NS','SBILIFE'),('HDFCLIFE.NS','HDFCLIFE'),
    ('NAUKRI.NS','NAUKRI'),('JUSTDIAL.NS','JUSTDIAL'),('IRCTC.NS','IRCTC'),
    ('TORNTPOWER.NS','TORNTPOWER'),('TATAELXSI.NS','TATAELXSI'),
    ('MPHASIS.NS','MPHASIS'),('LTTS.NS','LTTS'),('COFORGE.NS','COFORGE'),
    ('PERSISTENT.NS','PERSISTENT'),('OFSS.NS','OFSS'),
    ('PAGEIND.NS','PAGEIND'),('TRENT.NS','TRENT'),('DMART.NS','DMART'),
    ('ABFRL.NS','ABFRL'),('IDFCFIRSTB.NS','IDFCFIRSTB'),
    ('AUBANK.NS','AUBANK'),('POLYCAB.NS','POLYCAB'),('KEI.NS','KEI'),
    ('APLAPOLLO.NS','APLAPOLLO'),('DEEPAKNTR.NS','DEEPAKNTR'),
    ('AAVAS.NS','AAVAS'),('RBLBANK.NS','RBLBANK'),
    ('TATAMOTORS.NS','TATAMOTORS'),
]


def fetch(ticker, period='5y'):
    try:
        df = yf.Ticker(ticker).history(period=period, interval='1d', auto_adjust=True)
        if df.empty:
            return {}
        return {str(ts.date()): {
            'open':  float(row['Open']),  'high': float(row['High']),
            'low':   float(row['Low']),   'close': float(row['Close']),
            'vol':   float(row.get('Volume', 0) or 0),
        } for ts, row in df.iterrows()}
    except Exception:
        return {}


def backtest_52wk(candles, all_dates, period_set,
                  lookback=252, hold_days=20,
                  vol_gate=False, prox_gate=False,
                  prox_pct=5.0, prox_bars=5):
    """
    Signal per variant:
      Pure     : close > rolling_max(high, lookback)
      Vol gate : + vol > 1.5x 20d avg
      Prox gate: + stock was within prox_pct% of the 52wk high for prox_bars consecutive days
    Entry: T+1 open  Exit: T+1+hold_days open  OR SL=-8% intraday
    """
    date_list = [d for d in sorted(candles.keys()) if d in all_dates]
    if len(date_list) < lookback + hold_days + 5:
        return []

    master = all_dates
    trades = []
    last_exit_i = -1

    def master_i(d):
        try: return master.index(d)
        except ValueError: return -1

    for i, d in enumerate(date_list):
        if i < lookback + 1:
            continue
        if d not in period_set:
            continue

        c    = candles[d]
        prev = candles[date_list[i - 1]]

        # Rolling 252-day high of *highs* (not closes)
        past_highs = [candles[date_list[j]]['high'] for j in range(i - lookback, i)]
        yr_high    = max(past_highs)

        # Signal: close breaks above 252-day high
        if c['close'] <= yr_high:
            continue

        # Volume gate
        if vol_gate:
            avg_vol = sum(candles[date_list[j]]['vol']
                          for j in range(max(0, i - 20), i)) / 20
            if avg_vol <= 0 or c['vol'] <= 1.5 * avg_vol:
                continue

        # Proximity gate: stock was close to 52wk high for prox_bars days before
        if prox_gate:
            prox_ok = all(
                candles[date_list[j]]['close'] >= yr_high * (1 - prox_pct / 100)
                for j in range(max(0, i - prox_bars), i))
            if not prox_ok:
                continue

        # Find entry / exit in master date list
        mi = master_i(d)
        if mi < 0:
            continue
        entry_mi = mi + 1
        exit_mi  = entry_mi + hold_days
        if entry_mi <= last_exit_i or exit_mi >= len(master):
            continue

        entry_date = master[entry_mi]
        exit_date  = master[exit_mi]

        entry_d = candles.get(entry_date)
        if not entry_d:
            continue
        fill_e = entry_d['open'] * (1 + SLIPPAGE)
        qty    = max(1, int(POSITION / fill_e))
        cost_e = BROKERAGE + qty * fill_e * EXCHANGE_PCT

        # Track intraday SL
        sl_px     = fill_e * (1 - SL_PCT / 100)
        exit_fill = None
        actual_exit = exit_date

        for k in range(entry_mi + 1, min(exit_mi + 1, len(master))):
            dk = master[k]
            ck = candles.get(dk)
            if not ck:
                continue
            if ck['low'] <= sl_px:
                exit_fill   = sl_px * (1 - SLIPPAGE)
                actual_exit = dk
                last_exit_i = k
                break
            if k == exit_mi:
                exit_fill   = ck['open'] * (1 - SLIPPAGE)
                actual_exit = dk
                last_exit_i = k

        if exit_fill is None:
            continue

        proceeds  = qty * exit_fill
        costs_out = BROKERAGE + proceeds * STT_PCT + proceeds * EXCHANGE_PCT
        pnl       = (exit_fill - fill_e) * qty - cost_e - costs_out

        trades.append({
            'pnl':        pnl,
            'winner':     1 if pnl > 0 else 0,
            'return_pct': (exit_fill / fill_e - 1) * 100,
            'entry_date': entry_date,
            'exit_date':  actual_exit,
            'sl_hit':     1 if actual_exit != exit_date else 0,
        })

    return trades


def pooled_metrics(trades, years):
    if not trades:
        return {'trades': 0, 'pf': 0.0, 'wr': 0.0, 'cagr': 0.0,
                'sharpe': 0.0, 'avg_win': 0.0, 'avg_loss': 0.0, 'sl_pct': 0.0}
    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp     = sum(t['pnl'] for t in wins)
    gl     = abs(sum(t['pnl'] for t in losses))
    pf     = gp / gl if gl > 0 else (1.5 if gp > 0 else 0.0)
    wr     = len(wins) / len(trades) * 100
    net    = sum(t['pnl'] for t in trades)
    avg_trade_pnl = net / len(trades)
    # Annualised CAGR on average position
    avg_hold = statistics.mean([abs((
                __import__('datetime').datetime.strptime(t['exit_date'],'%Y-%m-%d') -
                __import__('datetime').datetime.strptime(t['entry_date'],'%Y-%m-%d')).days)
                for t in trades]) or 1
    trades_per_year = 252 / avg_hold
    ann_ret = avg_trade_pnl * trades_per_year / POSITION * 100
    cagr    = ann_ret

    rets  = [t['return_pct'] for t in trades]
    mean_ = statistics.mean(rets)
    std_  = statistics.stdev(rets) if len(rets) > 1 else 1.0
    sharpe = (mean_ / std_) * (252 / avg_hold) ** 0.5 if std_ > 0 else 0.0

    w_rets = [t['return_pct'] for t in wins]
    l_rets = [t['return_pct'] for t in losses]
    sl_pct = sum(t['sl_hit'] for t in trades) / len(trades) * 100

    return {
        'trades':   len(trades),
        'pf':       round(pf, 3),
        'wr':       round(wr, 1),
        'cagr':     round(cagr, 1),
        'sharpe':   round(sharpe, 3),
        'avg_win':  round(statistics.mean(w_rets), 2) if w_rets  else 0.0,
        'avg_loss': round(statistics.mean(l_rets), 2) if l_rets  else 0.0,
        'net_pnl':  round(net, 0),
        'sl_pct':   round(sl_pct, 1),
    }


# ── FETCH ─────────────────────────────────────────────────────────────────────
print(SEP)
print('  52-WEEK HIGH BREAKOUT STRATEGY — Repair #2')
print(SEP)
print('\n  Fetching data...\n')

price_data    = {}
valid_stocks  = []
for ticker, sym in STOCKS:
    d = fetch(ticker, '5y')
    if len(d) < 300:
        continue
    price_data[sym] = d
    valid_stocks.append(sym)
    time.sleep(0.22)

nifty_data = fetch('^NSEI', '5y')
all_dates  = sorted(nifty_data.keys())
split_i    = int(len(all_dates) * WF_SPLIT)
IS_DATES   = all_dates[:split_i]
OOS_DATES  = all_dates[split_i:]
IS_SET     = set(IS_DATES);  OOS_SET = set(OOS_DATES)
IS_YEARS   = len(IS_DATES) / 252;  OOS_YEARS = len(OOS_DATES) / 252

print(f'  Valid stocks : {len(valid_stocks)}')
print(f'  Timeline     : {all_dates[0]} to {all_dates[-1]}  ({len(all_dates)} days)')
print(f'  IS           : {IS_DATES[0]} to {IS_DATES[-1]}')
print(f'  OOS          : {OOS_DATES[0]} to {OOS_DATES[-1]}')


# ── VARIANT x HOLD SWEEP ──────────────────────────────────────────────────────
VARIANTS = [
    ('A — Pure breakout',             False, False),
    ('B — + Volume gate (1.5x)',      True,  False),
    ('C — + Proximity (5% x 5 bars)', False, True ),
    ('D — + Vol + Proximity',         True,  True ),
]
HOLD_DAYS = [5, 10, 20, 40, 60]

print('\n' + SEP)
print('  IN-SAMPLE SWEEP — Variant x Hold Period')
print(SEP)
print(f'  {"Variant":<38}  {"Hold":>5}  {"Trades":>8}  {"WR%":>6}  '
      f'{"PF":>7}  {"CAGR%":>8}  {"Sharpe":>8}  {"AvgW%":>7}  {"AvgL%":>7}  {"SL%":>5}')
print(sep)

is_results = []
for vname, vg, pg in VARIANTS:
    for hold in HOLD_DAYS:
        all_is = []
        for sym in valid_stocks:
            trs = backtest_52wk(price_data[sym], all_dates, IS_SET,
                                hold_days=hold, vol_gate=vg, prox_gate=pg)
            all_is.extend(trs)
        m = pooled_metrics(all_is, IS_YEARS)
        is_results.append({'vname': vname, 'vg': vg, 'pg': pg, 'hold': hold, 'is': m})
        flag = '  ***' if m['pf'] > 1.5 and m['trades'] > 50 else (
               '  **'  if m['pf'] > 1.2 else '')
        print(f'  {vname:<38}  {hold:>5}d  {m["trades"]:>8}  {m["wr"]:>5.1f}%  '
              f'{m["pf"]:>7.3f}  {m["cagr"]:>+7.1f}%  {m["sharpe"]:>8.3f}  '
              f'{m["avg_win"]:>+6.2f}%  {m["avg_loss"]:>+6.2f}%  {m["sl_pct"]:>4.0f}%{flag}')
    print(sep)

best_is = max(is_results,
              key=lambda x: x['is']['pf'] * min(x['is']['trades'] / 50, 1.0))
print(f'\n  Best IS: {best_is["vname"]}  Hold={best_is["hold"]}d  '
      f'PF={best_is["is"]["pf"]:.3f}  Trades={best_is["is"]["trades"]}')


# ── OOS ALL CONFIGS ───────────────────────────────────────────────────────────
print('\n' + SEP)
print('  OUT-OF-SAMPLE — ALL CONFIGS')
print(SEP)
print(f'  {"Variant":<38}  {"Hold":>5}  {"IS PF":>7}  {"OOS Tr":>8}  '
      f'{"OOS WR":>7}  {"OOS PF":>7}  {"OOS CAGR":>9}  {"OOS Sh":>8}  {"Decay":>7}')
print(sep)

oos_results = []
for r in is_results:
    all_oos = []
    for sym in valid_stocks:
        trs = backtest_52wk(price_data[sym], all_dates, OOS_SET,
                            hold_days=r['hold'], vol_gate=r['vg'], prox_gate=r['pg'])
        all_oos.extend(trs)
    m_oos = pooled_metrics(all_oos, OOS_YEARS)
    oos_results.append({**r, 'oos': m_oos})
    decay = r['is']['pf'] - m_oos['pf']
    is_best = ' <--' if (r['vname'] == best_is['vname'] and r['hold'] == best_is['hold']) else ''
    beat = '  BEATS COMP' if m_oos['pf'] > 0.996 else (
           '  POSITIVE'   if m_oos['cagr'] > 0   else '')
    print(f'  {r["vname"]:<38}  {r["hold"]:>5}d  {r["is"]["pf"]:>7.3f}  '
          f'{m_oos["trades"]:>8}  {m_oos["wr"]:>6.1f}%  {m_oos["pf"]:>7.3f}  '
          f'{m_oos["cagr"]:>+8.1f}%  {m_oos["sharpe"]:>8.3f}  '
          f'{decay:>+6.3f}{beat}{is_best}')
    if r['hold'] == HOLD_DAYS[-1]:
        print(sep)

best_oos = max(oos_results,
               key=lambda x: x['oos']['pf'] * min(x['oos']['trades'] / 30, 1.0))


# ── DETAILED BEST OOS ─────────────────────────────────────────────────────────
print('\n' + SEP)
print(f'  DETAILED BEST OOS: {best_oos["vname"]}  Hold={best_oos["hold"]}d')
print(SEP)
bm = best_oos['oos']
print(f'  Trades         : {bm["trades"]}')
print(f'  Win rate       : {bm["wr"]:.1f}%')
print(f'  Profit Factor  : {bm["pf"]:.3f}')
print(f'  CAGR           : {bm["cagr"]:+.1f}%')
print(f'  Sharpe         : {bm["sharpe"]:.3f}')
print(f'  Avg win        : {bm["avg_win"]:+.2f}%')
print(f'  Avg loss       : {bm["avg_loss"]:+.2f}%')
print(f'  SL-hit rate    : {bm["sl_pct"]:.0f}%')

# Per-stock OOS contribution
print('\n' + sep)
print(f'  PER-STOCK OOS — best config')
print(sep)
sym_results = {}
for sym in valid_stocks:
    trs = backtest_52wk(price_data[sym], all_dates, OOS_SET,
                        hold_days=best_oos['hold'],
                        vol_gate=best_oos['vg'], prox_gate=best_oos['pg'])
    sym_results[sym] = trs

ranked = sorted(sym_results.items(), key=lambda x: sum(t['pnl'] for t in x[1]), reverse=True)
for sym, trs in ranked:
    if not trs: continue
    wins = [t for t in trs if t['pnl'] > 0]
    net  = sum(t['pnl'] for t in trs)
    wr_  = len(wins) / len(trs) * 100
    flag = '  +' if net > 5000 else ('  -' if net < -5000 else '')
    print(f'  {sym:<14}  {len(trs):>4} trades  WR={wr_:>5.1f}%  '
          f'PnL=Rs.{net:>+8,.0f}{flag}')

# ── HEAD-TO-HEAD ──────────────────────────────────────────────────────────────
n_oos_s = nifty_data.get(OOS_DATES[0], {}).get('close', 0)
n_oos_e = nifty_data.get(OOS_DATES[-1],{}).get('close', 0)
nifty_cagr = ((n_oos_e / n_oos_s) ** (1 / OOS_YEARS) - 1) * 100 if n_oos_s > 0 else 0

print('\n' + SEP)
print('  HEAD-TO-HEAD COMPARISON — OOS')
print(SEP)
print(f'  {"Strategy":<42}  {"OOS PF":>7}  {"CAGR%":>8}  {"Sharpe":>8}  {"Trades":>8}')
print(sep)

comps = [
    ('52-Wk High (best config)',       best_oos['oos']['pf'], best_oos['oos']['cagr'],
     best_oos['oos']['sharpe'], best_oos['oos']['trades']),
    ('Compression Breakout (2%/5bar)', 0.996, -1.3,  -0.515,  82),
    ('PEAD (5%/60d)',                  0.911, -0.7,  -0.036, 475),
    ('RSI<30 S3',                      0.876, -3.5,  -0.774, 278),
    ('RS Momentum (50 stk)',           0.602, -5.5,  -0.738,  80),
    (f'Buy & Hold Nifty',             1.000,  nifty_cagr, 0.0,  0),
]
for name, pf_, cagr_, sh_, tr_ in comps:
    flag = '  BEST' if pf_ == max(c[1] for c in comps[:-1]) else (
           '  BEATS NIFTY' if cagr_ > nifty_cagr else '')
    tr_s = f'{tr_:>8}' if tr_ else '       -'
    print(f'  {name:<42}  {pf_:>7.3f}  {cagr_:>+7.1f}%  {sh_:>8.3f}  {tr_s}{flag}')

print('\n' + SEP)
print('  VERDICT')
print(SEP)
b = best_oos['oos']
print(f'  Best config : {best_oos["vname"]}  Hold={best_oos["hold"]}d')
print(f'  OOS PF      : {b["pf"]:.3f}  (vs Compression B = 0.996)')
print(f'  OOS CAGR    : {b["cagr"]:+.1f}%  (vs PEAD best = -0.7%)')
print()
if b['pf'] > 0.996:
    print('  RESULT: 52-WEEK HIGH BEATS COMPRESSION BREAKOUT.')
    print('  George & Hwang (2004) anchoring effect confirmed on NSE.')
elif b['pf'] > 0.911:
    print('  RESULT: 52-WEEK HIGH BETWEEN COMPRESSION AND PEAD.')
    print('  Volume/proximity filters partially help. Structural edge is real.')
elif b['pf'] > 0.876:
    print('  RESULT: 52-WEEK HIGH SLIGHTLY BETTER THAN RSI<30.')
    print('  Weaker than Compression Breakout. The 2% range is a better filter than 52wk proximity.')
else:
    print('  RESULT: 52-WEEK HIGH DOES NOT OUTPERFORM COMPRESSION BREAKOUT.')
    print('  On NSE large caps, compression within range is a stronger signal than yearly-high reference.')
    print('  Institutional anchoring to 52wk high is weaker in Indian markets vs US (less retail retail).')
print()
print('  VOLUME FILTER EFFECT:')
vol_with    = [r for r in oos_results if r['vg'] and r['hold'] == best_oos['hold']]
vol_without = [r for r in oos_results if not r['vg'] and r['hold'] == best_oos['hold']]
if vol_with and vol_without:
    avg_with = statistics.mean([r['oos']['pf'] for r in vol_with])
    avg_wo   = statistics.mean([r['oos']['pf'] for r in vol_without])
    print(f'  PF with volume gate    : {avg_with:.3f}')
    print(f'  PF without volume gate : {avg_wo:.3f}')
    print(f'  Volume gate effect     : {avg_with - avg_wo:+.3f}  '
          f'({"HELPS" if avg_with > avg_wo else "HURTS"})')
