"""
app/services/prometheus_service.py — query the on-prem Prometheus

The admin dashboard draws its own charts (to match the app's look) instead
of embedding Grafana. The chart DATA still comes from the same Prometheus
that Grafana uses — we just fetch it through Prometheus's HTTP API and let
the React/Vue front end render it.

Prometheus runs on the on-prem box (proj-mgmt) and is reached over the
Tailscale mesh. The URL is read from config.PROMETHEUS_URL, which comes from
.env — NEVER hardcode the Tailscale IP here (see coding-rules-and-constraints).

Every function degrades gracefully: if Prometheus is unreachable (Tailscale
down, on-prem box off), it returns an empty result instead of raising, so the
dashboard shows "no data" rather than a 500. This mirrors how audit_router
tolerates DynamoDB being unavailable.
"""

import time

import requests

import config

_TIMEOUT = 4  # seconds — keep the dashboard responsive even if Prometheus is slow


def _base() -> str:
    return config.PROMETHEUS_URL.rstrip("/")


def query(expr: str) -> list:
    """
    Instant query. Returns Prometheus 'result' list (possibly empty):
        [{"metric": {...}, "value": [<unix_ts>, "<value>"]}, ...]
    """
    try:
        resp = requests.get(
            f"{_base()}/api/v1/query",
            params={"query": expr},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("result", [])
    except Exception as exc:
        print(f"[prometheus_service] query failed ({expr}): {exc}")
        return []


def query_range(expr: str, minutes: int = 15, step: str = "30s") -> list:
    """
    Range query for time-series charts. Returns Prometheus matrix 'result':
        [{"metric": {...}, "values": [[<ts>, "<value>"], ...]}, ...]
    """
    end = time.time()
    start = end - minutes * 60
    try:
        resp = requests.get(
            f"{_base()}/api/v1/query_range",
            params={"query": expr, "start": start, "end": end, "step": step},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("result", [])
    except Exception as exc:
        print(f"[prometheus_service] query_range failed ({expr}): {exc}")
        return []


def scalar(expr: str, default: float = 0.0) -> float:
    """Convenience: run an instant query and return the first value as a float."""
    result = query(expr)
    if not result:
        return default
    try:
        return float(result[0]["value"][1])
    except (KeyError, IndexError, ValueError, TypeError):
        return default


def is_up() -> bool:
    """True if Prometheus answered at all — used for a health pill in the UI."""
    try:
        resp = requests.get(f"{_base()}/-/ready", timeout=_TIMEOUT)
        return resp.status_code == 200
    except Exception:
        return False
