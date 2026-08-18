"""
decile_analysis.py  --  Factor Decile Analysis for RS=50% / EP=50%
=====================================================================
At every rebalancing date, rank all stocks by composite score,
split into 10 deciles, record 10-day forward returns for each decile.

A genuine factor produces a smooth staircase: D1 (top) best, D10 worst.
"""

import time, math, statistics, warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

REBAL_DAYS = 10
FORWARD_DAYS = 10   # how far ahead we measure each decile's return
N_DECILES = 10

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
    ('CUMMINSIND.NS','CUMMINSIND'),('VOLTAS.NS','VOLTAS'),
    ('BERGEPAINT.NS','BERGEPAINT'),('KANSAINER.NS','KANSAINER'),
    ('DABUR.NS','DABUR'),('MARICO.NS','MARICO'),('COLPAL.NS','COLPAL'),
    ('GODREJCP.NS','GODREJCP'),('EMAMILTD.NS','EMAMILTD'),('PGHH.NS','PGHH'),
    ('LUPIN.NS','LUPIN'),('AUROPHARMA.NS','AUROPHARMA'),('BIOCON.NS','BIOCON'),
    ('ALKEM.NS','ALKEM'),('PFIZER.NS','PFIZER'),
    ('LICHSGFIN.NS','LICHSGFIN'),('M&MFIN.NS','M&MFIN'),('CHOLAFIN.NS','CHOLAFIN'),
    ('PFC.NS','PFC'),('RECLTD.NS','RECLTD'),('IRFC.NS','IRFC'),
    ('SAIL.NS','SAIL'),('NMDC.NS','NMDC'),('VEDL.NS','VEDL'),
    ('IGL.NS','IGL'),('MGL.NS','MGL'),('GUJGASLTD.NS','GUJGASLTD'),
    ('INDIGO.NS','INDIGO'),('SBILIFE.NS','SBILIFE'),('HDFCLIFE.NS','HDFCLIFE'),
    ('NAUKRI.NS','NAUKRI'),('IRCTC.NS','IRCTC'),
    ('TORNTPOWER.NS','TORNTPOWER'),('TATAELXSI.NS','TATAELXSI'),
    ('MPHASIS.NS','MPHASIS'),('LTTS.NS','LTTS'),('COFORGE.NS','COFORGE'),
    ('PERSISTENT.NS','PERSISTENT'),('OFSS.NS','OFSS'),
    ('TRENT.NS','TRENT'),('DMART.NS','DMART'),
    ('IDFCFIRSTB.NS','IDFCFIRSTB'),('AUBANK.NS','AUBANK'),
    ('POLYCAB.NS','POLYCAB'),('KEI.NS','KEI'),
    ('APLAPOLLO.NS','APLAPOLLO'),('DEEPAKNTR.NS','DEEPAKNTR'),
    ('RBLBANK.NS','RBLBANK'),('TATAMOTORS.NS','TATAMOTORS'),
    ('WHIRLPOOL.NS','WHIRLPOOL'),('PAGEIND.NS','PAGEIND'),
    ('VBL.NS','VBL'),('TVSMOTOR.NS','TVSMOTOR'),('ASHOKLEY.NS','ASHOKLEY'),
    ('MOTHERSON.NS','MOTHERSON'),('BHARATFORG.NS','BHARATFORG'),
    ('EXIDEIND.NS','EXIDEIND'),('CESC.NS','CESC'),('NHPC.NS','NHPC'),
    ('RVNL.NS','RVNL'),('MANAPPURAM.NS','MANAPPURAM'),
    ('KPITTECH.NS','KPITTECH'),('CYIENT.NS','CYIENT'),
    ('NAVINFLUOR.NS','NAVINFLUOR'),('PIIND.NS','PIIND'),
    ('METROPOLIS.NS','METROPOLIS'),('MAXHEALTH.NS','MAXHEALTH'),
    ('PNBHOUSING.NS','PNBHOUSING'),('CANFINHOME.NS','CANFINHOME'),
    ('CDSL.NS','CDSL'),('MCX.NS','MCX'),('ANGELONE.NS','ANGELONE'),
    ('RAMCOCEM.NS','RAMCOCEM'),('JKCEMENT.NS','JKCEMENT'),
    ('DALBHARAT.NS','DALBHARAT'),('SUNDARMFIN.NS','SUNDARMFIN'),
    ('ZENSARTECH.NS','ZENSARTECH'),('ASTRAL.NS','ASTRAL'),
    ('MCDOWELL-N.NS','MCDOWELL-N'),
]

