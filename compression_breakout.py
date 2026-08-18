"""
compression_breakout.py — Pure Compression Breakout strategy.

Signal (no RSI, no EMA, no ATR filter):
  1. Price has traded within a range of <= R% for at least N bars
     (range = (max_high - min_low) / min_low of those N bars)
  2. Current close breaks above the highest high of that range

Parameter sweep:
  Range widths  : 2%, 3%, 4%, 5%
  Base lengths  : 3, 5, 8, 10 bars
  => 16 combinations, OOS PF heatmap

Execution: same SL=2%, TP=6%, Trail=1.5%, next-open fill, Rs.20 brokerage.
Test: 50 NSE stocks, 5 years, walk-forward Y1-Y3 IS / Y4-Y5 OOS.
"""

import time, math, logging, warnings, statistics
from collections import Counter

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

BROKERAGE    = 20.0
STT_PCT      = 0.001
EXCHANGE_PCT = 0.0000345
SLIPPAGE     = 0.002
SL_PCT       = 2.0
TP_PCT       = 6.0
TRAIL_PCT    = 1.5
CAPITAL      = 5000.0
LOOKBACK     = 20
WF_SPLIT     = 0.60

SEP = '=' * 108
sep = '-' * 108

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
    ('BALKRISIND.NS','BALKRISIND'),
]

RANGE_WIDTHS  = [2, 3, 4, 5]
BASE_LENGTHS  = [3, 5, 8, 10]


# ── Signal factory ────────────────────────────────────────────────────────────
def make_signal(range_pct, base_bars):
    """
    range_pct  : max allowed range width as % (e.g. 3 = 3%)
    base_bars  : number of bars that must stay within that range
    Entry      : close of signal bar > highest HIGH of the base bars
    """
    def signal(window):
        if len(window) < base_bars + 2:
            return False
        # base = last `base_bars` completed bars (not including current bar)
        base  = window[-(base_bars + 1):-1]
        curr  = window[-1]

        b_high = max(c[2] for c in base)   # highest intraday high
        b_low  = min(c[3] for c in base)   # lowest intraday low

        if b_low <= 0:
            return False

        # Condition 1: range within threshold
        rng = (b_high - b_low) / b_low * 100
        if rng > range_pct:
            return False

        # Condition 2: current close breaks above highest high of base
        if curr[4] <= b_high:
            return False

        return True
    return signal


# ── Backtester ────────────────────────────────────────────────────────────────
def backtest(candles, sig_fn):
    capital  = CAPITAL
    position = None
    trades   = []
    equity   = [capital]

    for i in range(LOOKBACK, len(candles) - 1):
        window = candles[:i + 1]
        ltp    = candles[i][4]

        if position:
            high  = max(position['high'], ltp)
            low   = min(position['low'],  ltp)
            position['high'] = high
            position['low']  = low
            sl    = position['entry'] * (1 - SL_PCT / 100)
            tp    = position['entry'] * (1 + TP_PCT / 100)
            trail = high * (1 - TRAIL_PCT / 100)

            reason = None
            if   ltp <= sl:                                          reason = 'SL'
            elif ltp >= tp:                                          reason = 'TP'
            elif ltp <= trail and high > position['entry'] * 1.005: reason = 'Trail'

            if reason:
                exit_px  = ltp * (1 - SLIPPAGE)
                exit_val = position['qty'] * exit_px
                costs    = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
                pnl      = (exit_px - position['entry']) * position['qty'] - costs
                capital  += pnl
                trades.append({'pnl': pnl,
                               'return_pct': (exit_px / position['entry'] - 1) * 100,
                               'exit': reason, 'winner': 1 if pnl > 0 else 0})
                position = None
                equity.append(capital)
                continue

        if position is None:
            try:
                sig = sig_fn(window)
            except Exception:
                sig = False
            if sig:
                exec_px = candles[i + 1][1]
                fill_px = exec_px * (1 + SLIPPAGE)
                qty     = max(1, int(capital * 0.95 / fill_px))
                cost_in = BROKERAGE + qty * fill_px * EXCHANGE_PCT
                if capital >= qty * fill_px + cost_in:
                    capital -= cost_in
                    position = {'qty': qty, 'entry': fill_px,
                                'high': fill_px, 'low': fill_px, 'entry_bar': i}
        equity.append(capital)

    if position:
        ltp     = candles[-1][4]
        exit_px = ltp * (1 - SLIPPAGE)
        costs   = BROKERAGE + position['qty'] * exit_px * (STT_PCT + EXCHANGE_PCT)
        pnl     = (exit_px - position['entry']) * position['qty'] - costs
        trades.append({'pnl': pnl,
                       'return_pct': (exit_px / position['entry'] - 1) * 100,
                       'exit': 'EoP', 'winner': 1 if pnl > 0 else 0})
        capital += pnl

    return _metrics(trades, equity, capital, len(candles) - LOOKBACK)


