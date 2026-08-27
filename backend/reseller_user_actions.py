from __future__ import annotations

import contextlib
import io
import json
import re
import secrets
import sqlite3
from datetime import datetime
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field

from backend.reseller_profile import SESSION_COOKIE, connect_db, get_reseller_from_session
from backend.reseller_users import ensure_users_schema
from backend.reseller_create_user import allowed_inbound_ids, expiry_to_ms, gb_to_bytes, normalize_inbound_ids
from backend.xui_client import XUI_BASE_URL, XUIClient, XUIError, env_bool, env_string

router = APIRouter(prefix="/api/reseller", tags=["Reseller User Actions"])

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


class ModifyUserBody(BaseModel):
    traffic_gb: float = Field(default=0, ge=0, le=100000)
    expiry_date: str = ""
    enabled: bool = True
    comment: str = ""
    inbound_ids: list[int] = []
    limit_ip: int = Field(default=0, ge=0, le=1000)
    telegram_user_id: str = ""


class ToggleBody(BaseModel):
    enabled: bool


def now_text() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def to_int(value, default=0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(value))
    except Exception:
        return default


def valid_uuid(value) -> str:
    s = str(value or "").strip()
    return s if UUID_RE.match(s) else ""


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def table_columns(con: sqlite3.Connection, name: str) -> set[str]:
    if not table_exists(con, name):
        return set()
    return {str(r["name"]) for r in con.execute(f"PRAGMA table_info({name})").fetchall()}


def extract_client(data) -> dict:
    if not isinstance(data, dict):
        return {}
    obj = data
    for key in ("obj", "data", "result"):
        if isinstance(obj.get(key), dict):
            obj = obj[key]
            break
    if isinstance(obj.get("client"), dict):
        return obj["client"]
    if isinstance(obj.get("clients"), list) and obj["clients"] and isinstance(obj["clients"][0], dict):
        return obj["clients"][0]
    if isinstance(obj.get("settings"), str):
        with contextlib.suppress(Exception):
            clients = (json.loads(obj["settings"]) or {}).get("clients") or []
            if clients and isinstance(clients[0], dict):
                return clients[0]
    return obj if isinstance(obj, dict) else {}


def extract_links(data) -> list[str]:
    out: list[str] = []

    def walk(v):
        if isinstance(v, str):
            s = v.strip()
            if "://" in s and s not in out:
                out.append(s)
            return
        if isinstance(v, dict):
            for k in ("link", "url", "uri", "config", "subscription", "subscription_url", "subLink", "sub_link"):
                if k in v:
                    walk(v[k])
            for k in ("obj", "data", "result", "links", "configs", "uris", "items"):
                if k in v:
                    walk(v[k])
            return
        if isinstance(v, (list, tuple, set)):
            for x in v:
                walk(x)

    walk(data)
    return out


def parse_ids(value) -> list[int]:
    if value is None:
        return []
    if isinstance(value, list):
        return normalize_inbound_ids(value)
    with contextlib.suppress(Exception):
        return normalize_inbound_ids(json.loads(str(value)))
    return normalize_inbound_ids(value)


def owned_user(client_id: int, reseller_id: int) -> dict:
    ensure_users_schema()
    with connect_db() as con:
        row = con.execute(
            "SELECT * FROM clients WHERE id=? AND seller_rep_id=? AND COALESCE(status,'')!='deleted'",
            (int(client_id), int(reseller_id)),
        ).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    return dict(row)


def panel_get(xui: XUIClient, email: str) -> tuple[dict, dict]:
    raw = xui.get_client(email)
    return (raw if isinstance(raw, dict) else {}, extract_client(raw))


def safe_uuid(panel: dict, local: dict) -> str:
    for src in (panel, local):
        for k in ("uuid", "clientUuid", "client_uuid", "clientId", "client_id", "password", "id"):
            u = valid_uuid(src.get(k))
            if u:
                return u
    return ""


def safe_sub(panel: dict, local: dict) -> str:
    for src in (panel, local):
        for k in ("subId", "sub_id", "subscription_id"):
            s = str(src.get(k) or "").strip()
            if s and s.lower() not in ("0", "none", "null"):
                return s
    return ""


def inbound_ids_for(panel: dict, local: dict) -> list[int]:
    for k in ("inboundIds", "inbound_ids", "inbounds"):
        ids = parse_ids(panel.get(k))
        if ids:
            return ids
    return parse_ids(local.get("inbound_ids"))


