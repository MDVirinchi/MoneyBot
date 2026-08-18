"""
validate_signals.py — Contingency table validation for every useful indicator
and combination. Uses actual trade data with indicator snapshots.
Run: python validate_signals.py
"""

import time, logging, warnings, math, statistics
from collections import defaultdict
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from backtest import Backtester

STOCKS = [
    ('NSE_EQ|INE002A01018', 'RELIANCE'),
    ('NSE_EQ|INE467B01029', 'TCS'),
    ('NSE_EQ|INE009A01021', 'INFY'),
    ('NSE_EQ|INE040A01034', 'HDFCBANK'),
]

# ── Collect trades ────────────────────────────────────────────────────────────
print("Collecting trades...")
bt = Backtester(capital=5000.0)
all_trades = []
for inst, sym in STOCKS:
    m = bt.run(inst, sym, days=59, interval='30minute',
               min_score=0.40, regime_filter=False)
    if 'error' not in m:
        for t in m['trades']:
            t['symbol'] = sym
            all_trades.append(t)
    time.sleep(0.5)

N       = len(all_trades)
n_win   = sum(1 for t in all_trades if t['pnl'] > 0)
n_loss  = N - n_win
base_wr = n_win / N if N else 0

print(f"\nTotal trades: {N}  Winners: {n_win}  Losers: {n_loss}")
print(f"Baseline win rate: {base_wr*100:.1f}%\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def sig(t, key):
    """Raw signal value for a trade."""
    return t.get('entry_signals', {}).get(key)

def is_win(t):
    return t['pnl'] > 0

def contingency(trades, present_fn):
    """
    Returns (tp, fp, fn, tn):
      tp = present + win
      fp = present + loss
      fn = absent  + win
      tn = absent  + loss
    """
    tp = fp = fn = tn = 0
    for t in trades:
        w = is_win(t)
        p = present_fn(t)
        if p and w:     tp += 1
        elif p and not w: fp += 1
        elif not p and w: fn += 1
        else:             tn += 1
    return tp, fp, fn, tn

def stats_from_ct(tp, fp, fn, tn):
    present_total = tp + fp
    absent_total  = fn + tn
    wr_present = tp / present_total if present_total else 0
    wr_absent  = fn / absent_total  if absent_total  else 0
    lift       = wr_present / base_wr if base_wr else 0
    # Matthews Correlation Coefficient — works on imbalanced classes
    denom = math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn))
    mcc   = (tp*tn - fp*fn) / denom if denom else 0
    # Precision / Recall
    precision = tp / (tp+fp) if (tp+fp) else 0
    recall    = tp / (tp+fn) if (tp+fn) else 0
    return {
        'present_total': present_total,
        'absent_total':  absent_total,
        'wr_present':    wr_present,
        'wr_absent':     wr_absent,
        'lift':          lift,
        'mcc':           mcc,
        'precision':     precision,
        'recall':        recall,
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
    }

def print_ct(name, tp, fp, fn, tn, s):
    W = 52
    print(f"\n{'='*W}")
    print(f"  {name}")
    print(f"{'='*W}")
    print(f"  {'':20} {'WIN':>6}  {'LOSS':>6}  {'TOTAL':>6}")
    print(f"  {'Signal PRESENT':20} {tp:>6}  {fp:>6}  {tp+fp:>6}")
    print(f"  {'Signal ABSENT':20} {fn:>6}  {tn:>6}  {fn+tn:>6}")
    print(f"  {'TOTAL':20} {tp+fn:>6}  {fp+tn:>6}  {N:>6}")
    print(f"  {'-'*48}")
    print(f"  Win rate when PRESENT : {s['wr_present']*100:5.1f}%  "
          f"(baseline {base_wr*100:.1f}%)")
    print(f"  Win rate when ABSENT  : {s['wr_absent']*100:5.1f}%")
    print(f"  Lift over baseline    : {s['lift']:5.2f}x")
    print(f"  MCC                   : {s['mcc']:+.3f}  "
          f"(-1=anti  0=none  +1=perfect)")
    print(f"  Precision             : {s['precision']*100:5.1f}%")
    print(f"  Recall                : {s['recall']*100:5.1f}%")


