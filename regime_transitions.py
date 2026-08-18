"""
regime_transitions.py
Analyse Policy C regime switches and re-entry lag vs market bottom.
Uses the same Nifty data source as final_validation.py.
"""
import warnings, datetime
warnings.filterwarnings('ignore')
import yfinance as yf

# ── Fetch 5-year Nifty data (same as final_validation.py) ─────────────────────
print("Fetching Nifty 5-year data...")
raw = yf.download("^NSEI", period="5y", interval="1d", progress=False, auto_adjust=True)
closes_series = raw["Close"].dropna()
nifty_dates  = [d.strftime("%Y-%m-%d") for d in closes_series.index]
nifty_vals   = [float(v) for v in closes_series.values]
nifty_closes = list(zip(nifty_dates, nifty_vals))
N = len(nifty_dates)
print(f"Data: {nifty_dates[0]} to {nifty_dates[-1]}  ({N} trading days)\n")

# ── Build DMA table ────────────────────────────────────────────────────────────
nifty_dma = {}
for idx, (d, c) in enumerate(nifty_closes):
    dma50  = sum(v for _,v in nifty_closes[max(0,idx-49):idx+1]) / min(idx+1, 50)
    dma200 = sum(v for _,v in nifty_closes[max(0,idx-199):idx+1]) / min(idx+1, 200)
    nifty_dma[d] = {"close": c, "dma50": dma50, "dma200": dma200}

def get_regime(date):
    r = nifty_dma.get(date)
    if not r: return "Bull"
    c, d50, d200 = r["close"], r["dma50"], r["dma200"]
    if c < d200:    return "Bear"
    if d50 <= d200: return "Flat"
    return "Bull"

# ── Build daily regime list ────────────────────────────────────────────────────
daily_regimes = [(d, get_regime(d)) for d in nifty_dates]

# ── Detect transitions ─────────────────────────────────────────────────────────
transitions = []
for i in range(1, N):
    prev = daily_regimes[i-1][1]
    curr = daily_regimes[i][1]
    if curr != prev:
        transitions.append({
            "date": daily_regimes[i][0],
            "from": prev,
            "to":   curr,
            "nifty": nifty_dma[daily_regimes[i][0]]["close"],
        })

print(f"{'='*62}")
print(f"  POLICY C  —  ALL REGIME TRANSITIONS  ({len(transitions)} total)")
print(f"{'='*62}")
print(f"  {'Date':<12} {'From':<6} {'To':<6} {'Nifty':>8}")
print(f"  {'-'*50}")
for t in transitions:
    arrow = "v BEAR" if t["to"]=="Bear" else ("^ BULL" if t["to"]=="Bull" else "~ FLAT")
    print(f"  {t['date']:<12} {t['from']:<6} > {t['to']:<6}  {t['nifty']:>8.0f}  {arrow}")

# ── Transition summary counts ──────────────────────────────────────────────────
from collections import Counter
pair_counts = Counter(f"{t['from']}>{t['to']}" for t in transitions)
print(f"\n  Transition pair counts:")
for pair, cnt in sorted(pair_counts.items()):
    print(f"    {pair:<14} : {cnt}")

# ── Identify Bear episodes and compute re-entry lag ───────────────────────────
# A Bear episode = entry into Bear + exit from Bear (back to Bull or Flat)
# Re-entry lag  = first date regime exits Bear  MINUS  date of Nifty trough
#                 (trough = lowest close DURING the Bear episode)

bear_episodes = []
in_bear = False
bear_start_idx = None

for i, (d, reg) in enumerate(daily_regimes):
    if reg == "Bear" and not in_bear:
        in_bear = True
        bear_start_idx = i
    elif reg != "Bear" and in_bear:
        in_bear = False
        bear_end_idx = i  # first non-Bear day = re-entry signal day
        bear_episode_dates = [daily_regimes[j][0] for j in range(bear_start_idx, bear_end_idx)]
        bear_closes = [nifty_dma[d]["close"] for d in bear_episode_dates]
        trough_idx_local = bear_closes.index(min(bear_closes))
        trough_date = bear_episode_dates[trough_idx_local]
        reentry_date = daily_regimes[bear_end_idx][0]
        # Lag in calendar days
        td_trough  = datetime.date.fromisoformat(trough_date)
        td_reentry = datetime.date.fromisoformat(reentry_date)
        cal_lag = (td_reentry - td_trough).days
        # Lag in trading days
        td_lag = bear_end_idx - (bear_start_idx + trough_idx_local)
        bear_episodes.append({
            "bear_start":   daily_regimes[bear_start_idx][0],
            "bear_end":     reentry_date,
            "duration_td":  bear_end_idx - bear_start_idx,
            "trough_date":  trough_date,
            "trough_close": min(bear_closes),
            "reentry_date": reentry_date,
            "reentry_close": nifty_dma[reentry_date]["close"],
            "lag_cal_days": cal_lag,
            "lag_td":       td_lag,
            "nifty_recovery_pct": (nifty_dma[reentry_date]["close"] / min(bear_closes) - 1) * 100,
        })