def strip_internal_comment(value) -> str:
    out = []
    for raw in str(value or "").split("|"):
        p = raw.strip()
        low = p.lower()
        if not p or low == "reseller-panel" or low.startswith(("seller_rep=", "owner_rep=", "username=", "seller_name=")):
            continue
        out.append(p)
    return " | ".join(out)


def make_comment(rep_id: int, username: str, comment: str) -> str:
    text = f"reseller-panel | seller_rep={rep_id} | username={username}"
    comment = str(comment or "").strip()
    return text + (" | " + comment if comment else "")


def validate_inbounds(rep_id: int, requested: list[int], xui: XUIClient) -> list[int]:
    ids = normalize_inbound_ids(requested)
    if not ids:
        raise HTTPException(400, "Select at least one inbound")
    panel_ids = [int(r.get("id") or 0) for r in xui.inbounds() if int(r.get("id") or 0) > 0]
    allowed = set(allowed_inbound_ids(rep_id, panel_ids))
    if any(i not in allowed for i in ids):
        raise HTTPException(403, "One or more selected inbounds are not allowed")
    return ids


def safe_update(
    *, xui: XUIClient, local: dict, rep_id: int, inbound_ids=None,
    total_bytes=None, expiry_ms=None, limit_ip=None, enabled=None,
    comment=None, telegram_id=None, sub_override=None,
) -> dict:
    email = str(local.get("email") or "").strip()
    _, panel = panel_get(xui, email)
    uid = safe_uuid(panel, local)
    if not uid:
        raise XUIError("Valid client UUID could not be found. Update cancelled to protect the client.")
    sub_id = str(sub_override).strip() if sub_override is not None else safe_sub(panel, local)
    if not sub_id:
        raise XUIError("Subscription ID could not be found.")
    ids = normalize_inbound_ids(inbound_ids) if inbound_ids is not None else inbound_ids_for(panel, local)
    if not ids:
        raise XUIError("Client has no attached inbounds.")

    current_enabled = panel.get("enable")
    if current_enabled is None:
        current_enabled = bool(local.get("enabled", 1))

    client = {
        "email": email,
        "id": uid,
        "uuid": uid,
        "password": uid,
        "subId": sub_id,
        "flow": str(panel.get("flow") or ""),
        "enable": bool(enabled) if enabled is not None else bool(current_enabled),
        "limitIp": max(0, int(limit_ip)) if limit_ip is not None else to_int(panel.get("limitIp"), to_int(local.get("limit_ip"), 0)),
        "totalGB": max(0, int(total_bytes)) if total_bytes is not None else to_int(panel.get("totalGB"), to_int(local.get("total_limit_bytes"), 0)),
        "expiryTime": max(0, int(expiry_ms)) if expiry_ms is not None else to_int(panel.get("expiryTime"), to_int(local.get("expire_at_ms"), 0)),
        "tgId": max(0, int(telegram_id)) if telegram_id is not None else to_int(panel.get("tgId"), 0),
        "comment": str(comment) if comment is not None else str(panel.get("comment") or local.get("panel_comment") or ""),
        "group": str(panel.get("group") or local.get("group_name") or f"rep_{rep_id}"),
        "reset": to_int(panel.get("reset"), 0),
    }

    attempts = [
        ("client_inboundIds", {"client": dict(client), "inboundIds": ids}),
        ("client_inbound_ids", {"client": dict(client), "inbound_ids": ids}),
        ("client_inbounds", {"client": dict(client), "inbounds": ids}),
        ("top_level", {**client, "inboundIds": ids, "inbound_ids": ids}),
    ]
    errors = []
    for name, payload in attempts:
        try:
            resp = xui.request("POST", "/panel/api/clients/update/" + quote(email, safe=""), json=payload)
            with contextlib.suppress(Exception):
                xui.attach(email, ids)
            return {"ok": True, "method": name, "response": resp, "client": client, "inbound_ids": ids}
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise XUIError("x-ui update failed after all API variants: " + " | ".join(errors[-4:]))


def public_config_link(link: str, email: str, uid: str) -> str:
    if not env_bool("PUBLIC_LINK_REWRITE", False) or not link.lower().startswith("vless://"):
        return link
    host = env_string("PUBLIC_CONFIG_HOST")
    if not host:
        return link
    port = env_string("PUBLIC_CONFIG_PORT", "443")
    sid = env_string("PUBLIC_REALITY_SID")
    try:
        p = urlsplit(link)
        userinfo = p.netloc.rsplit("@", 1)[0] if "@" in p.netloc else ""
        userinfo = uid or userinfo
        if not userinfo:
            return link
        netloc = f"{userinfo}@{host}:{port}" if port else f"{userinfo}@{host}"
        q = dict(parse_qsl(p.query, keep_blank_values=True))
        if sid:
            q["sid"] = sid
        return urlunsplit((p.scheme, netloc, p.path, urlencode(q), p.fragment or email))
    except Exception:
        return link


