# Lifetime Court Booking Automation

Automate tennis court reservations at Lifetime Fitness (Santa Clara, org id
`13234`) via CourtReserve. One script: `lifetime_autobook.py`.

> Superseded a prior 6-script / 3-script layout (`scripts/`,
> `lifetime_cancel.py`, `lifetime_check_today.py`, `lifetime_check_target.py`)
> on 2026-10-11 — all functionality consolidated into one file as flags, the
> duplicates deleted. See `CLAUDE.md` at the repo root for full architecture
> notes, environment gotchas, and operational preferences; this file is the
> quick-reference for day-to-day use.

## Environment

Run everything with the zoneinfo shim on the path (Python 3.8 container, no
stdlib `zoneinfo`):
```bash
cd /home/yenchunc/AI_workspace
PYTHONPATH=/home/yenchunc/.shim python3 lifetime_autobook.py <flags>
```

Credentials/config are env-var overridable (see `lifetime_autobook.py`'s
module docstring and config section for the full list) — defaults are
hardcoded for this account, so usually no env vars are needed.

## Modes

### `--race` — daily competitive booking (production)

Books `today+7` (the club's actual booking-window edge), firing at exactly
11:59:59.900 America/Los_Angeles so the request lands the instant the
window opens. Warms up early (login + prefetch), keepalive-pings, refreshes
CSRF 8s before fire.

Deployed via crontab: `40 18 * * *` (fixed UTC, **not** `CRON_TZ` — see
gotcha below). 18:40 UTC covers both 11:40 AM PDT and 10:40 AM PST, so it
always starts well before noon PT regardless of DST; the script's own
`ZoneInfo`-based wait handles the DST-correct fire time internally.

### `--scan` — cancellation watcher, 2-7 days out

One **long-lived background process** (not cron-spawned per cycle) that
logs in once, then polls every `--scan-interval` seconds (default 60) for
a preferred slot opening up on any date `--scan-min-days`..`--scan-max-days`
out (default 2-7). Cheap read-only checks every cycle; a real booking
attempt only fires when a scan finds an actual opening.

Run via `nohup ... &`; a `@reboot` cron entry relaunches it if the
container restarts. **Restart manually after any code change** — it holds
the old module in memory:
```bash
pkill -f "python3 lifetime_autobook.py --scan"
cd /home/yenchunc/AI_workspace && PYTHONPATH=/home/yenchunc/.shim \
  nohup python3 lifetime_autobook.py --scan >> scan.log 2>&1 < /dev/null &
disown
```

### `--cancel=<id> [--reason="..."]`

Cancels a reservation by id. Get the id from `--list` (below) rather than
digging through the app's URLs.

### `--list[=YYYY-MM-DD]`

Read-only: lists your bookings for a date (default today). Never
books/cancels. This is also the reliable way to find a reservation's id —
no need to brute-force it.

### `--dry-run` / `--days-ahead=N`

`--dry-run` does login + availability check only, safe to run anytime.
`--days-ahead=N` overrides the target date for testing against a date
already inside the booking window — **never** change the `today+7` default
itself; that's the real competitive window the daily `--race` run needs.

## Known gotchas (this container, `build-yenchunc-focal-20261005` on gp-014)

- **`CRON_TZ` is silently broken** in this container's cron
  (`3.0pl1-136ubuntu1`) — confirmed empirically 2026-10-10 (two cron entries
  targeting the identical real-world instant, one plain-UTC one via
  `CRON_TZ`; only the UTC one fired). Don't use it.
- **Telegram is network-blocked** — `api.telegram.org` is MITM-intercepted
  by a content filter on this network (`issuer=O=NetAlerts`). Notifications
  go out via email through the internal `smtp.nvidia.com:25` relay instead
  (no auth needed).
- Python 3.8 needs the `zoneinfo` shim (`PYTHONPATH=~/.shim`, backed by
  `backports.zoneinfo`) and `ThreadPoolExecutor.shutdown(wait=False)` (not
  `cancel_futures=True`, which is 3.9+ only).

## CourtReserve API notes

- `app.courtreserve.com` — session-cookie auth (login, availability,
  cancel, `GetMyUpcomingReservations`).
- `reservations.courtreserve.com` — the actual `CreateReservation` POST,
  authenticated via a signed `requestData` token scraped from the booking
  page HTML, not cookies.
- `api4.courtreserve.com` (React "My Bookings" SPA) — dead end, auth isn't
  derivable from the main session cookies.
- Reservation ids are a sparse, platform-wide counter, not per-org/sequential.
- Club policy: 1 court per member per day; booking window opens exactly 7
  days out "to midnight".

## References

- CourtReserve: https://app.courtreserve.com
- Lifetime Fitness: https://www.lifetimeactivities.com/

**Last verified:** 2026-10-11 (live book → cancel round trip, `--scan` live
in production, email notifications confirmed delivered).