# ── Data fetch ─────────────────────────────────────────────────────────────────
print('Fetching data...')
price_data = {}; valid = []
for ticker, sym in STOCKS:
    try:
        df = yf.Ticker(ticker).history(period='5y', interval='1d', auto_adjust=True)
        if not df.empty:
            d = {str(ts.date()): {'close': float(r['Close']),
                                   'vol':   float(r.get('Volume',0) or 0)}
                 for ts, r in df.iterrows()}
            if len(d) >= 300:
                price_data[sym] = d; valid.append(sym)
    except Exception: pass
    time.sleep(0.22)

nifty = {}
try:
    df = yf.Ticker('^NSEI').history(period='5y', interval='1d', auto_adjust=True)
    nifty = {str(ts.date()): {'close': float(r['Close'])} for ts, r in df.iterrows()}
except Exception: pass

all_dates = sorted(nifty.keys())
N = len(all_dates)

# IS / OOS split (3y IS, 2y OOS — same as original walk-forward)
IS_CUTOFF  = all_dates[int(N * 0.6)]
print(f'Universe: {len(valid)} stocks  |  {all_dates[0]} to {all_dates[-1]}  ({N} days)')
print(f'IS cutoff: {IS_CUTOFF}  (60% IS / 40% OOS)')

# ── Factor engine ──────────────────────────────────────────────────────────────
def compute_composite(price_data, syms, nifty, dates, i):
    """Return {sym: composite_score} for all valid stocks at bar i."""
    if i < 72: return {}
    dn = dates[i]
    nc = nifty.get(dn, {}).get('close')
    np_ = nifty.get(dates[i-63], {}).get('close') if i >= 63 else None

    raw_rs = {}; raw_ep = {}
    for sym in syms:
        c = price_data[sym]
        sd = [d for d in dates[max(0,i-74):i+1] if d in c]
        if len(sd) < 50: continue
        # RS
        if nc and np_ and i >= 63:
            cn = c.get(dn,{}).get('close'); cp = c.get(dates[i-63],{}).get('close')
            if cn and cp: raw_rs[sym] = (cn/cp - 1)*100 - (nc/np_ - 1)*100
        # EP
        ed = sd[-63:]
        evols = [c[d]['vol'] for d in ed if c[d]['vol'] > 0]
        av = sum(evols)/len(evols) if evols else 0
        ep = 0.0
        for j in range(1, len(ed)):
            cj = c.get(ed[j]); cjm = c.get(ed[j-1])
            if not (cj and cjm and cjm['close'] > 0): continue
            dr = cj['close']/cjm['close'] - 1
            if dr > 0.02 and av > 0 and cj['vol'] > 1.5*av:
                ep = max(ep, dr*100)
        raw_ep[sym] = ep

    # Cross-sectional percentile rank
    def pctrank(d):
        items = sorted(d.items(), key=lambda x: x[1])
        n = len(items)
        return {sym: (r+1)/n*100 for r, (sym,_) in enumerate(items)}

    if not raw_rs or not raw_ep: return {}
    rnk_rs = pctrank(raw_rs)
    rnk_ep = pctrank(raw_ep)
    common = set(rnk_rs) & set(rnk_ep)
    return {sym: 0.5*rnk_rs[sym] + 0.5*rnk_ep[sym] for sym in common}

# ── Decile collection ──────────────────────────────────────────────────────────
# For each rebalancing point: score all stocks, assign decile, record FORWARD_DAYS return
# decile_obs[period][d] = list of forward returns  (period: 'full'/'is'/'oos')

decile_obs = {
    'full': {d: [] for d in range(1, N_DECILES+1)},
    'is':   {d: [] for d in range(1, N_DECILES+1)},
    'oos':  {d: [] for d in range(1, N_DECILES+1)},
}

# per-decile cumulative equity (for annualised return calculation)
# We'll track via average log returns

