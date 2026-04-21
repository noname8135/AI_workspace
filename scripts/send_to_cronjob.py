#!/usr/bin/env python3
"""Helper to send messages to @cronjobChannel"""
import requests
import sys

TELEGRAM_BOT_TOKEN = "8658174912:AAHsYOaCNcET2ULNAfBlB6Z2A3snqRg1l4k"
TELEGRAM_CHANNEL_ID = "-1003889752528"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

def send(message):
    """Send message to @cronjobChannel"""
    try:
        r = requests.post(
            TELEGRAM_API,
            data={
                "chat_id": TELEGRAM_CHANNEL_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=5
        )
        return r.status_code == 200
    except Exception as e:
        print(f"Error sending: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
        success = send(msg)
        sys.exit(0 if success else 1)
