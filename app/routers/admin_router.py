# shimon-vault/app/routers/admin_router.py

"""
routers/admin_router.py — data for the admin dashboard (the "Grafana-like" view)

The web app draws its own charts to match its UI, so this router returns plain
JSON the React/Vue front end can render with Chart.js. ALL endpoints are
ADMIN-ONLY.

  GET /admin/metrics/summary      -> headline numbers (cards/gauges)
  GET /admin/metrics/timeseries   -> per-minute counts for the line charts
  GET /admin/metrics/infra        -> best-effort CPU/mem/up from Prometheus

Why DynamoDB for most of it:
  The audit log is the single source of truth for security activity
  (login failures, access-denied, downloads, blocked IPs). Reading it back
  gives charts whose shape we control exactly. Prometheus is used only for
  infrastructure metrics (CPU/memory/request rate), which it owns.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr
from fastapi import APIRouter, Depends, Query

import config
from auth import require_role
from models import User, UserRole
from services import prometheus_service as prom

router = APIRouter()

# Event types we treat as "alerts" on the dashboard. We match on the string
# values stored in DynamoDB so this router never has to import the enum.
_ALERT_EVENT_TYPES = {
    "login_failure",
    "doc_access_denied",
    "token_replay",
    "malicious_upload",
    "exfiltration_attempt",
}
_ALERT_SEVERITIES = {"warning", "critical"}


def _audit_table():
    return boto3.resource("dynamodb", region_name=config.AWS_REGION).Table(
        config.DYNAMODB_AUDIT_TABLE
    )


def _incidents_table():
    return boto3.resource("dynamodb", region_name=config.AWS_REGION).Table(
        config.DYNAMODB_INCIDENTS_TABLE
    )


def _scan_recent_events(limit: int = 500) -> list:
    """Most recent audit events, newest first. Empty list if DynamoDB is down."""
    try:
        items = _audit_table().scan(Limit=limit).get("Items", [])
        return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)
    except Exception as exc:
        print(f"[admin_router] DynamoDB unavailable in _scan_recent_events: {exc}")
        return []


def _parse_ts(value: str):
    """Parse an ISO-8601 created_at into an aware datetime, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@router.get("/metrics/summary")
def metrics_summary(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Headline numbers for the dashboard cards."""
    events = _scan_recent_events()

    by_type = Counter(e.get("event_type", "unknown") for e in events)
    alert_count = sum(
        1 for e in events
        if e.get("event_type") in _ALERT_EVENT_TYPES
        or e.get("severity") in _ALERT_SEVERITIES
    )

    # Distinct attacker IPs seen in alert events == rough "blocked IPs" signal
    blocked_ips = {
        e.get("ip_address")
        for e in events
        if e.get("ip_address") and e.get("severity") in _ALERT_SEVERITIES
    }

    # Open incidents (admin-only table)
    try:
        open_incidents = _incidents_table().scan(
            FilterExpression=Attr("status").is_in(["open", "active"]),
        ).get("Items", [])
        open_incident_count = len(open_incidents)
    except Exception as exc:
        print(f"[admin_router] DynamoDB unavailable in incidents scan: {exc}")
        open_incident_count = 0

    return {
        "total_events": len(events),
        "login_failures": by_type.get("login_failure", 0),
        "access_denied": by_type.get("doc_access_denied", 0),
        "downloads": by_type.get("doc_download", 0),
        "alerts": alert_count,
        "blocked_ips": len(blocked_ips),
        "open_incidents": open_incident_count,
        "prometheus_up": prom.is_up(),
    }


@router.get("/metrics/timeseries")
def metrics_timeseries(
    minutes: int = Query(15, ge=1, le=180),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Per-minute counts over the last `minutes`, ready for a Chart.js line chart.
    Returns parallel arrays so the front end can plot directly:
        labels:        ["14:01", "14:02", ...]
        total:         [3, 5, ...]
        failures:      [0, 4, ...]   (login_failure events)
        alerts:        [0, 4, ...]   (warning/critical severity)
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=minutes)

    # Pre-seed every minute bucket with 0 so the chart has no gaps.
    buckets = {}
    for i in range(minutes + 1):
        ts = (window_start + timedelta(minutes=i)).replace(second=0, microsecond=0)
        buckets[ts] = {"total": 0, "failures": 0, "alerts": 0}

    for e in _scan_recent_events():
        dt = _parse_ts(e.get("created_at", ""))
        if dt is None or dt < window_start:
            continue
        key = dt.replace(second=0, microsecond=0)
        if key not in buckets:
            continue
        buckets[key]["total"] += 1
        if e.get("event_type") == "login_failure":
            buckets[key]["failures"] += 1
        if e.get("severity") in _ALERT_SEVERITIES:
            buckets[key]["alerts"] += 1

    ordered = sorted(buckets.items())
    return {
        "labels": [ts.strftime("%H:%M") for ts, _ in ordered],
        "total": [v["total"] for _, v in ordered],
        "failures": [v["failures"] for _, v in ordered],
        "alerts": [v["alerts"] for _, v in ordered],
    }


@router.get("/metrics/infra")
def metrics_infra(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Best-effort infrastructure metrics from Prometheus. Returns nulls (not an
    error) if Prometheus is unreachable or the metric name differs.

    NOTE: these PromQL expressions assume node_exporter is scraped. Confirm the
    exact metric/label names against your Prometheus targets and adjust if a
    value comes back null — the dashboard will still render, just empty.
    """
    cpu_pct = prom.scalar(
        '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
        default=None,
    )
    mem_pct = prom.scalar(
        '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100',
        default=None,
    )
    # http_request_duration_seconds_count is exposed by the FastAPI
    # instrumentator; rate() over it gives requests/sec.
    req_rate = prom.scalar(
        'sum(rate(http_request_duration_seconds_count[1m]))',
        default=None,
    )

    return {
        "prometheus_up": prom.is_up(),
        "cpu_percent": round(cpu_pct, 1) if cpu_pct is not None else None,
        "memory_percent": round(mem_pct, 1) if mem_pct is not None else None,
        "request_rate": round(req_rate, 2) if req_rate is not None else None,
    }
