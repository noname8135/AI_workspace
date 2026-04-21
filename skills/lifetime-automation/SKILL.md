# Lifetime Court Booking Automation

Automate tennis court reservations at Lifetime Fitness via CourtReserve.

## Overview

Three automated scripts manage your court bookings:
1. **Auto-Book** — Books court for next week, same weekday, at noon sharp
2. **Daily Reminder** — Texts you at 9 AM if court is booked (silent if not)
3. **Cancel** — Cancels reservations on demand with one command

All scripts send notifications to a Telegram channel (`@cronjobChannel`).

## Setup

### Prerequisites
- OpenClaw environment
- Telegram bot token + channel ID
- Lifetime Fitness account (username/password)
- Organization ID (usually from URL: `app.courtreserve.com/.../13234`)

### Credentials

Edit scripts to set:
```python
EMAIL    = "your-email@example.com"
PASSWORD = "your-password"
ORG_ID   = "13234"
```

Edit Telegram config:
```python
TELEGRAM_BOT_TOKEN = "your-bot-token"
TELEGRAM_CHANNEL_ID = "-1003889752528"
```

## Scripts

### 1. Auto-Booking (`lifetime_autobook.py`)

**What it does:**
- Logs in to Lifetime
- Waits until exactly noon
- Books court for the same weekday next week
- Tries time slots in order (8 PM preferred, then 7 PM, etc.)
- Tries courts in random order (spreads load)
- Sends result to Telegram

**Run time:** 11:59 AM daily (cron)

**How it books:**
1. Login via POST to `/Online/Account/LogIn/{ORG_ID}`
2. Prefetch auth tokens (requestData + CSRF)
3. Wait until noon
4. Parallel POST to `/Online/ReservationsApi/CreateReservation`
5. Try each time slot/court combo until success

**Result:**
- ✅ `✅ Court 1 5:00 PM–6:30 PM`
- ❌ `❌ Booking failed - all slots full`

**Logs:** `/home/noname8135/.openclaw/workspace/logs/lifetime_autobook.log`

---

### 2. Daily Checker (`lifetime_checker.py`)

**What it does:**
- Logs in to Lifetime
- Checks if you have a court booked TODAY
- Only sends message if court is booked (no noise)
- Reads from your member portal

**Run time:** 9:00 AM daily (cron)

**Result:**
- 📌 `📌 Court booked today: Court 1, 5:00 PM–6:30 PM` (if booked)
- (silence) if not booked

**Logs:** `/home/noname8135/.openclaw/workspace/logs/lifetime_checker.log`

---

### 3. Cancellation (`lifetime_cancel.py`)

**What it does:**
- Logs in to Lifetime
- Fetches reservation details via GET
- Submits cancellation form via POST
- Fills in reason: "Not needed anymore"
- Sends confirmation to Telegram

**Run manually when needed:**
```bash
python3 /home/noname8135/.openclaw/workspace/scripts/lifetime_cancel.py <reservation_id>
```

**How to get reservation ID:**
1. Go to Lifetime bookings
2. Click "Cancel" on a reservation
3. Copy the ID from the URL: `...?reservationId=52458474`
4. Use that ID in the command

**Flow:**
1. GET `/Online/MyProfile/CancelReservation/{ORG_ID}?reservationId={id}`
2. Extract all form fields (auto-populated)
3. Add reason: `SelectedReservation.CancellationReason=Not needed anymore`
4. POST to `/Online/MyProfile/CancelReservation/{ORG_ID}`
5. Returns `{"isValid":true}` on success

**Result:**
- ✅ `✅ Cancelled reservation 52458474`
- ❌ `❌ Failed to cancel reservation 52458474`

**Logs:** `/home/noname8135/.openclaw/workspace/logs/lifetime_cancel.log`

---

## Cron Setup

### View current jobs
```bash
openclaw cron list
```

### Add jobs (if not already set up)
```bash
# Auto-booking at 11:59 AM daily
openclaw cron add --name "lifetime-booking" --cron "59 11 * * *" \
  --message "python /home/noname8135/.openclaw/workspace/scripts/lifetime_autobook.py" \
  --agent main

# Daily reminder at 9 AM
openclaw cron add --name "lifetime-daily-checker" --cron "0 9 * * *" \
  --message "python /home/noname8135/.openclaw/workspace/scripts/lifetime_checker.py" \
  --agent main
```

## Telegram Notifications

### Channel Setup
- Channel: `@cronjobChannel`
- Bot: `@ShuaiChiouCronjobBot`
- Channel ID: `-1003889752528`

