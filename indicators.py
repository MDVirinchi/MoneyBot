"""
indicators.py — Advanced technical indicators for MoneyBot
Techniques sourced and adapted from:
  - ryantcullen/stock-bot   : Kelly Criterion sizing, slope/concavity signals, MA crossovers
  - crypto-code/Stock-Market: LSTM-style trend scoring, Evolution Strategy signal weighting
  - ashishkumar30/...       : Heikin-Ashi candles, Guppy MMA, RSI, candlestick patterns
  - hahnicity/pytrader      : Large-move detection, stochastic swing analysis
  - 0xramm/Indian-Stock-Market-API: NSE data enrichment
"""

import math
import statistics


# ── 1. BASIC INDICATORS ──────────────────────────────────────────────────────

def ema(prices: list, period: int) -> list:
    """Exponential Moving Average."""
    if not prices:
        return []
    k = 2 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(p * k + result[-1] * (1 - k))
    return result


def sma(prices: list, period: int) -> list:
    """Simple Moving Average."""
    result = []
    for i in range(len(prices)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(prices[i - period + 1: i + 1]) / period)
    return result


def rsi(prices: list, period: int = 14) -> list:
    """Relative Strength Index."""
    if len(prices) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_vals = []
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss else 100
        rsi_vals.append(100 - 100 / (1 + rs))
    return rsi_vals


# ── 2. HEIKIN-ASHI CANDLES (from ashishkumar30) ─────────────────────────────
# Smoother candles that filter out noise and make trends easier to spot.

def heikin_ashi(candles: list) -> list:
    """
    Convert OHLC candles to Heikin-Ashi.
    Input:  list of [ts, open, high, low, close, vol, oi]
    Output: list of [ha_open, ha_high, ha_low, ha_close]
    """
    if not candles:
        return []
    ha = []
    for i, c in enumerate(candles):
        o, h, l, cl = c[1], c[2], c[3], c[4]
        ha_close = (o + h + l + cl) / 4
        if i == 0:
            ha_open = (o + cl) / 2
        else:
            ha_open = (ha[i - 1][0] + ha[i - 1][3]) / 2
        ha_high = max(h, ha_open, ha_close)
        ha_low  = min(l, ha_open, ha_close)
        ha.append([ha_open, ha_high, ha_low, ha_close])
    return ha


def ha_trend(ha_candles: list, lookback: int = 3) -> str:
    """
    Determine trend from Heikin-Ashi candles.
    Returns 'BULLISH', 'BEARISH', or 'NEUTRAL'.
    """
    if len(ha_candles) < lookback:
        return "NEUTRAL"
    recent = ha_candles[-lookback:]
    # Bullish: close > open for all recent candles (green HA candles)
    all_bull = all(c[3] > c[0] for c in recent)
    all_bear = all(c[3] < c[0] for c in recent)
    if all_bull:
        return "BULLISH"
    if all_bear:
        return "BEARISH"
    return "NEUTRAL"


# ── 3. SLOPE & CONCAVITY SIGNALS (from ryantcullen/stock-bot) ────────────────
# Beyond just "is EMA above/below" — measures if trend is accelerating.

def slope(values: list, window: int = 3) -> float:
    """
    First derivative: rate of change over last `window` bars.
    Positive = trending up, negative = trending down.
    """
    if len(values) < window:
        return 0.0
    recent = values[-window:]
    if recent[0] == 0:
        return 0.0
    return (recent[-1] - recent[0]) / recent[0]


def concavity(values: list, window: int = 5) -> float:
    """
    Second derivative: is momentum accelerating or decelerating?
    Positive = speeding up, negative = slowing down.
    """
    if len(values) < window:
        return 0.0
    mid = window // 2
    first_half_slope  = slope(values[-window:-mid])
    second_half_slope = slope(values[-mid:])
    return second_half_slope - first_half_slope


def ma_flipped(values: list) -> bool:
    """True if the last two values crossed (sign change in diff from baseline)."""
    if len(values) < 3:
        return False
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    return (diffs[-2] < 0 and diffs[-1] > 0) or (diffs[-2] > 0 and diffs[-1] < 0)


