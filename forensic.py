"""
forensic.py — Trade-level forensic analysis: winners vs losers
Run: python forensic.py
"""

import time, logging, warnings, statistics
from collections import Counter
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from backtest import Backtester

STOCKS = [
    ('NSE_EQ|INE002A01018', 'RELIANCE'),
    ('NSE_EQ|INE467B01029', 'TCS'),
    ('NSE_EQ|INE009A01021', 'INFY'),
    ('NSE_EQ|INE040A01034', 'HDFCBANK'),
]

# ── Collect all trades ────────────────────────────────────────────────────────
print("Collecting trades from all 4 stocks...")
bt = Backtester(capital=5000.0)
all_trades = []
for inst, sym in STOCKS:
    m = bt.run(inst, sym, days=59, interval='30minute', min_score=0.40, regime_filter=False)
    if 'error' not in m:
        for t in m['trades']:
            t['symbol'] = sym
            all_trades.append(t)
    time.sleep(0.5)

winners = [t for t in all_trades if t['pnl'] > 0]
losers  = [t for t in all_trades if t['pnl'] <= 0]

print(f"\nTotal trades: {len(all_trades)}  |  Winners: {len(winners)}  |  Losers: {len(losers)}")
print()

# ── Helpers ───────────────────────────────────────────────────────────────────
def avg(lst):
    return statistics.mean(lst) if lst else 0.0

def get_num(trades, key):
    return [t['entry_signals'].get(key)
            for t in trades
            if isinstance(t.get('entry_signals'), dict) and t['entry_signals'].get(key) is not None]

def get_cat(trades, key):
    return [t['entry_signals'].get(key, '?')
            for t in trades
            if isinstance(t.get('entry_signals'), dict)]

def sep_bar(s):
    return '#' * min(40, int(s * 500))

def verdict(s):
    if s > 0.02:  return 'USEFUL'
    if s > 0.005: return 'MARGINAL'
    return 'NOISE'

# ── 1. Signal score ───────────────────────────────────────────────────────────
w_scores = [t['entry_score'] for t in winners if t.get('entry_score') is not None]
l_scores = [t['entry_score'] for t in losers  if t.get('entry_score') is not None]

print('=' * 64)
print('  1. SIGNAL SCORE AT ENTRY')
print('=' * 64)
print(f'  Winners avg : {avg(w_scores):.3f}')
print(f'  Losers  avg : {avg(l_scores):.3f}')
print(f'  Difference  : {avg(w_scores)-avg(l_scores):+.3f}')
print()

# ── 2. RSI ────────────────────────────────────────────────────────────────────
w_rsi = get_num(winners, 'rsi')
l_rsi = get_num(losers,  'rsi')

print('=' * 64)
print('  2. RSI AT ENTRY')
print('=' * 64)
print(f'  Winners avg RSI : {avg(w_rsi):.1f}')
print(f'  Losers  avg RSI : {avg(l_rsi):.1f}')
print(f'  Difference      : {avg(w_rsi)-avg(l_rsi):+.1f}')
for label, trades in [('Winners', winners), ('Losers', losers)]:
    vals = get_num(trades, 'rsi')
    n = len(vals) or 1
    low  = sum(1 for r in vals if r < 40) / n * 100
    mid  = sum(1 for r in vals if 40 <= r <= 60) / n * 100
    high = sum(1 for r in vals if r > 60) / n * 100
    print(f'  {label:8}: <40={low:.0f}%  40-60={mid:.0f}%  >60={high:.0f}%')
print()

# ── 3. EMA cross ─────────────────────────────────────────────────────────────
print('=' * 64)
print('  3. EMA9/21 CROSS STATE AT ENTRY')
print('=' * 64)
for label, trades in [('Winners', winners), ('Losers', losers)]:
    vals = get_cat(trades, 'ema_cross')
    n = len(vals) or 1
    buy  = vals.count('BUY')  / n * 100
    sell = vals.count('SELL') / n * 100
    hold = vals.count('HOLD') / n * 100
    print(f'  {label:8}: BUY={buy:.0f}%  SELL={sell:.0f}%  HOLD={hold:.0f}%')
print()

# ── 4. Heikin-Ashi ────────────────────────────────────────────────────────────
print('=' * 64)
print('  4. HEIKIN-ASHI TREND AT ENTRY')
print('=' * 64)
for label, trades in [('Winners', winners), ('Losers', losers)]:
    vals = get_cat(trades, 'heikin_ashi')
    n = len(vals) or 1
    bull = vals.count('BULLISH') / n * 100
    bear = vals.count('BEARISH') / n * 100
    neut = vals.count('NEUTRAL') / n * 100
    print(f'  {label:8}: BULLISH={bull:.0f}%  BEARISH={bear:.0f}%  NEUTRAL={neut:.0f}%')
