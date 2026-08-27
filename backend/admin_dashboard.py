from __future__ import annotations

import contextlib
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Cookie

from backend.admin_representatives import (
    _ai_live_inbounds,
    ensure_admin_schema,
    require_admin,
    table_exists,
)
from backend.reseller_profile import SESSION_COOKIE, connect_db


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Dashboard"],
)

_LAST_INBOUNDS: list[dict[str, Any]] = []


def _sync_live_usage_if_due() -> None:
    """Refresh the shared reseller traffic/online snapshot when due.

    The existing live sync module already throttles this call, so polling the
    admin dashboard does not cause a full X-UI traffic sync every 3 seconds.
    """
    with contextlib.suppress(Exception):
        from backend.reseller_live_quota import sync_if_due

        sync_if_due()


def _client_counts(con, rep_id: int) -> tuple[int, int]:
    if not table_exists(con, "clients"):
        return 0, 0

    cols = {
        str(row["name"])
        for row in con.execute("PRAGMA table_info(clients)").fetchall()
    }

    where = "seller_rep_id=?"
    if "status" in cols:
        where += " AND COALESCE(status,'')!='deleted'"

    total = int(
        con.execute(
            f"SELECT COUNT(*) AS total FROM clients WHERE {where}",
            (int(rep_id),),
        ).fetchone()["total"]
        or 0
    )

    online = 0
    if "is_online" in cols:
        online = int(
            con.execute(
                f"SELECT COUNT(*) AS total FROM clients WHERE {where} AND COALESCE(is_online,0)=1",
                (int(rep_id),),
            ).fetchone()["total"]
            or 0
        )

    return total, online


def _representatives(con) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT *
        FROM representatives
        WHERE COALESCE(deleted_at,'')=''
        ORDER BY id DESC
        """
    ).fetchall()

    output: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        rep_id = int(item.get("id") or 0)
        users, online = _client_counts(con, rep_id)

        quota = max(0, int(item.get("quota_bytes") or 0))
        used = max(0, int(item.get("used_bytes") or 0))
        quota_locked = bool(int(item.get("quota_locked") or 0))
        raw_status = str(item.get("status") or "active").strip().lower()
        visible_status = (
            "Active"
            if raw_status == "active" and not quota_locked
            else "Suspended"
        )

        output.append(
            {
                "id": rep_id,
                "username": str(item.get("username") or ""),
                "quota_bytes": quota,
                "used_bytes": used,
                "remaining_bytes": max(0, quota - used),
                "users": users,
                "online": online,
                "status": visible_status,
                "raw_status": raw_status,
                "quota_locked": quota_locked,
            }
        )

    return output


def _traffic_trend(con) -> list[dict[str, Any]]:
    today = date.today()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    totals = {day.isoformat(): 0 for day in days}

    if not table_exists(con, "traffic_events"):
        return [
            {"date": day.isoformat(), "bytes": 0}
            for day in days
        ]

    start = days[0].isoformat()
    end = (days[-1] + timedelta(days=1)).isoformat()

    rows = con.execute(
        """
        SELECT
            date(te.created_at) AS day,
            COALESCE(SUM(te.delta_bytes), 0) AS total
        FROM traffic_events te
        WHERE date(te.created_at) >= date(?)
          AND date(te.created_at) < date(?)
          AND COALESCE(te.delta_bytes,0) > 0
        GROUP BY date(te.created_at)
        """,
        (start, end),
    ).fetchall()

    for row in rows:
        day = str(row["day"] or "")
        if day in totals:
            totals[day] = max(0, int(row["total"] or 0))

    return [
        {"date": day.isoformat(), "bytes": totals[day.isoformat()]}
        for day in days
    ]


def _live_inbounds_safe() -> tuple[list[dict[str, Any]], bool]:
    global _LAST_INBOUNDS

    try:
        rows = _ai_live_inbounds()
        _LAST_INBOUNDS = rows
        return rows, True
    except Exception:
        # Keep the latest successful infrastructure snapshot on a temporary
        # X-UI error instead of wiping the dashboard.
        return list(_LAST_INBOUNDS), False


@router.get("/dashboard")
def admin_dashboard(
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    ensure_admin_schema()

    _sync_live_usage_if_due()

    with connect_db() as con:
        representatives = _representatives(con)
        trend = _traffic_trend(con)
        archived_used_bytes = 0
        if table_exists(con, "deleted_representatives"):
            row = con.execute(
                "SELECT COALESCE(SUM(used_bytes),0) AS total FROM deleted_representatives"
            ).fetchone()
            archived_used_bytes = int(row["total"] or 0) if row else 0

    inbounds, inbounds_live = _live_inbounds_safe()

    active = sum(1 for item in representatives if item["status"] == "Active")
    suspended = len(representatives) - active
    clients = sum(int(item["users"]) for item in representatives)
    online = sum(int(item["online"]) for item in representatives)
    quota_bytes = sum(int(item["quota_bytes"]) for item in representatives)
    used_bytes = sum(int(item["used_bytes"]) for item in representatives) + archived_used_bytes
    remaining_bytes = sum(int(item["remaining_bytes"]) for item in representatives)

    # Keep the compact dashboard list useful without changing its UI height.
    dashboard_representatives = sorted(
        representatives,
        key=lambda item: (
            int(item["used_bytes"]),
            int(item["id"]),
        ),
        reverse=True,
    )[:5]

    return {
        "ok": True,
        "poll_hint_ms": 3000,
        "summary": {
            "representatives": len(representatives),
            "active": active,
            "suspended": suspended,
            "clients": clients,
            "online": online,
            "quota_bytes": quota_bytes,
            "used_bytes": used_bytes,
            "remaining_bytes": remaining_bytes,
            "inbounds": len(inbounds),
            "available_inbounds": sum(1 for item in inbounds if item.get("enabled")),
        },
        "representatives": dashboard_representatives,
        "inbounds": inbounds[:5],
        "inbounds_live": inbounds_live,
        "trend": trend,
    }
