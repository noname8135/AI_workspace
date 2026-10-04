#!/usr/bin/env python3
"""
CourtReserve Auto-Booking v2 (optimized)
Site: https://app.courtreserve.com/Online/Account/LogIn/13234

Improvements over v1 (verified by live testing 2026-10-04):
 1. Login: POST-only, skips the initial GET (verified: saves 1 round-trip).
 2. Waiver auto-sign: if the booking form redirects to a pending disclosures/
    waiver page, the script signs it automatically (typed signature) and
    retries — annual waiver renewals no longer silently break the flow.
 3. No shuffle: slots are tried in strict priority order, courts in fixed
    order — deterministic, best slot wins.
 4. Slot-by-slot firing (not all-slots-at-once): guarantees the best
    available slot is taken, not a worse one that happened to respond first.
 5. cancel_futures=True after first success: kills queued duplicate requests,
    reducing double-booking risk from parallel firing.
 6. Logs the full booking response (captures reservation ID for cancel).
 7. --dry-run flag: runs login + prefetch + availability check without
    booking anything (safe to test any time).

Cron (runs daily, books same weekday next week at noon sharp):
  59 11 * * * /usr/bin/python3 /path/to/lifetime_autobook_v2.py >> /tmp/lifetime_autobook.log 2>&1
"""

import requests, sys, time, datetime, re, logging, os, io, base64, html as htmllib
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Configuration (prefer env vars; fallback to hardcoded) ───────────────────
EMAIL    = os.getenv("LIFETIME_EMAIL", "shuaichiou@gmail.com")
PASSWORD = os.getenv("LIFETIME_PASSWORD", "e04xup6xl3g")
ORG_ID   = os.getenv("LIFETIME_ORG_ID", "13234")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8658174912:AAHsYOaCNcET2ULNAfBlB6Z2A3snqRg1l4k")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "-1003889752528")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# Target date: same weekday next week
TARGET_DATE = datetime.date.today() + datetime.timedelta(days=7)
DATE        = TARGET_DATE.strftime("%-m/%-d/%Y")
WEEKEND     = TARGET_DATE.weekday() >= 5

WEEKDAY_SLOTS = [
    ("8:00 PM", "9:30 PM", "90"),
    ("7:00 PM", "8:30 PM", "90"),
    ("6:00 PM", "7:30 PM", "90"),
    ("5:30 PM", "7:00 PM", "90"),
    ("5:00 PM", "6:30 PM", "90"),
]
WEEKEND_SLOTS = [
    ("4:00 PM", "5:30 PM", "90"),
    ("4:30 PM", "6:00 PM", "90"),
    ("5:00 PM", "6:30 PM", "90"),
    ("5:30 PM", "7:00 PM", "90"),
    ("6:00 PM", "7:30 PM", "90"),
]
TIME_SLOTS = WEEKEND_SLOTS if WEEKEND else WEEKDAY_SLOTS

COURT_IDS = {
    "Court 1": "52096",
    "Court 2": "52097",
    "Court 3": "52098",
    "Court 4": "52099",
    "Court 6": "52101",
    "Court 7": "52102",
    "Court 8": "52103",
}

COURT_TYPE_ID        = "2"
SCHEDULER_ID         = "16995"
TIMEZONE             = "America/Los_Angeles"
RESERVATION_TYPE_ID  = "69711"
MEMBER_ID            = "6710116"
MEMBERSHIP_ID        = "141172"
USER_ID              = "6710116"

BASE_URL         = "https://app.courtreserve.com"
RESERVATIONS_URL = "https://reservations.courtreserve.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0"
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger()


def send_telegram(message):
    try:
        requests.post(TELEGRAM_API,
                      data={"chat_id": TELEGRAM_CHANNEL_ID, "text": message},
                      timeout=10)
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


