#!/usr/bin/env python3
"""
Check whether a target date has any CourtReserve booking (read-only).

Usage: python3 lifetime_check_target.py [YYYY-MM-DD]
  Default date: today + 7 days (the auto-booker's target), America/Los_Angeles.

Output (stdout), one line per booking:
  BOOKING id=<id> court="<court>" date=<M/D/YYYY> time="<time display>"
Or:
  NO_BOOKING_FOR <YYYY-MM-DD>

Exit code 0 on success, 1 on failure. Never books or cancels.
"""
import requests, sys, os, re, datetime
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
    m = re.search(r'/Date\((\d+)\)/', str(v or ""))
    if not m:
        return None
    return datetime.datetime.fromtimestamp(int(m.group(1)) / 1000, TZ).date()


def main():
    if len(sys.argv) > 1:
        target = datetime.date.fromisoformat(sys.argv[1])
    else:
        target = datetime.datetime.now(TZ).date() + datetime.timedelta(days=7)

    s = login()
    r = s.get(f"{BASE_URL}/Online/MyProfile/GetMyUpcomingReservations/{ORG_ID}",
              timeout=45)
    r.raise_for_status()
    data = r.json().get("Data") or []

    found = 0
    for res in data:
        d = parse_ms_date(res.get("Start"))
        if d is None:
            try:
                d = datetime.datetime.strptime(res.get("DateDisplay", ""),
                                               "%m/%d/%Y").date()
            except Exception:
                continue
        if d != target:
            continue
        found += 1
        rid = res.get("Id", "?")
        court = re.sub(r"<[^>]+>", "", str(res.get("CourtsDisplay") or "")).strip() or "?"
        time_display = (res.get("TimeDisplay") or "").strip() or "?"
        date_display = (res.get("DateDisplay") or "").strip()
        print(f'BOOKING id={rid} court="{court}" date={date_display} '
              f'time="{time_display}"')

    if not found:
        print(f"NO_BOOKING_FOR {target.isoformat()}")


if __name__ == "__main__":
    main()
