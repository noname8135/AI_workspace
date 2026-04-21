#!/usr/bin/env python3
"""
CourtReserve Multi-Location Auto-Booking Script
Tries Lifetime Fitness first (sId=16995), then Buchser High (sId=16996) as fallback
"""

import requests, sys, time, datetime, random, re, logging, os
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Telegram Config ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8658174912:AAHsYOaCNcET2ULNAfBlB6Z2A3snqRg1l4k")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "-1003889752528")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# ── Logging Setup ────────────────────────────────────────────────────────────
log_dir = "/mnt/c/Users/User/Desktop/AI_workspace/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "lifetime_autobook_multi.log")
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
EMAIL    = os.getenv("LIFETIME_EMAIL", "shuaichiou@gmail.com")
PASSWORD = os.getenv("LIFETIME_PASSWORD", "e04xup6xl3g")
ORG_ID   = os.getenv("LIFETIME_ORG_ID", "13234")

BASE_URL = "https://app.courtreserve.com"

# Location configs
LOCATIONS = {
    "Lifetime": {
        "sId": "16995",
        "courtTypeId": "2",
        "courts": [1, 2, 3, 4, 6, 7, 8],  # Skip court 5
    },
    "Buchser High": {
        "sId": "16996",
        "courtTypeId": "2",
        "courts": [1, 2, 3, 4, 6, 7, 8],  # Adjust as needed
    }
}

# Time slots (90 min duration)
TIME_SLOTS = [
    ("8:00 PM", "9:30 PM"),
    ("7:00 PM", "8:30 PM"),
    ("6:00 PM", "7:30 PM"),
    ("5:30 PM", "7:00 PM"),
    ("5:00 PM", "6:30 PM"),
]

# Tomorrow's date (book for same weekday next week)
TARGET_DATE = datetime.date.today() + datetime.timedelta(days=7)
TARGET_DATE_STR = TARGET_DATE.strftime("%-m/%-d/%Y")
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
        logging.info(f"Telegram: {message[:50]}...")
    except Exception as e:
        logging.error(f"Telegram failed: {e}")


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
        r = s.post(login_url, data={"UserNameOrEmail": EMAIL, "Password": PASSWORD}, headers={"Referer": login_url})
        if ".AspNet.ApplicationCookie" not in s.cookies:
            logging.error("Login FAILED: No auth cookie")
            return None
        logging.info("✓ Login OK")
        return s
    except Exception as e:
        logging.error(f"Login exception: {e}", exc_info=True)
        return None


def get_booking_tokens(s, location_name):
    """Get CSRF token and request data for a location."""
    try:
        sid = LOCATIONS[location_name]["sId"]
        bookings_url = f"{BASE_URL}/Online/Reservations/Bookings/{ORG_ID}?sId={sid}"
        
        logging.info(f"Fetching tokens for {location_name}...")
        r = s.get(bookings_url)
        
        # Extract requestData
        req_data_match = re.search(r'requestData\s*=\s*["\']([^"\']+)["\']', r.text)
        csrf_match = re.search(r'__RequestVerificationToken["\']?\s*value=["\']([^"\']+)["\']', r.text)
        
        if not req_data_match or not csrf_match:
            logging.warning(f"Could not extract tokens for {location_name}")
            return None
        
        return {
            "requestData": req_data_match.group(1),
            "csrf": csrf_match.group(1)
        }
    except Exception as e:
        logging.error(f"Token extraction failed: {e}")
        return None


def book_court(s, location_name, time_start, time_end, court_id, tokens):
    """Try to book a specific court at a location."""
    try:
        sid = LOCATIONS[location_name]["sId"]
        court_type_id = LOCATIONS[location_name]["courtTypeId"]
        
        booking_url = f"{BASE_URL}/Online/ReservationsApi/CreateReservation/{ORG_ID}"
        
        data = {
            "Date": TARGET_DATE_STR,
            "StartTime": time_start,
            "Duration": "90",
            "CourtId": str(court_id),
            "SchedulerId": sid,
            "CustomSchedulerId": sid,
            "CourtTypeId": court_type_id,
            "MemberId": "6710116",
            "MembershipId": "141172",
            "requestData": tokens["requestData"],
            "__RequestVerificationToken": tokens["csrf"]
        }
        
        r = s.post(booking_url, data=data, timeout=10)
        
        if r.status_code == 200:
            try:
                result = r.json()
                if result.get("isValid"):
                    return True, f"{location_name} Court {court_id} {time_start}–{time_end}"
            except:
                pass
        
        return False, None
    except Exception as e:
        logging.error(f"Booking exception: {e}")
        return False, None


def try_location(s, location_name):
    """Try to book at a location across all time slots and courts."""
    logging.info(f"\n{'='*60}")
    logging.info(f"Trying {location_name} for {TARGET_DATE_STR}")
    logging.info(f"{'='*60}")
    
    tokens = get_booking_tokens(s, location_name)
    if not tokens:
        logging.warning(f"Could not get tokens for {location_name}")
        return None
    
    # Try each time slot
    for time_start, time_end in TIME_SLOTS:
        logging.info(f"\nTrying {time_start}–{time_end}...")
        
        # Randomize court order
        courts = LOCATIONS[location_name]["courts"].copy()
        random.shuffle(courts)
        
        # Try courts in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for court_id in courts:
                future = executor.submit(book_court, s, location_name, time_start, time_end, court_id, tokens)
                futures[future] = court_id
            
            for future in as_completed(futures):
                success, booking_info = future.result()
                if success:
                    logging.info(f"✓ BOOKED: {booking_info}")
                    return booking_info
    
    logging.warning(f"All slots full at {location_name}")
    return None


if __name__ == "__main__":
    logging.info("="*80)
    logging.info(f"Multi-Location Booking — Targeting {TARGET_DATE_STR}")
    logging.info("="*80)
    
    # Wait until noon
    while True:
        now = datetime.datetime.now()
        if now.hour == 12 and now.minute >= 0:
            break
        time.sleep(1)
    
    logging.info(f"Noon reached. Starting booking at {datetime.datetime.now()}")
    
    s = login()
    if not s:
        logging.error("Login failed")
        send_telegram("❌ Multi-location booking failed: Login error")
        sys.exit(1)
    
    # Try Lifetime first
    result = try_location(s, "Lifetime")
    
    # If Lifetime fails, try Buchser High
    if not result:
        logging.info("\nLifetime failed, trying Buchser High...")
        result = try_location(s, "Buchser High")
    
    # Report result
    if result:
        msg = f"✅ {result}"
        logging.info(f"\n{msg}")
        send_telegram(msg)
        sys.exit(0)
    else:
        msg = f"❌ Booking failed - all locations/slots full ({TARGET_DATE_STR})"
        logging.error(f"\n{msg}")
        send_telegram(msg)
        sys.exit(1)
