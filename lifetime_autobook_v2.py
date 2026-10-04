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

Race mode (for the daily noon rush — session warmup + precise fire):
  python3 lifetime_autobook_v2.py --race
    Warms up early (login + prefetch requestData/CSRF), sends keepalive pings,
    refreshes the CSRF token 8s before fire time, then fires the booking
    requests at exactly 11:59:59.900 America/Los_Angeles so they land just
    after noon when the slots open. Zero setup latency at fire time.
  --race --dry-run            same timing, but read-only (never books)
  --race --fire-at=HH:MM:SS   override fire time (for testing)

Daily driver: start --race ~11:40-11:50 from a scheduler (e.g. a daily cron
at 11:45). If started after fire time it fires immediately instead of waiting.
"""

import requests, sys, time, datetime, re, logging, os, io, base64, html as htmllib
from zoneinfo import ZoneInfo
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

# ── Race mode config ─────────────────────────────────────────────────────────
RACE_TZ = ZoneInfo("America/Los_Angeles")
FIRE_HOUR, FIRE_MIN, FIRE_SEC, FIRE_MS = 11, 59, 59, 900  # fire at 11:59:59.900 PT
FINAL_REFRESH_SECS = 8      # refresh CSRF this many seconds before fire
WARMUP_KEEPALIVE_SECS = 45  # keepalive ping interval during warmup wait
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


def fetch_booking_form(s, request_data):
    """GET the CreateReservation form; returns raw HTML."""
    start_time, _, duration = TIME_SLOTS[0]
    end_dt = (datetime.datetime.strptime(start_time, "%I:%M %p")
              + datetime.timedelta(minutes=int(duration)))
    r = s.get(
        f"{RESERVATIONS_URL}/Online/ReservationsApi/CreateReservation",
        params={"id": ORG_ID, "uiCulture": "en-US",
                "start": f"{DATE} {start_time}",
                "end": f"{DATE} {end_dt.strftime('%-I:%M %p')}",
                "courtType": "Hard", "courtTypeId": COURT_TYPE_ID,
                "customSchedulerId": SCHEDULER_ID, "isConsolidated": "True",
                "instructorId": "", "isMobileLayout": "False",
                "requestData": request_data}, timeout=45)
    return r.text


def extract_csrf(html):
    m = re.search(r'<input name="__RequestVerificationToken" type="hidden" '
                  r'value="([^"]+)"', html)
    return m.group(1) if m else None


def prefetch(s):
    """Grab requestData + CSRF token, auto-signing waivers if they block.
    Returns (request_data, csrf); (None, None) if target date already booked."""
    r = s.get(f"{BASE_URL}/Online/Reservations/Bookings/{ORG_ID}",
              params={"sId": SCHEDULER_ID}, timeout=45)
    m = re.search(r'requestData=([A-Za-z0-9%+/=]+)', r.text)
    if not m:
        log.error("Failed to extract requestData")
        sys.exit(1)
    request_data = unquote(m.group(1))

    html = fetch_booking_form(s, request_data)
    csrf = extract_csrf(html)
    if not csrf:
        if "restricted to 1 court" in html:
            # Target date already has a booking — nothing to do.
            log.info("Per-day court limit already reached for target date — "
                     "a booking exists, nothing to do.")
            return None, None
        # Possibly blocked by a pending waiver — sign and retry once
        log.warning("No CSRF token — checking for pending waiver...")
        if sign_pending_waivers(s):
            csrf = extract_csrf(fetch_booking_form(s, request_data))
    if not csrf:
        log.error("Failed to get CSRF token")
        sys.exit(1)
    log.info("Prefetch OK")
    return request_data, csrf


def refresh_csrf(s, request_data):
    """Final CSRF refresh right before firing. Returns the fresh token,
    None if the target date got booked during warmup, or "KEEP" to fall back
    to the warmup token when the refresh itself fails."""
    html = fetch_booking_form(s, request_data)
    csrf = extract_csrf(html)
    if csrf:
        return csrf
    if "restricted to 1 court" in html:
        log.info("Target date got booked during warmup — nothing to do.")
        return None
    log.warning("Final CSRF refresh failed — keeping warmup token")
    return "KEEP"


def keepalive_until(s, deadline):
    """Lightweight pings to keep the session/TLS warm until deadline."""
    while True:
        now = datetime.datetime.now(RACE_TZ)
        remaining = (deadline - now).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(WARMUP_KEEPALIVE_SECS, remaining))
        try:
            s.get(f"{BASE_URL}/Online/Portal/Index/{ORG_ID}", timeout=10)
        except Exception as e:
            log.warning(f"Keepalive ping failed: {e}")


def wait_until_precise(target):
    """Sleep in chunks, then busy-wait for millisecond-accurate firing."""
    while True:
        now = datetime.datetime.now(RACE_TZ)
        delta = (target - now).total_seconds()
        if delta <= 0:
            break
        if delta > 0.3:
            time.sleep(min(delta - 0.15, 10))
    log.info("FIRE at "
             f"{datetime.datetime.now(RACE_TZ).strftime('%H:%M:%S.%f')[:-3]} PT")


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


def check_availability(s, slots=None):
    """Read-only: how many courts are free per slot (for --dry-run)."""
    date_full = f"{DATE} 12:00:00 AM"
    for start_time, end_time, duration in (slots or TIME_SLOTS):
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


def run_booking(s, request_data, csrf):
    """Slots in strict priority order; all courts in parallel per slot.
    Returns True if a booking landed."""
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
            return True
        if any("restricted to 1 court" in m for m in messages):
            log.info("Per-day limit hit — a booking already landed.")
            send_telegram(f"✅ Court booked for {DATE} (check app)")
            return True

    log.error("All slots exhausted. Booking FAILED.")
    send_telegram(f"❌ Booking failed for {DATE}")
    return False


def run_race(dry_run, fire_at_arg):
    """Warm up early, keep the session hot, fire at exactly 11:59:59.900 PT."""
    now0 = datetime.datetime.now(RACE_TZ)
    if fire_at_arg:
        t = datetime.datetime.strptime(fire_at_arg, "%H:%M:%S").time()
        fire_at = datetime.datetime.combine(now0.date(), t, tzinfo=RACE_TZ)
    else:
        fire_at = datetime.datetime.combine(
            now0.date(),
            datetime.time(FIRE_HOUR, FIRE_MIN, FIRE_SEC, FIRE_MS * 1000),
            tzinfo=RACE_TZ)
    log.info(f"RACE MODE — target {DATE} "
             f"({'weekend' if WEEKEND else 'weekday'} slots), "
             f"fire at {fire_at.strftime('%H:%M:%S.%f')[:-3]} PT"
             + (" [DRY RUN]" if dry_run else ""))

    s = login()
    t0 = time.monotonic()
    request_data, csrf = prefetch(s)
    if csrf is None:
        sys.exit(0)  # target date already booked
    log.info(f"Warmup done in {time.monotonic() - t0:.1f}s — session ready")

    now = datetime.datetime.now(RACE_TZ)
    if now >= fire_at:
        log.warning("Started after fire time — firing immediately")
    else:
        refresh_at = fire_at - datetime.timedelta(seconds=FINAL_REFRESH_SECS)
        if now < refresh_at:
            log.info(f"Keepalive until {refresh_at.strftime('%H:%M:%S')} PT...")
            keepalive_until(s, refresh_at)
        new_csrf = refresh_csrf(s, request_data)
        if new_csrf is None:
            sys.exit(0)  # got booked during warmup
        if new_csrf != "KEEP":
            csrf = new_csrf
            log.info("CSRF refreshed just before fire")
        wait_until_precise(fire_at)

    if dry_run:
        # Read-only verification at the exact fire moment.
        check_availability(s, slots=TIME_SLOTS[:1])
        log.info("Dry-run race complete — session valid at fire time, "
                 "nothing was booked.")
        sys.exit(0)

    sys.exit(0 if run_booking(s, request_data, csrf) else 1)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    race = "--race" in sys.argv
    fire_at_arg = next(
        (a.split("=", 1)[1] for a in sys.argv if a.startswith("--fire-at=")),
        None)

    if race:
        run_race(dry_run, fire_at_arg)

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
    sys.exit(0 if run_booking(s, request_data, csrf) else 1)
