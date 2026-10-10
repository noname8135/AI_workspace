# CLAUDE.md

Project instructions for Claude Code when working in this repo.

## What this repo is

CourtReserve auto-booking automation for Life Time Santa Clara (org id
`13234`), running from the `build-yenchunc-focal-20261005` LXC container on
Drive Farm host `gp-014`. Single script: `lifetime_autobook.py`.

## CourtReserve architecture (reverse-engineered, no official API/docs)

- `app.courtreserve.com` — main MVC app, session-cookie authenticated
  (`.AspNet.ApplicationCookie`, `ASP.NET_SessionId`). Login, availability
  checks, cancel flow all live here.
- `reservations.courtreserve.com` — separate subdomain for the actual
  `CreateReservation` POST. Authenticated via a signed `requestData` token
  scraped out of the booking page HTML, **not** cookies.
- `api4.courtreserve.com` — backs the React "My Bookings" SPA
  (`/Online/Bookings/List/{orgId}`). Auth mechanism is not derivable from the
  `app.courtreserve.com` session cookies — dead end, don't go back down this
  path to try to list/enumerate reservations.
- To cancel a reservation you need its numeric id. Flow:
  `GET /Online/MyProfile/CancelReservation/{orgId}?reservationId={id}` (harvest
  hidden form fields) → `POST` same URL with those fields + a
  `SelectedReservation.CancellationReason` (required). Returns
  `{"isValid":true}` on success. "not the owner" covers both a true
  ownership mismatch **and** an already-cancelled reservation — don't assume
  the former without checking.
- Reservation IDs are a sparse, platform-wide (not per-org) counter — not
  derivable by narrow brute force around a timestamp; need a wide window
  (~50-100 ids) if one is lost.
- Club policy: booking window opens exactly 7 days out "to midnight" (any
  slot on day-7 afternoon/evening gets rejected until the window actually
  opens), and is restricted to 1 court per member per day.

## Known environment gotchas (this container specifically)

- **Python 3.8 (focal)** — no stdlib `zoneinfo`. Fixed via
  `pip3 install --user backports.zoneinfo` + a shim at `~/.shim/zoneinfo.py`
  (`from backports.zoneinfo import ZoneInfo`). Every invocation needs
  `PYTHONPATH=~/.shim`.
- `ThreadPoolExecutor.shutdown(cancel_futures=True)` is 3.9+ only — use
  `shutdown(wait=False)` instead.
- **`CRON_TZ` is silently broken in this container's cron** (`cron
  3.0pl1-136ubuntu1`) — confirmed empirically 2026-10-10 by scheduling two
  entries for the identical real-world instant, one plain-UTC, one via
  `CRON_TZ=America/Los_Angeles`: only the UTC one fired. **Do not rely on
  `CRON_TZ`** for anything time-critical here. Workaround used: pin cron to
  a fixed UTC time early enough to cover both PDT and PST, and let the
  script itself compute the DST-correct fire time internally via
  `ZoneInfo("America/Los_Angeles")`.
- **Telegram is network-blocked** — `api.telegram.org` is MITM-intercepted
  by a content filter (`issuer=O=NetAlerts, CN=NetAlerts Services`, 24h
  cert validity) on this network. Don't try to "fix" this by trusting that
  CA — it's a deliberate block, not a cert hygiene issue. Notifications use
  email instead, via the internal `smtp.nvidia.com:25` relay (no auth
  needed, verified working).

## Script usage

```
python3 lifetime_autobook.py --race                        # daily competitive booking (today+7, fires 11:59:59.9 PT)
python3 lifetime_autobook.py --scan                         # persistent cancellation watcher, 2-7 days out
python3 lifetime_autobook.py --cancel=<id> [--reason="..."] # cancel a reservation
python3 lifetime_autobook.py --dry-run                      # read-only availability check, safe anytime
python3 lifetime_autobook.py --days-ahead=N                 # override target date for testing
```

Always run with `PYTHONPATH=/home/yenchunc/.shim` (see zoneinfo shim above).

### `--race` (production daily booking)

Warms up (login + prefetch), keepalive-pings the session, refreshes CSRF
8s before fire, then books at exactly 11:59:59.900 America/Los_Angeles.
Deployed via crontab: `40 18 * * *` (18:40 UTC — covers 11:40 AM PDT /
10:40 AM PST, always starts before noon PT regardless of DST; the UTC time
itself is intentionally not DST-adjusted — see CRON_TZ gotcha above).

### `--scan` (cancellation watcher)

One **long-lived process**, not re-spawned per cycle — logs in once, loops
every `--scan-interval` seconds (default 60) doing cheap read-only
availability checks across `--scan-min-days`..`--scan-max-days` (default
2-7) days out. Only fires a real (parallel-court POST) booking attempt when
a scan finds an actual opening, to keep steady-state request volume low and
avoid bot-detection risk. Run via `nohup ... &`, not cron — a fresh login
every single cycle at high frequency is unnecessary load. Restart manually
after any code change (`pkill -f "lifetime_autobook.py --scan"` then
relaunch) since it holds the old module code in memory. A `@reboot` cron
entry relaunches it if the container restarts.

## Operational preferences

- **Keep it to one script, no `_v2` suffix, no separate helper scripts** —
  cancel, scan, race, dry-run are all flags on `lifetime_autobook.py`, not
  separate files. Delete scratch/probe scripts after use.
- **Confirm before pushing** — commit locally, stop, let the user push.
- **Test with real live actions, then clean up** — e.g. book a real test
  court, verify, cancel it — don't assume a code path works from reading it.
- **Direct findings, no padding** — state what was verified, not what might
  be true; call out explicitly when something is a genuine policy/platform
  constraint vs. a script bug.
- Target date offset for the competitive daily run must stay `today+7` by
  default — never change that default casually; only override via
  `--days-ahead`/`LIFETIME_DAYS_AHEAD` for testing.