# ═════════════════════════════════════════════════════════════════════════════
# PART 1 — Individual indicator contingency tables
# ═════════════════════════════════════════════════════════════════════════════

print("\n" + "#"*52)
print("  PART 1 — INDIVIDUAL INDICATOR VALIDATION")
print("#"*52)

# ── Heikin-Ashi ───────────────────────────────────────────────────────────────
# Three presence definitions to test the "late predictor" hypothesis:
#  A) BULLISH (current usage — 3+ green HA candles)
#  B) NOT BULLISH (neutral or bearish — opposite bet)
#  C) NEUTRAL only (transition zone — potential reversal)

ha_bull   = lambda t: sig(t,'heikin_ashi') == 'BULLISH'
ha_notbull= lambda t: sig(t,'heikin_ashi') != 'BULLISH'
ha_neut   = lambda t: sig(t,'heikin_ashi') == 'NEUTRAL'
ha_bear   = lambda t: sig(t,'heikin_ashi') == 'BEARISH'

for name, fn in [
    ('HA — BULLISH present (current usage)',   ha_bull),
    ('HA — NOT BULLISH present (inverted)',     ha_notbull),
    ('HA — NEUTRAL present (reversal zone)',   ha_neut),
    ('HA — BEARISH present',                   ha_bear),
]:
    tp,fp,fn_,tn = contingency(all_trades, fn)
    s = stats_from_ct(tp,fp,fn_,tn)
    print_ct(name, tp,fp,fn_,tn, s)

# ── EMA Cross ─────────────────────────────────────────────────────────────────
ema_buy  = lambda t: sig(t,'ema_cross') == 'BUY'
ema_hold = lambda t: sig(t,'ema_cross') == 'HOLD'

for name, fn in [
    ('EMA Cross — fresh BUY cross (current usage)', ema_buy),
    ('EMA Cross — HOLD/stale (no fresh cross)',      ema_hold),
]:
    tp,fp,fn_,tn = contingency(all_trades, fn)
    s = stats_from_ct(tp,fp,fn_,tn, )
    print_ct(name, tp,fp,fn_,tn, s)

# ── Guppy MMA ─────────────────────────────────────────────────────────────────
guppy_buy  = lambda t: sig(t,'guppy') == 'BUY'
guppy_neut = lambda t: sig(t,'guppy') == 'NEUTRAL'
guppy_sell = lambda t: sig(t,'guppy') == 'SELL'

for name, fn in [
    ('Guppy MMA — BUY state',     guppy_buy),
    ('Guppy MMA — NEUTRAL state', guppy_neut),
    ('Guppy MMA — SELL state',    guppy_sell),
]:
    tp,fp,fn_,tn = contingency(all_trades, fn)
    s = stats_from_ct(tp,fp,fn_,tn)
    print_ct(name, tp,fp,fn_,tn, s)

# ── Slope & Concavity (validation of noise verdict) ───────────────────────────
slope_up  = lambda t: (sig(t,'e21_slope') or 0) >  0.001
slope_dn  = lambda t: (sig(t,'e21_slope') or 0) < -0.001
conc_up   = lambda t: (sig(t,'e21_concavity') or 0) > 0
conc_dn   = lambda t: (sig(t,'e21_concavity') or 0) < 0

for name, fn in [
    ('Slope — EMA21 rising  (>+0.001)',  slope_up),
    ('Slope — EMA21 falling (<-0.001)',  slope_dn),
    ('Concavity — accelerating (>0)',    conc_up),
    ('Concavity — decelerating (<0)',    conc_dn),
]:
    tp,fp,fn_,tn = contingency(all_trades, fn)
    s = stats_from_ct(tp,fp,fn_,tn)
    print_ct(name, tp,fp,fn_,tn, s)

# ── RSI validation ────────────────────────────────────────────────────────────
rsi_low  = lambda t: (sig(t,'rsi') or 50) < 40
rsi_mid  = lambda t: 40 <= (sig(t,'rsi') or 50) <= 60
rsi_high = lambda t: (sig(t,'rsi') or 50) > 60

for name, fn in [
    ('RSI — oversold   (<40)',  rsi_low),
    ('RSI — neutral (40-60)',   rsi_mid),
    ('RSI — overbought (>60)',  rsi_high),
]:
    tp,fp,fn_,tn = contingency(all_trades, fn)
    s = stats_from_ct(tp,fp,fn_,tn)
    print_ct(name, tp,fp,fn_,tn, s)


