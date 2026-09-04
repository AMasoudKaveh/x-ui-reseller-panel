from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Cookie, HTTPException

from backend.reseller_profile import (
    SESSION_COOKIE,
    connect_db,
    ensure_profile_schema,
    get_reseller_from_session,
)
from backend.xui_client import XUIClient, env_bool, env_string


router = APIRouter(
    prefix="/api/reseller/live",
    tags=["Reseller Live Traffic"],
)


POLL_SECONDS = max(
    5,
    int(float(env_string("POLL_SECONDS", "10") or "10")),
)

LIVE_PROBE_ENABLED = env_bool("ENABLE_LIVE_PROBE", False)

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-"
    r"[0-9a-fA-F]{12}$"
)

_SYNC_LOCK = threading.Lock()
_LAST_SYNC_AT = 0.0
_BG_TASK: asyncio.Task | None = None


def now_text() -> str:
    return datetime.now().isoformat(
        sep=" ",
        timespec="seconds",
    )


def now_ms() -> int:
    return int(time.time() * 1000)


def to_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default

        text = str(value).strip()

        if not text:
            return default

        return int(float(text))

    except Exception:
        return default


def table_exists(
    con: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def table_columns(
    con: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    if not table_exists(con, table_name):
        return set()

    return {
        str(row["name"])
        for row in con.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }


def add_column_if_missing(
    con: sqlite3.Connection,
    table_name: str,
    column_name: str,
    sql_type: str,
) -> None:
    columns = table_columns(
        con,
        table_name,
    )

    if column_name in columns:
        return

    con.execute(
        f"ALTER TABLE {table_name} "
        f"ADD COLUMN {column_name} {sql_type}"
    )


def ensure_live_schema() -> None:
    ensure_profile_schema()

    with connect_db() as con:
        if not table_exists(con, "clients"):
            return

        # Representative quota state is kept separate from manual status.
        # status becomes quota_blocked only while the traffic lock is active,
        # and quota_prev_status lets us restore the previous account state.
        for name, sql_type in {
            "updated_at": "TEXT",
            "quota_locked": "INTEGER NOT NULL DEFAULT 0",
            "quota_locked_at": "TEXT",
            "quota_prev_status": "TEXT",
            "quota_last_reconciled_at": "TEXT",
            "allowed_inbound_ids": "TEXT",
        }.items():
            add_column_if_missing(
                con,
                "representatives",
                name,
                sql_type,
            )

        # No visual UI changes are required for these columns. They only
        # preserve the exact reason/state used by quota enforcement.
        for name, sql_type in {
            "is_online": "INTEGER NOT NULL DEFAULT 0",
            "last_online_at": "TEXT",
            "panel_used_bytes": "INTEGER NOT NULL DEFAULT 0",
            "own_limit_exhausted": "INTEGER NOT NULL DEFAULT 0",
            "disable_reason": "TEXT NOT NULL DEFAULT ''",
            "rep_quota_hold": "INTEGER NOT NULL DEFAULT 0",
            "quota_prev_enabled": "INTEGER NOT NULL DEFAULT 0",
            "quota_prev_status": "TEXT",
            "quota_disabled_at": "TEXT",
            "last_panel_sync_at": "TEXT",
        }.items():
            add_column_if_missing(
                con,
                "clients",
                name,
                sql_type,
            )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS traffic_ledger(
                client_id INTEGER PRIMARY KEY,
                last_panel_up INTEGER NOT NULL DEFAULT 0,
                last_panel_down INTEGER NOT NULL DEFAULT 0,
                last_panel_total INTEGER NOT NULL DEFAULT 0,
                cumulative_used_bytes INTEGER NOT NULL DEFAULT 0,
                reset_detected_count INTEGER NOT NULL DEFAULT 0,
                last_reset_detected_at TEXT,
                last_seen_at TEXT,
                last_panel_used_bytes INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        for name, sql_type in {
            "last_panel_up": "INTEGER NOT NULL DEFAULT 0",
            "last_panel_down": "INTEGER NOT NULL DEFAULT 0",
            "last_panel_total": "INTEGER NOT NULL DEFAULT 0",
            "cumulative_used_bytes": "INTEGER NOT NULL DEFAULT 0",
            "reset_detected_count": "INTEGER NOT NULL DEFAULT 0",
            "last_reset_detected_at": "TEXT",
            "last_seen_at": "TEXT",
            "last_panel_used_bytes": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            add_column_if_missing(
                con,
                "traffic_ledger",
                name,
                sql_type,
            )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS traffic_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                client_id INTEGER,
                email TEXT,
                owner_rep_id INTEGER,
                seller_rep_id INTEGER,
                prev_panel_total INTEGER NOT NULL DEFAULT 0,
                current_panel_total INTEGER NOT NULL DEFAULT 0,
                delta_bytes INTEGER NOT NULL DEFAULT 0,
                cumulative_after INTEGER NOT NULL DEFAULT 0,
                event_type TEXT NOT NULL DEFAULT 'normal_delta'
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

        con.commit()


def flatten(value):
    output = []

    def walk(item):
        output.append(item)

        if isinstance(item, dict):
            for key, nested in item.items():
                output.append(key)
                walk(nested)

        elif isinstance(
            item,
            (list, tuple, set),
        ):
            for nested in item:
                walk(nested)

    walk(value)

    return output


def unwrap_object(value) -> dict:
    if not isinstance(value, dict):
        return {}

    for key in (
        "obj",
        "data",
        "result",
    ):
        nested = value.get(key)

        if isinstance(nested, dict):
            return nested

    return value


def extract_client(value) -> dict:
    obj = unwrap_object(value)

    if not isinstance(obj, dict):
        return {}

    client = obj.get("client")

    if isinstance(client, dict):
        return client

    clients = obj.get("clients")

    if (
        isinstance(clients, list)
        and clients
        and isinstance(clients[0], dict)
    ):
        return clients[0]

    settings = obj.get("settings")

    if isinstance(settings, str):
        with contextlib.suppress(Exception):
            parsed = json.loads(settings)
            clients = parsed.get("clients") or []

            if (
                isinstance(clients, list)
                and clients
                and isinstance(clients[0], dict)
            ):
                return clients[0]

    return obj


def first_number(
    values,
    keys,
) -> int:
    keyset = {
        str(key).lower()
        for key in keys
    }

    found = 0

    for item in flatten(values):
        if not isinstance(item, dict):
            continue

        for key, value in item.items():
            if str(key).lower() in keyset:
                number = to_int(
                    value,
                    -1,
                )

                if number >= 0:
                    found = max(
                        found,
                        number,
                    )

    return found


def first_bool(
    values,
    keys,
):
    keyset = {
        str(key).lower()
        for key in keys
    }

    for item in flatten(values):
        if not isinstance(item, dict):
            continue

        for key, value in item.items():
            if str(key).lower() not in keyset:
                continue

            if isinstance(value, bool):
                return value

            text = str(value or "").strip().lower()

            if text in (
                "1",
                "true",
                "yes",
                "online",
                "enabled",
                "active",
            ):
                return True

            if text in (
                "0",
                "false",
                "no",
                "offline",
                "disabled",
                "inactive",
            ):
                return False

    return None


def truthy_connection(value) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0

    text = str(value or "").strip().lower()

    return (
        bool(text)
        and text not in (
            "0",
            "false",
            "no",
            "none",
            "null",
            "offline",
            "disabled",
            "inactive",
            "[]",
            "{}",
        )
    )


def parse_online_response(
    data,
    known_emails: list[str],
) -> set[str]:
    known = {
        str(email).strip()
        for email in known_emails
        if str(email).strip()
    }

    found: set[str] = set()

    if isinstance(data, dict):
        for email in known:
            if (
                email in data
                and truthy_connection(
                    data.get(email)
                )
            ):
                found.add(email)

    for item in flatten(data):
        if isinstance(item, str):
            text = item.strip()

            if text in known:
                found.add(text)
                continue

            for email in known:
                if (
                    email
                    and email in text
                ):
                    found.add(email)

        elif isinstance(item, dict):
            email = str(
                item.get("email")
                or item.get("client_email")
                or item.get("clientEmail")
                or item.get("client")
                or item.get("name")
                or ""
            ).strip()

            if email in known:
                online_field = None

                for key in (
                    "online",
                    "isOnline",
                    "is_online",
                    "connected",
                    "active",
                ):
                    if key in item:
                        online_field = item.get(key)
                        break

                connection_value = None

                for key in (
                    "ip",
                    "ips",
                    "address",
                    "connections",
                    "connection",
                    "sessions",
                    "onlines",
                    "onlineIps",
                    "online_ips",
                ):
                    if key in item:
                        connection_value = item.get(key)
                        break

                if (
                    online_field is True
                    or truthy_connection(
                        connection_value
                    )
                ):
                    found.add(email)

            for candidate in known:
                if (
                    candidate in item
                    and truthy_connection(
                        item.get(candidate)
                    )
                ):
                    found.add(candidate)

    return found


def fetch_online_emails(
    xui: XUIClient,
    known_emails: list[str],
) -> set[str]:
    emails = [
        str(email).strip()
        for email in known_emails
        if str(email).strip()
    ]

    if not emails:
        return set()

    found: set[str] = set()
    successful_global_call = False

    attempts = [
        (
            "POST",
            "/panel/api/inbounds/onlines",
            {"emails": emails},
        ),
        (
            "POST",
            "/panel/api/inbounds/onlines",
            {"clientEmails": emails},
        ),
        (
            "POST",
            "/panel/api/inbounds/onlines",
            {"clients": emails},
        ),
        (
            "POST",
            "/panel/api/inbounds/onlines",
            emails,
        ),
        (
            "POST",
            "/panel/api/inbounds/onlines",
            {},
        ),
        (
            "GET",
            "/panel/api/inbounds/onlines",
            None,
        ),
        (
            "GET",
            "/panel/api/clients/online",
            None,
        ),
        (
            "GET",
            "/panel/api/clients/onlines",
            None,
        ),
    ]

    for method, path, payload in attempts:
        try:
            if payload is None:
                data = xui.request(
                    method,
                    path,
                )
            else:
                data = xui.request(
                    method,
                    path,
                    json=payload,
                )

            successful_global_call = True

            found |= parse_online_response(
                data,
                emails,
            )

        except Exception:
            continue

    # Per-client fallback is only used when every global online endpoint
    # failed. This prevents hundreds of unnecessary requests on large panels.
    if not successful_global_call:
        for email in emails:
            per_email_attempts = [
                (
                    "POST",
                    "/panel/api/inbounds/onlines",
                    {"email": email},
                ),
                (
                    "POST",
                    "/panel/api/clients/online",
                    {"email": email},
                ),
                (
                    "GET",
                    "/panel/api/clients/online/"
                    + quote(email, safe=""),
                    None,
                ),
            ]

            for method, path, payload in per_email_attempts:
                with contextlib.suppress(Exception):
                    if payload is None:
                        data = xui.request(
                            method,
                            path,
                        )
                    else:
                        data = xui.request(
                            method,
                            path,
                            json=payload,
                        )

                    found |= parse_online_response(
                        data,
                        emails,
                    )

                    if email in found:
                        break

    return found


def parse_local_inbound_ids(local: dict) -> list[int]:
    value = local.get("inbound_ids")

    if value is None:
        return []

    if isinstance(value, list):
        raw = value
    else:
        try:
            raw = json.loads(str(value))
        except Exception:
            raw = str(value).replace(",", " ").split()

    output = []

    for item in raw or []:
        number = to_int(item, 0)

        if (
            number > 0
            and number not in output
        ):
            output.append(number)

    return output


def valid_uuid(value) -> str:
    text = str(value or "").strip()

    return text if UUID_RE.match(text) else ""


def panel_uuid(
    panel: dict,
    local: dict,
) -> str:
    for source in (
        panel,
        local,
    ):
        for key in (
            "uuid",
            "clientUuid",
            "client_uuid",
            "clientId",
            "client_id",
            "password",
            "id",
        ):
            uid = valid_uuid(
                source.get(key)
            )

            if uid:
                return uid

    return ""


def panel_sub_id(
    panel: dict,
    local: dict,
) -> str:
    for source in (
        panel,
        local,
    ):
        for key in (
            "subId",
            "sub_id",
            "subscription_id",
        ):
            value = str(
                source.get(key)
                or ""
            ).strip()

            if (
                value
                and value.lower()
                not in (
                    "0",
                    "none",
                    "null",
                )
            ):
                return value

    return ""


def panel_inbound_ids(
    panel: dict,
    local: dict,
) -> list[int]:
    for key in (
        "inboundIds",
        "inbound_ids",
        "inbounds",
    ):
        value = panel.get(key)

        if isinstance(value, list):
            output = [
                to_int(item, 0)
                for item in value
            ]

            output = [
                item
                for item in output
                if item > 0
            ]

            if output:
                return list(dict.fromkeys(output))

    return parse_local_inbound_ids(local)


def panel_client_state(
    xui: XUIClient,
    local: dict,
    online_set: set[str],
) -> dict:
    email = str(
        local.get("email")
        or ""
    ).strip()

    raw_get = {}
    raw_traffic = {}

    with contextlib.suppress(Exception):
        raw_get = xui.request(
            "GET",
            "/panel/api/clients/get/"
            + quote(email, safe=""),
        )

    with contextlib.suppress(Exception):
        raw_traffic = xui.request(
            "GET",
            "/panel/api/clients/traffic/"
            + quote(email, safe=""),
        )

    panel = extract_client(raw_get)

    values = [
        raw_get,
        raw_traffic,
        panel,
    ]

    up = first_number(
        values,
        (
            "up",
            "upload",
            "uplink",
            "upBytes",
            "up_bytes",
        ),
    )

    down = first_number(
        values,
        (
            "down",
            "download",
            "downlink",
            "downBytes",
            "down_bytes",
        ),
    )

    explicit_used = first_number(
        values,
        (
            "used",
            "usage",
            "totalUsed",
            "total_used",
            "traffic",
            "traffic_used",
        ),
    )

    panel_used = (
        up + down
        if up + down > 0
        else explicit_used
    )

    total_limit = first_number(
        values,
        (
            "totalGB",
            "total",
            "limit",
            "totalBytes",
            "total_bytes",
        ),
    )

    expiry_ms = first_number(
        values,
        (
            "expiryTime",
            "expiry",
            "expire",
            "expire_at",
            "expireAt",
        ),
    )

    enabled = first_bool(
        values,
        (
            "enable",
            "enabled",
            "active",
        ),
    )

    online = first_bool(
        values,
        (
            "online",
            "isOnline",
            "is_online",
        ),
    )

    speed_up = first_number(
        values,
        (
            "upSpeed",
            "up_speed",
            "uplinkSpeed",
            "uploadSpeed",
        ),
    )

    speed_down = first_number(
        values,
        (
            "downSpeed",
            "down_speed",
            "downlinkSpeed",
            "downloadSpeed",
        ),
    )

    if email in online_set:
        online = True

    if (
        speed_up > 0
        or speed_down > 0
    ):
        online = True

    if online is None:
        online = False

    if total_limit <= 0:
        total_limit = to_int(
            local.get("total_limit_bytes"),
            0,
        )

    if expiry_ms == 0:
        expiry_ms = to_int(
            local.get("expire_at_ms"),
            0,
        )

    return {
        "ok":
            bool(raw_get or raw_traffic),
        "panel":
            panel,
        "email":
            email,
        "online":
            bool(online),
        "enabled":
            enabled,
        "panel_up_bytes":
            max(0, int(up or 0)),
        "panel_down_bytes":
            max(0, int(down or 0)),
        "panel_used_bytes":
            max(0, int(panel_used or 0)),
        "total_limit_bytes":
            max(0, int(total_limit or 0)),
        "expiry_ms":
            int(expiry_ms or 0),
    }


def set_panel_enabled(
    xui: XUIClient,
    local: dict,
    enabled: bool,
) -> bool:
    email = str(
        local.get("email")
        or ""
    ).strip()

    if not email:
        return False

    raw = xui.request(
        "GET",
        "/panel/api/clients/get/"
        + quote(email, safe=""),
    )

    panel = extract_client(raw)

    uid = panel_uuid(
        panel,
        local,
    )

    if not uid:
        return False

    sub_id = panel_sub_id(
        panel,
        local,
    )

    ids = panel_inbound_ids(
        panel,
        local,
    )

    payload_client = {
        "email":
            email,
        "id":
            uid,
        "uuid":
            uid,
        "password":
            uid,
        "subId":
            sub_id,
        "flow":
            str(panel.get("flow") or ""),
        "enable":
            bool(enabled),
        "limitIp":
            to_int(
                panel.get("limitIp"),
                to_int(
                    local.get("limit_ip"),
                    0,
                ),
            ),
        "totalGB":
            to_int(
                panel.get("totalGB"),
                to_int(
                    local.get("total_limit_bytes"),
                    0,
                ),
            ),
        "expiryTime":
            to_int(
                panel.get("expiryTime"),
                to_int(
                    local.get("expire_at_ms"),
                    0,
                ),
            ),
        "tgId":
            to_int(
                panel.get("tgId"),
                0,
            ),
        "comment":
            str(
                panel.get("comment")
                or local.get("panel_comment")
                or ""
            ),
        "group":
            str(
                panel.get("group")
                or local.get("group_name")
                or ""
            ),
        "reset":
            to_int(
                panel.get("reset"),
                0,
            ),
    }

    attempts = [
        {
            "client":
                dict(payload_client),
            "inboundIds":
                ids,
        },
        {
            "client":
                dict(payload_client),
            "inbound_ids":
                ids,
        },
        {
            **payload_client,
            "inboundIds":
                ids,
            "inbound_ids":
                ids,
        },
    ]

    for payload in attempts:
        try:
            xui.request(
                "POST",
                "/panel/api/clients/update/"
                + quote(email, safe=""),
                json=payload,
            )

            with contextlib.suppress(Exception):
                xui.attach(
                    email,
                    ids,
                )

            return True

        except Exception:
            continue

    return False


def sync_one_client(
    xui: XUIClient,
    local: dict,
    online_set: set[str],
) -> dict | None:
    client_id = to_int(
        local.get("id"),
        0,
    )

    email = str(
        local.get("email")
        or ""
    ).strip()

    if (
        client_id <= 0
        or not email
    ):
        return None

    state = panel_client_state(
        xui,
        local,
        online_set,
    )

    stamp = now_text()

    with connect_db() as con:
        ledger = con.execute(
            """
            SELECT *
            FROM traffic_ledger
            WHERE client_id=?
            """,
            (client_id,),
        ).fetchone()

        panel_used = int(
            state.get("panel_used_bytes")
            or 0
        )

        panel_up = int(
            state.get("panel_up_bytes")
            or 0
        )

        panel_down = int(
            state.get("panel_down_bytes")
            or 0
        )

        event_type = "no_change"
        delta = 0

        if ledger:
            cumulative = int(
                ledger["cumulative_used_bytes"]
                or 0
            )

            previous_panel = int(
                ledger["last_panel_used_bytes"]
                or 0
            )

            reset_count = int(
                ledger["reset_detected_count"]
                or 0
            )

            if state.get("ok"):
                if panel_used >= previous_panel:
                    delta = (
                        panel_used
                        - previous_panel
                    )
                    event_type = (
                        "normal_delta"
                        if delta > 0
                        else "no_change"
                    )

                else:
                    # A user reset or panel traffic reset happened between
                    # two syncs. The new lower value is consumption after
                    # the reset and must still be added to cumulative usage.
                    delta = panel_used
                    event_type = (
                        "panel_reset_detected"
                    )
                    reset_count += 1

                cumulative += max(
                    0,
                    delta,
                )

                con.execute(
                    """
                    UPDATE traffic_ledger
                    SET
                        last_panel_up=?,
                        last_panel_down=?,
                        last_panel_total=?,
                        last_panel_used_bytes=?,
                        cumulative_used_bytes=?,
                        reset_detected_count=?,
                        last_reset_detected_at=
                            CASE
                                WHEN ?='panel_reset_detected'
                                THEN ?
                                ELSE last_reset_detected_at
                            END,
                        last_seen_at=?
                    WHERE client_id=?
                    """,
                    (
                        panel_up,
                        panel_down,
                        panel_used,
                        panel_used,
                        cumulative,
                        reset_count,
                        event_type,
                        stamp,
                        stamp,
                        client_id,
                    ),
                )

        else:
            cumulative = (
                panel_used
                if state.get("ok")
                else 0
            )

            previous_panel = 0

            delta = cumulative

            event_type = (
                "initial_snapshot"
                if cumulative > 0
                else "no_change"
            )

            con.execute(
                """
                INSERT INTO traffic_ledger(
                    client_id,
                    last_panel_up,
                    last_panel_down,
                    last_panel_total,
                    cumulative_used_bytes,
                    reset_detected_count,
                    last_reset_detected_at,
                    last_seen_at,
                    last_panel_used_bytes
                )
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    client_id,
                    panel_up,
                    panel_down,
                    panel_used,
                    cumulative,
                    0,
                    None,
                    stamp,
                    panel_used,
                ),
            )

        if delta > 0:
            con.execute(
                """
                INSERT INTO traffic_events(
                    created_at,
                    client_id,
                    email,
                    owner_rep_id,
                    seller_rep_id,
                    prev_panel_total,
                    current_panel_total,
                    delta_bytes,
                    cumulative_after,
                    event_type
                )
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    stamp,
                    client_id,
                    email,
                    to_int(
                        local.get("owner_rep_id"),
                        0,
                    ),
                    to_int(
                        local.get("seller_rep_id"),
                        0,
                    ),
                    previous_panel,
                    panel_used,
                    delta,
                    cumulative,
                    event_type,
                ),
            )

        total_limit = int(
            state.get("total_limit_bytes")
            or to_int(
                local.get("total_limit_bytes"),
                0,
            )
        )

        expiry_ms = int(
            state.get("expiry_ms")
            or to_int(
                local.get("expire_at_ms"),
                0,
            )
        )

        own_limit_exhausted = (
            1
            if (
                total_limit > 0
                and panel_used >= total_limit
            )
            else 0
        )

        current_hold = to_int(
            local.get("rep_quota_hold"),
            0,
        )

        enabled = local.get("enabled")

        if (
            current_hold == 0
            and state.get("enabled")
            is not None
        ):
            enabled = (
                1
                if state.get("enabled")
                else 0
            )

        enabled = 1 if enabled else 0

        old_reason = str(
            local.get("disable_reason")
            or ""
        ).strip()

        disable_reason = old_reason

        expired = (
            expiry_ms > 0
            and expiry_ms <= now_ms()
        )

        if current_hold:
            disable_reason = "rep_quota"
            enabled = 0

        elif not enabled:
            if old_reason in (
                "manual",
                "external",
                "client_quota",
                "expired",
            ):
                disable_reason = old_reason
            elif own_limit_exhausted:
                disable_reason = "client_quota"
            elif expired:
                disable_reason = "expired"
            else:
                disable_reason = "external"

        else:
            # A client that is enabled directly in x-ui should not stay
            # permanently tagged as manually disabled in the local mirror.
            if disable_reason != "rep_quota":
                disable_reason = ""

        status = str(
            local.get("status")
            or "active"
        )

        if current_hold:
            status = "quota_disabled"

        elif not enabled:
            status = "disabled"

        elif status in (
            "disabled",
            "quota_disabled",
            "inactive",
            "blocked",
        ):
            status = "active"

        last_online = local.get(
            "last_online_at"
        )

        if state.get("online"):
            last_online = stamp

        con.execute(
            """
            UPDATE clients
            SET
                is_online=?,
                last_online_at=?,
                panel_used_bytes=?,
                own_limit_exhausted=?,
                total_limit_bytes=?,
                expire_at_ms=?,
                enabled=?,
                status=?,
                disable_reason=?,
                last_panel_sync_at=?,
                updated_at=?
            WHERE id=?
            """,
            (
                1 if state.get("online") else 0,
                last_online,
                panel_used,
                own_limit_exhausted,
                total_limit,
                expiry_ms,
                enabled,
                status,
                disable_reason,
                stamp,
                stamp,
                client_id,
            ),
        )

        con.commit()

    return {
        "id":
            client_id,
        "email":
            email,
        "online":
            bool(state.get("online")),
        "panel_used_bytes":
            panel_used,
        "cumulative_used_bytes":
            cumulative,
        "total_limit_bytes":
            total_limit,
        "own_limit_exhausted":
            bool(own_limit_exhausted),
    }


def representative_usage(
    con: sqlite3.Connection,
    rep_id: int,
) -> int:
    active = con.execute(
        """
        SELECT COALESCE(
            SUM(
                COALESCE(
                    l.cumulative_used_bytes,
                    0
                )
            ),
            0
        ) AS total
        FROM clients c
        LEFT JOIN traffic_ledger l
          ON l.client_id=c.id
        WHERE c.seller_rep_id=?
          AND COALESCE(c.status,'')!='deleted'
        """,
        (rep_id,),
    ).fetchone()

    active_used = int(
        active["total"]
        or 0
    )

    deleted_used = 0

    if table_exists(
        con,
        "deleted_client_usage",
    ):
        row = con.execute(
            """
            SELECT COALESCE(
                SUM(
                    cumulative_used_bytes
                ),
                0
            ) AS total
            FROM deleted_client_usage
            WHERE seller_rep_id=?
            """,
            (rep_id,),
        ).fetchone()

        deleted_used = int(
            row["total"]
            or 0
        )

    return max(
        0,
        active_used + deleted_used,
    )


def mark_rep_locked(
    rep: dict,
) -> None:
    rep_id = to_int(
        rep.get("id"),
        0,
    )

    if rep_id <= 0:
        return

    current_status = str(
        rep.get("status")
        or "active"
    )

    previous_status = str(
        rep.get("quota_prev_status")
        or ""
    ).strip()

    if not previous_status:
        previous_status = (
            current_status
            if current_status != "quota_blocked"
            else "active"
        )

    stamp = now_text()

    with connect_db() as con:
        con.execute(
            """
            UPDATE representatives
            SET
                quota_locked=1,
                quota_locked_at=
                    COALESCE(
                        quota_locked_at,
                        ?
                    ),
                quota_prev_status=?,
                status='quota_blocked',
                quota_last_reconciled_at=?,
                updated_at=?
            WHERE id=?
            """,
            (
                stamp,
                previous_status,
                stamp,
                stamp,
                rep_id,
            ),
        )

        # Existing sessions are invalidated immediately. On recharge the
        # reseller simply logs in again; no password/account data is lost.
        if table_exists(
            con,
            "auth_sessions",
        ):
            con.execute(
                """
                DELETE FROM auth_sessions
                WHERE role='reseller'
                  AND account_id=?
                """,
                (rep_id,),
            )

        con.commit()


def lock_eligible_clients(
    xui: XUIClient,
    rep_id: int,
) -> list[str]:
    disabled = []

    with connect_db() as con:
        rows = [
            dict(row)
            for row in con.execute(
                """
                SELECT *
                FROM clients
                WHERE seller_rep_id=?
                  AND COALESCE(status,'')!='deleted'
                ORDER BY id
                """,
                (rep_id,),
            ).fetchall()
        ]

    for local in rows:
        if to_int(
            local.get("rep_quota_hold"),
            0,
        ):
            continue

        # This is the key preservation rule:
        # only a client that was actually enabled and usable before the
        # representative quota lock is marked as quota-disabled.
        if not bool(
            local.get("enabled")
        ):
            continue

        if to_int(
            local.get("own_limit_exhausted"),
            0,
        ):
            continue

        expiry_ms = to_int(
            local.get("expire_at_ms"),
            0,
        )

        if (
            expiry_ms > 0
            and expiry_ms <= now_ms()
        ):
            continue

        reason = str(
            local.get("disable_reason")
            or ""
        ).strip()

        if reason in (
            "manual",
            "external",
            "client_quota",
            "expired",
        ):
            continue

        if not set_panel_enabled(
            xui,
            local,
            False,
        ):
            # Do not mark it as quota-held unless x-ui actually accepted
            # the disable. The next background pass will retry.
            continue

        stamp = now_text()

        with connect_db() as con:
            con.execute(
                """
                UPDATE clients
                SET
                    quota_prev_enabled=1,
                    quota_prev_status=?,
                    rep_quota_hold=1,
                    quota_disabled_at=?,
                    disable_reason='rep_quota',
                    enabled=0,
                    status='quota_disabled',
                    is_online=0,
                    updated_at=?
                WHERE id=?
                  AND seller_rep_id=?
                """,
                (
                    str(
                        local.get("status")
                        or "active"
                    ),
                    stamp,
                    stamp,
                    to_int(
                        local.get("id"),
                        0,
                    ),
                    rep_id,
                ),
            )

            con.commit()

        disabled.append(
            str(local.get("email") or "")
        )

    return disabled


def restore_quota_clients(
    xui: XUIClient,
    rep_id: int,
) -> tuple[list[str], list[str]]:
    restored = []
    failures = []

    with connect_db() as con:
        rows = [
            dict(row)
            for row in con.execute(
                """
                SELECT *
                FROM clients
                WHERE seller_rep_id=?
                  AND rep_quota_hold=1
                  AND COALESCE(status,'')!='deleted'
                ORDER BY id
                """,
                (rep_id,),
            ).fetchall()
        ]

    for local in rows:
        client_id = to_int(
            local.get("id"),
            0,
        )

        email = str(
            local.get("email")
            or ""
        )

        expiry_ms = to_int(
            local.get("expire_at_ms"),
            0,
        )

        expired = (
            expiry_ms > 0
            and expiry_ms <= now_ms()
        )

        own_limit_exhausted = bool(
            to_int(
                local.get("own_limit_exhausted"),
                0,
            )
        )

        if expired or own_limit_exhausted:
            # It was quota-held, but while locked the client's own state now
            # says it must remain disconnected. Clear only the representative
            # hold; do not enable the client.
            reason = (
                "expired"
                if expired
                else "client_quota"
            )

            with connect_db() as con:
                con.execute(
                    """
                    UPDATE clients
                    SET
                        rep_quota_hold=0,
                        quota_prev_enabled=0,
                        quota_prev_status=NULL,
                        quota_disabled_at=NULL,
                        disable_reason=?,
                        enabled=0,
                        status='disabled',
                        updated_at=?
                    WHERE id=?
                      AND seller_rep_id=?
                    """,
                    (
                        reason,
                        now_text(),
                        client_id,
                        rep_id,
                    ),
                )

                con.commit()

            continue

        if not bool(
            local.get("quota_prev_enabled")
        ):
            # Safety: a hold without a saved enabled state must never be
            # auto-enabled.
            with connect_db() as con:
                con.execute(
                    """
                    UPDATE clients
                    SET
                        rep_quota_hold=0,
                        quota_prev_status=NULL,
                        quota_disabled_at=NULL,
                        disable_reason='external',
                        updated_at=?
                    WHERE id=?
                      AND seller_rep_id=?
                    """,
                    (
                        now_text(),
                        client_id,
                        rep_id,
                    ),
                )

                con.commit()

            continue

        if not set_panel_enabled(
            xui,
            local,
            True,
        ):
            failures.append(email)
            continue

        previous_status = str(
            local.get("quota_prev_status")
            or "active"
        )

        if previous_status in (
            "quota_disabled",
            "disabled",
            "inactive",
            "blocked",
        ):
            previous_status = "active"

        with connect_db() as con:
            con.execute(
                """
                UPDATE clients
                SET
                    rep_quota_hold=0,
                    quota_prev_enabled=0,
                    quota_prev_status=NULL,
                    quota_disabled_at=NULL,
                    disable_reason='',
                    enabled=1,
                    status=?,
                    updated_at=?
                WHERE id=?
                  AND seller_rep_id=?
                """,
                (
                    previous_status,
                    now_text(),
                    client_id,
                    rep_id,
                ),
            )

            con.commit()

        restored.append(email)

    return restored, failures


def finalize_rep_unlock(
    rep: dict,
) -> None:
    rep_id = to_int(
        rep.get("id"),
        0,
    )

    previous_status = str(
        rep.get("quota_prev_status")
        or "active"
    ).strip()

    if previous_status == "quota_blocked":
        previous_status = "active"

    current_status = str(
        rep.get("status")
        or "quota_blocked"
    ).strip()

    # If an admin deliberately changed status while quota was locked,
    # preserve the admin's status instead of forcing active.
    restored_status = (
        previous_status
        if current_status == "quota_blocked"
        else current_status
    )

    stamp = now_text()

    with connect_db() as con:
        con.execute(
            """
            UPDATE representatives
            SET
                quota_locked=0,
                quota_locked_at=NULL,
                quota_prev_status=NULL,
                status=?,
                quota_last_reconciled_at=?,
                updated_at=?
            WHERE id=?
            """,
            (
                restored_status,
                stamp,
                stamp,
                rep_id,
            ),
        )

        con.commit()


def reconcile_quotas(
    xui: XUIClient,
) -> dict:
    ensure_live_schema()

    with connect_db() as con:
        reps = [
            dict(row)
            for row in con.execute(
                """
                SELECT *
                FROM representatives
                ORDER BY id
                """
            ).fetchall()
        ]

    locked = []
    restored = []
    restore_failures = []

    for rep in reps:
        rep_id = to_int(
            rep.get("id"),
            0,
        )

        if rep_id <= 0:
            continue

        with connect_db() as con:
            used = representative_usage(
                con,
                rep_id,
            )

            con.execute(
                """
                UPDATE representatives
                SET
                    used_bytes=?,
                    quota_last_reconciled_at=?,
                    updated_at=?
                WHERE id=?
                """,
                (
                    used,
                    now_text(),
                    now_text(),
                    rep_id,
                ),
            )

            con.commit()

        rep["used_bytes"] = used

        quota = max(
            0,
            to_int(
                rep.get("quota_bytes"),
                0,
            ),
        )

        quota_locked = bool(
            to_int(
                rep.get("quota_locked"),
                0,
            )
        )

        status = str(
            rep.get("status")
            or "active"
        )

        exceeded = (
            quota > 0
            and used >= quota
        )

        if exceeded:
            if not quota_locked:
                # Only active accounts become quota-blocked. A manually
                # inactive account remains an admin state and is not rewritten.
                if status == "active":
                    mark_rep_locked(rep)
                    rep["quota_locked"] = 1
                    rep["status"] = "quota_blocked"
                    quota_locked = True
                    locked.append(rep_id)

            if quota_locked or status == "quota_blocked":
                disabled = lock_eligible_clients(
                    xui,
                    rep_id,
                )

                if disabled:
                    locked.append(rep_id)

            continue

        # Quota was increased / changed to unlimited.
        if quota_locked or status == "quota_blocked":
            restored_clients, failures = restore_quota_clients(
                xui,
                rep_id,
            )

            restored.extend(
                restored_clients
            )

            restore_failures.extend(
                failures
            )

            if not failures:
                # Reload current rep because an admin may have changed status
                # while the quota lock was active.
                with connect_db() as con:
                    current = con.execute(
                        """
                        SELECT *
                        FROM representatives
                        WHERE id=?
                        """,
                        (rep_id,),
                    ).fetchone()

                if current:
                    finalize_rep_unlock(
                        dict(current)
                    )

    return {
        "locked_rep_ids":
            sorted(set(locked)),
        "restored_clients":
            restored,
        "restore_failures":
            restore_failures,
    }


def load_clients() -> list[dict]:
    ensure_live_schema()

    with connect_db() as con:
        return [
            dict(row)
            for row in con.execute(
                """
                SELECT *
                FROM clients
                WHERE COALESCE(status,'')!='deleted'
                ORDER BY id
                """
            ).fetchall()
        ]


def sync_all(
    force: bool = True,
) -> dict:
    global _LAST_SYNC_AT

    current = time.time()

    if (
        not force
        and current - _LAST_SYNC_AT < 3
    ):
        return {
            "ok": True,
            "skipped": True,
            "reason": "recent_sync",
        }

    if not _SYNC_LOCK.acquire(
        blocking=False
    ):
        return {
            "ok": True,
            "skipped": True,
            "reason": "sync_in_progress",
        }

    try:
        ensure_live_schema()

        rows = load_clients()

        if not rows:
            with connect_db() as con:
                reps = con.execute(
                    """
                    SELECT id
                    FROM representatives
                    """
                ).fetchall()

                for rep in reps:
                    con.execute(
                        """
                        UPDATE representatives
                        SET used_bytes=0,
                            quota_last_reconciled_at=?,
                            updated_at=?
                        WHERE id=?
                        """,
                        (
                            now_text(),
                            now_text(),
                            int(rep["id"]),
                        ),
                    )

                con.commit()

            _LAST_SYNC_AT = time.time()

            return {
                "ok": True,
                "clients": 0,
                "online": 0,
                "quota": {},
            }

        try:
            xui = XUIClient()
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

        known = [
            str(row.get("email") or "").strip()
            for row in rows
            if str(row.get("email") or "").strip()
        ]

        online_set = fetch_online_emails(
            xui,
            known,
        )

        synced = []

        for row in rows:
            try:
                result = sync_one_client(
                    xui,
                    row,
                    online_set,
                )

                if result:
                    synced.append(result)

            except Exception:
                # One broken/missing X-UI client must not stop all other users.
                continue

        quota_result = reconcile_quotas(
            xui
        )

        _LAST_SYNC_AT = time.time()

        return {
            "ok": True,
            "clients": len(synced),
            "online": sum(
                1
                for item in synced
                if item.get("online")
            ),
            "online_emails": sorted(
                online_set
            ),
            "quota": quota_result,
            "ts": now_text(),
        }

    finally:
        _SYNC_LOCK.release()


def sync_if_due() -> dict:
    return sync_all(
        force=False
    )


async def background_loop() -> None:
    await asyncio.sleep(2)

    while True:
        try:
            await asyncio.to_thread(
                sync_all,
                True,
            )
        except Exception:
            pass

        await asyncio.sleep(
            POLL_SECONDS
        )


def start_background_sync() -> None:
    global _BG_TASK

    if (
        _BG_TASK is not None
        and not _BG_TASK.done()
    ):
        return

    loop = asyncio.get_running_loop()

    _BG_TASK = loop.create_task(
        background_loop()
    )


async def stop_background_sync() -> None:
    global _BG_TASK

    task = _BG_TASK
    _BG_TASK = None

    if task is None or task.done():
        return

    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task


@router.get("/state")
def live_state(
    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):
    reseller = get_reseller_from_session(
        xui_session
    )

    rep_id = int(
        reseller["id"]
    )

    ensure_live_schema()

    with connect_db() as con:
        clients = con.execute(
            """
            SELECT
                id,
                email,
                seller_rep_id,
                is_online,
                last_online_at,
                panel_used_bytes,
                own_limit_exhausted,
                enabled,
                disable_reason,
                rep_quota_hold
            FROM clients
            WHERE COALESCE(status,'')!='deleted'
              AND seller_rep_id=?
            ORDER BY id
            """,
            (rep_id,),
        ).fetchall()

        rep = con.execute(
            """
            SELECT
                id,
                username,
                quota_bytes,
                used_bytes,
                status,
                quota_locked,
                quota_locked_at
            FROM representatives
            WHERE id=?
            """,
            (rep_id,),
        ).fetchone()

    return {
        "ok": True,
        "poll_seconds": POLL_SECONDS,
        "clients": [
            dict(row)
            for row in clients
        ],
        "representative": (
            dict(rep)
            if rep
            else None
        ),
    }


@router.post("/sync")
async def live_sync_now(
    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):
    reseller = get_reseller_from_session(
        xui_session
    )

    result = await asyncio.to_thread(
        sync_all,
        True,
    )

    rep_id = int(
        reseller["id"]
    )

    with connect_db() as con:
        rep = con.execute(
            """
            SELECT
                quota_bytes,
                used_bytes,
                status,
                quota_locked
            FROM representatives
            WHERE id=?
            """,
            (rep_id,),
        ).fetchone()

    return {
        "ok": bool(result.get("ok")),
        "representative": (
            dict(rep)
            if rep
            else None
        ),
        "ts": result.get("ts"),
    }

# === STEP7B SNAPSHOT FIX ===
# Fixes live traffic/online detection by using raw
# /panel/api/inbounds/list -> clientStats + settings as primary source.
# Existing quota/recharge logic above is preserved.

_STEP7B_OLD_PANEL_CLIENT_STATE = panel_client_state
_STEP7B_PANEL_SNAPSHOT: dict[str, dict] = {}
_STEP7B_ONLINE: set[str] = set()
_STEP7B_LAST_ERRORS: list[str] = []
_STEP7B_LAST_SNAPSHOT_AT = ""


def _step7b_rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("obj", "data", "result", "list", "items", "inbounds"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def _step7b_json(value, default):
    if isinstance(value, type(default)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, type(default)):
                return parsed
        except Exception:
            pass
    return default


def _step7b_email(value) -> str:
    return str(value or "").strip()


def _step7b_online_names(data, known_emails: list[str]) -> set[str]:
    canonical = {
        _step7b_email(email).casefold(): _step7b_email(email)
        for email in known_emails
        if _step7b_email(email)
    }
    found: set[str] = set()

    def add(value):
        text = _step7b_email(value)
        if not text:
            return
        key = text.casefold()
        if key in canonical:
            found.add(canonical[key])
            return
        for folded, original in canonical.items():
            if folded and folded in key:
                found.add(original)

    def truthy(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0
        text = str(value or "").strip().lower()
        return bool(text) and text not in (
            "0", "false", "no", "offline", "none", "null", "[]", "{}"
        )

    def walk(value):
        if isinstance(value, str):
            add(value)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return

        for key, nested in value.items():
            key_text = str(key or "").casefold()
            if key_text in canonical and truthy(nested):
                found.add(canonical[key_text])

        email = _step7b_email(
            value.get("email")
            or value.get("clientEmail")
            or value.get("client_email")
            or value.get("name")
            or value.get("client")
        )
        if email:
            active = None
            for key in ("online", "isOnline", "is_online", "connected"):
                if key in value:
                    active = truthy(value.get(key))
                    break
            connection = None
            for key in (
                "ip", "ips", "onlineIps", "online_ips", "connections", "sessions"
            ):
                if key in value:
                    connection = value.get(key)
                    break
            if active is True or truthy(connection):
                add(email)

        for nested in value.values():
            walk(nested)

    walk(data)
    return found


def _step7b_build_snapshot(xui: XUIClient, known_emails: list[str]):
    errors: list[str] = []
    canonical = {
        _step7b_email(email).casefold(): _step7b_email(email)
        for email in known_emails
        if _step7b_email(email)
    }
    snapshot: dict[str, dict] = {}

    try:
        raw = xui.request("GET", "/panel/api/inbounds/list")
        rows = _step7b_rows(raw)
    except Exception as exc:
        rows = []
        errors.append("GET /panel/api/inbounds/list: " + str(exc))

    def ensure(email: str):
        original = canonical.get(_step7b_email(email).casefold())
        if not original:
            return None
        if original not in snapshot:
            snapshot[original] = {
                "email": original,
                "panel_up_bytes": 0,
                "panel_down_bytes": 0,
                "panel_used_bytes": 0,
                "total_limit_bytes": 0,
                "expiry_ms": 0,
                "enabled": None,
                "online_hint": False,
                "panel": {},
                "inbound_ids": [],
            }
        return snapshot[original]

    current_ms = int(time.time() * 1000)
    recent_ms = max(15000, POLL_SECONDS * 2500)

    for inbound in rows:
        if not isinstance(inbound, dict):
            continue
        inbound_id = to_int(inbound.get("id"), 0)
        settings = _step7b_json(inbound.get("settings"), {})
        settings_clients = settings.get("clients") if isinstance(settings, dict) else []
        if not isinstance(settings_clients, list):
            settings_clients = []

        for client in settings_clients:
            if not isinstance(client, dict):
                continue
            state = ensure(client.get("email"))
            if state is None:
                continue
            if inbound_id > 0 and inbound_id not in state["inbound_ids"]:
                state["inbound_ids"].append(inbound_id)
            state["panel"] = {**state.get("panel", {}), **client}
            total = to_int(client.get("totalGB"), 0)
            if total > 0:
                state["total_limit_bytes"] = max(state["total_limit_bytes"], total)
            expiry = to_int(client.get("expiryTime"), 0)
            if expiry != 0:
                current_expiry = to_int(state.get("expiry_ms"), 0)
                if current_expiry == 0 or expiry > 0:
                    state["expiry_ms"] = expiry if current_expiry == 0 else max(current_expiry, expiry)
            if "enable" in client:
                state["enabled"] = bool(client.get("enable"))

        stats = (
            inbound.get("clientStats")
            or inbound.get("client_stats")
            or inbound.get("clientTraffics")
            or inbound.get("client_traffics")
            or []
        )
        stats = _step7b_json(stats, [])
        if not isinstance(stats, list):
            stats = []

        for stat in stats:
            if not isinstance(stat, dict):
                continue
            state = ensure(
                stat.get("email") or stat.get("clientEmail") or stat.get("client_email")
            )
            if state is None:
                continue
            if inbound_id > 0 and inbound_id not in state["inbound_ids"]:
                state["inbound_ids"].append(inbound_id)

            up = first_number(stat, ("up", "upload", "uplink", "upBytes", "up_bytes"))
            down = first_number(stat, ("down", "download", "downlink", "downBytes", "down_bytes"))
            used = first_number(stat, ("used", "usage", "totalUsed", "total_used", "traffic", "traffic_used"))
            # Keep current x-ui usage.
            # Do not sum the same client traffic across multiple inbounds.
            # Prefer explicit used value when x-ui provides it.
            if used > 0:
                state["panel_used_bytes"] = max(
                    state["panel_used_bytes"],
                    used,
                )
            else:
                state["panel_used_bytes"] = max(
                    state["panel_used_bytes"],
                    up + down,
                )

            state["panel_up_bytes"] = max(
                state["panel_up_bytes"],
                up,
            )

            state["panel_down_bytes"] = max(
                state["panel_down_bytes"],
                down,
            )

            total = first_number(stat, ("totalGB", "total", "limit", "totalBytes", "total_bytes"))
            if total > 0:
                state["total_limit_bytes"] = max(state["total_limit_bytes"], total)
            expiry = first_number(stat, ("expiryTime", "expiry", "expire", "expireAt", "expire_at"))
            if expiry != 0:
                current_expiry = to_int(state.get("expiry_ms"), 0)
                if current_expiry == 0 or expiry > 0:
                    state["expiry_ms"] = expiry if current_expiry == 0 else max(current_expiry, expiry)
            enabled = first_bool(stat, ("enable", "enabled", "active"))
            if enabled is not None:
                state["enabled"] = enabled
            direct_online = first_bool(stat, ("online", "isOnline", "is_online", "connected"))
            if direct_online is True:
                state["online_hint"] = True
            last_online = first_number(stat, ("lastOnline", "last_online", "lastOnlineAt", "last_online_at"))
            if 0 < last_online < 10_000_000_000:
                last_online *= 1000
            if last_online > 0 and abs(current_ms - last_online) <= recent_ms:
                state["online_hint"] = True

    for state in snapshot.values():
        # Only fallback to up+down if x-ui did not provide usage.
        # Avoid replacing explicit traffic with duplicated inbound totals.
        if state["panel_used_bytes"] <= 0:
            state["panel_used_bytes"] = (
                state["panel_up_bytes"]
                +
                state["panel_down_bytes"]
            )

    online: set[str] = set()
    attempts = [
        ("GET", "/panel/api/inbounds/onlines", None),
        ("POST", "/panel/api/inbounds/onlines", {}),
        ("GET", "/panel/api/clients/onlines", None),
        ("GET", "/panel/api/clients/online", None),
    ]
    successful = False
    for method, path, payload in attempts:
        try:
            if payload is None:
                response = xui.request(method, path)
            else:
                response = xui.request(method, path, json=payload)
            successful = True
            online |= _step7b_online_names(response, known_emails)
        except Exception as exc:
            errors.append(f"{method} {path}: {exc}")

    if not successful:
        for email, state in snapshot.items():
            if state.get("online_hint"):
                online.add(email)

    return snapshot, online, errors


def fetch_online_emails(xui: XUIClient, known_emails: list[str]) -> set[str]:
    global _STEP7B_PANEL_SNAPSHOT, _STEP7B_ONLINE, _STEP7B_LAST_ERRORS, _STEP7B_LAST_SNAPSHOT_AT
    snapshot, online, errors = _step7b_build_snapshot(xui, known_emails)
    _STEP7B_PANEL_SNAPSHOT = snapshot
    _STEP7B_ONLINE = set(online)
    _STEP7B_LAST_ERRORS = errors
    _STEP7B_LAST_SNAPSHOT_AT = now_text()
    return set(online)


def panel_client_state(xui: XUIClient, local: dict, online_set: set[str]) -> dict:
    email = _step7b_email(local.get("email"))
    state = _STEP7B_PANEL_SNAPSHOT.get(email)
    if state is None:
        folded = email.casefold()
        for candidate_email, candidate_state in _STEP7B_PANEL_SNAPSHOT.items():
            if candidate_email.casefold() == folded:
                state = candidate_state
                break

    if state is not None:
        enabled = state.get("enabled")
        if enabled is None:
            enabled = bool(local.get("enabled", 1))
        total_limit = to_int(state.get("total_limit_bytes"), 0)
        if total_limit <= 0:
            total_limit = to_int(local.get("total_limit_bytes"), 0)
        expiry_ms = to_int(state.get("expiry_ms"), 0)
        if expiry_ms == 0:
            expiry_ms = to_int(local.get("expire_at_ms"), 0)
        up = max(0, to_int(state.get("panel_up_bytes"), 0))
        down = max(0, to_int(state.get("panel_down_bytes"), 0))
        used = max(0, to_int(state.get("panel_used_bytes"), 0))
        return {
            "ok": True,
            "panel": state.get("panel") or {},
            "email": email,
            "online": email in online_set or bool(state.get("online_hint")),
            "enabled": bool(enabled),
            "panel_up_bytes": up,
            "panel_down_bytes": down,
            "panel_used_bytes": used,
            "total_limit_bytes": max(0, total_limit),
            "expiry_ms": int(expiry_ms),
        }

    return _STEP7B_OLD_PANEL_CLIENT_STATE(xui, local, online_set)


@router.get("/probe")
async def step7b_probe(
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    if not LIVE_PROBE_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    reseller = get_reseller_from_session(xui_session)
    result = await asyncio.to_thread(sync_all, True)
    rep_id = int(reseller["id"])
    ensure_live_schema()
    with connect_db() as con:
        rows = con.execute(
            """
            SELECT c.id,c.email,c.is_online,c.last_online_at,
                   c.panel_used_bytes,c.total_limit_bytes,c.enabled,
                   c.status,c.disable_reason,c.rep_quota_hold,
                   COALESCE(l.last_panel_used_bytes,0) AS ledger_panel,
                   COALESCE(l.cumulative_used_bytes,0) AS cumulative
            FROM clients c
            LEFT JOIN traffic_ledger l ON l.client_id=c.id
            WHERE c.seller_rep_id=? AND COALESCE(c.status,'')!='deleted'
            ORDER BY c.id
            """,
            (rep_id,),
        ).fetchall()
    return {
        "ok": bool(result.get("ok")),
        "sync": result,
        "snapshot_at": _STEP7B_LAST_SNAPSHOT_AT,
        "snapshot_clients": {
            email: {
                "used": state.get("panel_used_bytes", 0),
                "up": state.get("panel_up_bytes", 0),
                "down": state.get("panel_down_bytes", 0),
                "enabled": state.get("enabled"),
                "online_hint": state.get("online_hint", False),
                "inbound_ids": state.get("inbound_ids", []),
            }
            for email, state in _STEP7B_PANEL_SNAPSHOT.items()
            if any(str(row["email"]) == email for row in rows)
        },
        "online_emails": sorted(_STEP7B_ONLINE),
        "endpoint_errors": _STEP7B_LAST_ERRORS[-10:],
        "clients": [dict(row) for row in rows],
    }


# === USAGE BASELINE REPAIR V1 ===
# One-time repair after the multi-inbound traffic duplication fix.
#
# Goals:
# - User live usage always follows current x-ui traffic.
# - Existing polluted cumulative usage is rebased once to current real usage.
# - Deleted historical usage is cleared during this one-time baseline.
# - Representative used_bytes is rebuilt from the repaired ledger.
# - Future user resets DO NOT reduce representative cumulative usage.
#
# The migration marker prevents this baseline from ever running twice.

_USAGE_BASELINE_REPAIR_V1 = "usage_baseline_after_multi_inbound_fix_v1"
_USAGE_BASELINE_OLD_SYNC_ALL = sync_all


def _usage_baseline_repair_v1() -> bool:
    stamp = now_text()

    with connect_db() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS maintenance_migrations(
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        con.commit()

        already = con.execute(
            """
            SELECT 1
            FROM maintenance_migrations
            WHERE name=?
            LIMIT 1
            """,
            (_USAGE_BASELINE_REPAIR_V1,),
        ).fetchone()

        if already:
            return False

        # Prevent two concurrent sync workers from applying the baseline twice.
        con.execute("BEGIN IMMEDIATE")

        already = con.execute(
            """
            SELECT 1
            FROM maintenance_migrations
            WHERE name=?
            LIMIT 1
            """,
            (_USAGE_BASELINE_REPAIR_V1,),
        ).fetchone()

        if already:
            con.commit()
            return False

        clients = con.execute(
            """
            SELECT
                id,
                COALESCE(panel_used_bytes, 0) AS panel_used_bytes
            FROM clients
            WHERE LOWER(COALESCE(status, '')) != 'deleted'
            """
        ).fetchall()

        repaired_clients = 0
        created_ledgers = 0

        for row in clients:
            client_id = int(row["id"])
            current_used = max(
                0,
                int(row["panel_used_bytes"] or 0),
            )

            ledger = con.execute(
                """
                SELECT 1
                FROM traffic_ledger
                WHERE client_id=?
                """,
                (client_id,),
            ).fetchone()

            if ledger:
                con.execute(
                    """
                    UPDATE traffic_ledger
                    SET
                        last_panel_total=?,
                        last_panel_used_bytes=?,
                        cumulative_used_bytes=?,
                        last_seen_at=?
                    WHERE client_id=?
                    """,
                    (
                        current_used,
                        current_used,
                        current_used,
                        stamp,
                        client_id,
                    ),
                )
            else:
                con.execute(
                    """
                    INSERT INTO traffic_ledger(
                        client_id,
                        last_panel_total,
                        cumulative_used_bytes,
                        reset_detected_count,
                        last_seen_at,
                        last_panel_used_bytes
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        client_id,
                        current_used,
                        current_used,
                        0,
                        stamp,
                        current_used,
                    ),
                )
                created_ledgers += 1

            repaired_clients += 1

        # This migration intentionally creates a clean baseline based only
        # on users that currently exist. Old deleted-user accounting may
        # contain the same duplicated traffic bug, so it must not survive
        # the one-time repair.
        deleted_usage_exists = con.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name='deleted_client_usage'
            """
        ).fetchone()

        if deleted_usage_exists:
            con.execute(
                """
                UPDATE deleted_client_usage
                SET cumulative_used_bytes=0
                """
            )

        # Deleted local clients must not contribute polluted historical usage.
        con.execute(
            """
            UPDATE traffic_ledger
            SET
                last_panel_total=0,
                last_panel_used_bytes=0,
                cumulative_used_bytes=0
            WHERE client_id IN (
                SELECT id
                FROM clients
                WHERE LOWER(COALESCE(status, ''))='deleted'
            )
            """
        )

        # Rebuild every representative's used_bytes with the exact same
        # accounting function used by the live quota system.
        reps = con.execute(
            """
            SELECT id
            FROM representatives
            """
        ).fetchall()

        repaired_reps = 0

        for rep in reps:
            rep_id = int(rep["id"])
            used = max(
                0,
                int(representative_usage(con, rep_id)),
            )

            con.execute(
                """
                UPDATE representatives
                SET used_bytes=?
                WHERE id=?
                """,
                (
                    used,
                    rep_id,
                ),
            )

            repaired_reps += 1

        con.execute(
            """
            INSERT INTO maintenance_migrations(
                name,
                applied_at
            )
            VALUES(?,?)
            """,
            (
                _USAGE_BASELINE_REPAIR_V1,
                stamp,
            ),
        )

        con.commit()

    print(
        "[usage-repair-v1] applied:"
        f" clients={repaired_clients}"
        f" ledgers_created={created_ledgers}"
        f" representatives={repaired_reps}"
    )

    return True


def sync_all(*args, **kwargs):
    result = _USAGE_BASELINE_OLD_SYNC_ALL(
        *args,
        **kwargs,
    )

    # Baseline only after a successful sync using the fixed x-ui
    # traffic snapshot. If the sync fails, do nothing and retry later.
    if not isinstance(result, dict) or not result.get("ok"):
        return result

    try:
        repaired = _usage_baseline_repair_v1()
    except Exception as exc:
        print(
            "[usage-repair-v1] failed:",
            repr(exc),
        )
        # No marker is written on failure, so the next successful sync
        # will retry automatically.
        return result

    if repaired:
        # One additional sync starts normal delta accounting from the
        # clean baseline and refreshes representative quota state.
        try:
            return _USAGE_BASELINE_OLD_SYNC_ALL(True)
        except Exception as exc:
            print(
                "[usage-repair-v1] post-repair sync failed:",
                repr(exc),
            )

    return result