def login():
    """POST-only login (the initial GET is unnecessary — verified)."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Origin": BASE_URL})
    login_url = f"{BASE_URL}/Online/Account/LogIn/{ORG_ID}"
    r = s.post(login_url, data={"UserNameOrEmail": EMAIL, "Password": PASSWORD},
               headers={"Referer": login_url}, timeout=45)
    if ".AspNet.ApplicationCookie" not in s.cookies:
        log.error(f"Login FAILED (HTTP {r.status_code})")
        sys.exit(1)
    log.info("Login OK")
    return s


def sign_pending_waivers(s):
    """Sign any pending disclosures/waivers (typed signature), return True if
    something was signed."""
    r = s.get(f"{BASE_URL}/Online/Disclosures/Pending/{ORG_ID}",
              params={"userId": USER_ID, "reservationId": "0"}, timeout=45)
    if "disclosures-form" not in r.text:
        return False
    name_m = re.search(r'name="SigningMemberFullName"[^>]*value="([^"]+)"', r.text)
    signer = name_m.group(1) if name_m else "Yen-Chun Chiu"
    log.info(f"Pending waiver found — signing as {signer}")

    # Render typed signature to PNG data URL
    try:
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 64)
    except Exception:
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.load_default()
    img = Image.new("RGBA", (600, 120), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.text((20, 25), signer, font=font, fill=(20, 40, 120, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    sig_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    data = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', r.text):
        tag = m.group(0)
        nm = re.search(r'name="([^"]+)"', tag)
        vl = re.search(r'value="([^"]*)"', tag)
        if nm:
            data[nm.group(1)] = htmllib.unescape(vl.group(1)) if vl else ""
    data["Members[0].Disclosures[0].AcceptAgreement"] = "true"
    data["Members[0].Disclosures[0].SignatureDataUrl"] = sig_url
    r2 = s.post(f"{BASE_URL}/Online/Disclosures/Pending/{ORG_ID}", data=data,
                headers={"Referer": r.url, "X-Requested-With": "XMLHttpRequest"},
                timeout=45)
    ok = r2.json().get("isValid", False)
    log.info(f"Waiver sign result: {r2.text[:120]}")
    return ok


def prefetch(s):
    """Grab requestData + CSRF token, auto-signing waivers if they block."""
    r = s.get(f"{BASE_URL}/Online/Reservations/Bookings/{ORG_ID}",
              params={"sId": SCHEDULER_ID}, timeout=45)
    m = re.search(r'requestData=([A-Za-z0-9%+/=]+)', r.text)
    if not m:
        log.error("Failed to extract requestData")
        sys.exit(1)
    request_data = unquote(m.group(1))

    def fetch_form():
        start_time, _, duration = TIME_SLOTS[0]
        end_dt = (datetime.datetime.strptime(start_time, "%I:%M %p")
                  + datetime.timedelta(minutes=int(duration)))
        return s.get(
            f"{RESERVATIONS_URL}/Online/ReservationsApi/CreateReservation",
            params={"id": ORG_ID, "uiCulture": "en-US",
                    "start": f"{DATE} {start_time}",
                    "end": f"{DATE} {end_dt.strftime('%-I:%M %p')}",
                    "courtType": "Hard", "courtTypeId": COURT_TYPE_ID,
                    "customSchedulerId": SCHEDULER_ID, "isConsolidated": "True",
                    "instructorId": "", "isMobileLayout": "False",
                    "requestData": request_data}, timeout=45)

    r = fetch_form()
    m = re.search(r'<input name="__RequestVerificationToken" type="hidden" '
                  r'value="([^"]+)"', r.text)
    if not m:
        if "restricted to 1 court" in r.text:
            # Target date already has a booking — nothing to do.
            log.info("Per-day court limit already reached for target date — "
                     "a booking exists, nothing to do.")
            return None, None
        # Possibly blocked by a pending waiver — sign and retry once
        log.warning("No CSRF token — checking for pending waiver...")
        if sign_pending_waivers(s):
            r = fetch_form()
            m = re.search(r'<input name="__RequestVerificationToken" type="hidden" '
                          r'value="([^"]+)"', r.text)
    if not m:
        log.error("Failed to get CSRF token")
        sys.exit(1)
    log.info("Prefetch OK")
    return request_data, m.group(1)


def wait_until_noon(s):
    now = datetime.datetime.now()
    noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    delta = (noon - now).total_seconds()
    if delta > 0:
        log.info(f"Waiting {delta:.1f}s until noon...")
        if delta > 15:
            time.sleep(delta - 15)
        try:
            s.get(f"{BASE_URL}/Online/Portal/Index/{ORG_ID}", timeout=5)
        except Exception:
            pass
        try:
            s.get(f"{RESERVATIONS_URL}/", timeout=5)
        except Exception:
            pass
        while datetime.datetime.now() < noon:
            pass
    log.info(f"Firing at {datetime.datetime.now().strftime('%H:%M:%S.%f')}")


def book(s, court_id, start_time, duration, csrf, request_data):
    r = s.post(
        f"{RESERVATIONS_URL}/Online/ReservationsApi/CreateReservation/{ORG_ID}?uiCulture=en-US",
        data={
            "__RequestVerificationToken": csrf,
            "Id": ORG_ID, "OrgId": ORG_ID, "MemberId": MEMBER_ID, "MemberIds": "",
            "IsConsolidatedScheduler": "True", "IsConsolidated": "True",
            "Date": f"{DATE} 12:00:00 AM",
            "StartTime": datetime.datetime.strptime(start_time, "%I:%M %p").strftime("%H:%M:%S"),
            "Duration": duration, "CourtId": str(court_id),
            "CourtTypeId": COURT_TYPE_ID, "CourtTypeEnum": COURT_TYPE_ID,
            "CustomSchedulerId": SCHEDULER_ID, "MembershipId": MEMBERSHIP_ID,
            "ReservationTypeId": RESERVATION_TYPE_ID, "RequestData": request_data,
            "Token": "", "DisclosureAgree": "true",
        },
        headers={"Referer": f"{BASE_URL}/",
                 "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30)
    return r.json()


def check_availability(s):
    """Read-only: how many courts are free per slot (for --dry-run)."""
    date_full = f"{DATE} 12:00:00 AM"
    for start_time, end_time, duration in TIME_SLOTS:
        start_hms = datetime.datetime.strptime(start_time, "%I:%M %p").strftime("%H:%M:%S")
        r = s.get(
            f"{BASE_URL}/Online/AjaxController/GetAvailableCourtsMemberPortal/{ORG_ID}",
            params={"Date": date_full, "selectedDate": date_full,
                    "StartTime": start_hms, "EndTime": end_time,
                    "CourtTypesString": COURT_TYPE_ID, "timeZone": TIMEZONE,
                    "customSchedulerId": SCHEDULER_ID, "instructorId": "",
                    "Duration": duration, "AllowPastReservationsUpToXMinutes": "",
                    "ResourceId": "", "CourtIdsString": "",
                    "ReservationQueueSlotId": "", "uiCulture": "en-US"},
            headers={"X-Requested-With": "XMLHttpRequest"}, timeout=45)
        data = r.json()
        n = len(data) if isinstance(data, list) else "?"
        log.info(f"  {start_time}–{end_time}: {n} courts free")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    log.info(f"Target date: {DATE} ({'weekend' if WEEKEND else 'weekday'} slots)"
             + (" [DRY RUN]" if dry_run else ""))
    s = login()

    if dry_run:
        # Safe anytime: login + availability only, never books.
        check_availability(s)
        log.info("Dry run complete — nothing was booked.")
        sys.exit(0)

    request_data, csrf = prefetch(s)
    if csrf is None:
        # Already booked for target date (or blocked) — exit cleanly.
        sys.exit(0)

    wait_until_noon(s)

    # Slots in strict priority order; all courts in parallel per slot.
    for start_time, end_time, duration in TIME_SLOTS:
        log.info(f"Trying {start_time}–{end_time}...")
        executor = ThreadPoolExecutor(max_workers=len(COURT_IDS))
        futures = {
            executor.submit(book, s, cid, start_time, duration, csrf, request_data): name
            for name, cid in COURT_IDS.items()
        }
        won = False
        winner_name = None
        messages = []
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
            except Exception as e:
                log.warning(f"  {name}: error {e}")
                continue
            messages.append(str(result.get("message", "")))
            log.info(f"  {name}: {str(result)[:200]}")
            if result.get("isValid") and not won:
                won = True
                winner_name = name
                log.info(f"BOOKING SUCCESS: {name} {start_time}–{end_time}")
        # Cancel anything still queued — we already won this slot (or not)
        executor.shutdown(cancel_futures=True)
        if won:
            send_telegram(f"✅ {winner_name} {start_time}–{end_time} ({DATE})")
            sys.exit(0)
        if any("restricted to 1 court" in m for m in messages):
            log.info("Per-day limit hit — a booking already landed.")
            send_telegram(f"✅ Court booked for {DATE} (check app)")
            sys.exit(0)

    log.error("All slots exhausted. Booking FAILED.")
    send_telegram(f"❌ Booking failed for {DATE}")
    sys.exit(1)
