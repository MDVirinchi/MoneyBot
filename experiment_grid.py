"""
experiment_grid.py — Systematic search for PF > 1.2 on daily bars.

Experiment groups (each one isolated so only one variable changes at a time):
  A. Threshold sweep          (score gate 0.40 → 0.75)
  B. Regime filter            (Nifty EMA21 gate)
  C. R:R sweep                (widen TP, loosen trailing stop)
  D. Best threshold + regime
  E. Best R:R on best threshold+regime config
"""

import time, logging, warnings, itertools
from collections import defaultdict

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from backtest import Backtester, _grade

STOCKS = [
    ('NSE_EQ|INE002A01018', 'RELIANCE'),
    ('NSE_EQ|INE467B01029', 'TCS'),
    ('NSE_EQ|INE009A01021', 'INFY'),
    ('NSE_EQ|INE040A01034', 'HDFCBANK'),
]

bt = Backtester(capital=5000.0)

def run_all(label, **kwargs):
    """Run all 4 stocks with given kwargs, return avg metrics dict."""
    results = {}
    for inst, sym in STOCKS:
        m = bt.run(inst, sym, days=365, interval='1day', **kwargs)
        results[sym] = m
        time.sleep(0.4)
    trades = [results[s].get('total_trades', 0) for s in results if 'error' not in results[s]]
    wr     = [results[s].get('win_rate_pct', 0) for s in results if 'error' not in results[s]]
    pf     = [results[s].get('profit_factor', 0) for s in results if 'error' not in results[s]]
    sh     = [results[s].get('sharpe_ratio', 0)  for s in results if 'error' not in results[s]]
    cagr   = [results[s].get('cagr_pct', 0)      for s in results if 'error' not in results[s]]
    dd     = [results[s].get('max_drawdown_pct', 0) for s in results if 'error' not in results[s]]
    costs  = [results[s].get('total_costs_rs', 0)   for s in results if 'error' not in results[s]]
    n = len(trades) or 1
    return {
        'label':   label,
        'trades':  sum(trades)/n,
        'wr':      sum(wr)/n,
        'pf':      sum(pf)/n,
        'sharpe':  sum(sh)/n,
        'cagr':    sum(cagr)/n,
        'dd':      sum(dd)/n,
        'costs':   sum(costs)/n,
        'raw':     results,
    }

all_results = []

# ── A. Threshold sweep ────────────────────────────────────────────────────────
print('=' * 72)
print('  GROUP A — THRESHOLD SWEEP  (daily, SL=2%, TP=4%, Trail=1.5%)')
print('=' * 72)
for score in [0.40, 0.50, 0.60, 0.65, 0.70, 0.75]:
    label = f'A: score={score}'
    print(f'  Running {label}...', flush=True)
    r = run_all(label, min_score=score, regime_filter=False)
    all_results.append(r)
    print(f'    Trades={r["trades"]:.0f}  WR={r["wr"]:.1f}%  PF={r["pf"]:.3f}  '
          f'Sharpe={r["sharpe"]:.2f}  CAGR={r["cagr"]:+.1f}%  DD={r["dd"]:.1f}%')

# ── B. Regime filter sweep ────────────────────────────────────────────────────
print()
print('=' * 72)
print('  GROUP B — REGIME FILTER  (daily, score=0.40, SL=2%, TP=4%)')
print('=' * 72)
for regime in [False, True]:
    label = f'B: regime={regime}'
    print(f'  Running {label}...', flush=True)
    r = run_all(label, min_score=0.40, regime_filter=regime)
    all_results.append(r)
    print(f'    Trades={r["trades"]:.0f}  WR={r["wr"]:.1f}%  PF={r["pf"]:.3f}  '
          f'Sharpe={r["sharpe"]:.2f}  CAGR={r["cagr"]:+.1f}%  DD={r["dd"]:.1f}%')

# ── C. R:R sweep ──────────────────────────────────────────────────────────────
print()
print('=' * 72)
print('  GROUP C — R:R SWEEP  (daily, score=0.40, no regime)')
print('=' * 72)
rr_configs = [
    # (sl, tp, trail, label)
    (2.0, 4.0, 1.5,  'baseline SL2/TP4/T1.5'),
    (2.0, 6.0, 1.5,  'wider TP   SL2/TP6/T1.5'),
    (2.0, 8.0, 2.0,  'wide TP+T  SL2/TP8/T2.0'),
    (1.5, 6.0, 1.5,  'tight SL   SL1.5/TP6/T1.5'),
    (1.5, 4.5, 1.5,  '3:1 ratio  SL1.5/TP4.5/T1.5'),
    (2.0, 4.0, 2.5,  'loose trail SL2/TP4/T2.5'),
    (2.0, 4.0, 3.0,  'loose trail SL2/TP4/T3.0'),
]
for sl, tp, trail, desc in rr_configs:
    label = f'C: {desc}'
    print(f'  Running {label}...', flush=True)
    r = run_all(label, min_score=0.40, regime_filter=False,
                stop_loss_pct=sl, take_profit_pct=tp, trailing_stop_pct=trail)
    all_results.append(r)
    print(f'    Trades={r["trades"]:.0f}  WR={r["wr"]:.1f}%  PF={r["pf"]:.3f}  '
          f'Sharpe={r["sharpe"]:.2f}  CAGR={r["cagr"]:+.1f}%  DD={r["dd"]:.1f}%')

