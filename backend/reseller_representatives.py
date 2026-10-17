from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException

from backend.admin_representatives import (
    RepresentativeCreateBody,
    RepresentativeStatusBody,
    RepresentativeUpdateBody,
    delete_representative_subtree,
    ensure_admin_schema,
    get_rep,
    hash_password,
    invalidate_rep_sessions,
    normalize_status,
    now_text,
    parse_inbound_ids,
    reconcile_quota,
    rep_payload,
    representative_deletion_preview,
    restore_rep_clients,
    restrict_descendant_inbounds,
    suspend_rep_clients,
    validate_password,
    validate_username,
)
from backend.reseller_profile import SESSION_COOKIE, connect_db, get_reseller_from_session


router = APIRouter(prefix="/api/reseller/representatives", tags=["Reseller Representatives"])


def _actor(token: str | None) -> dict[str, Any]:
    return dict(get_reseller_from_session(token))


def _owned_child(con, actor_id: int, child_id: int) -> dict[str, Any]:
    row = con.execute(
        "SELECT * FROM representatives WHERE id=? AND parent_rep_id=? AND COALESCE(deleted_at,'')=''",
        (child_id, actor_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sub-representative not found")
    return dict(row)


def _actor_inbounds(actor: dict[str, Any]) -> list[int] | None:
    raw = actor.get("allowed_inbound_ids")
    return None if raw in (None, "") else parse_inbound_ids(raw)


def _validate_child_inbounds(actor: dict[str, Any], requested: list[int]) -> list[int]:
    selected = list(dict.fromkeys(int(item) for item in requested if int(item) > 0))
    allowed = _actor_inbounds(actor)
    if allowed is not None:
        invalid = [item for item in selected if item not in set(allowed)]
        if invalid:
            raise HTTPException(status_code=403, detail="A sub-representative cannot receive inbounds unavailable to its parent")
    return selected


@router.get("")
def list_children(xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    actor = _actor(xui_session)
    ensure_admin_schema()
    with connect_db() as con:
        rows = con.execute(
            "SELECT * FROM representatives WHERE parent_rep_id=? AND COALESCE(deleted_at,'')='' ORDER BY id DESC",
            (int(actor["id"]),),
        ).fetchall()
        payload = [rep_payload(con, row) for row in rows]
        from backend.reseller_live_quota import representative_usage
        deleted_rows = con.execute(
            "SELECT id FROM representatives WHERE parent_rep_id=? AND COALESCE(deleted_at,'')!=''",
            (int(actor["id"]),),
        ).fetchall()
        archived_used = sum(representative_usage(con, int(row["id"])) for row in deleted_rows)
        con.commit()
    return {"ok": True, "representatives": payload, "archived_used_bytes": archived_used}


@router.get("/inbounds")
def child_inbounds(xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    actor = _actor(xui_session)
    from backend.admin_representatives import _ai_live_inbounds
    rows = _ai_live_inbounds()
    allowed = _actor_inbounds(actor)
    if allowed is not None:
        allowed_set = set(allowed)
        rows = [row for row in rows if int(row.get("id") or 0) in allowed_set]
    return {"ok": True, "inbounds": rows}


@router.post("")
def create_child(body: RepresentativeCreateBody, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    actor = _actor(xui_session)
    ensure_admin_schema()
    username = validate_username(body.username)
    password = validate_password(body.password, required=True)
    status = normalize_status(body.status)
    inbound_ids = _validate_child_inbounds(actor, body.inbound_ids)
    with connect_db() as con:
        if con.execute("SELECT 1 FROM representatives WHERE username=?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="Username already exists")
        cur = con.execute(
            """INSERT INTO representatives(
               username,password_hash,status,created_at,quota_bytes,used_bytes,total_users,
               updated_at,allowed_inbound_ids,quota_locked,parent_rep_id)
               VALUES(?,?,?,?,?,0,0,?,?,0,?)""",
            (username, hash_password(password), status, int(time.time()), max(0, int(body.quota_bytes or 0)),
             now_text(), json.dumps(inbound_ids), int(actor["id"])),
        )
        child_id = int(cur.lastrowid)
        con.commit()
        payload = rep_payload(con, get_rep(con, child_id))
        con.commit()
    return {"ok": True, "representative": payload}


@router.patch("/{child_id}")
def update_child(child_id: int, body: RepresentativeUpdateBody, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    actor = _actor(xui_session)
    ensure_admin_schema()
    username = validate_username(body.username)
    password = validate_password(body.password, required=False)
    status = normalize_status(body.status)
    inbound_ids = _validate_child_inbounds(actor, body.inbound_ids)
    with connect_db() as con:
        current = _owned_child(con, int(actor["id"]), child_id)
        if con.execute("SELECT 1 FROM representatives WHERE username=? AND id<>?", (username, child_id)).fetchone():
            raise HTTPException(status_code=409, detail="Username already exists")
        used = int(current.get("used_bytes") or 0)
        quota = max(0, int(body.quota_bytes or 0))
        if status == "active" and quota > 0 and used >= quota:
            raise HTTPException(status_code=409, detail="Quota is exhausted; increase it before activation")
        fields = ["username=?", "quota_bytes=?", "status=?", "allowed_inbound_ids=?", "updated_at=?"]
        params: list[Any] = [username, quota, status, json.dumps(inbound_ids), now_text()]
        if password:
            fields.append("password_hash=?")
            params.append(hash_password(password))
        params.append(child_id)
        con.execute(f"UPDATE representatives SET {', '.join(fields)} WHERE id=?", tuple(params))
        restrict_descendant_inbounds(con, child_id, inbound_ids)
        if password or username != str(current.get("username") or "") or status != "active":
            invalidate_rep_sessions(con, child_id)
        con.commit()
    quota_result = reconcile_quota()
    with connect_db() as con:
        payload = rep_payload(con, get_rep(con, child_id))
        con.commit()
    return {"ok": True, "representative": payload, "quota_reconcile": quota_result}


@router.post("/{child_id}/status")
def set_child_status(child_id: int, body: RepresentativeStatusBody, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    actor = _actor(xui_session)
    desired = normalize_status(body.status)
    with connect_db() as con:
        current = _owned_child(con, int(actor["id"]), child_id)
        if desired == "active" and int(current.get("quota_bytes") or 0) > 0 and int(current.get("used_bytes") or 0) >= int(current.get("quota_bytes") or 0):
            raise HTTPException(status_code=409, detail="Quota is exhausted")
        con.execute("UPDATE representatives SET status=?,updated_at=? WHERE id=?", (desired, now_text(), child_id))
        if desired != "active":
            invalidate_rep_sessions(con, child_id)
        con.commit()
    reconcile_quota()
    with connect_db() as con:
        payload = rep_payload(con, get_rep(con, child_id))
        con.commit()
    return {"ok": True, "representative": payload}


@router.post("/{child_id}/reset-usage")
def reset_child_usage(child_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    actor = _actor(xui_session)
    from backend.reseller_live_quota import sync_all
    result = sync_all(True)
    if not result.get("ok") or result.get("skipped"):
        raise HTTPException(status_code=502, detail="A verified x-ui sync is required before resetting usage")
    with connect_db() as con:
        _owned_child(con, int(actor["id"]), child_id)
        client_ids = {int(row["id"]) for row in con.execute(
            """WITH RECURSIVE tree(id) AS (SELECT id FROM representatives WHERE id=? UNION ALL
               SELECT r.id FROM representatives r JOIN tree t ON r.parent_rep_id=t.id)
               SELECT c.id FROM clients c JOIN tree t ON c.seller_rep_id=t.id WHERE COALESCE(c.status,'')!='deleted'""",
            (child_id,),
        ).fetchall()}
        if client_ids - set(result.get("verified_client_ids") or []):
            raise HTTPException(status_code=502, detail="Some subtree client traffic could not be verified; usage was not reset")
        from backend.reseller_live_quota import representative_usage_tree
        _, raw_subtree, _ = representative_usage_tree(con)
        con.execute(
            "UPDATE representatives SET usage_baseline_bytes=?,used_bytes=0,updated_at=? WHERE id=?",
            (max(0, int(raw_subtree.get(child_id, 0))), now_text(), child_id),
        )
        con.commit()
    reconcile_quota()
    with connect_db() as con:
        payload = rep_payload(con, get_rep(con, child_id))
        con.commit()
    return {"ok": True, "representative": payload}


@router.delete("/{child_id}")
def delete_child(child_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    actor = _actor(xui_session)
    from backend.reseller_live_quota import sync_all
    result = sync_all(True)
    if not result.get("ok") or result.get("skipped"):
        raise HTTPException(status_code=502, detail="A verified x-ui sync is required before deletion")
    with connect_db() as con:
        _owned_child(con, int(actor["id"]), child_id)
    response = delete_representative_subtree(
        child_id,
        {int(value) for value in result.get("verified_client_ids") or []},
    )
    response["quota_reconcile"] = reconcile_quota()
    return response


@router.get("/{child_id}/deletion-preview")
def preview_child_deletion(child_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    actor = _actor(xui_session)
    with connect_db() as con:
        _owned_child(con, int(actor["id"]), child_id)
        return {"ok": True, **representative_deletion_preview(con, child_id)}