rebal_dates_used = 0
i = 72  # warmup
while i < N - FORWARD_DAYS:
    scores = compute_composite(price_data, valid, nifty, all_dates, i)
    if len(scores) >= N_DECILES * 2:  # need enough stocks for clean deciles
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        n = len(ranked)
        bucket_size = n / N_DECILES

        for d in range(1, N_DECILES+1):
            lo = int((d-1) * bucket_size)
            hi = int(d * bucket_size)
            bucket = ranked[lo:hi]

            fwd_rets = []
            for sym, _ in bucket:
                c = price_data[sym]
                entry_d = all_dates[i]
                exit_d  = all_dates[i + FORWARD_DAYS]
                p0 = c.get(entry_d, {}).get('close')
                p1 = c.get(exit_d,  {}).get('close')
                if p0 and p1 and p0 > 0:
                    fwd_rets.append((p1/p0 - 1)*100)

            if fwd_rets:
                avg = sum(fwd_rets)/len(fwd_rets)
                decile_obs['full'][d].append(avg)
                period = 'is' if all_dates[i] < IS_CUTOFF else 'oos'
                decile_obs[period][d].append(avg)

        rebal_dates_used += 1
    i += REBAL_DAYS

print(f'Rebalancing points used: {rebal_dates_used}\n')

# ── Nifty forward return benchmark ────────────────────────────────────────────
nifty_fwd = {'full': [], 'is': [], 'oos': []}
i = 72
while i < N - FORWARD_DAYS:
    d0 = all_dates[i]; d1 = all_dates[i + FORWARD_DAYS]
    n0 = nifty.get(d0,{}).get('close'); n1 = nifty.get(d1,{}).get('close')
    if n0 and n1:
        r = (n1/n0 - 1)*100
        nifty_fwd['full'].append(r)
        period = 'is' if d0 < IS_CUTOFF else 'oos'
        nifty_fwd[period].append(r)
    i += REBAL_DAYS

def nifty_avg(p): return sum(nifty_fwd[p])/len(nifty_fwd[p]) if nifty_fwd[p] else 0

# ── Reporting helper ───────────────────────────────────────────────────────────
BAR_CHARS = 40

def bar(val, mn, mx):
    """ASCII bar chart, anchored at zero, scaled to [mn, mx]."""
    span = mx - mn if mx > mn else 1
    zero_pos = int((-mn / span) * BAR_CHARS)
    val_pos  = int(((val - mn) / span) * BAR_CHARS)
    lo, hi = min(zero_pos, val_pos), max(zero_pos, val_pos)
    b = [' '] * BAR_CHARS
    b[zero_pos] = '|'
    for k in range(lo, hi+1): b[k] = '#'
    b[zero_pos] = '|'
    return ''.join(b)

def monotonicity(means):
    """Fraction of adjacent pairs that go in the right direction (D1 > D2 > ... > D10)."""
    n_correct = sum(1 for k in range(len(means)-1) if means[k] > means[k+1])
    return n_correct / (len(means)-1) * 100

def spread_t(d1_obs, d10_obs):
    """t-stat for D1 mean > D10 mean (Welch)."""
    if len(d1_obs) < 3 or len(d10_obs) < 3: return 0
    m1, m10 = statistics.mean(d1_obs), statistics.mean(d10_obs)
    v1  = statistics.variance(d1_obs)/len(d1_obs)
    v10 = statistics.variance(d10_obs)/len(d10_obs)
    se  = (v1 + v10)**0.5
    return (m1 - m10)/se if se > 0 else 0

SEP  = '=' * 100
sep  = '-' * 100
DECO = {1:'***', 2:'** ', 3:'*  ', 10:'   '}

