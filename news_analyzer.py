"""
News Analysis Module
- Fetches news from trusted sources (NSE, Moneycontrol, Economic Times)
- Analyzes sentiment using Claude AI
- Checks historical news-price reactions
- Returns trading signals based on news
"""

import time
import json
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
import anthropic
import config

log = logging.getLogger(__name__)

NEWS_HISTORY_FILE = Path("news_history.json")

# Trusted news sources
NEWS_SOURCES = [
    {
        "name": "Economic Times Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    },
    {
        "name": "Moneycontrol News",
        "url": "https://www.moneycontrol.com/rss/business.xml",
    },
    {
        "name": "NSE India News",
        "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    },
    {
        "name": "Business Standard Markets",
        "url": "https://www.business-standard.com/rss/markets-106.rss",
    },
    {
        "name": "Livemint Markets",
        "url": "https://www.livemint.com/rss/markets",
    },
]

# Keywords that strongly affect stock prices
BULLISH_KEYWORDS = [
    "profit", "revenue growth", "beats expectations", "record high",
    "acquisition", "contract won", "partnership", "dividend", "buyback",
    "upgrade", "outperform", "strong results", "expansion", "new order",
    "quarterly profit", "annual profit", "bonus shares", "stock split"
]

BEARISH_KEYWORDS = [
    "loss", "decline", "misses expectations", "lawsuit", "penalty",
    "fraud", "downgrade", "underperform", "weak results", "layoffs",
    "debt", "default", "investigation", "fine", "regulatory action",
    "profit warning", "revenue miss", "ceo resignation", "scandal"
]


def load_news_history():
    if NEWS_HISTORY_FILE.exists():
        return json.loads(NEWS_HISTORY_FILE.read_text(encoding="utf-8"))
    return {}

def save_news_history(history):
    NEWS_HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def fetch_rss_news(url, source_name):
    """Fetch news from RSS feed."""
    news_items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return news_items
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:20]:
            title = item.findtext("title", "").strip()
            desc  = item.findtext("description", "").strip()
            link  = item.findtext("link", "").strip()
            pub   = item.findtext("pubDate", str(datetime.now())).strip()
            if title:
                news_items.append({
                    "title": title,
                    "description": desc[:300],
                    "link": link,
                    "source": source_name,
                    "published": pub,
                    "fetched_at": str(datetime.now())
                })
    except Exception as e:
        log.warning(f"Failed to fetch news from {source_name}: {e}")
    return news_items


def extract_stock_symbols(text: str, known_symbols: list) -> list:
    """Find which stocks are mentioned in news text."""
    text_upper = text.upper()
    mentioned = []
    # Common company name to symbol mapping for Indian stocks
    name_map = {
        "ZOMATO": "ZOMATO", "TCS": "TCS", "INFOSYS": "INFY", "INFY": "INFY",
        "HDFC": "HDFCBANK", "RELIANCE": "RELIANCE", "WIPRO": "WIPRO",
        "TATA": "TATAMOTORS", "BAJAJ": "BAJFINANCE", "ICICI": "ICICIBANK",
        "AXIS BANK": "AXISBANK", "SBI": "SBIN", "KOTAK": "KOTAKBANK",
        "ADANI": "ADANIENT", "MARUTI": "MARUTI", "ASIAN PAINTS": "ASIANPAINT",
        "HUL": "HINDUNILVR", "ITC": "ITC", "BHARTI": "BHARTIARTL",
        "AIRTEL": "BHARTIARTL", "ONGC": "ONGC", "NTPC": "NTPC",
        "POWERGRID": "POWERGRID", "SUNPHARMA": "SUNPHARMA", "DRREDDY": "DRREDDY",
    }
    for name, symbol in name_map.items():
        if name in text_upper:
            if symbol not in mentioned:
                mentioned.append(symbol)
    return mentioned


def analyze_sentiment_ai(title: str, description: str) -> dict:
    """Use Claude AI to analyze news sentiment."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        prompt = f"""Analyze this Indian stock market news and respond in JSON only.

Title: {title}
Description: {description}

Respond with exactly this JSON format:
{{
  "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence": 0.0 to 1.0,
  "affected_stocks": ["SYMBOL1", "SYMBOL2"],
  "reason": "one line explanation",
  "expected_move": "UP" or "DOWN" or "SIDEWAYS",
  "magnitude": "HIGH" or "MEDIUM" or "LOW"
}}"""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        # Extract JSON
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        log.warning(f"AI sentiment analysis failed: {e}")

    # Fallback: keyword-based sentiment
    combined = (title + " " + description).lower()
    bullish_count = sum(1 for k in BULLISH_KEYWORDS if k in combined)
    bearish_count = sum(1 for k in BEARISH_KEYWORDS if k in combined)

    if bullish_count > bearish_count:
        return {"sentiment": "BULLISH", "confidence": 0.6, "affected_stocks": [],
                "reason": "Positive keywords detected", "expected_move": "UP", "magnitude": "LOW"}
    elif bearish_count > bullish_count:
        return {"sentiment": "BEARISH", "confidence": 0.6, "affected_stocks": [],
                "reason": "Negative keywords detected", "expected_move": "DOWN", "magnitude": "LOW"}
    return {"sentiment": "NEUTRAL", "confidence": 0.5, "affected_stocks": [],
            "reason": "No clear signal", "expected_move": "SIDEWAYS", "magnitude": "LOW"}


def record_news_reaction(symbol: str, news_title: str, sentiment: str,
                          price_before: float, price_after: float, hours_later: int = 2):
    """Record how a stock actually reacted to news for future learning."""
    history = load_news_history()
    if symbol not in history:
        history[symbol] = []

    pct_change = ((price_after - price_before) / price_before * 100) if price_before > 0 else 0
    history[symbol].append({
        "news": news_title[:100],
        "sentiment": sentiment,
        "price_before": price_before,
        "price_after": price_after,
        "pct_change": round(pct_change, 2),
        "hours_later": hours_later,
        "date": str(datetime.now().date())
    })
    # Keep last 100 reactions per stock
    history[symbol] = history[symbol][-100:]
    save_news_history(history)


def get_historical_reaction(symbol: str, sentiment: str) -> dict:
    """
    Check how this stock historically reacted to similar news sentiment.
    Returns average price change and confidence.
    """
    history = load_news_history()
    if symbol not in history:
        return {"avg_change": 0, "confidence": 0, "sample_size": 0}

    matching = [r for r in history[symbol] if r.get("sentiment") == sentiment]
    if not matching:
        return {"avg_change": 0, "confidence": 0, "sample_size": 0}

    avg_change = sum(r["pct_change"] for r in matching) / len(matching)
    # Confidence based on sample size and consistency
    consistency = sum(1 for r in matching if
        (avg_change > 0 and r["pct_change"] > 0) or
        (avg_change < 0 and r["pct_change"] < 0)
    ) / len(matching)

    return {
        "avg_change": round(avg_change, 2),
        "confidence": round(consistency, 2),
        "sample_size": len(matching)
    }


def get_news_signals(watchlist_symbols: list) -> list:
    """
    Main function: fetch news, analyze, cross-reference history.
    Returns list of trading signals.
    """
    signals = []
    all_news = []

    # Fetch from all sources
    for source in NEWS_SOURCES:
        items = fetch_rss_news(source["url"], source["name"])
        all_news.extend(items)
        time.sleep(1)

    log.info(f"Fetched {len(all_news)} news items from {len(NEWS_SOURCES)} sources")

    seen_titles = set()
    ai_calls = 0
    for news in all_news:
        title = news["title"]
        if title in seen_titles:
            continue
        seen_titles.add(title)

        # Cap AI calls to 20 per cycle to control API costs
        if ai_calls >= 20:
            analysis = {"sentiment": "NEUTRAL", "confidence": 0, "affected_stocks": [],
                        "reason": "AI cap reached", "expected_move": "SIDEWAYS", "magnitude": "LOW"}
        else:
            analysis = analyze_sentiment_ai(title, news["description"])
            ai_calls += 1
        if analysis["sentiment"] == "NEUTRAL":
            continue
        if analysis["confidence"] < 0.6:
            continue

        # Find affected stocks
        affected = analysis.get("affected_stocks", [])
        mentioned = extract_stock_symbols(title + " " + news["description"], watchlist_symbols)
        all_affected = list(set(affected + mentioned))

        for symbol in all_affected:
            # Check historical reaction
            hist = get_historical_reaction(symbol, analysis["sentiment"])

            # Build signal
            signal_strength = analysis["confidence"]
            if hist["sample_size"] >= 3:
                # Boost confidence if history confirms
                if hist["confidence"] >= 0.6:
                    signal_strength = min(1.0, signal_strength + 0.2)
                    log.info(f"History confirms: {symbol} avg {hist['avg_change']}% on {analysis['sentiment']} news")

            if signal_strength >= 0.65:
                signals.append({
                    "symbol": symbol,
                    "action": "BUY" if analysis["sentiment"] == "BULLISH" else "SELL",
                    "confidence": signal_strength,
                    "reason": analysis["reason"],
                    "news_title": title,
                    "source": news["source"],
                    "historical_avg_change": hist.get("avg_change", 0),
                    "historical_samples": hist.get("sample_size", 0),
                    "magnitude": analysis["magnitude"]
                })
                log.info(f"NEWS SIGNAL: {symbol} {analysis['sentiment']} | {title[:60]} | confidence={signal_strength:.2f}")

    return signals


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing news analyzer...")
    signals = get_news_signals(["ZOMATO", "TCS", "INFY", "HDFCBANK", "RELIANCE"])
    print(f"\nFound {len(signals)} signals:")
    for s in signals:
        print(f"  {s['action']} {s['symbol']} | {s['reason']} | confidence={s['confidence']:.2f}")
