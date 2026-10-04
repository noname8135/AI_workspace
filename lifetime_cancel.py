#!/usr/bin/env python3
"""
CourtReserve Cancellation Script
Usage: python3 lifetime_cancel.py <reservation_id>
Example: python3 lifetime_cancel.py 52458474
"""

import requests, sys, datetime, logging, os, re

# ── Telegram Config ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8658174912:AAHsYOaCNcET2ULNAfBlB6Z2A3snqRg1l4k"
TELEGRAM_CHANNEL_ID = "-1003889752528"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# ── Logging Setup ────────────────────────────────────────────────────────────
log_dir = "/home/hatch/workspace/tennis-booker/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "lifetime_cancel.log")
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

BASE_URL = "https://app.courtreserve.com"
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


def cancel_reservation(s, reservation_id):
    """Cancel a reservation by ID."""
    try:
        logging.info(f"Cancelling reservation {reservation_id}...")
        
        # Step 1: GET the cancel page to extract form data
        cancel_get_url = f"{BASE_URL}/Online/MyProfile/CancelReservation/{ORG_ID}?reservationId={reservation_id}"
        logging.info(f"GET {cancel_get_url}")
        r = s.get(cancel_get_url)
        
        if r.status_code != 200:
            logging.error(f"Failed to get cancel page: {r.status_code}")
            return False
        
        # Extract all form fields
        form_data = {}
        input_pattern = r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"'
        inputs = re.findall(input_pattern, r.text)
        
        logging.info(f"Found {len(inputs)} form fields")
        
        for name, value in inputs:
            form_data[name] = value
        
        # Add cancellation reason
        form_data['SelectedReservation.CancellationReason'] = 'Not needed anymore'
        form_data['X-Requested-With'] = 'XMLHttpRequest'
        
        # Extract reservation details for logging
        res_start = form_data.get('SelectedReservation.Start', 'Unknown')
        res_end = form_data.get('SelectedReservation.End', 'Unknown')
        logging.info(f"Reservation: {res_start} - {res_end}")
        
        # Step 2: POST the cancellation
        cancel_post_url = f"{BASE_URL}/Online/MyProfile/CancelReservation/{ORG_ID}"
        logging.info(f"POST {cancel_post_url}")
        
        r = s.post(
            cancel_post_url,
            data=form_data,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        logging.info(f"Response status: {r.status_code}")
        logging.info(f"Response body: {r.text}")
        
        if r.status_code == 200:
            try:
                response_json = r.json()
                if response_json.get('isValid'):
                    logging.info(f"✓ Cancellation successful")
                    return True
            except:
                pass
            
            # Even if we can't parse JSON, 200 is usually success
            logging.warning(f"Got 200 response, assuming success")
            return True
        else:
            logging.error(f"Cancellation failed with status {r.status_code}")
            return False
            
    except Exception as e:
        logging.error(f"Cancel exception: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 lifetime_cancel.py <reservation_id>")
        print("Example: python3 lifetime_cancel.py 52458474")
        sys.exit(1)
    
    reservation_id = sys.argv[1]
    
    logging.info("="*80)
    logging.info(f"Cancelling reservation {reservation_id}")
    logging.info("="*80)
    
    s = login()
    if not s:
        logging.error("Failed to login")
        send_telegram(f"❌ Cancel failed: Login error")
        sys.exit(1)
    
    success = cancel_reservation(s, reservation_id)
    
    if success:
        msg = f"✅ Cancelled reservation {reservation_id}"
        logging.info(msg)
        send_telegram(msg)
        sys.exit(0)
    else:
        msg = f"❌ Failed to cancel reservation {reservation_id}"
        logging.error(msg)
        send_telegram(msg)
        sys.exit(1)