# ── 4. GUPPY MULTIPLE MOVING AVERAGE (from ashishkumar30) ────────────────────
# 12 EMAs split into "trader" group (short) and "investor" group (long).
# When two groups expand apart in same direction = strong trend.

GUPPY_SHORT = [3, 5, 8, 10, 12, 15]
GUPPY_LONG  = [30, 35, 40, 45, 50, 60]

def guppy_signal(prices: list) -> str:
    """
    Returns 'BUY', 'SELL', or 'NEUTRAL' based on Guppy MMA.
    BUY:  all short EMAs > all long EMAs and short group is expanding
    SELL: all short EMAs < all long EMAs and short group is contracting
    """
    if len(prices) < 65:
        return "NEUTRAL"

    short_emas = [ema(prices, p)[-1] for p in GUPPY_SHORT]
    long_emas  = [ema(prices, p)[-1] for p in GUPPY_LONG]

    short_above_long = all(s > max(long_emas) for s in short_emas)
    short_below_long = all(s < min(long_emas) for s in short_emas)

    # Check if short group is expanding (spread increasing)
    short_spread = max(short_emas) - min(short_emas)
    short_emas_prev = [ema(prices[:-1], p)[-1] for p in GUPPY_SHORT]
    short_spread_prev = max(short_emas_prev) - min(short_emas_prev)
    expanding = short_spread > short_spread_prev

    if short_above_long and expanding:
        return "BUY"
    if short_below_long and not expanding:
        return "SELL"
    return "NEUTRAL"


# ── 5. KELLY CRITERION POSITION SIZING (from ryantcullen/stock-bot) ──────────
# Mathematically optimal bet size based on historical win rate and avg profit.

def kelly_position_size(capital: float, win_rate: float,
                         avg_win_pct: float, avg_loss_pct: float,
                         aggressiveness: float = 0.5) -> float:
    """
    Kelly Criterion: f* = (bp - q) / b
    where b = odds (avg_win/avg_loss), p = win_rate, q = 1-p

    aggressiveness: 0.0 = never trade, 1.0 = full Kelly (risky), 0.5 = half-Kelly (safer)

    Returns the rupee amount to invest.
    """
    if avg_loss_pct <= 0 or win_rate <= 0:
        return capital * 0.02  # fallback to 2% risk

    b = avg_win_pct / avg_loss_pct
    p = win_rate
    q = 1 - p
    kelly_fraction = (b * p - q) / b
    kelly_fraction = max(0.0, min(kelly_fraction, 0.25))  # cap at 25%
    adjusted = kelly_fraction * aggressiveness
    return round(capital * adjusted, 2)


# ── 6. LARGE-MOVE DETECTION (from hahnicity/pytrader) ────────────────────────
# Flag stocks that had an unusually large move yesterday — potential reversal.

def large_move_pct(candles: list, threshold_pct: float = 4.0) -> dict:
    """
    Detect if the most recent closed candle was a large move.
    Returns dict with 'is_large_move', 'direction', 'magnitude'.
    """
    if len(candles) < 2:
        return {"is_large_move": False, "direction": None, "magnitude": 0}

    prev_close = candles[-2][4]
    curr_close = candles[-1][4]
    if prev_close == 0:
        return {"is_large_move": False, "direction": None, "magnitude": 0}

    pct = (curr_close - prev_close) / prev_close * 100
    is_large = abs(pct) >= threshold_pct
    return {
        "is_large_move": is_large,
        "direction": "UP" if pct > 0 else "DOWN",
        "magnitude": round(abs(pct), 2)
    }


# ── 7. MULTI-STRATEGY SIGNAL SCORER ──────────────────────────────────────────
# Combines all signals into one confidence score (0–1). Inspired by
# crypto-code's Evolution Strategy weighting approach.