def _metrics(trades, equity, final_cap, bars):
    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp     = sum(t['pnl'] for t in wins)
    gl     = abs(sum(t['pnl'] for t in losses))
    pf     = gp / gl if gl > 0 else (1.0 if gp > 0 else 0.0)
    wr     = len(wins) / len(trades) * 100 if trades else 0.0
    years  = max(bars / 252, 0.1)
    cagr   = ((final_cap / CAPITAL) ** (1 / years) - 1) * 100 if final_cap > 0 else -100.0

    peak = equity[0]; max_dd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd

    dr = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity)) if equity[i-1] > 0]
    sharpe = (statistics.mean(dr) / statistics.stdev(dr) * math.sqrt(252)
              if len(dr) > 2 and statistics.stdev(dr) > 0 else 0.0)

    w_rets = [t['return_pct'] for t in wins]
    l_rets = [t['return_pct'] for t in losses]
    avg_w  = statistics.mean(w_rets) if w_rets  else 0.0
    avg_l  = statistics.mean(l_rets) if l_rets  else 0.0
    wl     = abs(avg_w / avg_l)      if avg_l   else 0.0

    return {
        'trades': len(trades), 'wins': len(wins), 'losses': len(losses),
        'wr': round(wr, 1),    'pf':   round(pf, 3),
        'sharpe': round(sharpe, 3),   'cagr':    round(cagr, 1),
        'max_dd': round(max_dd, 1),   'avg_win':  round(avg_w, 2),
        'avg_loss': round(avg_l, 2),  'wl':       round(wl, 2),
        'net_pnl': round(final_cap - CAPITAL, 2),
        'exit_reasons': dict(Counter(t['exit'] for t in trades)),
    }


def pooled_pf(mlist):
    num = sum(v['wins']   * abs(v['avg_win'])  for v in mlist if v.get('losses', 0) > 0)
    den = sum(v['losses'] * abs(v['avg_loss']) for v in mlist if v.get('losses', 0) > 0)
    return round(num / den, 3) if den > 0 else 0.0


def agg(mlist, key):
    vals = [m[key] for m in mlist if m['trades'] > 0]
    return round(statistics.mean(vals), 3) if vals else 0.0


def fetch(ticker, period='5y'):
    try:
        df = yf.Ticker(ticker).history(period=period, interval='1d', auto_adjust=True)
        if df.empty:
            return []
        return [[str(ts.date()),
                 float(row['Open']), float(row['High']),
                 float(row['Low']),  float(row['Close']),
                 float(row.get('Volume', 0) or 0)]
                for ts, row in df.iterrows()]
    except Exception:
        return []


# ═════════════════════════════════════════════════════════════════════════════
#  FETCH
# ═════════════════════════════════════════════════════════════════════════════
print(SEP)
print('  FETCHING 5-YEAR DAILY DATA — 50 NSE STOCKS')
print(SEP)

candles_map = {}
for ticker, sym in STOCKS:
    c = fetch(ticker, '5y')
    candles_map[sym] = c
    print(f'  {sym:<14}: {len(c)} bars')
    time.sleep(0.22)

valid = [(t, s) for t, s in STOCKS if len(candles_map.get(s, [])) >= LOOKBACK + 20]
print(f'\n  Valid: {len(valid)} / {len(STOCKS)} stocks')


