# shimon-vault/app/routers/audit_router.py

"""
routers/audit_router.py — AuditStream live feed

GET /audit/feed         -> last 100 audit events (all users for admin, own for viewer)
GET /audit/incidents    -> open security incidents (admin only)
GET /audit/my-activity  -> current user's own activity log

These endpoints feed the Grafana JSON API plugin for the live dashboard.
"""

import boto3
from boto3.dynamodb.conditions import Attr, Key
from fastapi import APIRouter, Depends

import config
from auth import get_current_user, require_role
from models import AuditEventType, User, UserRole

router = APIRouter()

_dynamodb = None


def _get_audit_table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=config.AWS_REGION)
    return _dynamodb.Table(config.DYNAMODB_AUDIT_TABLE)


def _get_incidents_table():
    dynamodb = boto3.resource("dynamodb", region_name=config.AWS_REGION)
    return dynamodb.Table(config.DYNAMODB_INCIDENTS_TABLE)


def _recent_events(table, limit: int):
    """
    Return the `limit` most recent audit events, newest first.

    WHY NOT table.scan(Limit=n):
      scan(Limit=n) returns the first n items DynamoDB happens to walk — an
      arbitrary page, not the newest n. Sorting that page by created_at yields
      "the newest of a random sample", so a burst of attack traffic could be
      absent from the feed entirely while older keep-alive rows showed. That is
      exactly what made the live demo feed unreliable.

    WHY THIS WORKS:
      The base table is keyed (id=uuid4, created_at), so its partition key is
      random and cannot be range-queried by time. The event_type-index GSI is
      keyed (event_type, created_at), so per event type we CAN ask DynamoDB for
      the newest rows directly — ScanIndexForward=False walks the sort key
      descending. AuditEventType is a small closed set, so taking the newest
      `limit` per type and merging is guaranteed to contain the true newest
      `limit` overall: any event in the global top-N is also in its own type's
      top-N.
    """
    collected = []
    for event_type in AuditEventType:
        response = table.query(
            IndexName="event_type-index",
            KeyConditionExpression=Key("event_type").eq(event_type.value),
            ScanIndexForward=False,   # newest first
            Limit=limit,
        )
        collected.extend(response.get("Items", []))

    collected.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return collected[:limit]


@router.get("/feed")
def get_audit_feed(
    limit: int = 100,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Return the most recent audit events. ADMIN ONLY — this is the full,
    cross-user trail, so the Grafana live-feed panel must use an admin token.
    Non-admins use GET /audit/my-activity to see only their own events.
    """
    table = _get_audit_table()
    try:
        items = _recent_events(table, limit)
    except Exception as exc:
        print(f"[audit_router] DynamoDB unavailable in get_audit_feed: {exc}")
        items = []

    return {"events": items, "count": len(items)}


@router.get("/incidents")
def get_incidents(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Return open security incidents. Admin only.
    Shown in the Grafana "Active Incidents" panel with red severity color.
    """
    table = _get_incidents_table()
    try:
        response = table.scan(
            FilterExpression=Attr("status").is_in(["open", "active"]),
        )
        incidents = sorted(
            response.get("Items", []),
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )
    except Exception as exc:
        print(f"[audit_router] DynamoDB unavailable in get_incidents: {exc}")
        incidents = []

    return {"incidents": incidents, "count": len(incidents)}


@router.get("/my-activity")
def get_my_activity(
    current_user: User = Depends(get_current_user),
):
    """Current user's own activity. Every user can see their own history."""
    table = _get_audit_table()
    try:
        response = table.scan(
            FilterExpression=Attr("user_id").eq(str(current_user.id)),
            Limit=50,
        )
        items = sorted(
            response.get("Items", []),
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )
    except Exception as exc:
        print(f"[audit_router] DynamoDB unavailable in get_my_activity: {exc}")
        items = []

    return {"events": items, "count": len(items)}