def print_decile_table(period_label, period_key):
    print(SEP)
    print(f'  DECILE ANALYSIS  --  {period_label}')
    print(SEP)

    obs_all = decile_obs[period_key]
    means   = [statistics.mean(obs_all[d]) if obs_all[d] else 0 for d in range(1, N_DECILES+1)]
    mn, mx  = min(means), max(means)
    nn      = nifty_avg(period_key)
    spread  = means[0] - means[-1]
    mono    = monotonicity(means)
    t       = spread_t(obs_all[1], obs_all[10])

    print(f'  {"Decile":<10} {"Label":<14} {"Avg Fwd Ret":>12} {"Obs":>6}  {"Bar (0=Nifty avg)":>10}')
    print(sep)
    labels = ['Top 10%','11-20%','21-30%','31-40%','41-50%',
              '51-60%','61-70%','71-80%','81-90%','Bottom 10%']
    for d in range(1, N_DECILES+1):
        obs  = obs_all[d]
        mean = statistics.mean(obs) if obs else 0
        n    = len(obs)
        b    = bar(mean, mn - 0.1, mx + 0.1)
        star = '***' if d == 1 else ('   ' if d == N_DECILES else '   ')
        print(f'  D{d:<9} {labels[d-1]:<14} {mean:>+10.3f}%  {n:>6}  {b}  {star}')
    print(sep)
    print(f'  {"Nifty B&H":24} {nn:>+10.3f}%  {"":>6}  {bar(nn, mn-0.1, mx+0.1)}')
    print()
    print(f'  D1 - D10 spread    : {spread:+.3f}%  per {FORWARD_DAYS}-day period')
    ann_spread = ((1 + spread/100)**(252/FORWARD_DAYS) - 1)*100
    print(f'  Annualised spread  : {ann_spread:+.1f}%  per year')
    print(f'  Monotonicity       : {mono:.0f}%  ({int(mono/100*(N_DECILES-1))}/{N_DECILES-1} pairs in correct order)')
    print(f'  D1 vs D10 t-stat   : {t:.2f}  (>2.0 = statistically significant at 95%)')
    if mono >= 89 and t > 2.0:
        print('  Verdict: STRONG STAIRCASE -- factor is real, robust, and statistically significant.')
    elif mono >= 67 and t > 1.5:
        print('  Verdict: SOLID STAIRCASE -- factor has genuine signal with minor noise.')
    elif mono >= 56:
        print('  Verdict: WEAK STAIRCASE -- directional bias present but noisy.')
    else:
        print('  Verdict: NO STAIRCASE -- factor does not rank stocks predictively.')

# ── Individual factor deciles (RS alone, EP alone, composite) ─────────────────
def compute_single_factor(price_data, syms, nifty, dates, i, factor):
    if i < 72: return {}
    dn = dates[i]
    nc = nifty.get(dn, {}).get('close')
    np_ = nifty.get(dates[i-63], {}).get('close') if i >= 63 else None

    raw = {}
    for sym in syms:
        c = price_data[sym]
        sd = [d for d in dates[max(0,i-74):i+1] if d in c]
        if len(sd) < 50: continue
        if factor == 'rs':
            if nc and np_:
                cn = c.get(dn,{}).get('close'); cp = c.get(dates[i-63],{}).get('close')
                if cn and cp: raw[sym] = (cn/cp - 1)*100 - (nc/np_ - 1)*100
        elif factor == 'ep':
            ed = sd[-63:]
            evols = [c[d]['vol'] for d in ed if c[d]['vol'] > 0]
            av = sum(evols)/len(evols) if evols else 0
            ep = 0.0
            for j in range(1, len(ed)):
                cj = c.get(ed[j]); cjm = c.get(ed[j-1])
                if not (cj and cjm and cjm['close'] > 0): continue
                dr = cj['close']/cjm['close'] - 1
                if dr > 0.02 and av > 0 and cj['vol'] > 1.5*av:
                    ep = max(ep, dr*100)
            raw[sym] = ep
    return raw

# Collect per-factor raw decile obs (OOS only — honest)
print('Running individual factor decile collection...')
factor_obs = {f: {d: [] for d in range(1, N_DECILES+1)} for f in ('rs','ep')}
i = 72
while i < N - FORWARD_DAYS:
    if all_dates[i] >= IS_CUTOFF:
        for f in ('rs','ep'):
            raw = compute_single_factor(price_data, valid, nifty, all_dates, i, f)
            if len(raw) >= N_DECILES * 2:
                ranked = sorted(raw.items(), key=lambda x: -x[1])
                n = len(ranked); bucket_size = n / N_DECILES
                for d in range(1, N_DECILES+1):
                    lo, hi = int((d-1)*bucket_size), int(d*bucket_size)
                    fwd = []
                    for sym, _ in ranked[lo:hi]:
                        c = price_data[sym]
                        p0 = c.get(all_dates[i],{}).get('close')
                        p1 = c.get(all_dates[i+FORWARD_DAYS],{}).get('close')
                        if p0 and p1 and p0 > 0: fwd.append((p1/p0-1)*100)
                    if fwd: factor_obs[f][d].append(sum(fwd)/len(fwd))
    i += REBAL_DAYS

