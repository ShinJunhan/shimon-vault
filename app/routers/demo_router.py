# shimon-vault/app/routers/demo_router.py

"""
routers/demo_router.py — one-click demo triggers for the presentation

These power the "run the demo" buttons in the admin console. They are
ADMIN-ONLY and can be turned off entirely with DEMO_ENABLED=false, because a
public "launch attack" button would itself be a vulnerability.

  POST /demo/test-notification    -> send a test alert to Slack + Telegram
  POST /demo/credential-stuffing  -> Act 2: fire N login attempts (background)
  POST /demo/access-control       -> Act 3: viewer repeatedly hits a document
                                      it doesn't own -> real 403s logged
  POST /demo/exfiltration         -> Act 4: editor rapidly re-downloads a
                                      real document -> real rate limiter trips
  POST /demo/ddos                 -> Act 5: concurrent burst at /docs/list
                                      -> spikes the real Prometheus request rate

Each simulation logs in as a REAL seeded demo account and calls REAL app
endpoints over HTTP, the same way scripts/simulate_*.sh do from a terminal.
This means the audit trail, rate limiting, and access control you see during
the demo are the actual application code running, not faked data.
"""

import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import config
from auth import require_role
from database import get_read_db
from models import Document, DocumentStatus, User, UserRole
from services.notify_service import notify_all

router = APIRouter()

_WEAK_PASSWORDS = [
    "password", "123456", "password123", "admin", "letmein",
    "qwerty", "abc123", "monkey", "master", "dragon",
    "111111", "baseball", "iloveyou", "trustno1", "sunshine",
]


def _require_demo_enabled():
    if not config.DEMO_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo endpoints are disabled (set DEMO_ENABLED=true to enable)",
        )


def _login_demo_account(base_url: str, email: str, password: str, attacker_ip: str) -> str:
    """Log in as a seeded demo account and return the JWT. Raises on failure."""
    resp = requests.post(
        f"{base_url.rstrip('/')}/auth/login",
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json", "X-Forwarded-For": attacker_ip},
        timeout=5,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"Login for {email} did not return a token")
    return token


# ─── Test notification ─────────────────────────────────────────────────────

@router.post("/test-notification")
def test_notification(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Send a harmless test message to both channels and report what happened.
    This is the reliable button — it proves Slack + Telegram wiring works and
    gives the toast something truthful to display.
    """
    _require_demo_enabled()

    message = (
        "*TEST NOTIFICATION -- ShimonVault*\n"
        f"Triggered by: {current_user.username}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n"
        "If you can read this in Slack and Telegram, alerting works."
    )
    result = notify_all(message)

    return {
        "detail": "Test notification sent",
        "channels": result,
        "all_ok": result.get("all_ok", False),
    }


# ─── Act 2 — Credential stuffing ────────────────────────────────────────────

def _run_credential_stuffing(base_url: str, attempts: int, attacker_ip: str) -> None:
    """Background worker — fires login attempts with wrong passwords."""
    target = f"{base_url.rstrip('/')}/auth/login"
    headers = {"Content-Type": "application/json", "X-Forwarded-For": attacker_ip}
    for i in range(attempts):
        email = f"user{random.randint(1, 50)}@example.com"
        password = random.choice(_WEAK_PASSWORDS)
        try:
            requests.post(target, json={"email": email, "password": password}, headers=headers, timeout=5)
        except Exception as exc:
            print(f"[demo] credential-stuffing request {i + 1} failed: {exc}")
    print(f"[demo] credential-stuffing finished: {attempts} attempts from {attacker_ip}")


@router.post("/credential-stuffing")
def credential_stuffing(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Launch the credential-stuffing simulation in the background and return
    immediately. The console then polls /audit/feed to show the attack and the
    automated response (alert -> incident -> IP block) unfolding live.
    """
    _require_demo_enabled()

    attempts = config.DEMO_LOGIN_ATTEMPTS
    attacker_ip = config.DEMO_ATTACKER_IP
    base_url = config.DEMO_BASE_URL

    thread = threading.Thread(
        target=_run_credential_stuffing,
        args=(base_url, attempts, attacker_ip),
        daemon=True,
        name="demo-credential-stuffing",
    )
    thread.start()

    return {
        "detail": "Credential-stuffing simulation started",
        "attempts": attempts,
        "attacker_ip": attacker_ip,
        "target": f"{base_url.rstrip('/')}/auth/login",
        "watch": "/audit/feed",
    }


# ─── Act 3 — Broken access control ──────────────────────────────────────────

def _run_access_control_attack(base_url: str, doc_id: str, attempts: int, attacker_ip: str) -> None:
    """
    Background worker. Logs in as the seeded VIEWER demo account, then
    repeatedly requests a document it does NOT own. Each call hits the real
    /docs/download/{id} route, so docs_router.py's real ownership check fires
    a real 403 and a real DOC_ACCESS_DENIED event on every attempt.
    """
    try:
        token = _login_demo_account(base_url, config.DEMO_VIEWER_EMAIL, config.DEMO_VIEWER_PASSWORD, attacker_ip)
    except Exception as exc:
        print(f"[demo] access-control attack: viewer login failed: {exc}")
        return

    headers = {"Authorization": f"Bearer {token}", "X-Forwarded-For": attacker_ip}
    target = f"{base_url.rstrip('/')}/docs/download/{doc_id}"
    for i in range(attempts):
        try:
            requests.get(target, headers=headers, timeout=5)
        except Exception as exc:
            print(f"[demo] access-control attempt {i + 1} failed: {exc}")
    print(f"[demo] access-control attack finished: {attempts} attempts against {doc_id}")


@router.post("/access-control")
def access_control_attack(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_read_db),
):
    """
    Act 3. Requires at least one ACTIVE document that the seeded viewer
    account does not own. Upload a document as admin or editor first if this
    returns a 400 asking for one.
    """
    _require_demo_enabled()

    viewer = db.query(User).filter(User.email == config.DEMO_VIEWER_EMAIL).first()
    if viewer is None:
        raise HTTPException(
            status_code=400,
            detail=f"Demo viewer account ({config.DEMO_VIEWER_EMAIL}) not found — run db/seed.sql",
        )

    target_doc = (
        db.query(Document)
        .filter(Document.status == DocumentStatus.ACTIVE, Document.owner_id != viewer.id)
        .first()
    )
    if target_doc is None:
        raise HTTPException(
            status_code=400,
            detail="No document owned by another user exists yet — upload one as admin or editor first",
        )

    attempts = config.DEMO_ACCESS_CONTROL_ATTEMPTS
    attacker_ip = config.DEMO_ATTACKER_IP
    base_url = config.DEMO_BASE_URL

    thread = threading.Thread(
        target=_run_access_control_attack,
        args=(base_url, str(target_doc.id), attempts, attacker_ip),
        daemon=True,
        name="demo-access-control",
    )
    thread.start()

    return {
        "detail": "Broken access control simulation started",
        "attempts": attempts,
        "target_document": str(target_doc.id),
        "attacker_ip": attacker_ip,
        "watch": "/audit/feed",
    }


