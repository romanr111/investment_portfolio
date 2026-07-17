"""Send Telegram notification when snapshot fetch completes or fails."""

import os
import sys

import requests


def notify() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set; skipping notification")
        return 0

    status = os.getenv("JOB_STATUS", "unknown")
    url = os.getenv("GITHUB_RUN_URL", "")

    if status == "success":
        text = f"✅ IB Flex snapshot fetched and stored as artifact.\n{url}"
    else:
        text = f"❌ IB Flex snapshot fetch failed (status: {status}).\n{url}"

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if not resp.ok:
            print(f"Telegram API error: {resp.status_code} {resp.text}", file=sys.stderr)
            return 1
    except requests.RequestException as exc:
        print(f"Telegram notification failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(notify())