print()

# ── 5. Guppy MMA ─────────────────────────────────────────────────────────────
print('=' * 64)
print('  5. GUPPY MMA STATE AT ENTRY')
print('=' * 64)
for label, trades in [('Winners', winners), ('Losers', losers)]:
    vals = get_cat(trades, 'guppy')
    n = len(vals) or 1
    buy  = vals.count('BUY')     / n * 100
    sell = vals.count('SELL')    / n * 100
    neut = vals.count('NEUTRAL') / n * 100
    print(f'  {label:8}: BUY={buy:.0f}%  SELL={sell:.0f}%  NEUTRAL={neut:.0f}%')
print()

# ── 6. EMA21 slope ────────────────────────────────────────────────────────────
w_slope = get_num(winners, 'e21_slope')
l_slope = get_num(losers,  'e21_slope')

print('=' * 64)
print('  6. EMA21 SLOPE AT ENTRY')
print('=' * 64)
print(f'  Winners avg : {avg(w_slope):+.6f}')
print(f'  Losers  avg : {avg(l_slope):+.6f}')
print(f'  Difference  : {avg(w_slope)-avg(l_slope):+.6f}')
for label, vals in [('Winners', w_slope), ('Losers', l_slope)]:
    n = len(vals) or 1
    up   = sum(1 for v in vals if v >  0.001) / n * 100
    flat = sum(1 for v in vals if abs(v) <= 0.001) / n * 100
    dn   = sum(1 for v in vals if v < -0.001) / n * 100
    print(f'  {label:8}: rising={up:.0f}%  flat={flat:.0f}%  falling={dn:.0f}%')
print()

# ── 7. EMA21 concavity ────────────────────────────────────────────────────────
w_conc = get_num(winners, 'e21_concavity')
l_conc = get_num(losers,  'e21_concavity')

print('=' * 64)
print('  7. EMA21 CONCAVITY (ACCELERATION) AT ENTRY')
print('=' * 64)
print(f'  Winners avg : {avg(w_conc):+.6f}')
print(f'  Losers  avg : {avg(l_conc):+.6f}')
print(f'  Difference  : {avg(w_conc)-avg(l_conc):+.6f}')
for label, vals in [('Winners', w_conc), ('Losers', l_conc)]:
    n = len(vals) or 1
    acc = sum(1 for v in vals if v > 0) / n * 100
    dec = sum(1 for v in vals if v < 0) / n * 100
    print(f'  {label:8}: accelerating={acc:.0f}%  decelerating={dec:.0f}%')
print()

# ── 8. Exit reasons ───────────────────────────────────────────────────────────
print('=' * 64)
print('  8. EXIT REASON BREAKDOWN')
print('=' * 64)
for label, trades in [('Winners', winners), ('Losers', losers)]:
    reasons = Counter()
    for t in trades:
        r = t.get('exit_reason', '?')
        if   r.startswith('StopLoss'):    reasons['StopLoss']    += 1
        elif r.startswith('TakeProfit'):  reasons['TakeProfit']  += 1
        elif r.startswith('Trailing'):    reasons['TrailingStop'] += 1
        elif r.startswith('Signal'):      reasons['SignalSELL']   += 1
        else:                             reasons['Other']        += 1
    total = sum(reasons.values()) or 1
    print(f'  {label:8}: ' + '  '.join(f'{k}={v/total*100:.0f}%' for k, v in reasons.items()))
print()

# ── 9. Return distribution ────────────────────────────────────────────────────
print('=' * 64)
print('  9. RETURN DISTRIBUTION')
print('=' * 64)
w_ret = [t['return_pct'] for t in winners]
l_ret = [t['return_pct'] for t in losers]
if w_ret:
    print(f'  Winners: avg={avg(w_ret):+.2f}%  min={min(w_ret):+.2f}%  max={max(w_ret):+.2f}%')
if l_ret:
    print(f'  Losers : avg={avg(l_ret):+.2f}%  min={min(l_ret):+.2f}%  max={max(l_ret):+.2f}%')
if w_ret and l_ret:
    print(f'  Avg W / Avg L ratio : {abs(avg(w_ret)/avg(l_ret)):.2f}x')
print()

# ── 10. Per-stock winner count ────────────────────────────────────────────────
print('=' * 64)
print('  10. WINNERS BY STOCK')
print('=' * 64)
for _, sym in STOCKS:
    sw = [t for t in winners if t['symbol'] == sym]
    sl = [t for t in losers  if t['symbol'] == sym]
    total = len(sw) + len(sl)
    wr = len(sw) / total * 100 if total else 0
    print(f'  {sym:<12}: {len(sw)}W / {len(sl)}L  ({wr:.0f}% win rate)  '
          f'best={max((t["return_pct"] for t in sw), default=0):+.2f}%  '
          f'worst={min((t["return_pct"] for t in sl), default=0):+.2f}%')
