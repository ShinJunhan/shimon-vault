"""
app/services/notify_service.py

Notification helper for the FastAPI app layer.
Sends to both Slack and Telegram simultaneously.
A failed notification never crashes the calling request handler.

This is the app-side equivalent of lambda/shared/notification.py.
They are separate files because Lambda and the app run in different
environments with different import paths.

CHANGE (admin/demo console):
  notify_all() now RETURNS a per-channel delivery status dict so the
  web app can show a truthful toast ("Slack delivered, Telegram delivered").
  It still never raises — existing callers that ignore the return value
  (e.g. auth_router credential-stuffing alerts) keep working unchanged.
"""

import json
import os
import urllib.request


def notify_slack(message: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        raise ValueError("SLACK_WEBHOOK_URL not set")
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"Slack returned {resp.status}")


def notify_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Telegram returned {resp.status}")


def notify_all(message: str) -> dict:
    """
    Send to all notification channels. Never fail silently, never raise.

    Returns a status dict the web app can turn into a toast:
        {
          "slack":    {"ok": True,  "error": None},
          "telegram": {"ok": False, "error": "Telegram returned 401"},
          "all_ok": False,
        }
    """
    status = {
        "slack": {"ok": False, "error": None},
        "telegram": {"ok": False, "error": None},
    }

    try:
        notify_slack(message)
        status["slack"]["ok"] = True
    except Exception as exc:
        status["slack"]["error"] = str(exc)
        print(f"[notify_all] Slack error: {exc}")

    try:
        notify_telegram(message)
        status["telegram"]["ok"] = True
    except Exception as exc:
        status["telegram"]["error"] = str(exc)
        print(f"[notify_all] Telegram error: {exc}")

    status["all_ok"] = status["slack"]["ok"] and status["telegram"]["ok"]
    if not status["all_ok"]:
        # Log but do NOT raise — a failed notification must never
        # crash a user-facing request or a Lambda function
        print(f"[notify_all] Non-fatal notification errors: {status}")

    return status