### Message Format
- **Auto-booking success:** `✅ Court 1 5:00 PM–6:30 PM`
- **Auto-booking failure:** `❌ Booking failed - all slots full`
- **Daily reminder (booked):** `📌 Court booked today: Court 1, 5:00 PM–6:30 PM`
- **Cancellation success:** `✅ Cancelled reservation 52458474`

## API Endpoints Used

### Login
```
POST /Online/Account/LogIn/{ORG_ID}
  Body: UserNameOrEmail, Password
```

### Booking (Prefetch)
```
GET /Online/Reservations/Bookings/{ORG_ID}?sId=16995
  → Extract: requestData (auth token), __RequestVerificationToken (CSRF)
```

### Booking (Reserve)
```
POST /Online/ReservationsApi/CreateReservation/{ORG_ID}
  Body: Date, StartTime, Duration, CourtId, MemberId, CSRF token, etc.
  Response: {"isValid": true/false, "message": "..."}
```

### Check Reservations
```
GET /Online/Portal/Index/{ORG_ID}
  → Parse HTML/JS for reservation details
```

### Cancel (Get Form)
```
GET /Online/MyProfile/CancelReservation/{ORG_ID}?reservationId={id}
  → Extract form fields (auto-populated from DB)
```

### Cancel (Submit)
```
POST /Online/MyProfile/CancelReservation/{ORG_ID}
  Body: SelectedReservation.*, CancellationReason, etc.
  Response: {"isValid": true}
```

## Troubleshooting

### Booking failed: "All slots exhausted"
- All preferred time slots are full
- Check Lifetime portal for available times
- Adjust `TIME_SLOTS` in script if needed

### Booking didn't run
- Check logs: `/home/noname8135/.openclaw/workspace/logs/lifetime_autobook.log`
- Verify cron is active: `openclaw cron list`
- Check login credentials (case-sensitive)

### Checker not sending messages
- It's designed to be silent if no court is booked (feature, not bug)
- Check logs to confirm it ran: `cat lifetime_checker.log`

### Cancel failed: "No reservation found"
- Wrong reservation ID
- Reservation already cancelled
- Network error — check logs

### Telegram notifications not arriving
- Verify bot is admin in channel
- Check bot token is correct
- Verify channel ID is correct

## Time Slots & Courts

### Preferred Times (in order)
1. 8:00 PM – 9:30 PM (90 min)
2. 7:00 PM – 8:30 PM (90 min)
3. 6:00 PM – 7:30 PM (90 min)
4. 5:30 PM – 7:00 PM (90 min)
5. 5:00 PM – 6:30 PM (90 min)

### Courts
- Court 1, 2, 3, 4, 6, 7, 8 (Court 5 skipped)

### Booking Logic
- Books 7 days ahead (same weekday next week)
- Tries courts in random order
- Parallel attempts (4 workers)
- Exits on first success

## Configuration

### File Structure
```
~/.openclaw/workspace/
├── scripts/
│   ├── lifetime_autobook.py
│   ├── lifetime_checker.py
│   └── lifetime_cancel.py
├── logs/
│   ├── lifetime_autobook.log
│   ├── lifetime_checker.log
│   └── lifetime_cancel.log
└── CRONTASKS.md
```

### Environment Variables (optional)
Can hardcode in scripts or use env vars:
```bash
export LIFETIME_EMAIL="your-email@example.com"
export LIFETIME_PASSWORD="your-password"
export LIFETIME_ORG_ID="13234"
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHANNEL_ID="..."
```

## Testing

### Test auto-booking manually
```bash
python3 /home/noname8135/.openclaw/workspace/scripts/lifetime_autobook.py
```
(Will wait until noon, then book)

### Test checker
```bash
python3 /home/noname8135/.openclaw/workspace/scripts/lifetime_checker.py
```

### Test cancellation
```bash
python3 /home/noname8135/.openclaw/workspace/scripts/lifetime_cancel.py 52458474
```
(Replace with real reservation ID)

## Notes

- **Why 11:59 AM?** CourtReserve opens bookings at exactly noon. Script waits until then, then fires immediately.
- **Why 7 days?** You can only book a week in advance at Lifetime.
- **Why silent checker?** Reduces notification noise. Only alerts when you have something to do (cancel).
- **Why manual cancel?** CourtReserve's JS-heavy portal makes automated detection hard. One-command manual cancel is simpler & safer.

## References

- Lifetime Fitness: https://www.lifetimeactivities.com/
- CourtReserve: https://app.courtreserve.com
- Telegram Bot API: https://core.telegram.org/bots/api

---

**Last tested:** April 20, 2026
**Status:** ✅ All three scripts working
