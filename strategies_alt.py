"""
strategies_alt.py — Three alternative entry hypotheses tested on daily bars.

Each strategy shares:
  - Same DataFetcher (yfinance daily, 365 days)
  - Same cost model: BROKERAGE=Rs.20, STT=0.1%, SLIPPAGE=0.2% each way
  - Same execution: signal on bar i close, fill at bar i+1 open
  - Same exit: SL=2%, TP=6%, TrailingStop=1.5%
  - Same capital: Rs.5,000 per stock

Strategies:
  S1 — EMA Pullback   : EMA21>EMA50 trend + price pulls back to EMA21 + bounces
  S2 — Breakout       : Close > 20-day high + volume > 1.5x 20-day avg
  S3 — Mean Reversion : RSI<30 oversold + recovery above 35

Run: python strategies_alt.py
"""

import time, logging, warnings, math, statistics
from collections import defaultdict

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from backtest import DataFetcher   # reuse data layer only

# ── Cost constants (identical to backtest.py) ─────────────────────────────────
BROKERAGE    = 20.0
STT_PCT      = 0.001
EXCHANGE_PCT = 0.0000345
SLIPPAGE     = 0.002

# ── Exit parameters ───────────────────────────────────────────────────────────
SL_PCT    = 2.0
TP_PCT    = 6.0
TRAIL_PCT = 1.5

INITIAL_CAPITAL = 5000.0
LOOKBACK        = 55    # bars needed to compute EMA50 + 5 spare

STOCKS = [
    ('NSE_EQ|INE002A01018', 'RELIANCE'),
    ('NSE_EQ|INE467B01029', 'TCS'),
    ('NSE_EQ|INE009A01021', 'INFY'),
    ('NSE_EQ|INE040A01034', 'HDFCBANK'),
]

fetcher = DataFetcher()


# ── Helpers ───────────────────────────────────────────────────────────────────
def ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def rsi(closes, period=14):
    if len(closes) <= period:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[-period - 1 + i] - closes[-period - 2 + i]
        (gains if d > 0 else losses).append(abs(d))
    ag = sum(gains) / period if gains else 0.0001
    al = sum(losses) / period if losses else 0.0001
    rs = ag / al
    return 100 - 100 / (1 + rs)


def avg_volume(candles, period=20):
    vols = [c[5] for c in candles[-period:] if c[5] > 0]
    return sum(vols) / len(vols) if vols else 1


