#!/usr/bin/env python3
"""
CourtReserve morning check: list today's reservations.

Usage: python3 lifetime_check_today.py
Output (stdout), one line per booking:
  BOOKING id=<id> court="<court>" date=<M/D/YYYY> time="<start> - <end>"
Or, when nothing is booked today:
  NO_BOOKINGS_TODAY <YYYY-MM-DD>

Exit code 0 on success (even with no bookings), 1 on failure.
Read-only: never books or cancels anything.
"""
import requests, sys, os, re, json, datetime
from zoneinfo import ZoneInfo

EMAIL    = os.getenv("LIFETIME_EMAIL", "shuaichiou@gmail.com")
PASSWORD = os.getenv("LIFETIME_PASSWORD", "e04xup6xl3g")
ORG_ID   = os.getenv("LIFETIME_ORG_ID", "13234")

BASE_URL = "https://app.courtreserve.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0"
TZ = ZoneInfo("America/Los_Angeles")


def login():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Origin": BASE_URL,
                      "X-Requested-With": "XMLHttpRequest"})
    login_url = f"{BASE_URL}/Online/Account/LogIn/{ORG_ID}"
    s.post(login_url, data={"UserNameOrEmail": EMAIL, "Password": PASSWORD},
           headers={"Referer": login_url}, timeout=45)
    if ".AspNet.ApplicationCookie" not in s.cookies:
        print("LOGIN_FAILED", file=sys.stderr)
        sys.exit(1)
    return s


def parse_ms_date(v):
    """'/Date(1791123975068)/' -> date in TZ; None if unparseable."""
    m = re.search(r'/Date\((\d+)\)/', str(v or ""))
    if not m:
        return None
    return datetime.datetime.fromtimestamp(int(m.group(1)) / 1000, TZ).date()


def main():
    today = datetime.datetime.now(TZ).date()
    s = login()
    r = s.get(f"{BASE_URL}/Online/MyProfile/GetMyUpcomingReservations/{ORG_ID}",
              timeout=45)
    r.raise_for_status()
    data = r.json().get("Data") or []

    found = 0
    for res in data:
        # Prefer the /Date(ms)/ field; fall back to DateDisplay "M/D/YYYY".
        d = parse_ms_date(res.get("Start"))
        if d is None:
            try:
                d = datetime.datetime.strptime(res.get("DateDisplay", ""),
                                               "%m/%d/%Y").date()
            except Exception:
                continue
        if d != today:
            continue
        found += 1
        rid = res.get("Id", "?")
        court = (res.get("CourtsDisplay") or "").strip() or "?"
        # CourtsDisplay may be HTML-ish; strip tags.
        court = re.sub(r"<[^>]+>", "", court).strip() or "?"
        time_display = (res.get("TimeDisplay") or "").strip() or "?"
        date_display = (res.get("DateDisplay") or "").strip()
        print(f'BOOKING id={rid} court="{court}" date={date_display} '
              f'time="{time_display}"')

    if not found:
        print(f"NO_BOOKINGS_TODAY {today.isoformat()}")


if __name__ == "__main__":
    main()