# Handle open Bear episode (if still in Bear at end of data)
if in_bear:
    bear_episode_dates = [daily_regimes[j][0] for j in range(bear_start_idx, N)]
    bear_closes = [nifty_dma[d]["close"] for d in bear_episode_dates]
    trough_idx_local = bear_closes.index(min(bear_closes))
    trough_date = bear_episode_dates[trough_idx_local]
    bear_episodes.append({
        "bear_start":   daily_regimes[bear_start_idx][0],
        "bear_end":     "OPEN",
        "duration_td":  N - bear_start_idx,
        "trough_date":  trough_date,
        "trough_close": min(bear_closes),
        "reentry_date": "—",
        "reentry_close": None,
        "lag_cal_days": None,
        "lag_td":       None,
        "nifty_recovery_pct": None,
    })

print(f"\n{'='*72}")
print(f"  BEAR EPISODES  ({len(bear_episodes)} episodes)")
print(f"{'='*72}")
header = f"  {'#':<3} {'Bear start':<12} {'Re-entry':<12} {'Dur(td)':<9} {'Trough date':<13} {'Trough':>7} {'Re-entry px':>11} {'Lag(cal)':>9} {'Lag(td)':>8} {'Recov%':>7}"
print(header)
print(f"  {'-'*90}")
for i, ep in enumerate(bear_episodes, 1):
    lag_cal = f"{ep['lag_cal_days']}d" if ep['lag_cal_days'] is not None else "OPEN"
    lag_td  = f"{ep['lag_td']}td"  if ep['lag_td'] is not None else "OPEN"
    recov   = f"{ep['nifty_recovery_pct']:+.1f}%" if ep['nifty_recovery_pct'] is not None else "OPEN"
    reentry_px = f"{ep['reentry_close']:.0f}" if ep['reentry_close'] else "—"
    print(f"  {i:<3} {ep['bear_start']:<12} {ep['bear_end']:<12} {ep['duration_td']:<9} {ep['trough_date']:<13} {ep['trough_close']:>7.0f} {reentry_px:>11} {lag_cal:>9} {lag_td:>8} {recov:>7}")

# ── Summary statistics (closed episodes only) ─────────────────────────────────
closed = [ep for ep in bear_episodes if ep["lag_cal_days"] is not None]
if closed:
    avg_cal = sum(ep["lag_cal_days"] for ep in closed) / len(closed)
    avg_td  = sum(ep["lag_td"]       for ep in closed) / len(closed)
    avg_rec = sum(ep["nifty_recovery_pct"] for ep in closed) / len(closed)
    avg_dur = sum(ep["duration_td"]   for ep in closed) / len(closed)
    max_lag = max(ep["lag_cal_days"]  for ep in closed)
    min_lag = min(ep["lag_cal_days"]  for ep in closed)
    print(f"\n{'='*60}")
    print(f"  RE-ENTRY LAG STATISTICS  ({len(closed)} closed Bear episodes)")
    print(f"{'='*60}")
    print(f"  Avg Bear duration        : {avg_dur:.1f} trading days")
    print(f"  Avg lag trough>re-entry  : {avg_cal:.1f} calendar days  /  {avg_td:.1f} trading days")
    print(f"  Min lag                  : {min_lag} calendar days")
    print(f"  Max lag                  : {max_lag} calendar days")
    print(f"  Avg Nifty recovery@reentry: {avg_rec:+.1f}% above trough")
    print(f"\n  NOTE: 'lag' = calendar days from Nifty trough (lowest Bear close)")
    print(f"        to first trading day the regime flips back to Bull or Flat.")
    print(f"        Strategy re-entry is next open after that signal day (+1 bar).")

# ── Regime time-in-state breakdown ────────────────────────────────────────────
from collections import Counter
regime_counts = Counter(r for _, r in daily_regimes)
total = sum(regime_counts.values())
print(f"\n{'='*40}")
print(f"  FULL-SAMPLE REGIME BREAKDOWN")
print(f"{'='*40}")
for reg in ["Bull", "Flat", "Bear"]:
    cnt = regime_counts[reg]
    print(f"  {reg:<6}: {cnt:>4} days  ({cnt/total*100:.1f}%)")
print(f"  Total : {total} trading days")
