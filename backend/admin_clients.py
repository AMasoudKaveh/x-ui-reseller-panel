from __future__ import annotations

import contextlib
import json
import secrets
import sqlite3
import time
from datetime import datetime
from urllib.parse import quote
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException

import backend.admin_representatives as admin_reps
from backend.reseller_create_user import expiry_to_ms, gb_to_bytes, normalize_inbound_ids
from backend.reseller_profile import SESSION_COOKIE, connect_db
from backend.reseller_user_actions import (
    ModifyUserBody,
    ToggleBody,
    access_bundle,
    delete_from_panel,
    ensure_deleted_usage_schema,
    inbound_ids_for,
    make_comment,
    now_text,
    panel_get,
    parse_ids,
    safe_sub,
    safe_update,
    safe_uuid,
    strip_internal_comment,
    table_columns,
    table_exists,
    to_int,
)
from backend.xui_client import XUIClient


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Clients"],
)

_LAST_INBOUNDS: list[dict[str, Any]] = []


def _require_admin(token: str | None) -> dict[str, Any]:
    return admin_reps.require_admin(token)


def _ensure_schema() -> None:
    admin_reps.ensure_admin_schema()
    ensure_deleted_usage_schema()


def _sync_if_due() -> None:
    with contextlib.suppress(Exception):
        from backend.reseller_live_quota import sync_if_due

        sync_if_due()


def _live_inbounds() -> list[dict[str, Any]]:
    global _LAST_INBOUNDS

    try:
        live_fn = getattr(admin_reps, "_ai_live_inbounds", None)
        if callable(live_fn):
            rows = live_fn()
        else:
            rows = []
            for item in XUIClient().inbounds():
                iid = to_int(item.get("id"), 0)
                if iid <= 0:
                    continue
                label = str(item.get("label") or item.get("remark") or f"Inbound #{iid}")
                rows.append({
                    "id": iid,
                    "name": label,
                    "label": label,
                    "port": to_int(item.get("port"), 0),
                    "protocol": str(item.get("protocol") or ""),
                    "network": str(item.get("network") or ""),
                    "security": str(item.get("security") or ""),
                    "enabled": bool(item.get("enabled", True)),
                    "clients": 0,
                    "online": 0,
                    "traffic_bytes": 0,
                    "speed_bps": 0,
                })
        if rows:
            _LAST_INBOUNDS = [dict(row) for row in rows]
        return [dict(row) for row in rows]
    except Exception:
        if _LAST_INBOUNDS:
            return [dict(row) for row in _LAST_INBOUNDS]
        raise


def _inbound_map() -> dict[int, dict[str, Any]]:
    return {
        to_int(row.get("id"), 0): row
        for row in _live_inbounds()
        if to_int(row.get("id"), 0) > 0
    }