def score_signals(candles: list) -> dict:
    """
    Evidence-based scorer. Weights derived from contingency table analysis
    on 109 real trades (forensic.py / validate_signals.py).

    Signal weights (total possible buy = 1.00):
      EMA fresh cross     0.40  lift=2.04x  MCC=+0.139  PRIMARY
      HA NEUTRAL state    0.35  lift=3.63x  MCC=+0.296  PRIMARY
      Guppy BUY           0.15  lift=1.43x  MCC=+0.056  SECONDARY
      RSI 40-60 neutral   0.05  lift=1.22x  MCC=+0.099  LIGHT CONFIRM
      Slope rising        0.05  lift=1.36x  MCC=+0.063  LIGHT CONFIRM

    Removed (confirmed noise or negative predictor):
      HA BULLISH bonus    was 0.20  lift=0.58x  MCC=-0.296  NEGATIVE
      EMA HOLD scoring    was 0.25  lift=0.77x  MCC=-0.139  NEGATIVE
      Concavity           was 0.10  lift=1.07x  MCC=+0.043  NOISE
    """
    if not candles or len(candles) < 30:
        return {"action": "HOLD", "score": 0, "signals": {}, "reasons": ["Not enough data"]}

    closes = [c[4] for c in candles]
    buy_score  = 0.0
    sell_score = 0.0
    reasons    = []
    signals    = {}

    # ── 1. EMA 9/21 FRESH CROSS — weight 0.40 ───────────────────
    # Only scores on the exact bar of crossover.
    # EMA HOLD state is removed (lift=0.77x, negative predictor).
    e9  = ema(closes, 9)
    e21 = ema(closes, 21)
    ema_cross = "BUY"  if (e9[-2] < e21[-2] and e9[-1] > e21[-1]) else \
                "SELL" if (e9[-2] > e21[-2] and e9[-1] < e21[-1]) else "HOLD"
    signals["ema_cross"] = ema_cross
    if ema_cross == "BUY":
        buy_score += 0.40
        reasons.append("EMA9 fresh cross above EMA21")
    elif ema_cross == "SELL":
        sell_score += 0.40
        reasons.append("EMA9 fresh cross below EMA21")
    # HOLD state: no score added (was the negative-predictor path)

    # ── 2. HEIKIN-ASHI NEUTRAL — weight 0.35 ────────────────────
    # Forensic finding: BULLISH=late entry (lift 0.58x, MCC -0.296).
    # NEUTRAL=transition/early entry (lift 3.63x, MCC +0.296).
    # BEARISH used for sell-side scoring only.
    ha    = heikin_ashi(candles)
    ha_t  = ha_trend(ha)
    signals["heikin_ashi"] = ha_t
    if ha_t == "NEUTRAL":
        buy_score += 0.35
        reasons.append("HA NEUTRAL: transition state — early entry signal")
    elif ha_t == "BEARISH":
        sell_score += 0.35
        reasons.append("HA BEARISH: 3 red candles — sell signal")
    # BULLISH: no bonus — confirmed late-entry predictor

    # ── 3. GUPPY MMA — weight 0.15 ──────────────────────────────
    # Secondary confirmation: lift=1.43x, MCC=+0.056.
    guppy = guppy_signal(closes)
    signals["guppy"] = guppy
    if guppy == "BUY":
        buy_score += 0.15
        reasons.append("Guppy MMA: short EMAs above long, expanding")
    elif guppy == "SELL":
        sell_score += 0.15
        reasons.append("Guppy MMA: short EMAs below long, contracting")

    # ── 4. RSI — weight 0.05 (light confirmation only) ──────────
    # RSI neutral 40-60: lift=1.22x, MCC=+0.099.
    # RSI oversold <40: lift=0.00x, MCC=-0.062 — REMOVED as buy signal.
    rsi_vals = rsi(closes)
    curr_rsi = rsi_vals[-1] if rsi_vals else 50
    signals["rsi"] = round(curr_rsi, 1)
    if 40 <= curr_rsi <= 60:
        buy_score += 0.05
        reasons.append(f"RSI neutral ({curr_rsi:.0f}) — not exhausted")
    elif curr_rsi > 65:
        sell_score += 0.05
        reasons.append(f"RSI overbought ({curr_rsi:.0f})")

    # ── 5. EMA21 SLOPE — weight 0.05 (light confirmation) ───────
    # Lift=1.36x, MCC=+0.063. Kept at reduced weight (was 0.15).
    e21_slope = slope(e21)
    signals["e21_slope"] = round(e21_slope, 5)
    if e21_slope > 0.001:
        buy_score += 0.05
        reasons.append(f"EMA21 rising (slope={e21_slope:.4f})")
    elif e21_slope < -0.001:
        sell_score += 0.05
        reasons.append(f"EMA21 falling (slope={e21_slope:.4f})")

    # ── 6. EMA21 CONCAVITY — REMOVED ────────────────────────────
    # Lift=1.07x, MCC=+0.043: statistically indistinguishable from noise.
    # Still computed and stored for forensic monitoring; not scored.
    e21_concav = concavity(e21)
    signals["e21_concavity"] = round(e21_concav, 5)

    # ── 7. LARGE-MOVE WARNING (unchanged) ───────────────────────
    lm = large_move_pct(candles)
    signals["large_move"] = lm
    if lm["is_large_move"]:
        if lm["direction"] == "UP":
            buy_score  = max(0, buy_score  - 0.10)
            sell_score += 0.10
            reasons.append(f"Large UP move ({lm['magnitude']}%) — reversal risk")
        else:
            sell_score = max(0, sell_score - 0.10)
            buy_score  += 0.10
            reasons.append(f"Large DOWN move ({lm['magnitude']}%) — bounce potential")

    # ── Final decision ───────────────────────────────────────────
    # Threshold kept at 0.35 to avoid empty signal periods during testing.
    # The primary signals (EMA 0.40 + HA_NEUTRAL 0.35) each alone exceed it.
    total = buy_score + sell_score if (buy_score + sell_score) > 0 else 1
    if buy_score > sell_score and buy_score >= 0.35:
        return {"action": "BUY",  "score": round(buy_score / total, 3),
                "signals": signals, "reasons": reasons}
    if sell_score > buy_score and sell_score >= 0.35:
        return {"action": "SELL", "score": round(sell_score / total, 3),
                "signals": signals, "reasons": reasons}
    return {"action": "HOLD", "score": 0, "signals": signals,
            "reasons": reasons or ["No clear signal"]}


