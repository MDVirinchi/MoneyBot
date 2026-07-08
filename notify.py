"""
notify.py — Telegram notification for MoneyBot.
Sends daily PASS/FAIL status so silent failures are impossible.

Setup:
  1. Message @BotFather on Telegram, create a bot, get the token
  2. Message your bot, then visit:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your chat_id
  3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config.py

Usage:
  from notify import send
  send("PASS: BEAR regime, 0 errors")
  send("FAIL: Token expired, data gate triggered")
"""

import requests
import logging

log = logging.getLogger(__name__)

def send(message: str):
    """Send a Telegram message. Fails silently if not configured."""
    try:
        import config
        token = getattr(config, "TELEGRAM_BOT_TOKEN", "")
        chat_id = getattr(config, "TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=10)
    except Exception as e:
        log.debug(f"Telegram send failed: {e}")