def _admin_user(client_id: int) -> dict[str, Any]:
    _ensure_schema()
    with connect_db() as con:
        row = con.execute(
            """
            SELECT c.*, r.username AS owner_username,
                   COALESCE(l.cumulative_used_bytes,0) AS cumulative_used_bytes
            FROM clients c
            LEFT JOIN representatives r ON r.id=c.seller_rep_id
            LEFT JOIN traffic_ledger l ON l.client_id=c.id
            WHERE c.id=? AND COALESCE(c.status,'')!='deleted'
            """,
            (int(client_id),),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")
    return dict(row)


def _rep_for_client(local: dict[str, Any]) -> dict[str, Any]:
    rep_id = to_int(local.get("seller_rep_id"), 0)
    if rep_id <= 0:
        raise HTTPException(status_code=409, detail="Client has no representative owner")
    with connect_db() as con:
        row = con.execute(
            "SELECT * FROM representatives WHERE id=? AND COALESCE(deleted_at,'')=''",
            (rep_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=409, detail="Representative owner no longer exists")
    return dict(row)


def _rep_allowed_ids(rep: dict[str, Any], live_ids: list[int]) -> list[int]:
    raw = rep.get("allowed_inbound_ids")
    # NULL preserves old/unrestricted representatives. Explicit [] means none.
    if raw is None or str(raw).strip() == "":
        return list(live_ids)
    return [iid for iid in admin_reps.parse_inbound_ids(raw) if iid in live_ids]


def _validate_admin_inbounds(
    local: dict[str, Any],
    requested: list[int],
    *,
    allow_current: bool = True,
) -> list[int]:
    ids = normalize_inbound_ids(requested)
    if not ids:
        raise HTTPException(status_code=400, detail="Select at least one inbound")

    live = _live_inbounds()
    live_ids = [to_int(row.get("id"), 0) for row in live if to_int(row.get("id"), 0) > 0]
    live_set = set(live_ids)
    invalid = [iid for iid in ids if iid not in live_set]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown inbound IDs: {', '.join(map(str, invalid))}")

    rep = _rep_for_client(local)
    permitted = set(_rep_allowed_ids(rep, live_ids))
    if allow_current:
        permitted.update(parse_ids(local.get("inbound_ids")))

    forbidden = [iid for iid in ids if iid not in permitted]
    if forbidden:
        raise HTTPException(
            status_code=403,
            detail="One or more selected inbounds are not allowed for this representative. Grant access in Representatives first.",
        )
    return ids


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).strip().isdigit():
        number = float(value)
        if number >= 1_000_000_000:
            if number > 10_000_000_000:
                number /= 1000
            with contextlib.suppress(Exception):
                return datetime.fromtimestamp(number)
    text = str(value).strip().replace("Z", "+00:00")
    with contextlib.suppress(Exception):
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            return dt.astimezone().replace(tzinfo=None)
        return dt
    return None


def _age_label(value: Any) -> str:
    dt = _parse_datetime(value)
    if not dt:
        return ""
    seconds = max(0, int((datetime.now() - dt).total_seconds()))
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    days = seconds // 86400
    if days < 30:
        return f"{days}d"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}y"