# ═════════════════════════════════════════════════════════════════════════════
# PART 2 — Combination contingency tables
# ═════════════════════════════════════════════════════════════════════════════

print("\n\n" + "#"*52)
print("  PART 2 — COMBINATION VALIDATION")
print("#"*52)

combos = [
    ('EMA Cross only',
     lambda t: ema_buy(t)),
    ('HA NEUTRAL only (reversal)',
     lambda t: ha_neut(t)),
    ('Guppy BUY only',
     lambda t: guppy_buy(t)),
    ('EMA + HA_NEUTRAL',
     lambda t: ema_buy(t) and ha_neut(t)),
    ('EMA + Guppy BUY',
     lambda t: ema_buy(t) and guppy_buy(t)),
    ('HA_NEUTRAL + Guppy BUY',
     lambda t: ha_neut(t) and guppy_buy(t)),
    ('EMA + HA_NEUTRAL + Guppy BUY',
     lambda t: ema_buy(t) and ha_neut(t) and guppy_buy(t)),
    # Inverted HA combos (test the "HA hurts" hypothesis)
    ('EMA + HA_BULLISH (current logic)',
     lambda t: ema_buy(t) and ha_bull(t)),
    ('EMA + NOT_HA_BULLISH (inverted)',
     lambda t: ema_buy(t) and ha_notbull(t)),
]

combo_summary = []
for name, fn in combos:
    tp,fp,fn_,tn = contingency(all_trades, fn)
    s = stats_from_ct(tp,fp,fn_,tn)
    print_ct(name, tp,fp,fn_,tn, s)
    combo_summary.append((name, s))


# ═════════════════════════════════════════════════════════════════════════════
# PART 3 — Summary ranking table
# ═════════════════════════════════════════════════════════════════════════════

print("\n\n" + "#"*52)
print("  PART 3 — RANKED SUMMARY (by Lift over baseline)")
print(f"  Baseline win rate: {base_wr*100:.1f}%")
print("#"*52)

all_results = []

# Singles
singles = [
    ('HA BULLISH (current)',     ha_bull),
    ('HA NOT-BULLISH (inverted)',ha_notbull),
    ('HA NEUTRAL (reversal)',    ha_neut),
    ('EMA fresh BUY',           ema_buy),
    ('EMA HOLD/stale',          ema_hold),
    ('Guppy BUY',               guppy_buy),
    ('Guppy NEUTRAL',           guppy_neut),
    ('RSI oversold <40',        rsi_low),
    ('RSI neutral 40-60',       rsi_mid),
    ('Slope rising',            slope_up),
    ('Concavity accel',         conc_up),
]
for name, fn in singles:
    tp,fp,fn_,tn = contingency(all_trades, fn)
    s = stats_from_ct(tp,fp,fn_,tn)
    all_results.append((name, s))

for name, s in combo_summary:
    all_results.append((name, s))

all_results.sort(key=lambda x: x[1]['lift'], reverse=True)

print(f"\n  {'Signal / Combination':<35} {'N':>5} {'WR%':>6} {'Lift':>6} "
      f"{'MCC':>6}  Verdict")
print(f"  {'-'*35} {'-'*5} {'-'*6} {'-'*6} {'-'*6}  {'-'*20}")

for name, s in all_results:
    n    = s['present_total']
    wr   = s['wr_present'] * 100
    lift = s['lift']
    mcc  = s['mcc']
    # Verdict
    if n < 5:
        v = 'TOO FEW SAMPLES'
    elif lift >= 2.0 and mcc > 0.05:
        v = 'STRONG EDGE'
    elif lift >= 1.5 and mcc > 0.02:
        v = 'USEFUL EDGE'
    elif lift >= 1.1:
        v = 'WEAK EDGE'
    elif lift >= 0.9:
        v = 'NEUTRAL / NOISE'
    else:
        v = 'NEGATIVE PREDICTOR'
    print(f"  {name:<35} {n:>5} {wr:>5.1f}% {lift:>6.2f} {mcc:>+6.3f}  {v}")

