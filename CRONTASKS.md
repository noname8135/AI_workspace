# Cron Tasks

Tracking all scheduled jobs for OpenClaw.

## Active Jobs

| Task Name | Schedule | Agent | Purpose | Status |
|-----------|----------|-------|---------|--------|
| lifetime-booking | 11:59 AM daily | main | Book tennis court for next week | ✅ Active |
| lifetime-daily-checker | 9:00 AM daily | main | Check if court booked today, remind to cancel if needed | ✅ Active |

## Rules
- **Minimize noise:** Only report when actionable (e.g., court is booked, not when nothing happens)
- **Telegram channel:** @cronjobChannel (-1003889752528)

## Cancellation ✅ TESTED & WORKING

**Script:** `python3 ~/scripts/lifetime_cancel.py <reservation_id>`

**Example:**
```bash
python3 /home/noname8135/.openclaw/workspace/scripts/lifetime_cancel.py 52458474
```

**How it works:**
1. Logs into Lifetime
2. Fetches reservation form via GET
3. Extracts all form fields automatically
4. POSTs cancellation with reason: "Not needed anymore"
5. Returns `{"isValid":true}` on success
6. Sends Telegram confirmation

**To get reservation ID:** Check your Lifetime bookings list, click cancel on a reservation, and grab the ID from the URL or form.

**Tested:** ✅ Successfully cancelled Wed 4/22 5:00 PM court

## Planned Jobs

| Task Name | Schedule | Agent | Purpose | Notes |
|-----------|----------|-------|---------|-------|
| Morning Trading Briefing | 9:00 AM daily | trading | Market summary & signals | TBD |

## How to Add

1. Decide: **name**, **schedule** (cron), **agent**, **purpose**
2. Edit `~/.openclaw/config.yaml` under `cron.jobs`
3. Update this file to track it
4. Test with `openclaw cron list`

## Cron Schedule Reference

- `0 9 * * *` → 9:00 AM every day
- `0 9 * * 1-5` → 9:00 AM Mon-Fri
- `0 */4 * * *` → every 4 hours
- `30 18 * * *` → 6:30 PM every day
