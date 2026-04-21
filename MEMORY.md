# MEMORY.md - Long-Term Memory

## About Shuai
- Full name: Yen-Chun Chiu, goes by Shuai Chiou
- Email: shuaichiou@gmail.com
- Timezone: America/Los_Angeles (Pacific)
- Focus: AI workflow setup, US stock trading, credit card optimization

## Setup State (as of 2026-04-21) ✅ COMPLETE

**SINGLE WORKSPACE:**
- Location: `/mnt/c/Users/User/Desktop/AI_workspace` (Windows WSL path)
- Remote: `https://github.com/noname8135/AI_workspace.git` (private repo)
- Status: ✅ Synced and backed up
- OpenClaw local: `/home/noname8135/.openclaw/workspace` (reference only, don't use)

**Agents:**
- Main agent: `agent:main` → default Telegram bot + webchat
- Trading agent: `agent:trading` → @ShuaiChiouTradingBot (created, not yet paired/tested)

**Integrations:**
- Notion: connected (no pages shared)
- Google Drive: not set up
- GitHub: configured with token
- Telegram: @cronjobChannel (-1003889752528) for notifications

## Lifetime Automation ✅ WORKING
- **Auto-booking** at 11:59 AM daily (books next week, same weekday)
- **Daily reminder** at 9 AM (only texts if court booked, silent if not)
- **Cancellation** script ready (one command: `python3 lifetime_cancel.py <id>`)
- **Tested:** Both booking and cancellation working perfectly
- **Logs:** `logs/lifetime_*.log` in workspace

## Preferences
- Prefers concise, low-noise responses
- Wants me to proactively write important things to *.md files
- Doesn't want too much filler/fluff
- **Single workspace:** Only work in `/mnt/c/Users/User/Desktop/AI_workspace`, don't create duplicates

## TODO
- [ ] Pair and test @ShuaiChiouTradingBot
- [ ] Share Notion top-level page with integration
- [ ] Set up morning trading briefing cron
- [x] GitHub access & initial setup
- [x] Lifetime court automation (fully working)
- [x] Credential separation (.env, .gitignore)