print(f"\n  Lift = win_rate_when_present / baseline_win_rate ({base_wr*100:.1f}%)")
print("  MCC  = Matthews Correlation Coefficient (+1=perfect, 0=random, -1=anti)")
print()


# ═════════════════════════════════════════════════════════════════════════════
# PART 4 — Heikin-Ashi late-predictor diagnosis
# ═════════════════════════════════════════════════════════════════════════════

print("#"*52)
print("  PART 4 — HEIKIN-ASHI: NEGATIVE / LATE / USEFUL?")
print("#"*52)

ha_states = ['BULLISH', 'NEUTRAL', 'BEARISH']
print(f"\n  HA state at entry  N_trades  Win%  Lift   Conclusion")
print(f"  {'-'*55}")
for state in ha_states:
    fn_ = lambda t, s=state: sig(t,'heikin_ashi') == s
    trades_in = [t for t in all_trades if fn_(t)]
    n = len(trades_in)
    wins = sum(1 for t in trades_in if is_win(t))
    wr = wins/n if n else 0
    lift = wr/base_wr if base_wr else 0
    if state == 'BULLISH':
        conclusion = 'Late entry — trend already 3+ bars old'
    elif state == 'NEUTRAL':
        conclusion = 'Transition zone — potential early entry'
    else:
        conclusion = 'Counter-trend — dangerous'
    print(f"  {state:<18} {n:>6}  {wr*100:>5.1f}%  {lift:>5.2f}x  {conclusion}")

# ── Sequence analysis: what was HA state the bar BEFORE entry? ────────────────
# (We check this from the stored signal — which is already the state AT entry)
# The key question: when HA transitions NEUTRAL->BULLISH, is that better than
# when it enters BULLISH->BULLISH (sustained)?
# We can approximate this by looking at entry_score ranges:
print(f"\n  HA BULLISH sub-analysis by signal score quartile:")
bull_trades = [t for t in all_trades if sig(t,'heikin_ashi') == 'BULLISH']
if bull_trades:
    scores = sorted(t.get('entry_score',0) for t in bull_trades)
    median_score = statistics.median(scores)
    high_score = [t for t in bull_trades if t.get('entry_score',0) >= median_score]
    low_score  = [t for t in bull_trades if t.get('entry_score',0) <  median_score]
    for label, group in [('High score (>= median)', high_score),
                         ('Low score  (<  median)', low_score)]:
        n = len(group)
        w = sum(1 for t in group if is_win(t))
        wr = w/n if n else 0
        print(f"  {label}: n={n}  WR={wr*100:.1f}%  lift={wr/base_wr:.2f}x")

print()


# ═════════════════════════════════════════════════════════════════════════════
# PART 5 — Final recommendation
# ═════════════════════════════════════════════════════════════════════════════

print("#"*52)
print("  PART 5 — EVIDENCE-BASED RECOMMENDATIONS")
print("#"*52)

best = [(n, s) for n,s in all_results if s['present_total'] >= 5]
best_lift = max(best, key=lambda x: x[1]['lift'])
best_mcc  = max(best, key=lambda x: x[1]['mcc'])

print(f"\n  Best lift   : '{best_lift[0]}'  "
      f"WR={best_lift[1]['wr_present']*100:.1f}%  "
      f"lift={best_lift[1]['lift']:.2f}x  n={best_lift[1]['present_total']}")
print(f"  Best MCC    : '{best_mcc[0]}'  "
      f"MCC={best_mcc[1]['mcc']:+.3f}  n={best_mcc[1]['present_total']}")

# Slope/concavity verdict
slope_s = stats_from_ct(*contingency(all_trades, slope_up))
conc_s  = stats_from_ct(*contingency(all_trades, conc_up))
print(f"\n  Slope (rising) lift={slope_s['lift']:.2f}x  MCC={slope_s['mcc']:+.3f}")
print(f"  Concavity (accel) lift={conc_s['lift']:.2f}x  MCC={conc_s['mcc']:+.3f}")
if slope_s['lift'] < 1.1 and abs(slope_s['mcc']) < 0.05:
    print("  VERDICT: Slope is statistically insignificant. REMOVE from scorer.")
if conc_s['lift'] < 1.1 and abs(conc_s['mcc']) < 0.05:
    print("  VERDICT: Concavity is statistically insignificant. REMOVE from scorer.")

print()