def subscription_url(all_links: list[str], sub_id: str) -> str:
    # === ADMIN STEP 5 EXTERNAL PROXY OUTPUT ===
    # Admin external subscription settings take precedence over the private
    # x-ui panel URL. If unset, preserve the exact old fallback behavior.
    with contextlib.suppress(Exception):
        from backend.admin_settings import public_subscription_override
        overridden = public_subscription_override(sub_id)
        if overridden:
            return overridden
    for l in all_links:
        if l.lower().startswith(("http://", "https://")) and "/sub/" in l.lower():
            return l
    base = env_string("PUBLIC_SUB_BASE_URL").rstrip("/")
    if base and sub_id:
        return base + "/sub/" + quote(sub_id, safe="")
    if XUI_BASE_URL and sub_id:
        with contextlib.suppress(Exception):
            p = urlsplit(XUI_BASE_URL)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}/sub/" + quote(sub_id, safe="")
    return ""


def link_label(link: str, index: int) -> str:
    with contextlib.suppress(Exception):
        frag = unquote(urlsplit(link).fragment or "").strip()
        if frag:
            return frag
    scheme = link.split("://", 1)[0].upper() if "://" in link else "CONFIG"
    return f"{scheme} Config {index}"


def make_qr_svg(text: str) -> str:
    if not text:
        return ""
    image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=7, border=2)
    buf = io.BytesIO()
    image.save(buf)
    return buf.getvalue().decode("utf-8", errors="replace")


def access_bundle(xui: XUIClient, local: dict) -> dict:
    email = str(local.get("email") or "").strip()
    raw_client, panel = {}, {}
    with contextlib.suppress(Exception):
        raw_client, panel = panel_get(xui, email)
    raw_links = {}
    with contextlib.suppress(Exception):
        raw_links = xui.request("GET", "/panel/api/clients/links/" + quote(email, safe=""))
    all_links = extract_links(raw_links) or extract_links(raw_client)
    uid = safe_uuid(panel, local)
    sub_id = safe_sub(panel, local)
    configs = []
    attached_ids = inbound_ids_for(panel, local)
    for link in all_links:
        low = link.lower()
        if low.startswith(("vless://", "vmess://", "trojan://", "ss://", "socks://")):
            rewritten = None
            with contextlib.suppress(Exception):
                from backend.admin_settings import rewrite_client_config
                rewritten = rewrite_client_config(link, attached_ids, xui)
            configs.append(rewritten if rewritten else link)
    sub_url = subscription_url(all_links, sub_id)
    return {
        "username": email,
        "uuid": uid,
        "sub_id": sub_id,
        "subscription_url": sub_url,
        "links": configs,
        "configs": [{"name": link_label(link, i), "link": link} for i, link in enumerate(configs, 1)],
        "qr_svg": make_qr_svg(sub_url),
    }


def delete_from_panel(xui: XUIClient, local: dict) -> dict:
    email = str(local.get("email") or "").strip()
    panel = {}
    with contextlib.suppress(Exception):
        _, panel = panel_get(xui, email)
    uid = safe_uuid(panel, local)
    ids = inbound_ids_for(panel, local)
    errors = []
    variants = [
        ("DELETE", "/panel/api/clients/" + quote(email, safe=""), None),
        ("POST", "/panel/api/clients/delete/" + quote(email, safe=""), None),
        ("POST", "/panel/api/clients/del/" + quote(email, safe=""), None),
        ("POST", "/panel/api/clients/" + quote(email, safe="") + "/delete", None),
        ("POST", "/panel/api/clients/delete", {"email": email, "id": uid}),
    ]
    for method, path, payload in variants:
        try:
            resp = xui.request(method, path, **({"json": payload} if payload is not None else {}))
            return {"ok": True, "method": f"{method} {path}", "response": resp}
        except Exception as e:
            errors.append(f"{method} {path}: {e}")
    if uid and ids:
        ok = 0
        classic_errors = []
        for iid in ids:
            try:
                xui.request("POST", f"/panel/api/inbounds/{int(iid)}/delClient/" + quote(uid, safe=""))
                ok += 1
            except Exception as e:
                classic_errors.append(f"inbound {iid}: {e}")
        if ok > 0:
            return {"ok": True, "method": "classic delClient", "deleted_from_inbounds": ok, "errors": classic_errors}
        errors.extend(classic_errors)
    raise XUIError("Delete from x-ui failed after all variants: " + " | ".join(errors[-12:]))