# Find best threshold and best R:R from above
best_thresh_r  = max((r for r in all_results if r['label'].startswith('A:')), key=lambda x: x['pf'])
best_rr_r      = max((r for r in all_results if r['label'].startswith('C:')), key=lambda x: x['pf'])
best_thresh    = float(best_thresh_r['label'].split('=')[1])
# extract best rr params from its label
best_rr_cfg    = rr_configs[all_results.index(best_rr_r) - all_results.index(
    next(r for r in all_results if r['label'].startswith('C:')))]

# ── D. Best threshold + regime ────────────────────────────────────────────────
print()
print('=' * 72)
print(f'  GROUP D — BEST THRESHOLD ({best_thresh}) + REGIME FILTER')
print('=' * 72)
for regime in [False, True]:
    label = f'D: score={best_thresh} regime={regime}'
    print(f'  Running {label}...', flush=True)
    r = run_all(label, min_score=best_thresh, regime_filter=regime)
    all_results.append(r)
    print(f'    Trades={r["trades"]:.0f}  WR={r["wr"]:.1f}%  PF={r["pf"]:.3f}  '
          f'Sharpe={r["sharpe"]:.2f}  CAGR={r["cagr"]:+.1f}%  DD={r["dd"]:.1f}%')

# ── E. Best threshold+regime + best R:R ──────────────────────────────────────
print()
print('=' * 72)
print(f'  GROUP E — BEST THRESHOLD + REGIME + BEST R:R')
print('=' * 72)
sl_b, tp_b, trail_b, desc_b = best_rr_cfg
for regime in [False, True]:
    label = f'E: score={best_thresh} regime={regime} {desc_b}'
    print(f'  Running {label}...', flush=True)
    r = run_all(label, min_score=best_thresh, regime_filter=regime,
                stop_loss_pct=sl_b, take_profit_pct=tp_b, trailing_stop_pct=trail_b)
    all_results.append(r)
    print(f'    Trades={r["trades"]:.0f}  WR={r["wr"]:.1f}%  PF={r["pf"]:.3f}  '
          f'Sharpe={r["sharpe"]:.2f}  CAGR={r["cagr"]:+.1f}%  DD={r["dd"]:.1f}%')

# ── MASTER RESULTS TABLE ──────────────────────────────────────────────────────
print()
print('=' * 90)
print('  MASTER RESULTS — ALL EXPERIMENTS (sorted by Profit Factor)')
print('=' * 90)
print(f'  {"Label":<42}  {"Trades":>6}  {"WR":>6}  {"PF":>6}  {"Sharpe":>7}  {"CAGR":>8}  {"DD":>7}')
print(f'  {"-"*42}  {"-"*6}  {"-"*6}  {"-"*6}  {"-"*7}  {"-"*8}  {"-"*7}')
for r in sorted(all_results, key=lambda x: x['pf'], reverse=True):
    flag = '  <-- BEST' if r['pf'] == max(x['pf'] for x in all_results) else ''
    pflag = '  ** PF>1.0 **' if r['pf'] >= 1.0 else ('  ** PF>0.5 **' if r['pf'] >= 0.5 else '')
    print(f'  {r["label"]:<42}  {r["trades"]:>6.0f}  {r["wr"]:>5.1f}%  {r["pf"]:>6.3f}  '
          f'{r["sharpe"]:>7.2f}  {r["cagr"]:>+7.1f}%  {r["dd"]:>6.1f}%{pflag}{flag}')

# ── VERDICT ───────────────────────────────────────────────────────────────────
best = max(all_results, key=lambda x: x['pf'])
print()
print('=' * 90)
print('  VERDICT')
print('=' * 90)
print(f'  Best config : {best["label"]}')
print(f'  Best PF     : {best["pf"]:.3f}')
print(f'  Best WR     : {best["wr"]:.1f}%')
print()
if best['pf'] >= 1.2:
    print('  RESULT: PF > 1.2 ACHIEVED. Strategy is viable — run live paper-trading.')
elif best['pf'] >= 1.0:
    print('  RESULT: Strategy breaks even but does not beat costs+slippage adequately.')
    print('  Marginal — needs further improvement before live deployment.')
elif best['pf'] >= 0.5:
    print('  RESULT: Strategy consistently loses money across all parameter combos.')
    print('  PF < 1.0 on every variant tested. Signal logic has weak directional edge.')
    print('  Recommendation: revisit entry signal fundamentals before further tuning.')
else:
    print('  RESULT: Strategy is fundamentally unprofitable.')
    print('  PF < 0.5 on best config — wins too small, losses too frequent.')
    print('  Parameter tuning cannot rescue a strategy with no underlying edge.')

# Per-stock breakdown of best config
print()
print('  Per-stock detail on best config:')
for sym in ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK']:
    m = best['raw'].get(sym, {})
    if 'error' in m: continue
    er = m.get('exit_reasons', {})
    print(f'    {sym:<12}  T={m["total_trades"]:>3}  WR={m["win_rate_pct"]:>5.1f}%  '
          f'PF={m["profit_factor"]:>.3f}  WL={m.get("win_loss_ratio",0):>.2f}x  '
          f'SL={er.get("stop_loss",0):>2}  TP={er.get("take_profit",0):>2}  '
          f'Trail={er.get("trailing_stop",0):>2}')
