#!/usr/bin/env python3
"""
CourtReserve Auto-Booking Script
Site: https://app.courtreserve.com/Online/Account/LogIn/13234

Cron (runs daily, books same weekday next week at noon sharp):
  59 11 * * * /opt/homebrew/bin/python3 /Users/yenchunc/Desktop/lifetime_autobook.py >> /tmp/lifetime_autobook.log 2>&1
"""

import requests, sys, time, datetime, random, re
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Configuration ────────────────────────────────────────────────────────────
EMAIL    = "shuaichiou@gmail.com"
PASSWORD = "e04xup6xl3g"
ORG_ID   = "13234"

# Target date: same weekday next week
TARGET_DATE = datetime.date.today() + datetime.timedelta(days=7)
DATE        = TARGET_DATE.strftime("%-m/%-d/%Y")

# Preferred time slots in priority order: (start, end, duration_minutes)
# All after 5PM, 90min minimum. Prefer 8PM (less competition, ends 9:30).
TIME_SLOTS = [
    ("8:00 PM", "9:30 PM", "90"),
    ("7:00 PM", "8:30 PM", "90"),
    ("6:00 PM", "7:30 PM", "90"),
    ("5:30 PM", "7:00 PM", "90"),
    ("5:00 PM", "6:30 PM", "90"),
]

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

BASE_URL         = "https://app.courtreserve.com"
RESERVATIONS_URL = "https://reservations.courtreserve.com"
# ─────────────────────────────────────────────────────────────────────────────


def login():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0", "Origin": BASE_URL})
    login_url = f"{BASE_URL}/Online/Account/LogIn/{ORG_ID}"
    s.get(login_url)
    s.post(login_url, data={"UserNameOrEmail": EMAIL, "Password": PASSWORD}, headers={"Referer": login_url})
    if ".AspNet.ApplicationCookie" not in s.cookies:
        print("Login FAILED"); sys.exit(1)
    print("Login OK")
    return s


def prefetch(s):
    """Before noon: grab the requestData auth token and CSRF token."""
    r = s.get(f"{BASE_URL}/Online/Reservations/Bookings/{ORG_ID}", params={"sId": SCHEDULER_ID})
    m = re.search(r'requestData=([A-Za-z0-9%+/=]+)', r.text)
    if not m:
        print("Failed to extract requestData"); sys.exit(1)
    request_data = unquote(m.group(1))

    start_time, _, duration = TIME_SLOTS[0]
    end_dt = datetime.datetime.strptime(start_time, "%I:%M %p") + datetime.timedelta(minutes=int(duration))
    r = s.get(f"{RESERVATIONS_URL}/Online/ReservationsApi/CreateReservation",
        params={"id": ORG_ID, "uiCulture": "en-US", "start": f"{DATE} {start_time}",
                "end": f"{DATE} {end_dt.strftime('%-I:%M %p')}", "courtType": "Hard",
                "courtTypeId": COURT_TYPE_ID, "customSchedulerId": SCHEDULER_ID,
                "isConsolidated": "True", "instructorId": "", "isMobileLayout": "False",
                "requestData": request_data})
    m = re.search(r'<input name="__RequestVerificationToken" type="hidden" value="([^"]+)"', r.text)
    if not m:
        print("Failed to get CSRF token"); sys.exit(1)
    print("Prefetch OK")
    return request_data, m.group(1)


def wait_until_noon(s):
    now  = datetime.datetime.now()
    noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    delta = (noon - now).total_seconds()
    if delta > 0:
        print(f"Waiting {delta:.1f}s until noon...")
        if delta > 15:
            time.sleep(delta - 15)
        # Keepalive: refresh session so it's not stale
        try:
            s.get(f"{BASE_URL}/Online/Portal/Index/{ORG_ID}", timeout=5)
            print("Session keepalive OK")
        except Exception:
            pass
        # Pre-warm TCP connection to reservations subdomain
        try:
            s.get(f"{RESERVATIONS_URL}/", timeout=5)
            print("TCP pre-warm OK")
        except Exception:
            pass
        # Busy-wait for exact noon
        while datetime.datetime.now() < noon:
            pass
    print(f"Firing at {datetime.datetime.now().strftime('%H:%M:%S.%f')}")


def get_available_courts(s, start_time, end_time, duration):
    """Debug helper: check which courts are open for a given slot."""
    date_full = f"{DATE} 12:00:00 AM"
    start_hms = datetime.datetime.strptime(start_time, "%I:%M %p").strftime("%H:%M:%S")
    r = s.get(f"{BASE_URL}/Online/AjaxController/GetAvailableCourtsMemberPortal/{ORG_ID}",
        params={"Date": date_full, "selectedDate": date_full, "StartTime": start_hms,
                "EndTime": end_time, "CourtTypesString": COURT_TYPE_ID, "timeZone": TIMEZONE,
                "customSchedulerId": SCHEDULER_ID, "instructorId": "", "Duration": duration,
                "AllowPastReservationsUpToXMinutes": "", "ResourceId": "", "CourtIdsString": "",
                "ReservationQueueSlotId": "", "uiCulture": "en-US"},
        headers={"X-Requested-With": "XMLHttpRequest"})
    return r.json()


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
        headers={"Referer": f"{BASE_URL}/", "Content-Type": "application/x-www-form-urlencoded"})
    return r.json()


if __name__ == "__main__":
    print(f"Target date: {DATE}")
    s = login()
    request_data, csrf = prefetch(s)
    wait_until_noon(s)

    slots = TIME_SLOTS[:]
    random.shuffle(slots)
    for start_time, end_time, duration in slots:
        court_items = list(COURT_IDS.items())
        random.shuffle(court_items)
        print(f"Trying {start_time}–{end_time}: {[n for n, _ in court_items]}")

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(book, s, court_id, start_time, duration, csrf, request_data): court_name
                for court_name, court_id in court_items
            }
            for future in as_completed(futures):
                court_name = futures[future]
                result = future.result()
                if result.get("isValid"):
                    print(f"Booking SUCCESS: {court_name} {start_time}–{end_time}")
                    sys.exit(0)
                print(f"  {court_name} failed: {result.get('message')} — trying next...")

    print("All slots and courts exhausted. Booking FAILED.")