def simulate(candles, signal_fn, strategy_name):
    """
    Walk-forward backtester.
    signal_fn(window) -> True to open a BUY position, False/None = no action.
    Returns metrics dict.
    """
    capital   = INITIAL_CAPITAL
    position  = None
    trades    = []
    equity    = [capital]

    for i in range(LOOKBACK, len(candles) - 1):
        window  = candles[:i + 1]          # bars 0..i inclusive
        current = candles[i]
        ltp     = current[4]               # close of bar i

        # ── manage open position ──────────────────────────────────────────────
        if position:
            sl    = position['entry'] * (1 - SL_PCT / 100)
            tp    = position['entry'] * (1 + TP_PCT / 100)
            high  = max(position['high'], ltp)
            position['high'] = high
            trail = high * (1 - TRAIL_PCT / 100)

            reason = None
            if ltp <= sl:     reason = 'StopLoss'
            elif ltp >= tp:   reason = 'TakeProfit'
            elif ltp <= trail and high > position['entry'] * 1.005:
                reason = 'TrailingStop'

            if reason:
                exit_px  = ltp * (1 - SLIPPAGE)
                exit_val = position['qty'] * exit_px
                costs    = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
                pnl      = (exit_px - position['entry']) * position['qty'] - costs
                capital += pnl
                ret      = (exit_px / position['entry'] - 1) * 100
                trades.append({'pnl': pnl, 'return_pct': ret,
                               'exit_reason': reason})
                position = None
                equity.append(capital)
                continue

        # ── check for new entry (no pyramid) ─────────────────────────────────
        if position is None:
            try:
                signal = signal_fn(window)
            except Exception:
                signal = False

            if signal:
                next_i   = i + 1
                exec_px  = candles[next_i][1]              # open of bar i+1
                fill_px  = exec_px * (1 + SLIPPAGE)
                qty      = max(1, int(capital * 0.95 / fill_px))
                cost_buy = BROKERAGE + qty * fill_px * EXCHANGE_PCT
                if capital >= qty * fill_px + cost_buy:
                    capital -= cost_buy
                    position = {'qty': qty, 'entry': fill_px,
                                'high': fill_px}

        equity.append(capital)

    # close any open position at end
    if position:
        ltp      = candles[-1][4]
        exit_px  = ltp * (1 - SLIPPAGE)
        exit_val = position['qty'] * exit_px
        costs    = BROKERAGE + exit_val * STT_PCT + exit_val * EXCHANGE_PCT
        pnl      = (exit_px - position['entry']) * position['qty'] - costs
        ret      = (exit_px / position['entry'] - 1) * 100
        trades.append({'pnl': pnl, 'return_pct': ret,
                       'exit_reason': 'EndOfPeriod'})
        capital += pnl

    # ── compute metrics ───────────────────────────────────────────────────────
    wins   = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]

    gross_profit = sum(t['pnl'] for t in wins)
    gross_loss   = abs(sum(t['pnl'] for t in losses))
    pf           = gross_profit / gross_loss if gross_loss > 0 else (1.0 if gross_profit > 0 else 0.0)
    wr           = len(wins) / len(trades) * 100 if trades else 0.0
    net_pnl      = capital - INITIAL_CAPITAL
    net_pnl_pct  = net_pnl / INITIAL_CAPITAL * 100

    # CAGR (assuming 252 trading days / year)
    bars_used    = len(candles) - LOOKBACK
    years        = bars_used / 252
    if years > 0 and capital > 0:
        cagr = ((capital / INITIAL_CAPITAL) ** (1 / years) - 1) * 100
    else:
        cagr = -100.0

    # Max drawdown
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe (daily returns)
    daily_rets = [(equity[i] - equity[i-1]) / equity[i-1]
                  for i in range(1, len(equity)) if equity[i-1] > 0]
    if len(daily_rets) > 2 and statistics.stdev(daily_rets) > 0:
        sharpe = (statistics.mean(daily_rets) / statistics.stdev(daily_rets)) * math.sqrt(252)
    else:
        sharpe = 0.0

    from collections import Counter
    exit_c = Counter(t['exit_reason'] for t in trades)

    w_rets = [t['return_pct'] for t in wins]
    l_rets = [t['return_pct'] for t in losses]
    avg_w  = statistics.mean(w_rets) if w_rets else 0
    avg_l  = statistics.mean(l_rets) if l_rets else 0
    wl_ratio = abs(avg_w / avg_l) if avg_l != 0 else 0

    total_costs = sum(
        BROKERAGE * 2 + abs(t['pnl']) * (STT_PCT + EXCHANGE_PCT * 2)
        for t in trades
    )

    return {
        'strategy':         strategy_name,
        'total_trades':     len(trades),
        'win_rate_pct':     round(wr, 2),
        'profit_factor':    round(pf, 3),
        'sharpe_ratio':     round(sharpe, 3),
        'cagr_pct':         round(cagr, 2),
        'max_drawdown_pct': round(max_dd, 2),
        'net_pnl':          round(net_pnl, 2),
        'net_pnl_pct':      round(net_pnl_pct, 2),
        'wl_ratio':         round(wl_ratio, 2),
        'exit_reasons':     dict(exit_c),
        'total_costs_rs':   round(total_costs, 0),
    }


# ==============================================================================
#  STRATEGY 1 — EMA PULLBACK
# ==============================================================================
def signal_ema_pullback(window):
    """
    Trend   : EMA21 > EMA50 (confirmed uptrend)
    Pullback: Within last 5 bars, low touched within 2% above EMA21
              (price pulled back toward the mean)
    Bounce  : Latest close is above EMA21 (bounce confirmed)
    Slope   : EMA21 slope is positive (trend still rising)
    """
    closes = [c[4] for c in window]
    lows   = [c[3] for c in window]

    e21 = ema(closes, 21)
    e50 = ema(closes, 50)

    if len(e21) < 5 or len(e50) < 2:
        return False

    curr_e21 = e21[-1]
    curr_e50 = e50[-1]
    curr_close = closes[-1]

    # Trend: EMA21 must be above EMA50
    if curr_e21 <= curr_e50:
        return False

    # Slope: EMA21 must be rising (compare to 3 bars ago)
    if len(e21) < 4 or e21[-1] <= e21[-4]:
        return False

    # Pullback: within last 5 bars the low came within 2% above EMA21
    # (price tested the EMA21 support level)
    pullback_zone_touched = False
    for j in range(1, 6):
        if j >= len(window):
            break
        bar_low   = lows[-j]
        e21_then  = e21[-(j)]
        if e21_then is None:
            continue
        # Low came within 2% above EMA21 (pulled back to support)
        if bar_low <= e21_then * 1.02:
            pullback_zone_touched = True
            break

    if not pullback_zone_touched:
        return False

    # Bounce: current close is back above EMA21 (not still in pullback)
    if curr_close <= curr_e21:
        return False

    # Not already deep into the trend (close < 5% above EMA21 — fresh bounce)
    if curr_close > curr_e21 * 1.05:
        return False

    return True