def ensure_deleted_usage_schema():
    with connect_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS deleted_client_usage(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                email TEXT UNIQUE,
                seller_rep_id INTEGER,
                owner_rep_id INTEGER,
                cumulative_used_bytes INTEGER DEFAULT 0,
                deleted_at TEXT,
                reason TEXT
            )
        """)
        con.commit()


@router.get("/users/{client_id}/details")
def user_details(client_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    rep = get_reseller_from_session(xui_session)
    local = owned_user(client_id, int(rep["id"]))
    panel, err = {}, ""
    try:
        _, panel = panel_get(XUIClient(), str(local.get("email") or ""))
    except Exception as e:
        err = str(e)
    traffic = to_int(panel.get("totalGB"), to_int(local.get("total_limit_bytes"), 0))
    expiry_ms = to_int(panel.get("expiryTime"), to_int(local.get("expire_at_ms"), 0))
    expiry_date = ""
    if expiry_ms > 0:
        with contextlib.suppress(Exception):
            expiry_date = datetime.fromtimestamp(expiry_ms / 1000).strftime("%Y-%m-%d")
    en = panel.get("enable")
    enabled = bool(en) if en is not None else bool(local.get("enabled", 1))
    return {
        "ok": True,
        "user": {
            "id": int(client_id),
            "username": local.get("email"),
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


@router.put("/users/{client_id}")
def modify_user(client_id: int, body: ModifyUserBody, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    rep = get_reseller_from_session(xui_session)
    rep_id = int(rep["id"])
    local = owned_user(client_id, rep_id)
    xui = XUIClient()
    ids = validate_inbounds(rep_id, body.inbound_ids, xui)
    tg = str(body.telegram_user_id or "").strip()
    if tg and not tg.isdigit():
        raise HTTPException(400, "Telegram User ID must be numeric")
    try:
        result = safe_update(
            xui=xui, local=local, rep_id=rep_id, inbound_ids=ids,
            total_bytes=gb_to_bytes(body.traffic_gb), expiry_ms=expiry_to_ms(body.expiry_date),
            limit_ip=body.limit_ip, enabled=body.enabled,
            comment=make_comment(rep_id, str(local.get("email") or ""), body.comment),
            telegram_id=int(tg) if tg else 0,
        )
    except Exception as e:
        raise HTTPException(502, str(e))
    c = result["client"]
    with connect_db() as con:
        con.execute("""
            UPDATE clients SET uuid=?,sub_id=?,inbound_ids=?,total_limit_bytes=?,expire_at_ms=?,enabled=?,status=?,panel_comment=?,group_name=?,limit_ip=?,updated_at=?
            WHERE id=? AND seller_rep_id=?
        """, (
            c["id"], c["subId"], json.dumps(ids), c["totalGB"], c["expiryTime"], 1 if c["enable"] else 0,
            "active" if c["enable"] else "disabled", c["comment"], c["group"], c["limitIp"], now_text(), int(client_id), rep_id,
        ))
        con.commit()
    return {"ok": True, "xui_method": result["method"]}


@router.get("/users/{client_id}/access")
def user_access(client_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    rep = get_reseller_from_session(xui_session)
    local = owned_user(client_id, int(rep["id"]))
    try:
        return {"ok": True, **access_bundle(XUIClient(), local)}
    except Exception as e:
        raise HTTPException(502, "Unable to load client links: " + str(e))


@router.post("/users/{client_id}/toggle")
def toggle_user(client_id: int, body: ToggleBody, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    rep = get_reseller_from_session(xui_session)
    rep_id = int(rep["id"])
    local = owned_user(client_id, rep_id)
    try:
        result = safe_update(xui=XUIClient(), local=local, rep_id=rep_id, enabled=body.enabled)
    except Exception as e:
        raise HTTPException(502, str(e))
    with connect_db() as con:
        con.execute("UPDATE clients SET enabled=?,status=?,updated_at=? WHERE id=? AND seller_rep_id=?", (
            1 if body.enabled else 0, "active" if body.enabled else "disabled", now_text(), int(client_id), rep_id,
        ))
        con.commit()
    return {"ok": True, "enabled": body.enabled, "xui_method": result["method"]}


@router.post("/users/{client_id}/reset-usage")
def reset_usage(client_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    rep = get_reseller_from_session(xui_session)
    rep_id = int(rep["id"])
    local = owned_user(client_id, rep_id)
    email = str(local.get("email") or "")
    xui = XUIClient()
    errors = []
    ok = False
    try:
        xui.request("POST", "/panel/api/clients/resetTraffic/" + quote(email, safe=""))
        ok = True
    except Exception as e:
        errors.append(str(e))
    if not ok:
        successes = 0
        for iid in parse_ids(local.get("inbound_ids")):
            try:
                xui.request("POST", f"/panel/api/inbounds/{int(iid)}/resetClientTraffic/" + quote(email, safe=""))
                successes += 1
            except Exception as e:
                errors.append(f"inbound {iid}: {e}")
        ok = successes > 0
    if not ok:
        raise HTTPException(502, "x-ui traffic reset failed: " + " | ".join(errors[-8:]))

    # cumulative_used_bytes intentionally stays untouched.
    with connect_db() as con:
        if table_exists(con, "traffic_ledger"):
            cols = table_columns(con, "traffic_ledger")
            sets, vals = [], []
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
        con.execute("UPDATE clients SET updated_at=? WHERE id=? AND seller_rep_id=?", (now_text(), int(client_id), rep_id))
        con.commit()
    return {"ok": True, "note": "Panel traffic reset; representative cumulative usage preserved."}


@router.post("/users/{client_id}/revoke-subscription")
def revoke_subscription(client_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    rep = get_reseller_from_session(xui_session)
    rep_id = int(rep["id"])
    local = owned_user(client_id, rep_id)
    new_sub = secrets.token_urlsafe(10).replace("-", "").replace("_", "")[:14]
    xui = XUIClient()
    try:
        result = safe_update(xui=xui, local=local, rep_id=rep_id, sub_override=new_sub)
    except Exception as e:
        raise HTTPException(502, str(e))
    with connect_db() as con:
        con.execute("UPDATE clients SET sub_id=?,updated_at=? WHERE id=? AND seller_rep_id=?", (new_sub, now_text(), int(client_id), rep_id))
        con.commit()
    return {"ok": True, "sub_id": new_sub, "xui_method": result["method"]}


@router.delete("/users/{client_id}")
def remove_user(client_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    rep = get_reseller_from_session(xui_session)
    rep_id = int(rep["id"])
    local = owned_user(client_id, rep_id)
    try:
        panel_result = delete_from_panel(XUIClient(), local)
    except Exception as e:
        raise HTTPException(502, "x-ui delete failed; local user was kept. " + str(e))

    ensure_deleted_usage_schema()
    archived_used = 0
    with connect_db() as con:
        if table_exists(con, "traffic_ledger"):
            row = con.execute("SELECT cumulative_used_bytes FROM traffic_ledger WHERE client_id=?", (int(client_id),)).fetchone()
            archived_used = int(row["cumulative_used_bytes"] or 0) if row else 0
        con.execute("""
            INSERT INTO deleted_client_usage(client_id,email,seller_rep_id,owner_rep_id,cumulative_used_bytes,deleted_at,reason)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
              client_id=excluded.client_id,
              seller_rep_id=excluded.seller_rep_id,
              owner_rep_id=excluded.owner_rep_id,
              cumulative_used_bytes=MAX(deleted_client_usage.cumulative_used_bytes, excluded.cumulative_used_bytes),
              deleted_at=excluded.deleted_at,
              reason=excluded.reason
        """, (
            int(client_id), str(local.get("email") or ""), rep_id,
            to_int(local.get("owner_rep_id"), rep_id), archived_used, now_text(), "delete",
        ))
        con.execute("DELETE FROM clients WHERE id=? AND seller_rep_id=?", (int(client_id), rep_id))
        if table_exists(con, "traffic_ledger"):
            con.execute("DELETE FROM traffic_ledger WHERE client_id=?", (int(client_id),))
        con.execute("""
            UPDATE representatives SET total_users=(
                SELECT COUNT(*) FROM clients WHERE seller_rep_id=? AND COALESCE(status,'')!='deleted'
            ) WHERE id=?
        """, (rep_id, rep_id))
        con.commit()
    return {"ok": True, "deleted": local.get("email"), "archived_used_bytes": archived_used, "panel_delete": panel_result}