# ── Print all tables ───────────────────────────────────────────────────────────
print_decile_table('FULL PERIOD (5 years, Jun 2021 - Jun 2026)', 'full')
print()
print_decile_table('IN-SAMPLE  (Years 1-3, Jun 2021 - ~Jun 2024)', 'is')
print()
print_decile_table('OUT-OF-SAMPLE  (Years 4-5, ~Jun 2024 - Jun 2026)', 'oos')

# ── Individual factor comparison (OOS only) ────────────────────────────────────
print()
print(SEP)
print('  INDIVIDUAL FACTOR DECILE BREAKDOWN  --  OOS ONLY')
print('  (Shows which factor is driving the staircase)')
print(SEP)
print(f'  {"Decile":<10} {"RS alone":>12}  {"EP alone":>12}  {"Composite":>12}')
print(sep)
oos_comp_means = [statistics.mean(decile_obs['oos'][d]) if decile_obs['oos'][d] else 0
                  for d in range(1, N_DECILES+1)]
for d in range(1, N_DECILES+1):
    rs_m  = statistics.mean(factor_obs['rs'][d])  if factor_obs['rs'][d]  else 0
    ep_m  = statistics.mean(factor_obs['ep'][d])  if factor_obs['ep'][d]  else 0
    co_m  = oos_comp_means[d-1]
    best  = '  <- best' if d == 1 else ('  <- worst' if d == 10 else '')
    print(f'  D{d:<9} {rs_m:>+11.3f}%  {ep_m:>+11.3f}%  {co_m:>+11.3f}%{best}')
print(sep)
# Spreads
rs_sp  = (statistics.mean(factor_obs['rs'][1])  if factor_obs['rs'][1]  else 0) - \
         (statistics.mean(factor_obs['rs'][10]) if factor_obs['rs'][10] else 0)
ep_sp  = (statistics.mean(factor_obs['ep'][1])  if factor_obs['ep'][1]  else 0) - \
         (statistics.mean(factor_obs['ep'][10]) if factor_obs['ep'][10] else 0)
co_sp  = oos_comp_means[0] - oos_comp_means[-1]
print(f'  {"D1-D10 spread":<10} {rs_sp:>+11.3f}%  {ep_sp:>+11.3f}%  {co_sp:>+11.3f}%')
rs_mn  = monotonicity([statistics.mean(factor_obs['rs'][d])  if factor_obs['rs'][d]  else 0 for d in range(1,11)])
ep_mn  = monotonicity([statistics.mean(factor_obs['ep'][d])  if factor_obs['ep'][d]  else 0 for d in range(1,11)])
co_mn  = monotonicity(oos_comp_means)
print(f'  {"Monotonicity":<10} {rs_mn:>+10.0f}%  {ep_mn:>+10.0f}%  {co_mn:>+10.0f}%')

# ── Staircase summary ──────────────────────────────────────────────────────────
print()
print(SEP)
print('  VISUAL STAIRCASE  --  OOS COMPOSITE  (each # = ~0.05% return)')
print(SEP)
mn_v = min(oos_comp_means); mx_v = max(oos_comp_means)
labels = ['Top 10%  ','11-20%   ','21-30%   ','31-40%   ','41-50%   ',
          '51-60%   ','61-70%   ','71-80%   ','81-90%   ','Bottom 10%']
for idx, m in enumerate(oos_comp_means):
    d = idx + 1
    scaled = int(((m - mn_v)/(mx_v - mn_v + 1e-9)) * 50)
    bar_s  = '#' * scaled
    print(f'  D{d}  {labels[idx]}  {m:>+7.3f}%  |{bar_s}')
print()
print(f'  Full spread D1 to D10: {oos_comp_means[0]:+.3f}% to {oos_comp_means[-1]:+.3f}%  '
      f'({oos_comp_means[0]-oos_comp_means[-1]:+.3f}% per {FORWARD_DAYS} days)')
ann = ((1+(oos_comp_means[0]-oos_comp_means[-1])/100)**(252/FORWARD_DAYS)-1)*100
print(f'  Annualised D1-D10 edge: {ann:+.1f}% per year')