# ==============================================================================
#  STRATEGY 2 — BREAKOUT
# ==============================================================================
def signal_breakout(window):
    """
    Breakout: Close exceeds the highest close of the previous 20 bars
    Volume  : Current volume > 1.5x the 20-bar average volume
    Filter  : Not already extended (close < 20-day high * 1.03 — fresh break)
    Trend   : Price above EMA50 (no breakouts in downtrends)
    """
    closes  = [c[4] for c in window]
    volumes = [c[5] for c in window]

    if len(closes) < 22:
        return False

    curr_close  = closes[-1]
    curr_vol    = volumes[-1]
    prev_high20 = max(closes[-21:-1])   # highest close of prior 20 bars
    avg_vol20   = sum(volumes[-21:-1]) / 20

    # Price breaks above 20-day high
    if curr_close <= prev_high20:
        return False

    # Volume confirmation
    if avg_vol20 <= 0 or curr_vol < avg_vol20 * 1.5:
        return False

    # Not over-extended (within 3% above breakout level)
    if curr_close > prev_high20 * 1.03:
        return False

    # Trend filter: price above EMA50
    e50 = ema(closes, 50)
    if not e50 or curr_close < e50[-1]:
        return False

    return True


# ==============================================================================
#  STRATEGY 3 — MEAN REVERSION (RSI oversold recovery)
# ==============================================================================
def signal_mean_reversion(window):
    """
    Setup   : RSI dropped below 30 within last 5 bars (oversold reached)
    Trigger : RSI has now recovered above 35 (momentum turning)
    Filter  : Price above 200-bar EMA (only reversal in long-term uptrends)
    Filter  : Current RSI < 55 (not already overbought on recovery)
    """
    closes = [c[4] for c in window]

    if len(closes) < 25:
        return False

    curr_rsi = rsi(closes, 14)

    # RSI must have been oversold within last 5 bars and now recovering
    was_oversold = False
    for j in range(2, 7):
        if j >= len(closes):
            break
        past_rsi = rsi(closes[:-j+1] if j > 1 else closes, 14)
        if past_rsi < 30:
            was_oversold = True
            break

    if not was_oversold:
        return False

    # Now recovering (RSI crossed back above 35)
    if curr_rsi < 35 or curr_rsi > 55:
        return False

    # Long-term trend filter: price above 200-bar EMA (or 50 if not enough data)
    period = 200 if len(closes) >= 202 else 50
    e_long = ema(closes, period)
    if not e_long or closes[-1] < e_long[-1] * 0.98:
        return False

    return True


# ==============================================================================
#  RUN ALL THREE STRATEGIES ON ALL FOUR STOCKS
# ==============================================================================
STRATEGIES = [
    ('S1_EMA_Pullback',   signal_ema_pullback),
    ('S2_Breakout',        signal_breakout),
    ('S3_Mean_Reversion',  signal_mean_reversion),
]

all_results = defaultdict(dict)  # strategy -> symbol -> metrics

print('Fetching daily data (365 days) and running all strategies...')
print()

# Fetch candles once per stock, reuse across strategies
stock_candles = {}
for inst, sym in STOCKS:
    candles = fetcher.get_candles(inst, '1day', 365)
    stock_candles[sym] = candles
    print(f'  {sym}: {len(candles)} daily bars')
    time.sleep(0.5)

print()

for strat_name, sig_fn in STRATEGIES:
    print(f'Running {strat_name}...')
    for inst, sym in STOCKS:
        candles = stock_candles[sym]
        if len(candles) < LOOKBACK + 5:
            all_results[strat_name][sym] = {'error': 'insufficient data'}
            continue
        m = simulate(candles, sig_fn, strat_name)
        all_results[strat_name][sym] = m
        print(f'  {sym:<12}: T={m["total_trades"]:>3}  WR={m["win_rate_pct"]:>5.1f}%  '
              f'PF={m["profit_factor"]:>6.3f}  CAGR={m["cagr_pct"]:>+7.1f}%  '
              f'DD={m["max_drawdown_pct"]:>5.1f}%  '
              f'WL={m["wl_ratio"]:>4.2f}x')

# ── COMPARISON TABLE ──────────────────────────────────────────────────────────
SEP = '=' * 88
sep = '-' * 88

print()
print(SEP)
print('  FULL RESULTS — 3 STRATEGIES × 4 STOCKS  (daily bars, 365 days, Rs.5000 capital)')
print(SEP)
print(f'  {"Strategy":<22}  {"Stock":<10}  {"Trades":>6}  {"WR%":>6}  '
      f'{"PF":>6}  {"Sharpe":>7}  {"CAGR%":>8}  {"MaxDD%":>7}  {"WL":>5}  Exits')
print(sep)