def _expiry_label(expire_at_ms: Any) -> str:
    value = to_int(expire_at_ms, 0)
    if value <= 0:
        return "∞"
    remaining = int(value / 1000 - time.time())
    if remaining <= 0:
        return "Expired"
    days = (remaining + 86399) // 86400
    if days >= 2:
        return f"{days} days"
    hours = max(1, (remaining + 3599) // 3600)
    return f"{hours}h"


def _is_expired(local: dict[str, Any], expiry_ms: int | None = None) -> bool:
    value = to_int(expiry_ms if expiry_ms is not None else local.get("expire_at_ms"), 0)
    return value > 0 and value <= int(time.time() * 1000)


def _client_status(local: dict[str, Any]) -> str:
    if bool(to_int(local.get("rep_quota_hold"), 0)):
        return "Quota Hold"
    if bool(to_int(local.get("own_limit_exhausted"), 0)):
        return "Limited"
    if _is_expired(local):
        return "Expired"
    if not bool(to_int(local.get("enabled"), 1)):
        return "Disabled"
    return "Active"


def _can_enable(
    local: dict[str, Any],
    *,
    total_bytes: int | None = None,
    expiry_ms: int | None = None,
) -> tuple[bool, str]:
    rep = _rep_for_client(local)
    rep_status = str(rep.get("status") or "active").strip().lower()
    if rep_status != "active":
        return False, "Representative is not active"
    quota = to_int(rep.get("quota_bytes"), 0)
    used = to_int(rep.get("used_bytes"), 0)
    if bool(to_int(rep.get("quota_locked"), 0)) or (quota > 0 and used >= quota):
        return False, "Representative quota is exhausted"

    expiry = to_int(expiry_ms if expiry_ms is not None else local.get("expire_at_ms"), 0)
    if expiry > 0 and expiry <= int(time.time() * 1000):
        return False, "Client is expired. Extend expiry before enabling."

    limit_value = to_int(total_bytes if total_bytes is not None else local.get("total_limit_bytes"), 0)
    cumulative = to_int(local.get("cumulative_used_bytes"), 0)
    if limit_value > 0 and cumulative >= limit_value:
        return False, "Client traffic limit is exhausted. Increase the client limit before enabling."

    # A representative-admin hold should normally be cleared by activating the
    # representative. Do not let a client action bypass an active hold.
    if bool(to_int(local.get("rep_admin_hold"), 0)) and rep_status != "active":
        return False, "Client is held by representative suspension"
    return True, ""


def _clear_lifecycle_on_manual_disable(con: sqlite3.Connection, client_id: int) -> None:
    cols = table_columns(con, "clients")
    assignments: list[str] = []
    values: list[Any] = []
    for col, value in (
        ("rep_quota_hold", 0),
        ("quota_prev_enabled", 0),
        ("quota_prev_status", None),
        ("quota_disabled_at", None),
        ("rep_admin_hold", 0),
        ("rep_admin_prev_enabled", 0),
        ("rep_admin_prev_status", None),
        ("rep_admin_disabled_at", None),
    ):
        if col in cols:
            assignments.append(f"{col}=?")
            values.append(value)
    if assignments:
        values.append(int(client_id))
        con.execute(f"UPDATE clients SET {', '.join(assignments)} WHERE id=?", tuple(values))


def _update_local_lifecycle(
    con: sqlite3.Connection,
    client_id: int,
    *,
    enabled: bool,
    total_bytes: int,
    expiry_ms: int,
) -> None:
    cumulative_row = None
    if table_exists(con, "traffic_ledger"):
        cumulative_row = con.execute(
            "SELECT cumulative_used_bytes FROM traffic_ledger WHERE client_id=?",
            (int(client_id),),
        ).fetchone()
    cumulative = to_int(cumulative_row["cumulative_used_bytes"], 0) if cumulative_row else 0
    own_exhausted = 1 if total_bytes > 0 and cumulative >= total_bytes else 0

    if enabled:
        con.execute(
            """
            UPDATE clients
            SET enabled=1,
                status='active',
                own_limit_exhausted=?,
                disable_reason='',
                rep_quota_hold=0,
                quota_prev_enabled=0,
                quota_prev_status=NULL,
                quota_disabled_at=NULL,
                rep_admin_hold=0,
                rep_admin_prev_enabled=0,
                rep_admin_prev_status=NULL,
                rep_admin_disabled_at=NULL,
                updated_at=?
            WHERE id=?
            """,
            (own_exhausted, now_text(), int(client_id)),
        )
    else:
        _clear_lifecycle_on_manual_disable(con, client_id)
        con.execute(
            """
            UPDATE clients
            SET enabled=0,
                status='disabled',
                own_limit_exhausted=?,
                disable_reason='manual',
                is_online=0,
                updated_at=?
            WHERE id=?
            """,
            (own_exhausted, now_text(), int(client_id)),
        )


def _inbound_label(ids: list[int], mapping: dict[int, dict[str, Any]]) -> str:
    names: list[str] = []
    for iid in ids:
        row = mapping.get(int(iid))
        label = str((row or {}).get("name") or (row or {}).get("label") or f"#{iid}")
        if label not in names:
            names.append(label)
    if not names:
        return "—"
    if len(names) <= 2:
        return " · ".join(names)
    return f"{names[0]} +{len(names)-1}"


@router.get("/clients")
def list_admin_clients(
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    _ensure_schema()
    _sync_if_due()

    try:
        inbound_map = _inbound_map()
    except Exception:
        inbound_map = {}

    with connect_db() as con:
        rows = con.execute(
            """
            SELECT c.*,
                   r.username AS owner_username,
                   COALESCE(l.cumulative_used_bytes,0) AS cumulative_used_bytes
            FROM clients c
            LEFT JOIN representatives r ON r.id=c.seller_rep_id
            LEFT JOIN traffic_ledger l ON l.client_id=c.id
            WHERE COALESCE(c.status,'')!='deleted'
            ORDER BY c.id DESC
            """
        ).fetchall()

    clients: list[dict[str, Any]] = []
    active = online = disabled = expired = 0
    for row in rows:
        local = dict(row)
        status = _client_status(local)
        is_online = bool(to_int(local.get("is_online"), 0))
        enabled = bool(to_int(local.get("enabled"), 1))
        used = max(0, to_int(local.get("cumulative_used_bytes"), 0))
        limit = max(0, to_int(local.get("total_limit_bytes"), 0))
        percent = min(100.0, used / limit * 100.0) if limit > 0 else 0.0
        ids = parse_ids(local.get("inbound_ids"))

        if status == "Active":
            active += 1
        else:
            disabled += 1
        if status == "Expired":
            expired += 1
        if is_online:
            online += 1

        owner_id = to_int(local.get("seller_rep_id"), 0)
        owner = str(local.get("owner_username") or (f"#{owner_id}" if owner_id else "Super Admin"))
        clients.append({
            "id": int(local["id"]),
            "username": str(local.get("email") or ""),
            "owner": owner,
            "owner_id": owner_id,
            "status": status,
            "enabled": enabled,
            "online": is_online,
            "expires_in": _expiry_label(local.get("expire_at_ms")),
            "expire_at_ms": to_int(local.get("expire_at_ms"), 0),
            "used_bytes": used,
            "limit_bytes": limit,
            "usage_percent": round(percent, 4),
            "inbound_ids": ids,
            "inbound": _inbound_label(ids, inbound_map),
            "age": _age_label(local.get("created_at")),
            "created_at": str(local.get("created_at") or ""),
            "updated_at": str(local.get("updated_at") or ""),
            "disable_reason": str(local.get("disable_reason") or ""),
            "rep_quota_hold": bool(to_int(local.get("rep_quota_hold"), 0)),
            "own_limit_exhausted": bool(to_int(local.get("own_limit_exhausted"), 0)),
        })

    return {
        "ok": True,
        "poll_hint_ms": 3000,
        "summary": {
            "total": len(clients),
            "active": active,
            "online": online,
            "disabled": disabled,
            "expired": expired,
        },
        "clients": clients,
    }


@router.get("/clients/{client_id}/details")
def admin_client_details(
    client_id: int,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    _sync_if_due()
    local = _admin_user(client_id)
    panel: dict[str, Any] = {}
    err = ""
    try:
        _, panel = panel_get(XUIClient(), str(local.get("email") or ""))
    except Exception as exc:
        err = str(exc)

    traffic = to_int(panel.get("totalGB"), to_int(local.get("total_limit_bytes"), 0))
    expiry_ms = to_int(panel.get("expiryTime"), to_int(local.get("expire_at_ms"), 0))
    expiry_date = ""
    if expiry_ms > 0:
        with contextlib.suppress(Exception):
            expiry_date = datetime.fromtimestamp(expiry_ms / 1000).strftime("%Y-%m-%d")
    panel_enabled = panel.get("enable")
    enabled = bool(panel_enabled) if panel_enabled is not None else bool(to_int(local.get("enabled"), 1))

    return {
        "ok": True,
        "user": {
            "id": int(client_id),
            "username": str(local.get("email") or ""),
            "owner_id": to_int(local.get("seller_rep_id"), 0),
            "owner": str(local.get("owner_username") or ""),
            "traffic_gb": round(traffic / 1024 / 1024 / 1024, 4),
            "expiry_date": expiry_date,
            "enabled": enabled,
            "comment": strip_internal_comment(panel.get("comment") or local.get("panel_comment")),
            "inbound_ids": inbound_ids_for(panel, local),
            "limit_ip": to_int(panel.get("limitIp"), to_int(local.get("limit_ip"), 0)),
            "telegram_user_id": str(panel.get("tgId") or panel.get("tg_id") or ""),
            "uuid": safe_uuid(panel, local),
            "sub_id": safe_sub(panel, local),
            "panel_connected": not bool(err),
            "panel_error": err,
        },
    }


@router.get("/clients/{client_id}/inbounds")
def admin_client_inbounds(
    client_id: int,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    local = _admin_user(client_id)
    rep = _rep_for_client(local)
    try:
        live = _live_inbounds()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load live x-ui inbounds: {exc}")

    live_ids = [to_int(row.get("id"), 0) for row in live if to_int(row.get("id"), 0) > 0]
    permitted = set(_rep_allowed_ids(rep, live_ids))
    # Keep already-attached inbounds visible even if permission was later removed.
    permitted.update(parse_ids(local.get("inbound_ids")))
    rows = [row for row in live if to_int(row.get("id"), 0) in permitted]

    return {
        "ok": True,
        "live": True,
        "poll_hint_ms": 3000,
        "inbounds": rows,
    }


@router.put("/clients/{client_id}")
def modify_admin_client(
    client_id: int,
    body: ModifyUserBody,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    _sync_if_due()
    local = _admin_user(client_id)
    rep_id = to_int(local.get("seller_rep_id"), 0)
    ids = _validate_admin_inbounds(local, body.inbound_ids, allow_current=True)
    tg = str(body.telegram_user_id or "").strip()
    if tg and not tg.isdigit():
        raise HTTPException(status_code=400, detail="Telegram User ID must be numeric")

    total_bytes = gb_to_bytes(body.traffic_gb)
    expiry_ms = expiry_to_ms(body.expiry_date)
    if body.enabled:
        ok, reason = _can_enable(local, total_bytes=total_bytes, expiry_ms=expiry_ms)
        if not ok:
            raise HTTPException(status_code=409, detail=reason)

    try:
        result = safe_update(
            xui=XUIClient(),
            local=local,
            rep_id=rep_id,
            inbound_ids=ids,
            total_bytes=total_bytes,
            expiry_ms=expiry_ms,
            limit_ip=body.limit_ip,
            enabled=body.enabled,
            comment=make_comment(rep_id, str(local.get("email") or ""), body.comment),
            telegram_id=int(tg) if tg else 0,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    c = result["client"]
    with connect_db() as con:
        con.execute(
            """
            UPDATE clients
            SET uuid=?, sub_id=?, inbound_ids=?, total_limit_bytes=?, expire_at_ms=?,
                panel_comment=?, group_name=?, limit_ip=?, updated_at=?
            WHERE id=?
            """,
            (
                c["id"], c["subId"], json.dumps(ids), c["totalGB"], c["expiryTime"],
                c["comment"], c["group"], c["limitIp"], now_text(), int(client_id),
            ),
        )
        _update_local_lifecycle(
            con,
            int(client_id),
            enabled=bool(c["enable"]),
            total_bytes=to_int(c["totalGB"], 0),
            expiry_ms=to_int(c["expiryTime"], 0),
        )
        con.commit()

    with contextlib.suppress(Exception):
        from backend.reseller_live_quota import reconcile_quotas

        reconcile_quotas(XUIClient())
    return {"ok": True, "xui_method": result["method"]}


@router.get("/clients/{client_id}/access")
def admin_client_access(
    client_id: int,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    local = _admin_user(client_id)
    try:
        return {"ok": True, **access_bundle(XUIClient(), local)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to load client links: " + str(exc))


@router.post("/clients/{client_id}/toggle")
def toggle_admin_client(
    client_id: int,
    body: ToggleBody,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    _sync_if_due()
    local = _admin_user(client_id)
    rep_id = to_int(local.get("seller_rep_id"), 0)

    if body.enabled:
        ok, reason = _can_enable(local)
        if not ok:
            raise HTTPException(status_code=409, detail=reason)

    try:
        result = safe_update(
            xui=XUIClient(),
            local=local,
            rep_id=rep_id,
            enabled=body.enabled,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    with connect_db() as con:
        _update_local_lifecycle(
            con,
            int(client_id),
            enabled=bool(body.enabled),
            total_bytes=to_int(local.get("total_limit_bytes"), 0),
            expiry_ms=to_int(local.get("expire_at_ms"), 0),
        )
        con.commit()

    return {"ok": True, "enabled": body.enabled, "xui_method": result["method"]}


@router.post("/clients/{client_id}/reset-usage")
def reset_admin_client_usage(
    client_id: int,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    local = _admin_user(client_id)
    email = str(local.get("email") or "")
    xui = XUIClient()
    errors: list[str] = []
    ok = False
    try:
        xui.request("POST", "/panel/api/clients/resetTraffic/" + quote(email, safe=""))
        ok = True
    except Exception as exc:
        errors.append(str(exc))

    if not ok:
        successes = 0
        for iid in parse_ids(local.get("inbound_ids")):
            try:
                xui.request("POST", f"/panel/api/inbounds/{int(iid)}/resetClientTraffic/" + quote(email, safe=""))
                successes += 1
            except Exception as exc:
                errors.append(f"inbound {iid}: {exc}")
        ok = successes > 0

    if not ok:
        raise HTTPException(status_code=502, detail="x-ui traffic reset failed: " + " | ".join(errors[-8:]))

    # Do not touch cumulative_used_bytes. Only reset the panel baseline.
    with connect_db() as con:
        if table_exists(con, "traffic_ledger"):
            cols = table_columns(con, "traffic_ledger")
            sets: list[str] = []
            vals: list[Any] = []
            for col in ("last_panel_up", "last_panel_down", "last_panel_total", "last_panel_used_bytes"):
                if col in cols:
                    sets.append(f"{col}=?")
                    vals.append(0)
            if "last_seen_at" in cols:
                sets.append("last_seen_at=?")
                vals.append(now_text())
            if sets:
                vals.append(int(client_id))
                con.execute(f"UPDATE traffic_ledger SET {', '.join(sets)} WHERE client_id=?", tuple(vals))
        con.execute("UPDATE clients SET panel_used_bytes=0, updated_at=? WHERE id=?", (now_text(), int(client_id)))
        con.commit()

    return {"ok": True, "note": "Panel traffic reset; representative cumulative usage preserved."}


@router.post("/clients/{client_id}/revoke-subscription")
def revoke_admin_client_subscription(
    client_id: int,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    local = _admin_user(client_id)
    rep_id = to_int(local.get("seller_rep_id"), 0)
    new_sub = secrets.token_urlsafe(10).replace("-", "").replace("_", "")[:14]
    try:
        result = safe_update(
            xui=XUIClient(),
            local=local,
            rep_id=rep_id,
            sub_override=new_sub,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    with connect_db() as con:
        con.execute(
            "UPDATE clients SET sub_id=?, updated_at=? WHERE id=?",
            (new_sub, now_text(), int(client_id)),
        )
        con.commit()

    return {"ok": True, "sub_id": new_sub, "xui_method": result["method"]}


@router.delete("/clients/{client_id}")
def remove_admin_client(
    client_id: int,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    _require_admin(xui_session)
    _sync_if_due()
    local = _admin_user(client_id)
    rep_id = to_int(local.get("seller_rep_id"), 0)

    try:
        panel_result = delete_from_panel(XUIClient(), local)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="x-ui delete failed; local client was kept. " + str(exc))

    ensure_deleted_usage_schema()
    archived_used = to_int(local.get("cumulative_used_bytes"), 0)
    with connect_db() as con:
        if table_exists(con, "traffic_ledger"):
            row = con.execute(
                "SELECT cumulative_used_bytes FROM traffic_ledger WHERE client_id=?",
                (int(client_id),),
            ).fetchone()
            if row:
                archived_used = max(archived_used, to_int(row["cumulative_used_bytes"], 0))

        con.execute(
            """
            INSERT INTO deleted_client_usage(
                client_id,email,seller_rep_id,owner_rep_id,cumulative_used_bytes,deleted_at,reason
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
              client_id=excluded.client_id,
              seller_rep_id=excluded.seller_rep_id,
              owner_rep_id=excluded.owner_rep_id,
              cumulative_used_bytes=MAX(deleted_client_usage.cumulative_used_bytes, excluded.cumulative_used_bytes),
              deleted_at=excluded.deleted_at,
              reason=excluded.reason
            """,
            (
                int(client_id), str(local.get("email") or ""), rep_id,
                to_int(local.get("owner_rep_id"), rep_id), archived_used, now_text(), "admin_delete",
            ),
        )
        con.execute("DELETE FROM clients WHERE id=?", (int(client_id),))
        if table_exists(con, "traffic_ledger"):
            con.execute("DELETE FROM traffic_ledger WHERE client_id=?", (int(client_id),))
        if rep_id > 0:
            con.execute(
                """
                UPDATE representatives
                SET total_users=(
                    SELECT COUNT(*) FROM clients
                    WHERE seller_rep_id=? AND COALESCE(status,'')!='deleted'
                ), updated_at=?
                WHERE id=?
                """,
                (rep_id, now_text(), rep_id),
            )
        con.commit()

    return {
        "ok": True,
        "deleted": local.get("email"),
        "archived_used_bytes": archived_used,
        "panel_delete": panel_result,
    }