print()

# ── 11. Indicator predictive value ranking ────────────────────────────────────
print('=' * 64)
print('  11. INDICATOR PREDICTIVE VALUE RANKING')
print('  separation = normalised difference between winner/loser averages')
print('  USEFUL > 0.02  |  MARGINAL 0.005-0.02  |  NOISE < 0.005')
print('=' * 64)

rankings = []

# Score
s = abs(avg(w_scores) - avg(l_scores))
rankings.append(('Signal Score',    s, f'W:{avg(w_scores):.3f} vs L:{avg(l_scores):.3f}'))

# RSI (normalised /100)
s = abs(avg(w_rsi) - avg(l_rsi)) / 100
rankings.append(('RSI',             s, f'W:{avg(w_rsi):.1f} vs L:{avg(l_rsi):.1f}'))

# Slope
s = abs(avg(w_slope) - avg(l_slope))
rankings.append(('EMA21 Slope',     s, f'W:{avg(w_slope):+.6f} vs L:{avg(l_slope):+.6f}'))

# Concavity
s = abs(avg(w_conc) - avg(l_conc))
rankings.append(('EMA21 Concavity', s, f'W:{avg(w_conc):+.6f} vs L:{avg(l_conc):+.6f}'))

# Guppy BUY rate separation
w_g = get_cat(winners, 'guppy')
l_g = get_cat(losers,  'guppy')
wg = w_g.count('BUY') / (len(w_g) or 1)
lg = l_g.count('BUY') / (len(l_g) or 1)
s = abs(wg - lg)
rankings.append(('Guppy MMA',       s, f'W BUY={wg*100:.0f}% vs L BUY={lg*100:.0f}%'))

# HA BULLISH rate separation
w_h = get_cat(winners, 'heikin_ashi')
l_h = get_cat(losers,  'heikin_ashi')
wh = w_h.count('BULLISH') / (len(w_h) or 1)
lh = l_h.count('BULLISH') / (len(l_h) or 1)
s = abs(wh - lh)
rankings.append(('Heikin-Ashi',     s, f'W BULL={wh*100:.0f}% vs L BULL={lh*100:.0f}%'))

# EMA cross BUY rate separation
w_e = get_cat(winners, 'ema_cross')
l_e = get_cat(losers,  'ema_cross')
we = w_e.count('BUY') / (len(w_e) or 1)
le = l_e.count('BUY') / (len(l_e) or 1)
s = abs(we - le)
rankings.append(('EMA Cross',       s, f'W BUY={we*100:.0f}% vs L BUY={le*100:.0f}%'))

rankings.sort(key=lambda x: x[1], reverse=True)
print()
for rank, (name, s, detail) in enumerate(rankings, 1):
    bar = sep_bar(s)
    v   = verdict(s)
    print(f'  {rank}. {name:<18} sep={s:.4f}  {bar}')
    print(f'       {detail}  [{v}]')
print()

# ── 12. Key insight summary ───────────────────────────────────────────────────
print('=' * 64)
print('  12. DIAGNOSTIC SUMMARY')
print('=' * 64)

# Does higher score predict wins?
score_sep = abs(avg(w_scores) - avg(l_scores))
if score_sep < 0.01:
    print('  [!] Score is NOT predictive — winners and losers enter at same score.')
    print('      The combined scorer is averaging away all signal information.')
else:
    print(f'  [OK] Score shows {score_sep:.3f} separation — some predictive value.')

# Does HA matter?
ha_sep = abs(wh - lh)
if ha_sep < 0.05:
    print('  [!] Heikin-Ashi BULLISH rate is same for W and L — no edge here.')
else:
    print(f'  [OK] Heikin-Ashi shows {ha_sep:.2%} separation.')

# Does EMA cross matter?
ema_sep = abs(we - le)
if ema_sep < 0.05:
    print('  [!] EMA cross fires on same % of W and L — no selectivity.')
else:
    print(f'  [OK] EMA cross shows {ema_sep:.2%} separation.')

# Win/loss return ratio
if w_ret and l_ret:
    ratio = abs(avg(w_ret) / avg(l_ret))
    if ratio < 1.0:
        print(f'  [!] Avg win ({avg(w_ret):+.2f}%) < avg loss ({avg(l_ret):+.2f}%).')
        print('      Even with a 50% win rate this system would lose money.')
    else:
        print(f'  [OK] Avg win/loss ratio = {ratio:.2f}x.')

# Loss streak evidence
max_loss_streak = 0
cur = 0
for t in all_trades:
    if t['pnl'] <= 0:
        cur += 1
        max_loss_streak = max(max_loss_streak, cur)
    else:
        cur = 0
print(f'  [!] Longest losing streak across all trades: {max_loss_streak}')
print()
