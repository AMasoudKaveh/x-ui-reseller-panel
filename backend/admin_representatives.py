from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field

from backend.reseller_profile import (
    SESSION_COOKIE,
    connect_db,
    ensure_profile_schema,
)
from backend.xui_client import XUIClient


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Representatives"],
)

PBKDF2_ROUNDS = 200_000
GB = 1024 ** 3
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")


class RepresentativeCreateBody(BaseModel):
    username: str
    password: str
    quota_bytes: int = Field(default=0, ge=0)
    status: str = "Active"
    inbound_ids: list[int] = Field(default_factory=list)


class RepresentativeUpdateBody(BaseModel):
    username: str
    password: str = ""
    quota_bytes: int = Field(default=0, ge=0)
    status: str = "Active"
    inbound_ids: list[int] = Field(default_factory=list)


class RepresentativeStatusBody(BaseModel):
    status: str


class RepresentativeRechargeBody(BaseModel):
    add_bytes: int = Field(ge=0)


def now_text() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return bool(
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(con, table):
        return set()
    return {
        str(row["name"])
        for row in con.execute(f"PRAGMA table_info({table})").fetchall()
    }


def ensure_column(
    con: sqlite3.Connection,
    table: str,
    name: str,
    ddl: str,
) -> None:
    if name not in columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def ensure_admin_schema() -> None:
    ensure_profile_schema()

    with connect_db() as con:
        ensure_column(con, "representatives", "updated_at", "TEXT")
        # NULL means unrestricted for old representatives. The JSON string []
        # means explicitly no inbound access.
        ensure_column(con, "representatives", "allowed_inbound_ids", "TEXT")
        ensure_column(con, "representatives", "quota_locked", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(con, "representatives", "quota_locked_at", "TEXT")
        ensure_column(con, "representatives", "quota_prev_status", "TEXT")
        ensure_column(con, "representatives", "quota_last_reconciled_at", "TEXT")
        ensure_column(con, "representatives", "deleted_at", "TEXT")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS deleted_representatives(
                original_rep_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                quota_bytes INTEGER NOT NULL DEFAULT 0,
                used_bytes INTEGER NOT NULL DEFAULT 0,
                client_count INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NOT NULL
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS deleted_client_usage(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                email TEXT UNIQUE,
                seller_rep_id INTEGER,
                owner_rep_id INTEGER,
                cumulative_used_bytes INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                reason TEXT
            )
            """
        )

        if table_exists(con, "clients"):
            # Keep this router safe even when Step 7 columns were not created
            # yet. These are the lifecycle fields used by quota/admin holds.
            client_columns = {
                "enabled": "INTEGER NOT NULL DEFAULT 1",
                "status": "TEXT",
                "is_online": "INTEGER NOT NULL DEFAULT 0",
                "updated_at": "TEXT",
                "expire_at_ms": "INTEGER NOT NULL DEFAULT 0",
                "own_limit_exhausted": "INTEGER NOT NULL DEFAULT 0",
                "disable_reason": "TEXT NOT NULL DEFAULT ''",
                "rep_quota_hold": "INTEGER NOT NULL DEFAULT 0",
                "quota_prev_enabled": "INTEGER NOT NULL DEFAULT 0",
                "quota_prev_status": "TEXT",
                "quota_disabled_at": "TEXT",
                "rep_admin_hold": "INTEGER NOT NULL DEFAULT 0",
                "rep_admin_prev_enabled": "INTEGER NOT NULL DEFAULT 0",
                "rep_admin_prev_status": "TEXT",
                "rep_admin_disabled_at": "TEXT",
            }
            for name, ddl in client_columns.items():
                ensure_column(con, "clients", name, ddl)

        con.commit()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ROUNDS,
    ).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def require_admin(token: str | None) -> dict[str, Any]:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_admin_schema()
    now = int(time.time())

    with connect_db() as con:
        session = con.execute(
            """
            SELECT role, account_id, expires_at
            FROM auth_sessions
            WHERE token=?
            """,
            (token,),
        ).fetchone()

        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")

        if int(session["expires_at"] or 0) <= now:
            con.execute("DELETE FROM auth_sessions WHERE token=?", (token,))
            con.commit()
            raise HTTPException(status_code=401, detail="Session expired")

        if str(session["role"] or "") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        admin = con.execute(
            "SELECT id, username, is_active FROM admins WHERE id=?",
            (int(session["account_id"]),),
        ).fetchone()

        if not admin or not bool(admin["is_active"]):
            raise HTTPException(status_code=403, detail="Admin account is inactive")

        return dict(admin)


def normalize_status(value: str) -> str:
    value = str(value or "").strip().lower()
    if value in {"active", "enabled", "on"}:
        return "active"
    if value in {"suspended", "suspend", "inactive", "disabled", "off"}:
        return "suspended"
    raise HTTPException(status_code=400, detail="Status must be Active or Suspended")


def normalize_inbound_ids(values: list[int] | None) -> list[int]:
    result: list[int] = []
    for value in values or []:
        try:
            inbound_id = int(value)
        except (TypeError, ValueError):
            continue
        if inbound_id > 0 and inbound_id not in result:
            result.append(inbound_id)
    return result


def parse_inbound_ids(raw: Any) -> list[int]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple, set)):
        return normalize_inbound_ids(list(raw))
    try:
        parsed = json.loads(str(raw))
        if isinstance(parsed, list):
            return normalize_inbound_ids(parsed)
    except Exception:
        pass
    return normalize_inbound_ids(re.findall(r"\d+", str(raw)))


def validate_username(username: str) -> str:
    username = str(username or "").strip()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3-64 characters and contain only letters, numbers, . _ @ -",
        )
    return username


def validate_password(password: str, *, required: bool) -> str:
    password = str(password or "")
    if required and len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if password and len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    return password


def panel_inbounds() -> list[dict[str, Any]]:
    try:
        return XUIClient().inbounds()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load x-ui inbounds: {exc}")


def validate_allowed_inbounds(inbound_ids: list[int]) -> list[int]:
    requested = normalize_inbound_ids(inbound_ids)
    if not requested:
        return []

    panel_ids = {int(item.get("id") or 0) for item in panel_inbounds()}
    invalid = [item for item in requested if item not in panel_ids]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown inbound IDs: {', '.join(map(str, invalid))}",
        )
    return requested


def date_label(value: Any) -> str:
    if value in (None, ""):
        return ""

    if isinstance(value, (int, float)) or str(value).strip().isdigit():
        with contextlib.suppress(Exception):
            return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d")

    text = str(value).strip()
    if len(text) >= 10:
        return text[:10]
    return text


def get_rep(con: sqlite3.Connection, rep_id: int) -> dict[str, Any]:
    row = con.execute(
        "SELECT * FROM representatives WHERE id=?",
        (int(rep_id),),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Representative not found")
    return dict(row)


def client_counts(con: sqlite3.Connection, rep_id: int) -> tuple[int, int]:
    if not table_exists(con, "clients"):
        return 0, 0

    client_cols = columns(con, "clients")
    where = "seller_rep_id=?"
    if "status" in client_cols:
        where += " AND COALESCE(status,'')!='deleted'"

    total_row = con.execute(
        f"SELECT COUNT(*) AS total FROM clients WHERE {where}",
        (rep_id,),
    ).fetchone()
    total = int(total_row["total"] or 0)

    online = 0
    if "is_online" in client_cols:
        online_row = con.execute(
            f"SELECT COUNT(*) AS total FROM clients WHERE {where} AND COALESCE(is_online,0)=1",
            (rep_id,),
        ).fetchone()
        online = int(online_row["total"] or 0)

    return total, online


def rep_payload(con: sqlite3.Connection, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    rep = dict(row)
    rep_id = int(rep.get("id") or 0)
    total_users, online = client_counts(con, rep_id)

    if "total_users" in columns(con, "representatives"):
        con.execute(
            "UPDATE representatives SET total_users=? WHERE id=?",
            (total_users, rep_id),
        )

    raw_status = str(rep.get("status") or "active").lower()
    quota_locked = bool(int(rep.get("quota_locked") or 0))
    visible_status = "Active" if raw_status == "active" and not quota_locked else "Suspended"

    raw_allowed = rep.get("allowed_inbound_ids")
    # NULL/empty on legacy rows means unrestricted. For the admin UI we return
    # all current inbounds so the existing modal accurately reflects access.
    if raw_allowed in (None, ""):
        try:
            allowed = [int(item.get("id") or 0) for item in XUIClient().inbounds()]
            allowed = [item for item in allowed if item > 0]
        except Exception:
            allowed = []
    else:
        allowed = parse_inbound_ids(raw_allowed)

    return {
        "id": rep_id,
        "username": str(rep.get("username") or ""),
        "quota_bytes": max(0, int(rep.get("quota_bytes") or 0)),
        "used_bytes": max(0, int(rep.get("used_bytes") or 0)),
        "users": total_users,
        "online": online,
        "status": visible_status,
        "raw_status": raw_status,
        "quota_locked": quota_locked,
        "inbound_ids": allowed,
        "created_at": date_label(rep.get("created_at")),
        "updated_at": date_label(rep.get("updated_at") or rep.get("created_at")),
    }


def invalidate_rep_sessions(con: sqlite3.Connection, rep_id: int) -> None:
    if table_exists(con, "auth_sessions"):
        con.execute(
            "DELETE FROM auth_sessions WHERE role='reseller' AND account_id=?",
            (int(rep_id),),
        )


def _panel_set_enabled(local: dict[str, Any], enabled: bool) -> None:
    xui = XUIClient()
    rep_id = int(local.get("seller_rep_id") or 0)

    # Reuse the already-tested user action updater when available.
    try:
        from backend.reseller_user_actions import safe_update

        safe_update(
            xui=xui,
            local=local,
            rep_id=rep_id,
            enabled=bool(enabled),
        )
        return
    except ImportError:
        pass
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    # Step 7 live/quota module has the same safe UUID-preserving behavior.
    try:
        from backend.reseller_live_quota import set_panel_enabled

        if set_panel_enabled(xui, local, bool(enabled)):
            return
        raise RuntimeError("x-ui rejected enable/disable update")
    except ImportError as exc:
        raise RuntimeError("No safe x-ui client updater is available") from exc


def suspend_rep_clients(rep_id: int, reason: str = "rep_admin_suspend") -> dict[str, Any]:
    ensure_admin_schema()
    disabled: list[str] = []
    failures: list[str] = []

    with connect_db() as con:
        if not table_exists(con, "clients"):
            return {"disabled": disabled, "failures": failures}
        rows = [
            dict(row)
            for row in con.execute(
                """
                SELECT * FROM clients
                WHERE seller_rep_id=?
                  AND COALESCE(status,'')!='deleted'
                ORDER BY id
                """,
                (rep_id,),
            ).fetchall()
        ]

    now_ms = int(time.time() * 1000)

    for local in rows:
        if not bool(local.get("enabled")):
            continue
        if int(local.get("rep_admin_hold") or 0):
            continue
        if int(local.get("rep_quota_hold") or 0):
            continue
        if int(local.get("own_limit_exhausted") or 0):
            continue

        expiry_ms = int(local.get("expire_at_ms") or 0)
        if expiry_ms > 0 and expiry_ms <= now_ms:
            continue

        existing_reason = str(local.get("disable_reason") or "").strip()
        if existing_reason in {"manual", "external", "client_quota", "expired"}:
            continue

        email = str(local.get("email") or "")
        try:
            _panel_set_enabled(local, False)
        except Exception as exc:
            failures.append(f"{email}: {exc}")
            continue

        with connect_db() as con:
            con.execute(
                """
                UPDATE clients
                SET rep_admin_hold=1,
                    rep_admin_prev_enabled=1,
                    rep_admin_prev_status=?,
                    rep_admin_disabled_at=?,
                    disable_reason=?,
                    enabled=0,
                    status='admin_disabled',
                    is_online=0,
                    updated_at=?
                WHERE id=? AND seller_rep_id=?
                """,
                (
                    str(local.get("status") or "active"),
                    now_text(),
                    reason,
                    now_text(),
                    int(local.get("id") or 0),
                    rep_id,
                ),
            )
            con.commit()
        disabled.append(email)

    return {"disabled": disabled, "failures": failures}


def restore_rep_clients(rep_id: int) -> dict[str, Any]:
    ensure_admin_schema()
    restored: list[str] = []
    failures: list[str] = []

    with connect_db() as con:
        rep = get_rep(con, rep_id)
        quota = int(rep.get("quota_bytes") or 0)
        used = int(rep.get("used_bytes") or 0)
        if int(rep.get("quota_locked") or 0) or (quota > 0 and used >= quota):
            return {"restored": restored, "failures": failures, "skipped": "quota_locked"}

        if not table_exists(con, "clients"):
            return {"restored": restored, "failures": failures}

        rows = [
            dict(row)
            for row in con.execute(
                """
                SELECT * FROM clients
                WHERE seller_rep_id=?
                  AND rep_admin_hold=1
                  AND COALESCE(status,'')!='deleted'
                ORDER BY id
                """,
                (rep_id,),
            ).fetchall()
        ]

    now_ms = int(time.time() * 1000)

    for local in rows:
        client_id = int(local.get("id") or 0)
        email = str(local.get("email") or "")
        expiry_ms = int(local.get("expire_at_ms") or 0)
        expired = expiry_ms > 0 and expiry_ms <= now_ms
        own_limit = bool(int(local.get("own_limit_exhausted") or 0))

        if expired or own_limit or int(local.get("rep_quota_hold") or 0):
            reason = "expired" if expired else ("client_quota" if own_limit else "rep_quota")
            with connect_db() as con:
                con.execute(
                    """
                    UPDATE clients
                    SET rep_admin_hold=0,
                        rep_admin_prev_enabled=0,
                        rep_admin_prev_status=NULL,
                        rep_admin_disabled_at=NULL,
                        disable_reason=?,
                        updated_at=?
                    WHERE id=? AND seller_rep_id=?
                    """,
                    (reason, now_text(), client_id, rep_id),
                )
                con.commit()
            continue

        if not bool(local.get("rep_admin_prev_enabled")):
            with connect_db() as con:
                con.execute(
                    """
                    UPDATE clients
                    SET rep_admin_hold=0,
                        rep_admin_prev_status=NULL,
                        rep_admin_disabled_at=NULL,
                        disable_reason='external',
                        updated_at=?
                    WHERE id=? AND seller_rep_id=?
                    """,
                    (now_text(), client_id, rep_id),
                )
                con.commit()
            continue

        try:
            _panel_set_enabled(local, True)
        except Exception as exc:
            failures.append(f"{email}: {exc}")
            continue

        previous_status = str(local.get("rep_admin_prev_status") or "active")
        if previous_status in {"admin_disabled", "disabled", "inactive", "blocked", "quota_disabled"}:
            previous_status = "active"

        with connect_db() as con:
            con.execute(
                """
                UPDATE clients
                SET rep_admin_hold=0,
                    rep_admin_prev_enabled=0,
                    rep_admin_prev_status=NULL,
                    rep_admin_disabled_at=NULL,
                    disable_reason='',
                    enabled=1,
                    status=?,
                    updated_at=?
                WHERE id=? AND seller_rep_id=?
                """,
                (previous_status, now_text(), client_id, rep_id),
            )
            con.commit()
        restored.append(email)

    return {"restored": restored, "failures": failures}


def reconcile_quota() -> dict[str, Any]:
    try:
        from backend.reseller_live_quota import reconcile_quotas
        return reconcile_quotas(XUIClient())
    except ImportError:
        return {"ok": True, "skipped": "live_quota_module_not_installed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# === ADMIN STEP 2: LIVE READ-ONLY INBOUNDS ===
_ADMIN_INBOUND_SPEED_STATE: dict[int, tuple[int, float]] = {}


def _ai_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("obj", "data", "result", "items", "list", "inbounds"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _ai_json(value: Any, default: Any) -> Any:
    if isinstance(value, type(default)):
        return value
    if isinstance(value, str):
        with contextlib.suppress(Exception):
            parsed = json.loads(value)
            if isinstance(parsed, type(default)):
                return parsed
    return default


def _ai_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _ai_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "enabled", "active"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "inactive"}:
        return False
    return default


def _ai_first_number(row: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        if key in row:
            value = _ai_int(row.get(key), 0)
            if value:
                return value
    return 0


def _ai_online_emails(xui: XUIClient, known_emails: set[str]) -> tuple[set[str], bool]:
    if not known_emails:
        return set(), True

    canonical = {
        str(email).strip().casefold(): str(email).strip()
        for email in known_emails
        if str(email).strip()
    }

    def parse(value: Any) -> set[str]:
        found: set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, str):
                key = node.strip().casefold()
                if key in canonical:
                    found.add(canonical[key])
                return

            if isinstance(node, list):
                for item in node:
                    walk(item)
                return

            if not isinstance(node, dict):
                return

            for key, nested in node.items():
                folded = str(key or "").strip().casefold()
                if folded in canonical and _ai_bool(nested, False):
                    found.add(canonical[folded])

            email = str(
                node.get("email")
                or node.get("clientEmail")
                or node.get("client_email")
                or node.get("name")
                or ""
            ).strip()
            if email.casefold() in canonical:
                active = None
                for key in ("online", "isOnline", "is_online", "connected"):
                    if key in node:
                        active = _ai_bool(node.get(key), False)
                        break
                if active is True:
                    found.add(canonical[email.casefold()])

            for nested in node.values():
                walk(nested)

        walk(value)
        return found

    attempts: list[tuple[str, str, dict[str, Any] | None]] = [
        ("GET", "/panel/api/inbounds/onlines", None),
        ("POST", "/panel/api/inbounds/onlines", {}),
        ("GET", "/panel/api/clients/onlines", None),
        ("GET", "/panel/api/clients/online", None),
    ]

    for method, endpoint, payload in attempts:
        try:
            if payload is None:
                response = xui.request(method, endpoint)
            else:
                response = xui.request(method, endpoint, json=payload)
            return parse(response), True
        except Exception:
            continue

    return set(), False


def _ai_live_inbounds() -> list[dict[str, Any]]:
    xui = XUIClient()
    raw = xui.request("GET", "/panel/api/inbounds/list")
    rows = _ai_rows(raw)

    prepared: list[dict[str, Any]] = []
    known_emails: set[str] = set()
    now_ms = int(time.time() * 1000)

    for row in rows:
        inbound_id = _ai_int(row.get("id"), 0)
        if inbound_id <= 0:
            continue

        stream = _ai_json(row.get("streamSettings"), {})
        settings = _ai_json(row.get("settings"), {})

        settings_clients = settings.get("clients") if isinstance(settings, dict) else []
        if not isinstance(settings_clients, list):
            settings_clients = []

        stats = (
            row.get("clientStats")
            or row.get("client_stats")
            or row.get("clientTraffics")
            or row.get("client_traffics")
            or []
        )
        stats = _ai_json(stats, [])
        if not isinstance(stats, list):
            stats = []

        client_emails: set[str] = set()
        online_hints: set[str] = set()

        for client in settings_clients:
            if not isinstance(client, dict):
                continue
            email = str(client.get("email") or "").strip()
            if email:
                client_emails.add(email)
                known_emails.add(email)

        stats_traffic = 0
        for stat in stats:
            if not isinstance(stat, dict):
                continue
            email = str(
                stat.get("email")
                or stat.get("clientEmail")
                or stat.get("client_email")
                or ""
            ).strip()
            if email:
                client_emails.add(email)
                known_emails.add(email)

            up = _ai_first_number(stat, ("up", "upload", "uplink", "upBytes", "up_bytes"))
            down = _ai_first_number(stat, ("down", "download", "downlink", "downBytes", "down_bytes"))
            stats_traffic += max(0, up) + max(0, down)

            direct_online = None
            for key in ("online", "isOnline", "is_online", "connected"):
                if key in stat:
                    direct_online = _ai_bool(stat.get(key), False)
                    break
            if email and direct_online is True:
                online_hints.add(email)

            last_online = _ai_first_number(
                stat,
                ("lastOnline", "last_online", "lastOnlineAt", "last_online_at"),
            )
            if 0 < last_online < 10_000_000_000:
                last_online *= 1000
            if email and last_online > 0 and abs(now_ms - last_online) <= 15_000:
                online_hints.add(email)

        up = _ai_first_number(row, ("up", "upload", "uplink", "upBytes", "up_bytes"))
        down = _ai_first_number(row, ("down", "download", "downlink", "downBytes", "down_bytes"))
        traffic = max(0, up) + max(0, down)
        if traffic <= 0:
            traffic = max(0, stats_traffic)

        port = _ai_int(row.get("port"), 0)
        protocol = str(row.get("protocol") or "").strip().lower()
        network = str(
            (stream.get("network") if isinstance(stream, dict) else "")
            or row.get("network")
            or ""
        ).strip().lower()
        security = str(
            (stream.get("security") if isinstance(stream, dict) else "")
            or row.get("security")
            or ""
        ).strip().lower()
        remark = str(row.get("remark") or row.get("tag") or "").strip()
        label = remark or f"in-{port}-{network or protocol or 'tcp'}"

        prepared.append({
            "id": inbound_id,
            "name": label,
            "label": label,
            "node": str(row.get("node") or row.get("nodeName") or "Local panel").strip() or "Local panel",
            "port": port,
            "protocol": protocol,
            "network": network,
            "security": security,
            "enabled": _ai_bool(row.get("enable", row.get("enabled", True)), True),
            "clients": len(client_emails),
            "client_emails": client_emails,
            "online_hints": online_hints,
            "traffic_bytes": traffic,
        })

    online_emails, online_endpoint_ok = _ai_online_emails(xui, known_emails)
    monotonic_now = time.monotonic()
    current_ids: set[int] = set()
    output: list[dict[str, Any]] = []

    for item in prepared:
        inbound_id = int(item["id"])
        current_ids.add(inbound_id)
        traffic = int(item["traffic_bytes"])
        previous = _ADMIN_INBOUND_SPEED_STATE.get(inbound_id)
        speed_bps = 0
        if previous is not None:
            previous_traffic, previous_at = previous
            elapsed = monotonic_now - previous_at
            if elapsed > 0 and traffic >= previous_traffic:
                speed_bps = int((traffic - previous_traffic) / elapsed)
        _ADMIN_INBOUND_SPEED_STATE[inbound_id] = (traffic, monotonic_now)

        source_online = online_emails if online_endpoint_ok else set(item["online_hints"])
        online_count = len(set(item["client_emails"]) & source_online)

        output.append({
            "id": inbound_id,
            "name": item["name"],
            "label": item["label"],
            "node": item["node"],
            "port": int(item["port"]),
            "protocol": item["protocol"],
            "network": item["network"],
            "security": item["security"],
            "enabled": bool(item["enabled"]),
            "clients": int(item["clients"]),
            "online": online_count,
            "traffic_bytes": traffic,
            "speed_bps": max(0, speed_bps),
        })

    for inbound_id in list(_ADMIN_INBOUND_SPEED_STATE):
        if inbound_id not in current_ids:
            _ADMIN_INBOUND_SPEED_STATE.pop(inbound_id, None)

    return sorted(output, key=lambda item: int(item["id"]))


@router.get("/inbounds")
def admin_inbounds(
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    try:
        rows = _ai_live_inbounds()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load live x-ui inbounds: {exc}")
    return {
        "ok": True,
        "read_only": True,
        "live": True,
        "poll_hint_ms": 3000,
        "inbounds": rows,
    }


@router.get("/representatives")
def list_representatives(
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    ensure_admin_schema()

    with connect_db() as con:
        rows = con.execute(
            """
            SELECT * FROM representatives
            WHERE COALESCE(deleted_at,'')=''
            ORDER BY id DESC
            """
        ).fetchall()
        payload = [rep_payload(con, row) for row in rows]
        con.commit()

        archived_row = con.execute(
            "SELECT COALESCE(SUM(used_bytes),0) AS total FROM deleted_representatives"
        ).fetchone()
        archived_used_bytes = int(archived_row["total"] or 0) if archived_row else 0

    return {
        "ok": True,
        "representatives": payload,
        "archived_used_bytes": archived_used_bytes,
    }


@router.post("/representatives")
def create_representative(
    body: RepresentativeCreateBody,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    ensure_admin_schema()

    username = validate_username(body.username)
    password = validate_password(body.password, required=True)
    status = normalize_status(body.status)
    inbound_ids = validate_allowed_inbounds(body.inbound_ids)
    quota_bytes = max(0, int(body.quota_bytes or 0))
    created_at = int(time.time())

    with connect_db() as con:
        duplicate = con.execute(
            "SELECT id FROM representatives WHERE username=?",
            (username,),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="Username already exists")

        cur = con.execute(
            """
            INSERT INTO representatives(
                username,
                password_hash,
                status,
                created_at,
                quota_bytes,
                used_bytes,
                total_users,
                updated_at,
                allowed_inbound_ids,
                quota_locked
            )
            VALUES(?,?,?,?,?,0,0,?,?,0)
            """,
            (
                username,
                hash_password(password),
                status,
                created_at,
                quota_bytes,
                now_text(),
                json.dumps(inbound_ids),
            ),
        )
        rep_id = int(cur.lastrowid)
        con.commit()

    if status == "suspended":
        # New reps have no clients, but this keeps lifecycle semantics uniform.
        with connect_db() as con:
            invalidate_rep_sessions(con, rep_id)
            con.commit()

    with connect_db() as con:
        representative = rep_payload(con, get_rep(con, rep_id))
        con.commit()

    return {"ok": True, "representative": representative}


@router.patch("/representatives/{rep_id}")
def update_representative(
    rep_id: int,
    body: RepresentativeUpdateBody,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    ensure_admin_schema()

    username = validate_username(body.username)
    password = validate_password(body.password, required=False)
    desired_status = normalize_status(body.status)
    inbound_ids = validate_allowed_inbounds(body.inbound_ids)
    quota_bytes = max(0, int(body.quota_bytes or 0))

    with connect_db() as con:
        current = get_rep(con, rep_id)
        if str(current.get("status") or "") == "deleted" or current.get("deleted_at"):
            raise HTTPException(status_code=404, detail="Representative not found")

        duplicate = con.execute(
            "SELECT id FROM representatives WHERE username=? AND id<>?",
            (username, rep_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="Username already exists")

        used_bytes = max(0, int(current.get("used_bytes") or 0))
        if desired_status == "active" and quota_bytes > 0 and used_bytes >= quota_bytes:
            raise HTTPException(
                status_code=409,
                detail="Quota is already exhausted. Increase quota above current usage before activating this representative.",
            )

        previous_status = str(current.get("status") or "active").lower()
        status_to_store = desired_status

        params: list[Any] = [
            username,
            quota_bytes,
            status_to_store,
            json.dumps(inbound_ids),
            now_text(),
        ]
        password_sql = ""
        if password:
            password_sql = ", password_hash=?"
            params.append(hash_password(password))
        params.append(rep_id)

        con.execute(
            f"""
            UPDATE representatives
            SET username=?,
                quota_bytes=?,
                status=?,
                allowed_inbound_ids=?,
                updated_at=?
                {password_sql}
            WHERE id=?
            """,
            tuple(params),
        )

        if password or username != str(current.get("username") or ""):
            invalidate_rep_sessions(con, rep_id)

        con.commit()

    lifecycle: dict[str, Any] = {}

    if desired_status == "suspended":
        # Always retry the hold operation. This makes a second Save repair any
        # previous x-ui failure instead of silently leaving a client enabled.
        lifecycle["suspend"] = suspend_rep_clients(rep_id)
        with connect_db() as con:
            invalidate_rep_sessions(con, rep_id)
            con.commit()

    quota_result = reconcile_quota()

    if desired_status == "active":
        # A quota recharge may have just removed quota_locked. Reload before
        # restoring only users held by an explicit admin suspension.
        lifecycle["activate"] = restore_rep_clients(rep_id)

    with connect_db() as con:
        representative = rep_payload(con, get_rep(con, rep_id))
        con.commit()

    return {
        "ok": True,
        "representative": representative,
        "lifecycle": lifecycle,
        "quota_reconcile": quota_result,
    }


@router.post("/representatives/{rep_id}/status")
def set_representative_status(
    rep_id: int,
    body: RepresentativeStatusBody,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    ensure_admin_schema()
    desired = normalize_status(body.status)

    with connect_db() as con:
        current = get_rep(con, rep_id)
        quota = int(current.get("quota_bytes") or 0)
        used = int(current.get("used_bytes") or 0)
        if desired == "active" and quota > 0 and used >= quota:
            raise HTTPException(
                status_code=409,
                detail="Quota is exhausted. Recharge the representative before activation.",
            )

        con.execute(
            "UPDATE representatives SET status=?, updated_at=? WHERE id=?",
            (desired, now_text(), rep_id),
        )
        if desired == "suspended":
            invalidate_rep_sessions(con, rep_id)
        con.commit()

    # Reconcile quota before activation so a freshly recharged representative
    # can restore admin-held clients in the same action.
    quota_result = reconcile_quota()
    lifecycle = suspend_rep_clients(rep_id) if desired == "suspended" else restore_rep_clients(rep_id)

    with connect_db() as con:
        representative = rep_payload(con, get_rep(con, rep_id))
        con.commit()

    return {
        "ok": True,
        "representative": representative,
        "lifecycle": lifecycle,
        "quota_reconcile": quota_result,
    }


@router.post("/representatives/{rep_id}/recharge")
def recharge_representative(
    rep_id: int,
    body: RepresentativeRechargeBody,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    ensure_admin_schema()

    with connect_db() as con:
        current = get_rep(con, rep_id)
        old_quota = max(0, int(current.get("quota_bytes") or 0))
        new_quota = old_quota + max(0, int(body.add_bytes or 0))
        con.execute(
            "UPDATE representatives SET quota_bytes=?, updated_at=? WHERE id=?",
            (new_quota, now_text(), rep_id),
        )
        con.commit()

    quota_result = reconcile_quota()

    with connect_db() as con:
        representative = rep_payload(con, get_rep(con, rep_id))
        con.commit()

    return {
        "ok": True,
        "representative": representative,
        "quota_reconcile": quota_result,
    }


@router.post("/representatives/{rep_id}/reset-usage")
def reset_representative_usage(
    rep_id: int,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    ensure_admin_schema()

    with connect_db() as con:
        get_rep(con, rep_id)

        if table_exists(con, "traffic_ledger") and table_exists(con, "clients"):
            con.execute(
                """
                UPDATE traffic_ledger
                SET cumulative_used_bytes=0
                WHERE client_id IN (
                    SELECT id FROM clients WHERE seller_rep_id=?
                )
                """,
                (rep_id,),
            )

        if table_exists(con, "deleted_client_usage"):
            deleted_cols = columns(con, "deleted_client_usage")
            if "seller_rep_id" in deleted_cols and "cumulative_used_bytes" in deleted_cols:
                con.execute(
                    """
                    UPDATE deleted_client_usage
                    SET cumulative_used_bytes=0
                    WHERE seller_rep_id=?
                    """,
                    (rep_id,),
                )

        con.execute(
            "UPDATE representatives SET used_bytes=0, updated_at=? WHERE id=?",
            (now_text(), rep_id),
        )
        con.commit()

    # last_panel_used_bytes is intentionally preserved, so old x-ui traffic is
    # the new baseline and only traffic generated after this reset is counted.
    quota_result = reconcile_quota()

    with connect_db() as con:
        representative = rep_payload(con, get_rep(con, rep_id))
        con.commit()

    return {
        "ok": True,
        "representative": representative,
        "quota_reconcile": quota_result,
        "note": "Representative cumulative period reset. Client x-ui counters were not reset.",
    }


@router.delete("/representatives/{rep_id}")
def delete_representative(
    rep_id: int,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    require_admin(xui_session)
    ensure_admin_schema()

    # First make sure every currently eligible x-ui client is disabled.  We do
    # not remove clients from x-ui here; the primary x-ui panel remains the
    # infrastructure source of truth and the disabled configs can still be
    # inspected there if needed.
    lifecycle = suspend_rep_clients(rep_id, reason="rep_deleted")
    if lifecycle.get("failures"):
        raise HTTPException(
            status_code=502,
            detail="Could not disable every active x-ui client. Representative was not removed; retry after x-ui is reachable. "
            + " | ".join(lifecycle.get("failures") or []),
        )

    with connect_db() as con:
        rep = get_rep(con, rep_id)
        username = str(rep.get("username") or "")
        quota_bytes = max(0, int(rep.get("quota_bytes") or 0))
        used_bytes = max(0, int(rep.get("used_bytes") or 0))

        client_rows: list[dict[str, Any]] = []
        if table_exists(con, "clients"):
            client_rows = [
                dict(row)
                for row in con.execute(
                    "SELECT * FROM clients WHERE seller_rep_id=?",
                    (rep_id,),
                ).fetchall()
            ]

        # Preserve every client's cumulative traffic before removing local rows.
        # This keeps historical accounting intact even after a representative is
        # permanently removed from the active database tables.
        if client_rows:
            for local in client_rows:
                client_id = int(local.get("id") or 0)
                email = str(local.get("email") or "")
                cumulative = 0
                if table_exists(con, "traffic_ledger"):
                    row = con.execute(
                        "SELECT cumulative_used_bytes FROM traffic_ledger WHERE client_id=?",
                        (client_id,),
                    ).fetchone()
                    if row:
                        cumulative = max(0, int(row["cumulative_used_bytes"] or 0))

                con.execute(
                    """
                    INSERT INTO deleted_client_usage(
                        client_id,email,seller_rep_id,owner_rep_id,
                        cumulative_used_bytes,deleted_at,reason
                    )
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(email) DO UPDATE SET
                      client_id=excluded.client_id,
                      seller_rep_id=excluded.seller_rep_id,
                      owner_rep_id=excluded.owner_rep_id,
                      cumulative_used_bytes=MAX(
                          deleted_client_usage.cumulative_used_bytes,
                          excluded.cumulative_used_bytes
                      ),
                      deleted_at=excluded.deleted_at,
                      reason=excluded.reason
                    """,
                    (
                        client_id,
                        email,
                        rep_id,
                        int(local.get("owner_rep_id") or rep_id),
                        cumulative,
                        now_text(),
                        "representative_deleted",
                    ),
                )

        con.execute(
            """
            INSERT INTO deleted_representatives(
                original_rep_id,username,quota_bytes,used_bytes,client_count,deleted_at
            )
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(original_rep_id) DO UPDATE SET
              username=excluded.username,
              quota_bytes=excluded.quota_bytes,
              used_bytes=MAX(deleted_representatives.used_bytes, excluded.used_bytes),
              client_count=MAX(deleted_representatives.client_count, excluded.client_count),
              deleted_at=excluded.deleted_at
            """,
            (rep_id, username, quota_bytes, used_bytes, len(client_rows), now_text()),
        )

        invalidate_rep_sessions(con, rep_id)

        if table_exists(con, "traffic_ledger") and client_rows:
            ids = [int(row.get("id") or 0) for row in client_rows if int(row.get("id") or 0) > 0]
            if ids:
                marks = ",".join("?" for _ in ids)
                con.execute(f"DELETE FROM traffic_ledger WHERE client_id IN ({marks})", ids)

        if table_exists(con, "clients"):
            con.execute("DELETE FROM clients WHERE seller_rep_id=?", (rep_id,))

        # Historical traffic_events are intentionally retained.  The admin
        # dashboard uses them for the 7-day traffic chart even after deletion.
        con.execute("DELETE FROM representatives WHERE id=?", (rep_id,))
        con.commit()

    return {
        "ok": True,
        "hard_deleted": True,
        "archived_used_bytes": used_bytes,
        "archived_clients": len(client_rows),
        "lifecycle": lifecycle,
        "note": "Representative permanently deleted; historical traffic was archived.",
    }
