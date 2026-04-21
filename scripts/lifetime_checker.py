#!/usr/bin/env python3
"""
CourtReserve Daily Check Script
Checks if there's a court booked TODAY and sends reminder to Telegram.
Only reports if a court is actually booked (no noise if no reservation).

Cron: 0 9 * * * (9 AM daily)
"""

import requests, sys, datetime, logging, os, re
from urllib.parse import unquote

# ── Telegram Config ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8658174912:AAHsYOaCNcET2ULNAfBlB6Z2A3snqRg1l4k"
TELEGRAM_CHANNEL_ID = "-1003889752528"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# ── Logging Setup ────────────────────────────────────────────────────────────
log_dir = "/home/noname8135/.openclaw/workspace/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "lifetime_checker.log")
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

# Today's date for checking
TODAY = datetime.date.today().strftime("%-m/%-d/%Y")

BASE_URL         = "https://app.courtreserve.com"
RESERVATIONS_URL = "https://reservations.courtreserve.com"
# ─────────────────────────────────────────────────────────────────────────────


def send_telegram(message):
    """Send message to Telegram channel."""
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


def login():
    """Login to CourtReserve."""
    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0",
            "Origin": BASE_URL
        })
        login_url = f"{BASE_URL}/Online/Account/LogIn/{ORG_ID}"
        s.get(login_url)
        s.post(login_url, data={"UserNameOrEmail": EMAIL, "Password": PASSWORD}, headers={"Referer": login_url})
        if ".AspNet.ApplicationCookie" not in s.cookies:
            logging.error("Login FAILED: No auth cookie")
            return None
        logging.info("Login OK")
        return s
    except Exception as e:
        logging.error(f"Login exception: {e}", exc_info=True)
        return None


def get_reservations(s):
    """Fetch all reservations for today and return court details."""
    try:
        # Access member portal to get reservations
        r = s.get(f"{BASE_URL}/Online/Portal/Index/{ORG_ID}")
        
        # Look for reservations in the page
        # Pattern: Extract court name and time from reservation display
        # This is a simplified approach - you may need to adjust based on actual page structure
        
        # Alternative: Use the member reservations API
        r = s.get(
            f"{BASE_URL}/Online/AjaxController/GetMemberReservations/{ORG_ID}",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if r.status_code != 200:
            logging.error(f"Failed to fetch reservations: {r.status_code}")
            return None
        
        try:
            data = r.json()
            logging.info(f"Reservations data: {data}")
            
            # Look for today's reservations in the response
            if isinstance(data, dict) and "reservations" in data:
                for res in data["reservations"]:
                    res_date = res.get("date", "")
                    if TODAY in res_date or res_date == TODAY:
                        court = res.get("courtName", "Unknown Court")
                        start_time = res.get("startTime", "Unknown Time")
                        end_time = res.get("endTime", "Unknown Time")
                        return {
                            "court": court,
                            "start": start_time,
                            "end": end_time,
                            "date": res_date
                        }
            return None
        except Exception as e:
            logging.warning(f"Failed to parse JSON response: {e}")
            # Try HTML parsing as fallback
            return parse_reservations_html(r.text)
    except Exception as e:
        logging.error(f"Get reservations exception: {e}", exc_info=True)
        return None


def parse_reservations_html(html):
    """Parse reservation details from HTML page as fallback."""
    try:
        # Look for reservation blocks containing TODAY's date
        # This is a simplified pattern - adjust based on actual HTML structure
        if TODAY not in html:
            return None
        
        # Pattern to match: Court Name + Time
        # Example: "Court 1" or "Court 2" followed by time like "5:00 PM"
        pattern = r'Court\s+(\d+).*?(\d{1,2}:\d{2}\s+(?:AM|PM)).*?(\d{1,2}:\d{2}\s+(?:AM|PM))'
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        
        if match:
            return {
                "court": f"Court {match.group(1)}",
                "start": match.group(2),
                "end": match.group(3),
                "date": TODAY
            }
        
        # If can't parse, log and return None
        logging.warning("Could not parse reservation from HTML")
        return None
    except Exception as e:
        logging.error(f"HTML parse exception: {e}", exc_info=True)
        return None


if __name__ == "__main__":
    logging.info("="*80)
    logging.info(f"Checking for reservations on {TODAY}")
    logging.info("="*80)
    
    s = login()
    if not s:
        logging.error("Failed to login")
        send_telegram("⚠️ Checker: Login failed")
        sys.exit(1)
    
    reservation = get_reservations(s)
    
    if reservation:
        court = reservation.get("court", "Unknown")
        start = reservation.get("start", "Unknown")
        end = reservation.get("end", "Unknown")
        msg = f"📌 Court booked today: {court}, {start}–{end}"
        logging.info(msg)
        send_telegram(msg)
    else:
        logging.info("No reservations found for today - no notification sent")
    
    logging.info("="*80)
    sys.exit(0)