# ─── Act 4 — Bulk exfiltration ───────────────────────────────────────────────

def _run_exfiltration(base_url: str, doc_id: str, attempts: int, attacker_ip: str) -> None:
    """
    Background worker. Logs in as the seeded EDITOR demo account (broad
    access) and rapidly re-requests the same real document. The first ~10
    calls succeed for real (200 + a real DOC_DOWNLOAD event each); once your
    existing rate limiter's 10-per-60s threshold is crossed, slowapi itself
    returns 429 for the rest — a real rate-limit trip, not a simulated one.
    """
    try:
        token = _login_demo_account(base_url, config.DEMO_EDITOR_EMAIL, config.DEMO_EDITOR_PASSWORD, attacker_ip)
    except Exception as exc:
        print(f"[demo] exfiltration: editor login failed: {exc}")
        return

    headers = {"Authorization": f"Bearer {token}", "X-Forwarded-For": attacker_ip}
    target = f"{base_url.rstrip('/')}/docs/download/{doc_id}"
    for i in range(attempts):
        try:
            requests.get(target, headers=headers, timeout=5)
        except Exception as exc:
            print(f"[demo] exfiltration attempt {i + 1} failed: {exc}")
    print(f"[demo] exfiltration finished: {attempts} attempts against {doc_id}")


@router.post("/exfiltration")
def exfiltration_attack(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_read_db),
):
    """Act 4. Requires at least one ACTIVE document to exist anywhere."""
    _require_demo_enabled()

    target_doc = db.query(Document).filter(Document.status == DocumentStatus.ACTIVE).first()
    if target_doc is None:
        raise HTTPException(
            status_code=400,
            detail="No documents exist yet — upload one first (any role)",
        )

    attempts = config.DEMO_EXFILTRATION_ATTEMPTS
    attacker_ip = config.DEMO_ATTACKER_IP
    base_url = config.DEMO_BASE_URL

    thread = threading.Thread(
        target=_run_exfiltration,
        args=(base_url, str(target_doc.id), attempts, attacker_ip),
        daemon=True,
        name="demo-exfiltration",
    )
    thread.start()

    return {
        "detail": "Bulk exfiltration simulation started",
        "attempts": attempts,
        "target_document": str(target_doc.id),
        "attacker_ip": attacker_ip,
        "watch": "/audit/feed",
    }


# ─── Act 5 — DDoS / traffic flood ────────────────────────────────────────────

def _fire_one_request(base_url: str, token: str, attacker_ip: str) -> None:
    try:
        requests.get(
            f"{base_url.rstrip('/')}/docs/list",
            headers={"Authorization": f"Bearer {token}", "X-Forwarded-For": attacker_ip},
            timeout=5,
        )
    except Exception:
        pass  # expected under load — this is what we're demonstrating


def _run_ddos(base_url: str, token: str, total_requests: int, concurrency: int, attacker_ip: str) -> None:
    """
    Background worker. Fires a burst of concurrent GET /docs/list requests
    using a thread pool, to visibly spike the real Prometheus request-rate
    metric that /admin/metrics/infra reads. This demonstrates traffic load on
    your dashboard; it does not attempt to verify or force real ASG scaling,
    since that depends on independent CloudWatch alarm timing.
    """
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for _ in range(total_requests):
            pool.submit(_fire_one_request, base_url, token, attacker_ip)
    print(f"[demo] DDoS simulation finished: {total_requests} requests, concurrency {concurrency}")


@router.post("/ddos")
def ddos_attack(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_read_db),
):
    """Act 5. Uses the seeded viewer account to authenticate the flood traffic."""
    _require_demo_enabled()

    attacker_ip = config.DEMO_ATTACKER_IP
    base_url = config.DEMO_BASE_URL

    try:
        token = _login_demo_account(base_url, config.DEMO_VIEWER_EMAIL, config.DEMO_VIEWER_PASSWORD, attacker_ip)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not authenticate demo account: {exc}")

    total_requests = config.DEMO_DDOS_REQUESTS
    concurrency = config.DEMO_DDOS_CONCURRENCY

    thread = threading.Thread(
        target=_run_ddos,
        args=(base_url, token, total_requests, concurrency, attacker_ip),
        daemon=True,
        name="demo-ddos",
    )
    thread.start()

    return {
        "detail": "Traffic flood simulation started",
        "total_requests": total_requests,
        "concurrency": concurrency,
        "watch": "/admin/metrics/infra",
    }