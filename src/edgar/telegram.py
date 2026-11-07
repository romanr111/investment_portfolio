"""Telegram digest delivery helper.

Never raises: every failure mode returns (ok, detail) so a Telegram outage
cannot break a run whose state is already committed. Absent credentials are
a clean "not configured" skip decided by the caller.
"""
import logging

from requests import exceptions as requests_exceptions

logger = logging.getLogger(__name__)

TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_CHARS = 4096
DEFAULT_TIMEOUT_SECONDS = 10


def truncate_for_telegram(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = text or ""
    return text[:limit]


def send(session, token, chat_id, text, timeout_s=DEFAULT_TIMEOUT_SECONDS):
    """POST sendMessage; returns (ok, detail)."""
    if not token or not chat_id:
        return False, "telegram not configured"
    url = TELEGRAM_SEND_URL.format(token=token)
    payload = {"chat_id": chat_id, "text": truncate_for_telegram(text)}
    try:
        response = session.post(url, data=payload, timeout=timeout_s)
    except requests_exceptions.RequestException as exc:
        return False, f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # any other transport failure: never raise
        return False, f"{type(exc).__name__}: {exc}"
    try:
        payload_json = response.json()
        body_ok = bool(payload_json.get("ok"))
        description = str(payload_json.get("description") or "")[:200]
    except ValueError:
        body_ok = False
        description = ""
    if response.status_code == 200 and body_ok:
        return True, "ok"
    detail = description or f"HTTP {response.status_code}"
    logger.debug("telegram send failed: %s", detail)
    return False, detail