for strat_name, _ in STRATEGIES:
    for _, sym in STOCKS:
        m = all_results[strat_name].get(sym, {})
        if 'error' in m:
            print(f'  {strat_name:<22}  {sym:<10}  -- insufficient data --')
            continue
        er = m.get('exit_reasons', {})
        exit_str = (f'SL={er.get("StopLoss",0)}'
                    f' TP={er.get("TakeProfit",0)}'
                    f' Tr={er.get("TrailingStop",0)}'
                    f' Oth={er.get("EndOfPeriod",0)+er.get("Signal",0)}')
        print(f'  {strat_name:<22}  {sym:<10}  {m["total_trades"]:>6}  '
              f'{m["win_rate_pct"]:>5.1f}%  {m["profit_factor"]:>6.3f}  '
              f'{m["sharpe_ratio"]:>7.3f}  {m["cagr_pct"]:>+7.1f}%  '
              f'{m["max_drawdown_pct"]:>6.1f}%  {m["wl_ratio"]:>4.2f}x  {exit_str}')
    print(sep)

# ── AVERAGES PER STRATEGY ─────────────────────────────────────────────────────
print()
print(SEP)
print('  AVERAGES PER STRATEGY  (across all 4 stocks)')
print(SEP)
print(f'  {"Strategy":<22}  {"Trades":>6}  {"WR%":>6}  {"PF":>6}  '
      f'{"Sharpe":>7}  {"CAGR%":>8}  {"MaxDD%":>7}  {"WL":>5}')
print(sep)

strategy_avgs = {}
for strat_name, _ in STRATEGIES:
    vals = [all_results[strat_name][sym]
            for _, sym in STOCKS
            if 'error' not in all_results[strat_name].get(sym, {'error': 1})]
    if not vals:
        continue
    n = len(vals)
    avg = lambda k: sum(v[k] for v in vals) / n
    row = {
        'trades': avg('total_trades'),
        'wr':     avg('win_rate_pct'),
        'pf':     avg('profit_factor'),
        'sharpe': avg('sharpe_ratio'),
        'cagr':   avg('cagr_pct'),
        'dd':     avg('max_drawdown_pct'),
        'wl':     avg('wl_ratio'),
    }
    strategy_avgs[strat_name] = row
    print(f'  {strat_name:<22}  {row["trades"]:>6.1f}  {row["wr"]:>5.1f}%  '
          f'{row["pf"]:>6.3f}  {row["sharpe"]:>7.3f}  {row["cagr"]:>+7.1f}%  '
          f'{row["dd"]:>6.1f}%  {row["wl"]:>4.2f}x')

# Reference line: old EMA cross strategy
print(sep)
print(f'  {"[EMA Cross baseline]":<22}  {"51":>6}  {"18.3":>5}%  '
      f'{"0.179":>6}  {"    N/A":>7}  {"  -51.8":>7}%  {"51.9":>6}%  {"0.88":>4}x  '
      f'<-- previous best')

# ── VERDICT ───────────────────────────────────────────────────────────────────
print()
print(SEP)
print('  VERDICT')
print(SEP)

best_strat = max(strategy_avgs, key=lambda k: strategy_avgs[k]['pf']) if strategy_avgs else None
if best_strat:
    best_pf = strategy_avgs[best_strat]['pf']
    print(f'  Best strategy: {best_strat}  (avg PF = {best_pf:.3f})')
    print()
    if best_pf >= 1.2:
        print('  RESULT: PF > 1.2 ACHIEVED on', best_strat)
        print('  This strategy family has an edge. Proceed to parameter optimization.')
    elif best_pf >= 0.5:
        print('  RESULT: PF > 0.5 achieved — partial edge detected.')
        print('  Strategy shows promise. Worth further optimization.')
    elif best_pf > 0.179:
        print('  RESULT: Best alternative beats EMA cross baseline but PF < 0.5.')
        print('  Marginal improvement — insufficient for further optimization.')
    else:
        print('  RESULT: No alternative strategy beats the EMA cross baseline.')
        print('  All three families unprofitable on NSE large-caps over this period.')

    # Per-strategy verdict
    print()
    for strat_name, _ in STRATEGIES:
        if strat_name not in strategy_avgs:
            continue
        row = strategy_avgs[strat_name]
        pf  = row['pf']
        if pf >= 1.2:
            verdict = 'VIABLE — proceed to optimization'
        elif pf >= 0.5:
            verdict = 'PROMISING — worth further testing'
        elif pf >= 0.2:
            verdict = 'MARGINAL — beats random but not costs'
        else:
            verdict = 'UNPROFITABLE — discard'
        print(f'  {strat_name:<24}  PF={pf:.3f}  WR={row["wr"]:.1f}%  -> {verdict}')