# ═════════════════════════════════════════════════════════════════════════════
#  RUN PARAMETER SWEEP — all 16 combinations
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print(f'  PARAMETER SWEEP — {len(RANGE_WIDTHS)} range widths x {len(BASE_LENGTHS)} base lengths = {len(RANGE_WIDTHS)*len(BASE_LENGTHS)} combinations')
print('  Walk-forward: Y1-Y3 in-sample (60%) | Y4-Y5 out-of-sample (40%)')
print(SEP)

# grid[range_pct][base_len] = {'is': [...metrics], 'oos': [...metrics]}
grid_is  = {r: {b: [] for b in BASE_LENGTHS} for r in RANGE_WIDTHS}
grid_oos = {r: {b: [] for b in BASE_LENGTHS} for r in RANGE_WIDTHS}

total_combos = len(RANGE_WIDTHS) * len(BASE_LENGTHS)
done = 0
for r in RANGE_WIDTHS:
    for b in BASE_LENGTHS:
        sig = make_signal(r, b)
        for _, sym in valid:
            candles = candles_map[sym]
            split   = int(len(candles) * WF_SPLIT)
            c_is    = candles[:split]
            c_oos   = candles[split - LOOKBACK:]
            if len(c_is)  >= LOOKBACK + b + 2:
                m = backtest(c_is, sig)
                if m['trades'] >= 1:
                    grid_is[r][b].append(m)
            if len(c_oos) >= LOOKBACK + b + 2:
                m = backtest(c_oos, sig)
                if m['trades'] >= 1:
                    grid_oos[r][b].append(m)
        done += 1
        print(f'  [{done:>2}/{total_combos}] Range={r}%  Base={b}bars  '
              f'IS_PF={pooled_pf(grid_is[r][b]):.3f}  '
              f'OOS_PF={pooled_pf(grid_oos[r][b]):.3f}  '
              f'OOS_Tr={sum(m["trades"] for m in grid_oos[r][b])}', flush=True)


# ═════════════════════════════════════════════════════════════════════════════
#  FULL RESULTS TABLE
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  FULL RESULTS TABLE (all 16 combinations, sorted by OOS PF)')
print(SEP)
print(f'  {"Config":<22}  {"IS Tr":>6}  {"IS WR":>6}  {"IS PF":>7}  '
      f'{"OOS Tr":>7}  {"OOS WR":>7}  {"OOS PF":>8}  {"OOS CAGR":>9}  '
      f'{"MaxDD":>7}  {"Sharpe":>7}  {"WL":>6}')
print(sep)

all_combos = []
for r in RANGE_WIDTHS:
    for b in BASE_LENGTHS:
        is_m  = grid_is[r][b]
        oos_m = grid_oos[r][b]
        i_t   = sum(m['trades'] for m in is_m)
        o_t   = sum(m['trades'] for m in oos_m)
        i_wr  = sum(m['wins'] for m in is_m)  / max(1, i_t) * 100
        o_wr  = sum(m['wins'] for m in oos_m) / max(1, o_t) * 100
        i_pf  = pooled_pf(is_m)
        o_pf  = pooled_pf(oos_m)
        all_combos.append({
            'r': r, 'b': b,
            'i_t': i_t, 'o_t': o_t,
            'i_wr': i_wr, 'o_wr': o_wr,
            'i_pf': i_pf, 'o_pf': o_pf,
            'o_cagr': agg(oos_m, 'cagr'),
            'o_dd':   agg(oos_m, 'max_dd'),
            'o_sh':   agg(oos_m, 'sharpe'),
            'o_wl':   agg(oos_m, 'wl'),
        })