# ── 8. WIN RATE TRACKER ───────────────────────────────────────────────────────
# Tracks historical win/loss for Kelly Criterion calculation.

def compute_stats(trades: list) -> dict:
    """
    From the trading state trades list, compute win_rate, avg_win_pct, avg_loss_pct.
    """
    if not trades:
        return {"win_rate": 0.5, "avg_win_pct": 0.02, "avg_loss_pct": 0.01}

    wins  = [t for t in trades if t.get("pnl", 0) > 0]
    losses= [t for t in trades if t.get("pnl", 0) <= 0]

    win_rate    = len(wins) / len(trades) if trades else 0.5
    avg_win_pct = (
        statistics.mean([t["pnl"] / (t["entry"] * t["qty"]) for t in wins])
        if wins else 0.02
    )
    avg_loss_pct = (
        statistics.mean([abs(t["pnl"]) / (t["entry"] * t["qty"]) for t in losses])
        if losses else 0.01
    )
    return {
        "win_rate":     round(win_rate, 3),
        "avg_win_pct":  round(avg_win_pct, 4),
        "avg_loss_pct": round(avg_loss_pct, 4),
        "total_trades": len(trades),
    }


if __name__ == "__main__":
    # Quick self-test with synthetic data
    import random
    random.seed(42)
    prices = [100.0]
    for _ in range(100):
        prices.append(prices[-1] * (1 + random.uniform(-0.02, 0.025)))
    candles = [[i, prices[i]*0.99, prices[i]*1.01, prices[i]*0.98, prices[i], 10000, 0]
               for i in range(len(prices))]

    result = score_signals(candles)
    print(f"Action: {result['action']}  Score: {result['score']}")
    print(f"Signals: {result['signals']}")
    print(f"Reasons: {result['reasons']}")

    stats = compute_stats([
        {"pnl": 120, "entry": 500, "qty": 10},
        {"pnl": -50, "entry": 500, "qty": 10},
        {"pnl": 80,  "entry": 500, "qty": 10},
    ])
    print(f"\nTrade stats: {stats}")
    kelly = kelly_position_size(5000, stats["win_rate"], stats["avg_win_pct"], stats["avg_loss_pct"])
    print(f"Kelly position size on Rs.5000: Rs.{kelly}")
