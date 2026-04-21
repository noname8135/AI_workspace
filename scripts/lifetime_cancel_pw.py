#!/usr/bin/env python3
"""
CourtReserve Cancellation Script (Playwright)
Logs in, navigates portal, finds reservation, cancels with reason.
"""

import asyncio
from playwright.async_api import async_playwright
import datetime
import logging
import os
import requests

# ── Telegram Config ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8658174912:AAHsYOaCNcET2ULNAfBlB6Z2A3snqRg1l4k"
TELEGRAM_CHANNEL_ID = "-1003889752528"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# ── Logging Setup ────────────────────────────────────────────────────────────
log_dir = "/home/noname8135/.openclaw/workspace/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "lifetime_cancel_pw.log")
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# ── Configuration ────────────────────────────────────────────────────────────
EMAIL    = "shuaichiou@gmail.com"
PASSWORD = "e04xup6xl3g"
ORG_ID   = "13234"

TOMORROW = (datetime.date.today() + datetime.timedelta(days=1))
TOMORROW_STR = TOMORROW.strftime("%-m/%-d/%Y")

BASE_URL = "https://app.courtreserve.com"
# ─────────────────────────────────────────────────────────────────────────────


def send_telegram(message):
    """Send message to Telegram."""
    try:
        requests.post(
            TELEGRAM_API,
            data={
                "chat_id": TELEGRAM_CHANNEL_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=5
        )
        logging.info(f"Telegram sent: {message[:50]}...")
    except Exception as e:
        logging.error(f"Failed to send Telegram: {e}")


async def cancel_reservation():
    """Main cancellation flow."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            logging.info("="*80)
            logging.info(f"Attempting to cancel reservation for {TOMORROW_STR}")
            logging.info("="*80)
            
            # Login
            logging.info("Navigating to login...")
            login_url = f"{BASE_URL}/Online/Account/LogIn/{ORG_ID}"
            await page.goto(login_url, wait_until="networkidle")
            logging.info("Login page loaded")
            
            # Fill in credentials
            await page.fill('input[name="UserNameOrEmail"]', EMAIL)
            await page.fill('input[name="Password"]', PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle")
            logging.info("✓ Logged in")
            
            # Go to member portal
            portal_url = f"{BASE_URL}/Online/Portal/Index/{ORG_ID}"
            logging.info(f"Navigating to portal: {portal_url}")
            await page.goto(portal_url, wait_until="networkidle")
            await page.wait_for_timeout(2000)  # Wait for JS rendering
            logging.info("Portal loaded")
            
            # Look for tomorrow's reservation
            # Wait for reservation elements to appear
            await page.wait_for_selector("[data-reservation-id], .reservation, .booking", timeout=10000)
            
            # Get all visible text containing tomorrow's date
            page_content = await page.content()
            logging.info(f"Page content length: {len(page_content)}")
            
            # Look for edit/modify buttons for tomorrow's date
            # First, find all divs/sections that contain tomorrow's date
            reservation_found = False
            
            # Try to find elements by tomorrow's date
            date_patterns = [TOMORROW_STR, TOMORROW.strftime("%m/%d/%Y"), TOMORROW.strftime("%-m/%-d/%Y")]
            
            for date_pattern in date_patterns:
                logging.info(f"Looking for date pattern: {date_pattern}")
                # Find all elements containing this date
                elements = await page.query_selector_all(f"text/{date_pattern}")
                if elements:
                    logging.info(f"Found {len(elements)} elements with date {date_pattern}")
                    
                    # For each element, look for a nearby Edit/Modify button
                    for elem in elements[:1]:  # Take first match
                        # Get parent container
                        parent = await elem.evaluate("el => el.closest('[data-reservation-id], .reservation-item, tr, .booking')")
                        
                        if parent:
                            # Look for edit button within this container
                            edit_btn = await parent.query_selector("button:has-text('Edit'), a:has-text('Edit'), [class*='edit']")
                            
                            if edit_btn:
                                logging.info(f"Found Edit button for {date_pattern}")
                                await edit_btn.click()
                                await page.wait_for_load_state("networkidle")
                                reservation_found = True
                                break
            
            if not reservation_found:
                logging.warning("Could not find reservation edit button")
                # Try a different approach: look for all buttons/links
                all_buttons = await page.query_selector_all("button, a[role='button'], input[type='button']")
                logging.info(f"Found {len(all_buttons)} total buttons on page")
                
                # Screenshot for debugging
                await page.screenshot(path="/tmp/lifetime_portal.png")
                logging.info("Saved screenshot to /tmp/lifetime_portal.png")
                send_telegram("❌ Cancel failed: Could not find reservation on portal")
                return False
            
            # Now on edit page - look for Cancel button
            logging.info("Looking for Cancel button...")
            await page.wait_for_timeout(1000)
            
            cancel_btn = await page.query_selector("button:has-text('Cancel'), a:has-text('Cancel'), input[value='Cancel']")
            if cancel_btn:
                logging.info("Found Cancel button")
                await cancel_btn.click()
                await page.wait_for_load_state("networkidle")
            else:
                logging.warning("Could not find Cancel button, trying alternative selectors...")
                # Try clicking any button with "cancel" in it
                cancel_btns = await page.query_selector_all("button, a")
                for btn in cancel_btns:
                    text = await btn.inner_text()
                    if "cancel" in text.lower():
                        logging.info(f"Clicking button: {text}")
                        await btn.click()
                        await page.wait_for_load_state("networkidle")
                        break
            
            # Now fill in cancellation reason
            logging.info("Looking for cancellation reason form...")
            
            # Wait a moment for form to appear
            await page.wait_for_timeout(1000)
            
            # Look for reason field
            reason_selector = "select[name*='reason'], textarea[name*='reason'], input[name*='reason']"
            reason_field = await page.query_selector(reason_selector)
            
            if reason_field:
                await reason_field.fill("Not needed anymore")
                logging.info("✓ Filled in cancellation reason")
            else:
                logging.warning("Could not find reason field, proceeding...")
            
            # Look for submit/confirm button
            await page.wait_for_timeout(500)
            submit_btn = await page.query_selector("button:has-text('Confirm'), button:has-text('Submit'), button:has-text('OK')")
            
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_load_state("networkidle")
                logging.info("✓ Submitted cancellation")
            else:
                logging.warning("Could not find submit button")
            
            # Check for success message
            await page.wait_for_timeout(1000)
            success_indicators = await page.content()
            
            if any(word in success_indicators.lower() for word in ["cancel", "success", "confirm", "completed"]):
                msg = f"✅ Cancelled court reservation for {TOMORROW_STR}"
                logging.info(msg)
                send_telegram(msg)
                return True
            else:
                logging.info("Could not confirm success, but form was submitted")
                send_telegram(f"⚠️ Cancellation submitted (unconfirmed) for {TOMORROW_STR}")
                return True
            
        except Exception as e:
            logging.error(f"Exception: {e}", exc_info=True)
            send_telegram(f"❌ Cancel failed: {str(e)[:50]}")
            return False
        
        finally:
            await browser.close()
            logging.info("="*80)


if __name__ == "__main__":
    success = asyncio.run(cancel_reservation())
    exit(0 if success else 1)