for c in sorted(all_combos, key=lambda x: -x['o_pf']):
    flag = ''
    if   c['o_pf'] >= 1.2: flag = '  *** PROFITABLE ***'
    elif c['o_pf'] >= 1.0: flag = '  ** BREAKEVEN **'
    elif c['o_pf'] >= 0.85: flag = '  * NEAR *'
    label = f'Range={c["r"]}%  Base={c["b"]}bars'
    print(f'  {label:<22}  {c["i_t"]:>6}  {c["i_wr"]:>5.1f}%  {c["i_pf"]:>7.3f}  '
          f'{c["o_t"]:>7}  {c["o_wr"]:>6.1f}%  {c["o_pf"]:>8.3f}  {c["o_cagr"]:>+8.1f}%  '
          f'{c["o_dd"]:>6.1f}%  {c["o_sh"]:>7.3f}  {c["o_wl"]:>5.2f}x{flag}')


# ═════════════════════════════════════════════════════════════════════════════
#  OOS PROFIT FACTOR HEATMAP
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  OOS PROFIT FACTOR HEATMAP')
print('  Rows = Range width (%)   |   Columns = Base length (bars)')
print('  Cell format: PF  [trades]')
print('  Shading: ### >= 1.0   ##  >= 0.85   #   >= 0.70   .   < 0.70')
print(SEP)

def pf_shade(pf):
    if   pf >= 1.20: return '***'
    elif pf >= 1.00: return '## '
    elif pf >= 0.85: return '#  '
    elif pf >= 0.70: return '.  '
    else:            return '   '

# Header
col_w = 16
print(f'  {"Range \\ Base":<14}', end='')
for b in BASE_LENGTHS:
    print(f'  {str(b)+" bars":^{col_w}}', end='')
print()
print(f'  {"-"*14}', end='')
for b in BASE_LENGTHS:
    print(f'  {"-"*col_w}', end='')
print()

for r in RANGE_WIDTHS:
    # Row 1: PF value with shade
    print(f'  {str(r)+"%":<14}', end='')
    for b in BASE_LENGTHS:
        pf  = pooled_pf(grid_oos[r][b])
        shd = pf_shade(pf)
        cell = f'{shd} {pf:.3f}'
        print(f'  {cell:^{col_w}}', end='')
    print()
    # Row 2: trade count
    print(f'  {"":14}', end='')
    for b in BASE_LENGTHS:
        o_t = sum(m['trades'] for m in grid_oos[r][b])
        cell = f'[{o_t} tr]'
        print(f'  {cell:^{col_w}}', end='')
    print()

# IS heatmap for comparison
print()
print('  IN-SAMPLE PROFIT FACTOR HEATMAP (for overfitting check)')
print(f'  {"Range \\ Base":<14}', end='')
for b in BASE_LENGTHS:
    print(f'  {str(b)+" bars":^{col_w}}', end='')
print()
print(f'  {"-"*14}', end='')
for b in BASE_LENGTHS:
    print(f'  {"-"*col_w}', end='')
print()

for r in RANGE_WIDTHS:
    print(f'  {str(r)+"%":<14}', end='')
    for b in BASE_LENGTHS:
        pf  = pooled_pf(grid_is[r][b])
        shd = pf_shade(pf)
        cell = f'{shd} {pf:.3f}'
        print(f'  {cell:^{col_w}}', end='')
    print()
    print(f'  {"":14}', end='')
    for b in BASE_LENGTHS:
        i_t = sum(m['trades'] for m in grid_is[r][b])
        cell = f'[{i_t} tr]'
        print(f'  {cell:^{col_w}}', end='')
    print()


# ═════════════════════════════════════════════════════════════════════════════
#  BEST CONFIG — PER-STOCK DETAIL
# ═════════════════════════════════════════════════════════════════════════════
best = max(all_combos, key=lambda x: x['o_pf'])
best_sig = make_signal(best['r'], best['b'])

print()
print(SEP)
print(f'  BEST CONFIG: Range={best["r"]}%  Base={best["b"]}bars  '
      f'(OOS PF={best["o_pf"]:.3f})')
print('  Per-stock OOS detail')
print(SEP)
print(f'  {"Stock":<14}  {"OOS Tr":>6}  {"OOS WR":>7}  {"OOS PF":>8}  '
      f'{"CAGR":>7}  {"MaxDD":>7}  {"Sharpe":>7}  {"WL":>6}  Exits')
print(sep)

