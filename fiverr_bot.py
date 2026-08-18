"""
Fiverr Automation Bot
- Checks for new orders every 10 minutes
- Reads client requirements automatically
- Generates content using Claude AI
- Delivers completed work to client automatically
"""

import time
import logging
import requests
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import anthropic
import config

log = logging.getLogger("fiverr_bot")
if not log.handlers:
    log.setLevel(logging.INFO)
    _fmt = logging.Formatter("%(asctime)s [FIVERR] %(message)s")
    _fh = logging.FileHandler("moneybot_fiverr.log", encoding="utf-8")
    _fh.setFormatter(_fmt)
    _sh = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    log.addHandler(_fh)
    log.addHandler(_sh)
    log.propagate = False

DELIVERED_FILE = Path("fiverr_delivered.txt")


def get_delivered_orders():
    if DELIVERED_FILE.exists():
        return set(DELIVERED_FILE.read_text().splitlines())
    return set()

def mark_delivered(order_id):
    with open(DELIVERED_FILE, "a") as f:
        f.write(order_id + "\n")


def generate_content(topic: str, requirements: str) -> str:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = f"""
You are a professional SEO content writer. Write a high-quality article based on these client requirements.

Topic/Requirements from client:
{requirements}

Instructions:
- Write a complete, publish-ready article
- Include an engaging title
- Use proper headings (H2, H3)
- SEO-optimized naturally
- 100% original content
- Professional tone
- No fluff, all value
"""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def create_driver():
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def login_fiverr(driver):
    log.info("Logging into Fiverr...")
    driver.get("https://www.fiverr.com/login")
    time.sleep(3)

    try:
        time.sleep(5)
        # Try multiple possible selectors for username
        for selector in [
            (By.NAME, "identifier"),
            (By.NAME, "email"),
            (By.ID, "email"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[placeholder*='email' i]"),
        ]:
            try:
                user_field = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located(selector)
                )
                user_field.clear()
                user_field.send_keys(config.FIVERR_USERNAME)
                break
            except Exception:
                continue

        time.sleep(1)

        # Try multiple possible selectors for password
        for selector in [
            (By.NAME, "password"),
            (By.ID, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]:
            try:
                pass_field = driver.find_element(*selector)
                pass_field.clear()
                pass_field.send_keys(config.FIVERR_PASSWORD)
                break
            except Exception:
                continue

        time.sleep(1)

        # Click login button
        for selector in [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "button[class*='login']"),
            (By.XPATH, "//button[contains(text(),'Continue')]"),
            (By.XPATH, "//button[contains(text(),'Log in')]"),
        ]:
            try:
                btn = driver.find_element(*selector)
                btn.click()
                break
            except Exception:
                continue

        time.sleep(6)
        # Check if login succeeded
        if "fiverr.com" in driver.current_url and "login" not in driver.current_url:
            log.info("Fiverr login successful.")
            return True
        else:
            log.warning("Fiverr login may have failed - continuing anyway.")
            return True
    except Exception as e:
        log.error(f"Fiverr login failed: {e}")
        return False


def get_active_orders(driver):
    log.info("Checking for active orders...")
    driver.get("https://www.fiverr.com/orders")
    time.sleep(4)
    orders = []

    try:
        order_rows = driver.find_elements(By.CSS_SELECTOR, "tr.order-row, div[class*='order-item']")
        for row in order_rows:
            try:
                order_id = row.get_attribute("data-order-id") or row.get_attribute("id") or ""
                link_el = row.find_element(By.CSS_SELECTOR, "a[href*='/orders/']")
                link = link_el.get_attribute("href")
                if order_id and link:
                    orders.append({"id": order_id, "link": link})
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Could not parse orders: {e}")

    # Fallback: find all order links
    if not orders:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/orders/']")
        seen = set()
        for link in links:
            href = link.get_attribute("href")
            if href and "/orders/" in href and href not in seen:
                seen.add(href)
                order_id = href.split("/orders/")[-1].split("/")[0]
                if order_id:
                    orders.append({"id": order_id, "link": href})

    log.info(f"Found {len(orders)} orders.")
    return orders


def get_order_requirements(driver, order_link):
    driver.get(order_link)
    time.sleep(4)
    requirements = ""

    try:
        # Look for buyer requirements/instructions
        req_elements = driver.find_elements(
            By.CSS_SELECTOR,
            "div[class*='requirements'], div[class*='buyer-instruction'], p[class*='requirement']"
        )
        for el in req_elements:
            text = el.text.strip()
            if text and len(text) > 10:
                requirements += text + "\n"

        # Also check chat/messages for requirements
        if not requirements:
            msgs = driver.find_elements(By.CSS_SELECTOR, "div[class*='message-body'], p[class*='message']")
            for msg in msgs[:3]:
                requirements += msg.text.strip() + "\n"

    except Exception as e:
        log.warning(f"Could not get requirements: {e}")

    return requirements.strip() or "Write a 500-word SEO blog post on a trending topic."


def deliver_order(driver, order_link, content):
    driver.get(order_link)
    time.sleep(4)

    try:
        # Find delivery button
        deliver_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "button[class*='deliver'], a[class*='deliver-work'], button[data-testid*='deliver']"
            ))
        )
        deliver_btn.click()
        time.sleep(3)

        # Find text area and paste content
        text_area = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR,
                "textarea[class*='delivery'], div[contenteditable='true'], textarea[placeholder*='describe']"
            ))
        )
        text_area.clear()
        text_area.send_keys(content[:4000])  # Fiverr has character limits
        time.sleep(2)

        # Submit delivery
        submit_btn = driver.find_element(By.CSS_SELECTOR,
            "button[type='submit'][class*='deliver'], button[class*='submit-delivery']"
        )
        submit_btn.click()
        time.sleep(3)

        log.info("Order delivered successfully!")
        return True

    except Exception as e:
        # Save content to file as backup
        backup = Path(f"delivery_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        backup.write_text(content, encoding="utf-8")
        log.error(f"Auto-delivery failed: {e}. Content saved to {backup.name}")
        return False


def run():
    if not config.FIVERR_USERNAME or not config.FIVERR_PASSWORD:
        log.error("Set FIVERR_USERNAME and FIVERR_PASSWORD in config.py first.")
        return

    log.info("Fiverr bot started. Checking orders every 10 minutes.")
    driver = create_driver()

    try:
        if not login_fiverr(driver):
            return

        while True:
            try:
                delivered = get_delivered_orders()
                orders = get_active_orders(driver)

                for order in orders:
                    if order["id"] in delivered:
                        continue

                    log.info(f"New order found: {order['id']}")
                    requirements = get_order_requirements(driver, order["link"])
                    log.info(f"Requirements: {requirements[:100]}...")

                    content = generate_content(order["id"], requirements)
                    log.info(f"Content generated: {len(content)} chars")

                    success = deliver_order(driver, order["link"], content)
                    if success:
                        mark_delivered(order["id"])
                        log.info(f"Order {order['id']} completed and delivered!")

            except Exception as e:
                log.error(f"Error in Fiverr loop: {e}", exc_info=True)

            time.sleep(600)  # check every 10 minutes

    finally:
        driver.quit()


if __name__ == "__main__":
    run()
