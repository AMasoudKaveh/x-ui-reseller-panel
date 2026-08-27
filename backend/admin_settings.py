from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import backend.admin_representatives as admin_reps
from backend.reseller_profile import SESSION_COOKIE, connect_db
from backend.xui_client import XUIClient

router = APIRouter(prefix="/api/admin/settings", tags=["Admin Settings"])

PBKDF2_ROUNDS = 200_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")
HOST_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
SID_RE = re.compile(r"^[0-9a-fA-F]{0,32}$")
MAX_RESTORE_BYTES = 128 * 1024 * 1024

_SUB_PORT_CACHE: tuple[float, int] = (0.0, 0)


class ConfigProxyBody(BaseModel):
    inbound_id: int = Field(gt=0)
    host: str = ""
    port: int = Field(default=0, ge=0, le=65535)
    reality_sid: str = ""


class SubscriptionProxyBody(BaseModel):
    host: str = ""
    port: int = Field(default=0, ge=0, le=65535)


class CredentialsBody(BaseModel):
    current_password: str
    username: str
    new_password: str = ""


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _require_admin(token: str | None) -> dict[str, Any]:
    return admin_reps.require_admin(token)


def ensure_settings_schema() -> None:
    admin_reps.ensure_admin_schema()
    with connect_db() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT
            )
            """
        )
        con.commit()


def _get_setting(key: str, default: str = "") -> str:
    ensure_settings_schema()
    with connect_db() as con:
        row = con.execute("SELECT value FROM admin_settings WHERE key=?", (key,)).fetchone()
    return str(row["value"] if row else default)


def _set_setting(key: str, value: str) -> None:
    ensure_settings_schema()
    with connect_db() as con:
        con.execute(
            """
            INSERT INTO admin_settings(key,value,updated_at)
            VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
            """,
            (key, str(value), _now()),
        )
        con.commit()


def _normalize_host(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if "://" in text:
        parsed = urlsplit(text)
        text = parsed.hostname or ""
    else:
        text = text.split("/", 1)[0].strip()
        # Keep IPv6 out of this simple UI setting. hostname:port is accepted.
        if text.count(":") == 1:
            left, right = text.rsplit(":", 1)
            if right.isdigit():
                text = left
    text = text.strip().strip(".")
    if not text or " " in text or not HOST_RE.fullmatch(text):
        raise HTTPException(status_code=400, detail="External host is invalid")
    return text


def _config_overrides() -> dict[str, dict[str, Any]]:
    raw = _get_setting("config_proxy_overrides", "{}")
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        try:
            iid = int(key)
        except Exception:
            continue
        if iid <= 0:
            continue
        host = str(value.get("host") or "").strip()
        if not host:
            continue
        out[str(iid)] = {
            "host": host,
            "port": max(0, int(value.get("port") or 0)),
            "reality_sid": str(value.get("reality_sid") or "").strip(),
        }
    return out


def _save_config_overrides(data: dict[str, dict[str, Any]]) -> None:
    _set_setting("config_proxy_overrides", json.dumps(data, separators=(",", ":"), sort_keys=True))


def _find_int_by_keys(value: Any, wanted: set[str]) -> int:
    if isinstance(value, dict):
        for key, nested in value.items():
            folded = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if folded in wanted:
                with contextlib.suppress(Exception):
                    n = int(float(nested))
                    if 1 <= n <= 65535:
                        return n
        for nested in value.values():
            found = _find_int_by_keys(nested, wanted)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_int_by_keys(nested, wanted)
            if found:
                return found
    elif isinstance(value, str):
        with contextlib.suppress(Exception):
            parsed = json.loads(value)
            return _find_int_by_keys(parsed, wanted)
    return 0


def detect_panel_subscription_port(force: bool = False) -> int:
    global _SUB_PORT_CACHE
    now = time.monotonic()
    cached_at, cached_port = _SUB_PORT_CACHE
    if not force and cached_at and now - cached_at < 60:
        return cached_port

    wanted = {
        "subport",
        "subscriptionport",
        "subwebport",
        "sublistenport",
        "subscriptionlistenport",
    }
    xui = XUIClient()
    endpoints = (
        "/panel/api/setting/all",
        "/panel/api/settings/all",
        "/panel/api/setting/getAll",
        "/panel/api/server/getConfigJson",
    )
    detected = 0
    for endpoint in endpoints:
        try:
            data = xui.request("GET", endpoint)
            detected = _find_int_by_keys(data, wanted)
            if detected:
                break
        except Exception:
            continue
    _SUB_PORT_CACHE = (now, detected)
    return detected


def subscription_port_values() -> tuple[int, int, int]:
    manual = 0
    with contextlib.suppress(Exception):
        manual = int(_get_setting("subscription_proxy_port", "0") or 0)
    detected = 0
    with contextlib.suppress(Exception):
        detected = detect_panel_subscription_port()
    effective = manual or detected or 2096
    return manual, detected, effective


def public_subscription_override(sub_id: str) -> str:
    sub_id = str(sub_id or "").strip()
    if not sub_id:
        return ""
    host = _get_setting("subscription_proxy_host", "").strip()
    if not host:
        return ""
    _, _, port = subscription_port_values()
    authority = f"{host}:{port}" if port else host
    return f"https://{authority}/sub/{quote(sub_id, safe='')}"


def _inbound_candidates(inbound_ids: list[int], xui: XUIClient) -> list[dict[str, Any]]:
    wanted = {int(v) for v in inbound_ids if int(v) > 0}
    if not wanted:
        return []
    rows: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        for item in xui.inbounds():
            try:
                iid = int(item.get("id") or 0)
            except Exception:
                continue
            if iid in wanted:
                rows.append(dict(item))
    return rows


def _resolve_inbound_id(link: str, inbound_ids: list[int], xui: XUIClient, override_ids: set[int]) -> int:
    ids = [int(v) for v in inbound_ids if int(v) > 0 and int(v) in override_ids]
    if not ids:
        return 0
    if len(ids) == 1:
        return ids[0]

    try:
        parsed = urlsplit(link)
        port = int(parsed.port or 0)
        scheme = str(parsed.scheme or "").lower()
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        network = str(query.get("type") or query.get("network") or "").lower()
        security = str(query.get("security") or "").lower()
    except Exception:
        return 0

    scored: list[tuple[int, int]] = []
    for item in _inbound_candidates(ids, xui):
        iid = int(item.get("id") or 0)
        if iid not in ids:
            continue
        score = 0
        item_port = int(item.get("port") or 0)
        item_protocol = str(item.get("protocol") or "").lower()
        item_network = str(item.get("network") or "").lower()
        item_security = str(item.get("security") or "").lower()
        if port and item_port == port:
            score += 8
        if scheme and item_protocol and scheme == item_protocol:
            score += 4
        if network and item_network and network == item_network:
            score += 3
        if security and item_security and security == item_security:
            score += 3
        scored.append((score, iid))

    if not scored:
        return 0
    scored.sort(reverse=True)
    if scored[0][0] <= 0:
        return 0
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return 0
    return scored[0][1]


def rewrite_client_config(link: str, inbound_ids: list[int], xui: XUIClient) -> str | None:
    """Return a rewritten link only when an admin per-inbound override applies."""
    overrides = _config_overrides()
    if not overrides:
        return None
    override_ids = {int(k) for k in overrides.keys()}
    inbound_id = _resolve_inbound_id(link, inbound_ids, xui, override_ids)
    if inbound_id <= 0:
        return None
    override = overrides.get(str(inbound_id)) or {}
    host = str(override.get("host") or "").strip()
    if not host:
        return None

    try:
        parsed = urlsplit(link)
        if not parsed.scheme or "@" not in parsed.netloc:
            return None
        userinfo = parsed.netloc.rsplit("@", 1)[0]
        original_port = int(parsed.port or 0)
        external_port = int(override.get("port") or 0) or original_port
        netloc = f"{userinfo}@{host}:{external_port}" if external_port else f"{userinfo}@{host}"
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        sid = str(override.get("reality_sid") or "").strip()
        if sid:
            replaced = False
            new_pairs: list[tuple[str, str]] = []
            for key, value in pairs:
                if key.lower() == "sid":
                    if not replaced:
                        new_pairs.append((key, sid))
                        replaced = True
                else:
                    new_pairs.append((key, value))
            if not replaced:
                new_pairs.append(("sid", sid))
            pairs = new_pairs
        return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(pairs), parsed.fragment))
    except Exception:
        return None


def _verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, salt, expected = str(stored).split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            str(password).encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ROUNDS,
        ).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ROUNDS,
    ).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def _db_backup_bytes() -> bytes:
    fd, name = tempfile.mkstemp(prefix="xui-panel-backup-", suffix=".sqlite3")
    os.close(fd)
    try:
        with connect_db() as src, sqlite3.connect(name) as dst:
            src.backup(dst)
        return Path(name).read_bytes()
    finally:
        with contextlib.suppress(Exception):
            os.unlink(name)


def _validate_restore_db(path: str) -> None:
    with sqlite3.connect(path) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise HTTPException(status_code=400, detail="Backup database failed integrity check")
        tables = {
            str(row[0])
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {"admins", "representatives", "auth_sessions"}
        missing = sorted(required - tables)
        if missing:
            raise HTTPException(status_code=400, detail="Backup is missing required tables: " + ", ".join(missing))


def _save_pre_restore_backup() -> str:
    data = _db_backup_bytes()
    base = Path(__file__).resolve().parent / "data" / "backups"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"before-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
    path.write_bytes(data)
    return str(path)


@router.get("")
def get_admin_settings(xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    admin = _require_admin(xui_session)
    ensure_settings_schema()
    manual, detected, effective = subscription_port_values()
    overrides = _config_overrides()
    return {
        "ok": True,
        "username": str(admin.get("username") or ""),
        "config_overrides": [
            {
                "inbound_id": int(key),
                "host": value.get("host") or "",
                "port": int(value.get("port") or 0),
                "reality_sid": value.get("reality_sid") or "",
            }
            for key, value in sorted(overrides.items(), key=lambda item: int(item[0]))
        ],
        "subscription": {
            "host": _get_setting("subscription_proxy_host", ""),
            "port": manual,
            "detected_port": detected,
            "effective_port": effective,
            "fallback_port": 2096,
        },
    }


@router.put("/config-proxy")
def save_config_proxy(body: ConfigProxyBody, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    _require_admin(xui_session)
    live_ids = {int(row.get("id") or 0) for row in admin_reps.panel_inbounds()}
    if int(body.inbound_id) not in live_ids:
        raise HTTPException(status_code=400, detail="Inbound no longer exists in x-ui")

    overrides = _config_overrides()
    host = _normalize_host(body.host)
    sid = str(body.reality_sid or "").strip()
    if sid and not SID_RE.fullmatch(sid):
        raise HTTPException(status_code=400, detail="Reality SID must be hexadecimal")

    if not host:
        overrides.pop(str(int(body.inbound_id)), None)
    else:
        overrides[str(int(body.inbound_id))] = {
            "host": host,
            "port": int(body.port or 0),
            "reality_sid": sid,
        }
    _save_config_overrides(overrides)
    return {"ok": True}


@router.delete("/config-proxy/{inbound_id}")
def remove_config_proxy(inbound_id: int, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    _require_admin(xui_session)
    overrides = _config_overrides()
    overrides.pop(str(int(inbound_id)), None)
    _save_config_overrides(overrides)
    return {"ok": True}


@router.put("/subscription-proxy")
def save_subscription_proxy(body: SubscriptionProxyBody, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    _require_admin(xui_session)
    host = _normalize_host(body.host)
    _set_setting("subscription_proxy_host", host)
    _set_setting("subscription_proxy_port", str(int(body.port or 0)))
    manual, detected, effective = subscription_port_values()
    return {"ok": True, "port": manual, "detected_port": detected, "effective_port": effective}


@router.put("/credentials")
def update_admin_credentials(body: CredentialsBody, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    admin = _require_admin(xui_session)
    username = str(body.username or "").strip()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=400, detail="Username must be 3-64 characters and contain only letters, numbers, . _ @ -")
    if body.new_password and len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    with connect_db() as con:
        row = con.execute("SELECT id,username,password_hash FROM admins WHERE id=?", (int(admin["id"]),)).fetchone()
        if not row or not _verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        conflict = con.execute("SELECT id FROM admins WHERE username=? AND id<>?", (username, int(admin["id"]))).fetchone()
        if conflict:
            raise HTTPException(status_code=409, detail="Username is already in use")
        if body.new_password:
            con.execute(
                "UPDATE admins SET username=?,password_hash=? WHERE id=?",
                (username, _hash_password(body.new_password), int(admin["id"])),
            )
        else:
            con.execute("UPDATE admins SET username=? WHERE id=?", (username, int(admin["id"])))
        # Keep this browser session, invalidate other admin sessions for this account.
        con.execute(
            "DELETE FROM auth_sessions WHERE role='admin' AND account_id=? AND token<>?",
            (int(admin["id"]), str(xui_session)),
        )
        con.commit()
    return {"ok": True, "username": username}


@router.get("/backup")
def download_backup(xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    _require_admin(xui_session)
    data = _db_backup_bytes()
    filename = f"xui-panel-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
    return Response(
        content=data,
        media_type="application/vnd.sqlite3",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_backup(request: Request, xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    _require_admin(xui_session)
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Backup file is empty")
    if len(payload) > MAX_RESTORE_BYTES:
        raise HTTPException(status_code=413, detail="Backup file is too large")
    if not payload.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=400, detail="Only SQLite backup files created by this panel are accepted")

    fd, temp_name = tempfile.mkstemp(prefix="xui-restore-", suffix=".sqlite3")
    os.close(fd)
    try:
        Path(temp_name).write_bytes(payload)
        _validate_restore_db(temp_name)
        safe_copy = _save_pre_restore_backup()

        with sqlite3.connect(temp_name) as source, connect_db() as target:
            source.backup(target)
            target.commit()

        # Recreate optional columns/settings if the backup came from an older version.
        admin_reps.ensure_admin_schema()
        ensure_settings_schema()
        with connect_db() as con:
            # Restored sessions may be stale. Force a clean login after restore.
            con.execute("DELETE FROM auth_sessions")
            con.commit()

        return {
            "ok": True,
            "relogin_required": True,
            "safety_backup": Path(safe_copy).name,
        }
    finally:
        with contextlib.suppress(Exception):
            os.unlink(temp_name)
