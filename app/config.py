"""
config.py — ShimonVault application configuration
Reads all settings from environment variables.
Secrets are never hardcoded; values are injected at runtime via .env or EC2 user_data.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Return env var value or raise at startup if truly required."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Required environment variable '{name}' is not set")
    return value


# ── Project identity ──────────────────────────────────────────────────────────
PROJECT_NAME = os.getenv("PROJECT_NAME", "shimonvault")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# ── Database (MUST use psycopg2 sync driver — asyncpg is incompatible) ────────
# WRITE_DB_URL → AWS RDS primary (all writes go here)
# READ_DB_URL  → on-prem Docker replica via Tailscale (read-only queries)
WRITE_DB_URL = os.getenv(
    "WRITE_DB_URL",
    "postgresql+psycopg2://shimonvault:changeme@localhost:5432/shimonvault"
)
READ_DB_URL = os.getenv(
    "READ_DB_URL",
    "postgresql+psycopg2://shimonvault:changeme@localhost:5432/shimonvault"
)

# ── JWT ───────────────────────────────────────────────────────────────────────
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
# Alias used by auth.py — always keep these in sync
JWT_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES

# ── AWS ───────────────────────────────────────────────────────────────────────
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
AWS_ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID", "")

# ── S3 ────────────────────────────────────────────────────────────────────────
S3_BUCKET_DOCS = os.getenv("S3_BUCKET_DOCS", f"{PROJECT_NAME}-docs")
S3_BUCKET_REPORTS = os.getenv("S3_BUCKET_REPORTS", f"{PROJECT_NAME}-reports")
S3_PRESIGNED_URL_EXPIRY = int(os.getenv("S3_PRESIGNED_URL_EXPIRY", "900"))  # 15 min

# ── DynamoDB ──────────────────────────────────────────────────────────────────
DYNAMODB_AUDIT_TABLE = os.getenv("DYNAMODB_AUDIT_TABLE", f"{PROJECT_NAME}-audit-log")
DYNAMODB_INCIDENTS_TABLE = os.getenv("DYNAMODB_INCIDENTS_TABLE", f"{PROJECT_NAME}-incidents")
DYNAMODB_MEETINGS_TABLE = os.getenv("DYNAMODB_MEETINGS_TABLE", f"{PROJECT_NAME}-meetings")

# ── SNS ───────────────────────────────────────────────────────────────────────
SNS_TOPIC_SECURITY_ALERT = os.getenv("SNS_TOPIC_SECURITY_ALERT", "")
SNS_TOPIC_CREDENTIAL_STUFFING = os.getenv("SNS_TOPIC_CREDENTIAL_STUFFING", "")
SNS_TOPIC_INFRA_ALERT = os.getenv("SNS_TOPIC_INFRA_ALERT", "")
# Optional — meeting reminders Lambda may not be wired yet
SNS_TOPIC_MEETING_REMINDERS = os.getenv("SNS_TOPIC_MEETING_REMINDERS", "")

# ── Lambda ────────────────────────────────────────────────────────────────────
LAMBDA_BLOCK_IP_NAME = os.getenv("LAMBDA_BLOCK_IP_NAME", f"{PROJECT_NAME}-block-ip")
LAMBDA_LOG_INCIDENT = os.getenv("LAMBDA_LOG_INCIDENT", f"{PROJECT_NAME}-log-incident")

# ── Notifications (Slack + Telegram) ──────────────────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Prometheus (on-prem monitoring, via Tailscale) ────────────────────────────
# The admin dashboard fetches infra metrics through Prometheus's HTTP API.
# Prometheus runs on proj-mgmt. NEVER hardcode the Tailscale IP here — set
# PROMETHEUS_URL in .env, e.g. http://100.106.194.10:9090
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

# ── Demo console ──────────────────────────────────────────────────────────────
# Master switch for the one-click demo buttons. Set DEMO_ENABLED=false to make
# every /demo/* endpoint return 403 (safe default for any "real" deployment).
DEMO_ENABLED = os.getenv("DEMO_ENABLED", "true").lower() == "true"
# Public base URL the in-app attack runner targets. In deployment set this to
# the live app URL (https://shimonvault.junhanshin.com) — never hardcode.
DEMO_BASE_URL = os.getenv("DEMO_BASE_URL", "http://localhost:8000")
# Fake attacker IP shown in the audit log during demos. 203.0.113.0/24 is the
# RFC 5737 TEST-NET-3 documentation range — not a real address.
DEMO_ATTACKER_IP = os.getenv("DEMO_ATTACKER_IP", "203.0.113.42")
DEMO_LOGIN_ATTEMPTS = int(os.getenv("DEMO_LOGIN_ATTEMPTS", "30"))
# Seeded demo accounts used by the access-control and exfiltration
# simulations below. These are fake demo credentials already committed
# in db/seed.sql — not production secrets — but still overridable via
# .env so nothing is truly hardcoded.
DEMO_VIEWER_EMAIL = os.getenv("DEMO_VIEWER_EMAIL", "viewer@shimonvault.com")
DEMO_VIEWER_PASSWORD = os.getenv("DEMO_VIEWER_PASSWORD", "View9012!")
DEMO_EDITOR_EMAIL = os.getenv("DEMO_EDITOR_EMAIL", "editor@shimonvault.com")
DEMO_EDITOR_PASSWORD = os.getenv("DEMO_EDITOR_PASSWORD", "Edit5678!")

DEMO_ACCESS_CONTROL_ATTEMPTS = int(os.getenv("DEMO_ACCESS_CONTROL_ATTEMPTS", "6"))
DEMO_EXFILTRATION_ATTEMPTS = int(os.getenv("DEMO_EXFILTRATION_ATTEMPTS", "15"))
DEMO_DDOS_REQUESTS = int(os.getenv("DEMO_DDOS_REQUESTS", "200"))
DEMO_DDOS_CONCURRENCY = int(os.getenv("DEMO_DDOS_CONCURRENCY", "20"))

# ── Rate limiting ─────────────────────────────────────────────────────────────
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
RATE_LIMIT_DOWNLOAD = os.getenv("RATE_LIMIT_DOWNLOAD", "10/60seconds")
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")

# ── Security Group (for Lambda block_ip) ──────────────────────────────────────
APP_SECURITY_GROUP_ID = os.getenv("APP_SECURITY_GROUP_ID", "")

# Rate limit strings used by slowapi decorators
LOGIN_RATE_LIMIT = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
DOWNLOAD_RATE_LIMIT = os.getenv("RATE_LIMIT_DOWNLOAD", "10/60seconds")
DEFAULT_RATE_LIMIT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