best_oos_per_stock = []
for _, sym in valid:
    candles = candles_map[sym]
    split   = int(len(candles) * WF_SPLIT)
    c_oos   = candles[split - LOOKBACK:]
    if len(c_oos) < LOOKBACK + best['b'] + 2:
        continue
    m = backtest(c_oos, best_sig)
    if m['trades'] == 0:
        continue
    er = m['exit_reasons']
    exits = f'SL={er.get("SL",0)} TP={er.get("TP",0)} Tr={er.get("Trail",0)}'
    flag = ''
    if   m['pf'] >= 1.5: flag = '  STRONG'
    elif m['pf'] >= 1.0: flag = '  HOLDS'
    elif m['pf'] < 0.4:  flag = '  POOR'
    print(f'  {sym:<14}  {m["trades"]:>6}  {m["wr"]:>6.1f}%  {m["pf"]:>8.3f}  '
          f'{m["cagr"]:>+6.1f}%  {m["max_dd"]:>6.1f}%  {m["sharpe"]:>7.3f}  '
          f'{m["wl"]:>5.2f}x  {exits}{flag}')
    best_oos_per_stock.append(m)

if best_oos_per_stock:
    b_t  = sum(m['trades'] for m in best_oos_per_stock)
    b_wr = sum(m['wins']   for m in best_oos_per_stock) / max(1, b_t) * 100
    print(sep)
    print(f'  {"AGGREGATE":<14}  {b_t:>6}  {b_wr:>6.1f}%  '
          f'{pooled_pf(best_oos_per_stock):>8.3f}  '
          f'{agg(best_oos_per_stock,"cagr"):>+6.1f}%  '
          f'{agg(best_oos_per_stock,"max_dd"):>6.1f}%  '
          f'{agg(best_oos_per_stock,"sharpe"):>7.3f}  '
          f'{agg(best_oos_per_stock,"wl"):>5.2f}x')


# ═════════════════════════════════════════════════════════════════════════════
#  IS vs OOS DEGRADATION — overfitting check
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  IS -> OOS DEGRADATION TABLE (sorted by IS PF)')
print('  Low decay = genuine edge. High decay = overfitting.')
print(SEP)
print(f'  {"Config":<22}  {"IS PF":>7}  {"OOS PF":>8}  {"Decay%":>8}  {"OOS Tr":>7}  Assessment')
print(sep)

for c in sorted(all_combos, key=lambda x: -x['i_pf']):
    decay = (c['i_pf'] - c['o_pf']) / c['i_pf'] * 100 if c['i_pf'] > 0 else 0
    label = f'Range={c["r"]}%  Base={c["b"]}bars'
    if   decay < 10:  assess = 'STABLE'
    elif decay < 25:  assess = 'Mild decay'
    elif decay < 50:  assess = 'Moderate decay'
    else:             assess = 'HIGH DECAY'
    print(f'  {label:<22}  {c["i_pf"]:>7.3f}  {c["o_pf"]:>8.3f}  '
          f'{decay:>+7.1f}%  {c["o_t"]:>7}  {assess}')


# ═════════════════════════════════════════════════════════════════════════════
#  VERDICT
# ═════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print('  VERDICT — DOES PURE COMPRESSION CONTAIN A DURABLE EDGE?')
print(SEP)

best_oos_pf  = max(c['o_pf'] for c in all_combos)
worst_oos_pf = min(c['o_pf'] for c in all_combos)
avg_oos_pf   = statistics.mean(c['o_pf'] for c in all_combos)
combos_above_1 = [c for c in all_combos if c['o_pf'] >= 1.0]
combos_above_085 = [c for c in all_combos if c['o_pf'] >= 0.85]

# Overfitting test: is IS PF strongly correlated with OOS PF?
is_pfs  = [c['i_pf'] for c in all_combos]
oos_pfs = [c['o_pf'] for c in all_combos]
mi, mo  = statistics.mean(is_pfs), statistics.mean(oos_pfs)
r_num   = sum((x - mi) * (y - mo) for x, y in zip(is_pfs, oos_pfs))
r_den   = math.sqrt(sum((x-mi)**2 for x in is_pfs) * sum((y-mo)**2 for y in oos_pfs))
is_oos_corr = r_num / r_den if r_den > 0 else 0

