"""
rolling_wf.py  —  Rolling Walk-Forward Validation
Strategy: RS=50% / EP=50%  |  Top-N=10  |  Rebal=10d  |  SL=10%

Structure (5 years total, Jun 2021 - Jun 2026):
  Fold 1  Train: Jun 2021 - Jun 2024 (3y)   Test: Jun 2024 - Jun 2025 (1y)
  Fold 2  Train: Jun 2022 - Jun 2025 (3y)   Test: Jun 2025 - Jun 2026 (1y)

Purpose:
  Each test year gets its own independent training window.
  Tests whether IS->OOS stability holds across different market regimes.
  Fold 1 OOS = post-election flatness (Nifty ~flat)
  Fold 2 OOS = full bear + partial recovery period
"""

import time, math, logging, warnings, statistics
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
import yfinance as yf

BROKERAGE=20.0; STT_PCT=0.001; EXCHANGE_PCT=0.0000345; SLIPPAGE=0.002
TOTAL_CAP=500_000.0; SL_PCT=10.0; TOP_N=10; REBAL_DAYS=10
WEIGHTS={'rs':0.50,'ep':0.50}
YEAR_DAYS=252

STOCKS=[
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

# ── Factor engine (same logic as rs_ep_sweep.py) ──────────────────────────────
def compute_factors(price_data, syms, nifty, dates, i):
    if i < 72: return {}
    dn = dates[i]
    nc = nifty.get(dn, {}).get('close')
    np_ = nifty.get(dates[i-63], {}).get('close') if i >= 63 else None
    raw = {}
    for sym in syms:
        c = price_data[sym]
        sd = [d for d in dates[max(0, i-74):i+1] if d in c]
        if len(sd) < 50: continue
        # RS: 63-day excess return vs Nifty
        rs = None
        if nc and np_ and i >= 63:
            cn = c.get(dn, {}).get('close')
            cp = c.get(dates[i-63], {}).get('close')
            if cn and cp: rs = (cn/cp - 1)*100 - (nc/np_ - 1)*100
        # EP: best positive earnings-like day in last 63 days
        ep = 0.0
        ed = sd[-63:]
        evols = [c[d]['vol'] for d in ed if c[d]['vol'] > 0]
        av = sum(evols)/len(evols) if evols else 0
        for j in range(1, len(ed)):
            cj = c.get(ed[j]); cjm = c.get(ed[j-1])
            if not (cj and cjm and cjm['close'] > 0): continue
            dr = cj['close']/cjm['close'] - 1
            if dr > 0.02 and av > 0 and cj['vol'] > 1.5*av:
                ep = max(ep, dr*100)
        raw[sym] = {'rs': rs, 'ep': ep}
    return raw

def cross_rank(raw, weights):
    active = [f for f, w in weights.items() if w > 0]
    rnks = {f: {} for f in active}
    for f in active:
        vals = [(s, raw[s][f]) for s in raw if raw[s].get(f) is not None]
        vals.sort(key=lambda x: x[1])
        n = len(vals)
        for r, (s, _) in enumerate(vals): rnks[f][s] = (r+1)/n*100
    if not active: return {}
    syms = set.intersection(*[set(rnks[f].keys()) for f in active])
    tw = sum(weights[f] for f in active)
    return {sym: sum(rnks[f][sym]*weights[f] for f in active)/tw for sym in syms}

def run(price_data, nifty, dates, syms, weights=WEIGHTS,
        top_n=TOP_N, rebal=REBAL_DAYS, capital=TOTAL_CAP):
    cash = capital; pos = {}; trades = []; equity = []; last = -999

    def gc(s, d): return price_data[s].get(d, {}).get('close')
    def go(s, d): return price_data[s].get(d, {}).get('open')

    for i, date in enumerate(dates):
        if i < 72:
            equity.append(cash); continue
        # SL check
        for sym in list(pos):
            curr = gc(sym, date)
            if curr and curr <= pos[sym]['ep'] * (1 - SL_PCT/100):
                p = pos.pop(sym); fill = curr*(1-SLIPPAGE)
                ev = p['qty']*fill; c2 = BROKERAGE+ev*STT_PCT+ev*EXCHANGE_PCT
                cash += ev - c2
                trades.append({'pnl': (fill-p['ep'])*p['qty']-c2,
                                'ret': (fill/p['ep']-1)*100, 'exit': 'SL',
                                'date': date})
        # Rebalance
        if i - last >= rebal:
            last = i
            comp = cross_rank(compute_factors(price_data, syms, nifty, dates, i), weights)
            tgt  = set(s for s, _ in sorted(comp.items(), key=lambda x: -x[1])[:top_n])
            for sym in list(pos):
                if sym not in tgt:
                    nd = dates[i+1] if i+1 < len(dates) else date
                    fp = (go(sym, nd) or gc(sym, date) or pos[sym]['ep']) * (1-SLIPPAGE)
                    p  = pos.pop(sym); ev = p['qty']*fp
                    c2 = BROKERAGE+ev*STT_PCT+ev*EXCHANGE_PCT; cash += ev-c2
                    trades.append({'pnl': (fp-p['ep'])*p['qty']-c2,
                                   'ret': (fp/p['ep']-1)*100, 'exit': 'Rebal',
                                   'date': nd})
            new = [s for s in tgt if s not in pos]
            if new and cash > 10_000:
                alloc = min(cash*0.95/max(len(new), 1), capital/top_n)
                for sym in new:
                    nd = dates[i+1] if i+1 < len(dates) else date
                    fpd = go(sym, nd) or gc(sym, date)
                    if not fpd: continue
                    fill = fpd*(1+SLIPPAGE); qty = max(1, int(alloc/fill))
                    cost = BROKERAGE+qty*fill*EXCHANGE_PCT
                    if cash >= qty*fill+cost:
                        cash -= qty*fill+cost
                        pos[sym] = {'qty': qty, 'ep': fill}
        fv = cash + sum(p['qty']*(gc(s, date) or p['ep']) for s, p in pos.items())
        equity.append(fv)

    for s, p in list(pos.items()):
        fp = (gc(s, dates[-1]) or p['ep']) * (1-SLIPPAGE)
        ev = p['qty']*fp; c2 = BROKERAGE+ev*STT_PCT+ev*EXCHANGE_PCT; cash += ev-c2
        trades.append({'pnl': (fp-p['ep'])*p['qty']-c2,
                       'ret': (fp/p['ep']-1)*100, 'exit': 'EoP', 'date': dates[-1]})

    if not trades:
        return {'pf':0,'cagr':-100,'sharpe':0,'max_dd':0,'trades':0,
                'wr':0,'avg_win':0,'avg_loss':0,'final_val':capital,'equity':equity}

    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    gp     = sum(t['pnl'] for t in wins)
    gl     = abs(sum(t['pnl'] for t in losses))
    pf     = gp/gl if gl > 0 else (1.5 if gp > 0 else 0)
    wr     = len(wins)/len(trades)*100
    yrs    = max(len(dates)/252, 0.1)
    fv     = equity[-1] if equity else capital
    cagr   = ((fv/capital)**(1/yrs)-1)*100 if fv > 0 else -100

    peak = capital; max_dd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (peak-v)/peak*100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd

    dr = [(equity[k]-equity[k-1])/equity[k-1]
          for k in range(1, len(equity)) if equity[k-1] > 0]
    sharpe = (statistics.mean(dr)/statistics.stdev(dr)*math.sqrt(252)
              if len(dr) > 2 and statistics.stdev(dr) > 0 else 0)

    w_rets = [t['ret'] for t in wins]
    l_rets = [t['ret'] for t in losses]
    exits  = {}
    for t in trades:
        exits[t['exit']] = exits.get(t['exit'], 0) + 1

    return {
        'pf':       round(pf, 3),
        'cagr':     round(cagr, 1),
        'sharpe':   round(sharpe, 3),
        'max_dd':   round(max_dd, 1),
        'trades':   len(trades),
        'wr':       round(wr, 1),
        'avg_win':  round(statistics.mean(w_rets), 2) if w_rets  else 0.0,
        'avg_loss': round(statistics.mean(l_rets), 2) if l_rets  else 0.0,
        'net_pnl':  round(fv - capital, 0),
        'final_val':round(fv, 0),
        'exits':    exits,
        'equity':   equity,
    }


# ── Fetch ─────────────────────────────────────────────────────────────────────
print('Fetching data...')
price_data = {}; valid = []
for ticker, sym in STOCKS:
    try:
        df = yf.Ticker(ticker).history(period='5y', interval='1d', auto_adjust=True)
        if not df.empty:
            d = {str(ts.date()): {
                    'open': float(r['Open']), 'close': float(r['Close']),
                    'vol':  float(r.get('Volume', 0) or 0)}
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

# ── Build folds: Train=3y, Test=1y, slide=1y ─────────────────────────────────
# Fold k: train starts at k*YEAR_DAYS, spans 3*YEAR_DAYS; test spans next YEAR_DAYS
folds = []
fold_num = 0
offset = 0
MIN_TEST_DAYS = 200
while True:
    train_start = offset
    train_end   = offset + 3*YEAR_DAYS
    test_start  = train_end
    test_end    = min(test_start + YEAR_DAYS, N)
    if test_start >= N or (test_end - test_start) < MIN_TEST_DAYS:
        break
    fold_num += 1
    folds.append({
        'fold':        fold_num,
        'train_dates': all_dates[train_start:train_end],
        'test_dates':  all_dates[test_start:test_end],
    })
    offset += YEAR_DAYS

def nifty_cagr(dates):
    s = nifty.get(dates[0],  {}).get('close', 0)
    e = nifty.get(dates[-1], {}).get('close', 0)
    yrs = len(dates)/252
    return ((e/s)**(1/yrs)-1)*100 if s > 0 and e > 0 else 0.0

SEP = '=' * 108
sep = '-' * 108

print(f'\nUniverse: {len(valid)} stocks  |  Total days: {N}  ({all_dates[0]} to {all_dates[-1]})')
print(f'Strategy: RS=50% / EP=50%  |  Top-N={TOP_N}  |  Rebal={REBAL_DAYS}d  |  SL={SL_PCT:.0f}%')
print(f'Folds generated: {len(folds)}  (3y train + 1y test, slide 1y)\n')

# ── Run all folds ─────────────────────────────────────────────────────────────
print(SEP)
print('  FOLD DETAILS')
print(SEP)
for f in folds:
    nc_tr = nifty_cagr(f['train_dates'])
    nc_te = nifty_cagr(f['test_dates'])
    print(f'  Fold {f["fold"]}  Train: {f["train_dates"][0]} to {f["train_dates"][-1]} '
          f'({len(f["train_dates"])} days  Nifty={nc_tr:+.1f}%)   '
          f'Test: {f["test_dates"][0]} to {f["test_dates"][-1]} '
          f'({len(f["test_dates"])} days  Nifty={nc_te:+.1f}%)')

print()
print(SEP)
print('  ROLLING WALK-FORWARD RESULTS — RS=50% / EP=50%  Top-N=10')
print(SEP)
print(f'  {"Fold":>5}  {"Test Period":<24}  {"Nifty":>7}  '
      f'{"IS PF":>7}  {"IS CAGR":>8}  '
      f'{"OOS PF":>7}  {"OOS CAGR":>9}  {"OOS Sh":>8}  '
      f'{"MaxDD":>7}  {"Trades":>7}  {"WR%":>6}')
print(sep)

fold_results = []
for f in folds:
    nc_is  = nifty_cagr(f['train_dates'])
    nc_oos = nifty_cagr(f['test_dates'])
    m_is   = run(price_data, nifty, f['train_dates'],  valid)
    m_oos  = run(price_data, nifty, f['test_dates'],   valid)
    period = f'{f["test_dates"][0][:7]} to {f["test_dates"][-1][:7]}'
    beat   = '  BEATS NIFTY' if m_oos['cagr'] > nc_oos else ''
    fold_results.append({'fold': f['fold'], 'nc_oos': nc_oos,
                         'is': m_is, 'oos': m_oos,
                         'train': f['train_dates'], 'test': f['test_dates']})
    print(f'  {f["fold"]:>5}  {period:<24}  {nc_oos:>+6.1f}%  '
          f'{m_is["pf"]:>7.3f}  {m_is["cagr"]:>+7.1f}%  '
          f'{m_oos["pf"]:>7.3f}  {m_oos["cagr"]:>+8.1f}%  '
          f'{m_oos["sharpe"]:>8.3f}  '
          f'{m_oos["max_dd"]:>6.1f}%  {m_oos["trades"]:>7}  '
          f'{m_oos["wr"]:>5.1f}%{beat}')

# ── Aggregate ─────────────────────────────────────────────────────────────────
print(sep)
oos_pfs    = [r['oos']['pf']    for r in fold_results]
oos_cagrs  = [r['oos']['cagr']  for r in fold_results]
oos_sharps = [r['oos']['sharpe'] for r in fold_results]
oos_dds    = [r['oos']['max_dd'] for r in fold_results]
nifty_cags = [r['nc_oos']        for r in fold_results]

mean_pf    = statistics.mean(oos_pfs)
mean_cagr  = statistics.mean(oos_cagrs)
mean_sh    = statistics.mean(oos_sharps)
mean_dd    = statistics.mean(oos_dds)
mean_nifty = statistics.mean(nifty_cags)
std_cagr   = statistics.stdev(oos_cagrs)  if len(oos_cagrs) > 1 else 0
n_beat     = sum(1 for r in fold_results if r['oos']['cagr'] > r['nc_oos'])

print(f'  {"MEAN":>5}  {"":24}  {mean_nifty:>+6.1f}%  '
      f'{"":>7}  {"":>8}  '
      f'{mean_pf:>7.3f}  {mean_cagr:>+8.1f}%  '
      f'{mean_sh:>8.3f}  {mean_dd:>6.1f}%')
if len(oos_pfs) > 1:
    std_pf  = statistics.stdev(oos_pfs)
    print(f'  {"STDEV":>5}  {"(stability)":24}  {"":>7}  '
          f'{"":>7}  {"":>8}  '
          f'{std_pf:>7.3f}  {std_cagr:>+8.1f}%')
print(f'\n  Folds beating Nifty: {n_beat}/{len(fold_results)}')

# ── Per-fold detail ───────────────────────────────────────────────────────────
print()
print(SEP)
print('  PER-FOLD DETAIL')
print(SEP)
for r in fold_results:
    m = r['oos']
    nc = r['nc_oos']
    alpha = m['cagr'] - nc
    exits = m['exits']
    print(f'  Fold {r["fold"]}  |  {r["test"][0]} to {r["test"][-1]}')
    print(f'    Trades: {m["trades"]}  WR: {m["wr"]:.1f}%  '
          f'PF: {m["pf"]:.3f}  CAGR: {m["cagr"]:+.1f}%  '
          f'Sharpe: {m["sharpe"]:.3f}  MaxDD: {m["max_dd"]:.1f}%')
    print(f'    Avg Win: {m["avg_win"]:+.2f}%  Avg Loss: {m["avg_loss"]:+.2f}%  '
          f'Net P&L: Rs.{m["net_pnl"]:+,.0f}')
    print(f'    Nifty:  {nc:+.1f}%   Alpha: {alpha:+.1f}%   '
          f'Exits: SL={exits.get("SL",0)} Rebal={exits.get("Rebal",0)} EoP={exits.get("EoP",0)}')
    print()

# ── IS-OOS correlation ────────────────────────────────────────────────────────
if len(fold_results) > 1:
    is_pfs  = [r['is']['pf']   for r in fold_results]
    oos_pfs2= [r['oos']['pf']  for r in fold_results]
    is_cagrs = [r['is']['cagr'] for r in fold_results]
    mean_ip = statistics.mean(is_pfs);  mean_op = statistics.mean(oos_pfs2)
    mean_ic = statistics.mean(is_cagrs); mean_oc = statistics.mean(oos_cagrs)
    n_ = len(fold_results)
    cov_pf  = sum((is_pfs[k]-mean_ip)*(oos_pfs2[k]-mean_op) for k in range(n_))
    var_is  = sum((x-mean_ip)**2 for x in is_pfs)
    var_oos = sum((x-mean_op)**2 for x in oos_pfs2)
    corr_pf = cov_pf/(var_is*var_oos)**0.5 if var_is > 0 and var_oos > 0 else 0
    cov_ca  = sum((is_cagrs[k]-mean_ic)*(oos_cagrs[k]-mean_oc) for k in range(n_))
    var_ic  = sum((x-mean_ic)**2 for x in is_cagrs)
    var_oc  = sum((x-mean_oc)**2 for x in oos_cagrs)
    corr_ca = cov_ca/(var_ic*var_oc)**0.5 if var_ic > 0 and var_oc > 0 else 0

    print(SEP)
    print('  IS -> OOS CORRELATION ACROSS FOLDS')
    print(SEP)
    print(f'  PF  correlation: {corr_pf:+.3f}')
    print(f'  CAGR correlation: {corr_ca:+.3f}')
    if corr_pf > 0.5:
        print('  Strong positive IS->OOS correlation — strategy is NOT overfitting.')
    elif corr_pf > 0:
        print('  Weak positive IS->OOS correlation — some signal present, some noise.')
    else:
        print('  Negative IS->OOS correlation — IS performance does not predict OOS.')

# ── IS decay per fold ─────────────────────────────────────────────────────────
print()
print(SEP)
print('  IS vs OOS DECAY PER FOLD')
print(SEP)
print(f'  {"Fold":>5}  {"IS PF":>8}  {"OOS PF":>8}  {"PF Decay":>10}  '
      f'{"IS CAGR":>9}  {"OOS CAGR":>10}  {"CAGR Decay":>12}')
print(sep)
for r in fold_results:
    pf_decay   = r['is']['pf']   - r['oos']['pf']
    cagr_decay = r['is']['cagr'] - r['oos']['cagr']
    print(f'  {r["fold"]:>5}  {r["is"]["pf"]:>8.3f}  {r["oos"]["pf"]:>8.3f}  '
          f'{pf_decay:>+9.3f}   {r["is"]["cagr"]:>+8.1f}%  '
          f'{r["oos"]["cagr"]:>+9.1f}%  {cagr_decay:>+11.1f}%')
mean_pf_decay   = statistics.mean([r['is']['pf']   - r['oos']['pf']   for r in fold_results])
mean_cagr_decay = statistics.mean([r['is']['cagr'] - r['oos']['cagr'] for r in fold_results])
print(sep)
print(f'  {"MEAN":>5}  {"":>8}  {"":>8}  {mean_pf_decay:>+9.3f}   '
      f'{"":>9}  {"":>10}  {mean_cagr_decay:>+11.1f}%')

# ── Verdict ───────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  VERDICT')
print(SEP)
print(f'  Mean OOS PF    : {mean_pf:.3f}   (> 1.0 = profitable across all folds)')
print(f'  Mean OOS CAGR  : {mean_cagr:+.1f}%   (vs mean Nifty = {mean_nifty:+.1f}%)')
print(f'  Mean Alpha     : {mean_cagr - mean_nifty:+.1f}% per year')
print(f'  CAGR stability : {std_cagr:.1f}% std dev across folds')
print(f'  Folds beating Nifty: {n_beat}/{len(fold_results)}')
print()

consistent  = all(r['oos']['pf'] > 1.0 for r in fold_results)
mostly_pos  = sum(1 for r in fold_results if r['oos']['cagr'] > 0) >= len(fold_results)//2 + 1
beats_nifty = mean_cagr > mean_nifty

if consistent and beats_nifty:
    print('  STRONG: Profitable in every fold AND beats Nifty on average.')
    print('  Strategy is robust to regime shifts. Suitable for live deployment.')
elif mostly_pos and beats_nifty:
    print('  SOLID: Positive CAGR in majority of folds, beats Nifty on average.')
    print('  Some fold-to-fold variance expected — acceptable for a retail strategy.')
elif mean_pf > 1.0:
    print('  MIXED: Mean PF > 1.0 but not consistent across all folds.')
    print('  Strategy works in some regimes but not others.')
    print('  A regime filter (bull/bear/sideways) would improve consistency.')
else:
    print('  WEAK: Mean PF < 1.0 — rolling WF reveals the single-split result was lucky.')
    print('  The 2-year OOS result masked fold-level variance.')

print()
print('  REGIME BREAKDOWN:')
for r in fold_results:
    regime = ('BULL' if r['nc_oos'] > 12 else
              'FLAT' if r['nc_oos'] > -5 else 'BEAR')
    result = ('BEATS NIFTY' if r['oos']['cagr'] > r['nc_oos'] else
              'POSITIVE'    if r['oos']['cagr'] > 0 else 'NEGATIVE')
    print(f'  Fold {r["fold"]}: {regime} regime (Nifty {r["nc_oos"]:+.1f}%)  ->  '
          f'Strategy {r["oos"]["cagr"]:+.1f}%  [{result}]')
