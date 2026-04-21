# Credentials Setup

To use the Lifetime automation scripts safely, follow this guide.

## Option 1: Environment Variables (Recommended)

### Create `.env` file in workspace root

```bash
cd /home/noname8135/.openclaw/workspace
cp .env.example .env
nano .env
```

Edit `.env` with your real credentials:
```
LIFETIME_EMAIL=your-email@example.com
LIFETIME_PASSWORD=your-password
LIFETIME_ORG_ID=13234
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHANNEL_ID=-1003889752528
```

### Load in scripts

Scripts already check for env vars before using hardcoded defaults:
```python
EMAIL = os.getenv("LIFETIME_EMAIL", "shuaichiou@gmail.com")
PASSWORD = os.getenv("LIFETIME_PASSWORD", "e04xup6xl3g")
```

### Before committing to GitHub

```bash
# .gitignore already excludes .env, but double-check:
cat .gitignore | grep "\.env"

# Verify .env won't be committed:
git status | grep .env
```

---

## Option 2: Hardcoded (Current Setup)

Credentials are currently hardcoded in scripts. **This works but isn't safe for public repos.**

To migrate later:
1. Edit each script
2. Replace hardcoded strings with `os.getenv("VAR_NAME", "default")`
3. Create `.env` with real values
4. Test with `python3 script.py`

---

## Files

- `.env.example` — Template (safe to commit, shows all vars needed)
- `.env` — Actual credentials (⚠️ gitignore'd, never commit)
- `scripts/*.py` — Read from env vars (with fallback defaults)

---

## Security

✅ `.env` is in `.gitignore` — won't be accidentally committed
✅ `.env.example` shows what's needed — good for documentation
✅ Fallback hardcoded values work if `.env` missing
✅ Safe to make repo public later (just remove hardcoded creds)

---

## Testing

After setting up `.env`:

```bash
# Test booking script reads env vars
python3 scripts/lifetime_autobook.py

# Check which values were loaded (prints in logs):
tail -20 logs/lifetime_autobook.log
```

If you see `"Login OK"` — credentials are working! ✅