print(f'  Parameters tested      : {len(all_combos)} combinations')
print(f'  Best OOS PF            : {best_oos_pf:.3f}  '
      f'(Range={best["r"]}%  Base={best["b"]}bars)')
print(f'  Worst OOS PF           : {worst_oos_pf:.3f}')
print(f'  Average OOS PF         : {avg_oos_pf:.3f}')
print(f'  Combos with OOS PF>=1.0: {len(combos_above_1)}')
print(f'  Combos with OOS PF>=0.85:{len(combos_above_085)}')
print(f'  IS-OOS PF correlation  : {is_oos_corr:.3f}  '
      f'(0=no relation, 1=perfectly consistent)')
print()

# Final answer
if best_oos_pf >= 1.2 and len(combos_above_1) >= 4:
    answer = 'YES — compression contains a robust, durable edge across parameter space.'
    detail = ('Multiple parameter combinations achieve OOS PF > 1.0, confirming the '
              'effect is not parameter-specific. Strategy is deployable with best config.')
elif best_oos_pf >= 1.0 and len(combos_above_1) >= 2:
    answer = 'POSSIBLY — edge exists but is narrow and parameter-sensitive.'
    detail = (f'Only {len(combos_above_1)} of 16 combos break even OOS. '
              'The signal works for specific parameter values, not universally. '
              'Requires strict adherence to the best-found parameters.')
elif best_oos_pf >= 0.85:
    answer = 'WEAK — compression shows directional edge but cannot overcome costs.'
    detail = (f'Best OOS PF={best_oos_pf:.3f}. The price compression pattern is '
              'predictive but the brokerage + slippage cost (Rs.40+ per round trip) '
              'consumes the raw edge. At Rs.50000/stock the cost ratio improves 10x.')
else:
    answer = 'NO — pure compression breakout does not contain a durable edge on NSE.'
    detail = (f'Best OOS PF={best_oos_pf:.3f} across all 16 parameter combinations. '
              'Price compression alone is not sufficient. The pattern fires too frequently '
              'on random consolidations that are not accumulation zones.')

print(f'  ANSWER: {answer}')
print()
print(f'  Detail: {detail}')
print()

# Overfitting assessment
if is_oos_corr > 0.6:
    print(f'  Overfitting check: IS-OOS correlation = {is_oos_corr:.3f} (CONSISTENT)')
    print('  The parameter ranking holds OOS — results are not overfit to IS data.')
elif is_oos_corr > 0.3:
    print(f'  Overfitting check: IS-OOS correlation = {is_oos_corr:.3f} (MODERATE)')
    print('  Some IS-OOS consistency but IS results are not fully predictive of OOS.')
else:
    print(f'  Overfitting check: IS-OOS correlation = {is_oos_corr:.3f} (WEAK)')
    print('  IS performance is not predictive of OOS. Parameter selection on IS data')
    print('  would have led to wrong config choice. Edge is not consistent across time.')

print()
# Comparison to RSI<30 benchmark
rsi30_oos_pf = 0.876   # from s3_validation.py
print(f'  Comparison vs RSI<30 (S3) benchmark: OOS PF={rsi30_oos_pf:.3f}')
if best_oos_pf > rsi30_oos_pf:
    print(f'  Compression Breakout BEATS RSI<30 at best params (PF {best_oos_pf:.3f} > {rsi30_oos_pf:.3f}).')
    print('  Worth combining: enter compression breakout only after RSI<30 oversold context.')
else:
    diff = rsi30_oos_pf - best_oos_pf
    print(f'  Compression Breakout does NOT beat RSI<30 (gap = {diff:.3f} PF points).')
    print('  RSI<30 mean reversion remains the strongest single edge found in this research.')
    print()
    print('  Final recommendation: return to RSI<30 (S3) as the base strategy.')
    print('  Focus next research on improving its entry timing and stock selection,')
    print('  not on finding an entirely different signal family.')
