from __future__ import annotations

import json
import sqlite3
import time

from datetime import (
    datetime,
    timezone,
)

from fastapi import (
    APIRouter,
    Cookie,
)

from backend.reseller_profile import (
    SESSION_COOKIE,
    connect_db,
    ensure_profile_schema,
    get_reseller_from_session,
)


router = APIRouter(
    prefix="/api/reseller",
    tags=["Reseller Users"],
)




def table_exists(
    con: sqlite3.Connection,
    table_name: str,
) -> bool:

    row = con.execute(
        """
        SELECT name

        FROM sqlite_master

        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def ensure_users_schema() -> None:

    ensure_profile_schema()

    with connect_db() as con:

        #
        # Same important client columns
        # as the old production backend.
        #

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (

                id INTEGER
                    PRIMARY KEY AUTOINCREMENT,

                email TEXT
                    NOT NULL,

                uuid TEXT,

                sub_id TEXT,

                panel_id TEXT,

                owner_rep_id INTEGER,

                seller_rep_id INTEGER,

                customer_name TEXT,

                customer_ref TEXT,

                service_type TEXT
                    NOT NULL
                    DEFAULT 'normal',

                inbound_ids TEXT
                    NOT NULL
                    DEFAULT '[]',

                total_limit_bytes INTEGER
                    NOT NULL
                    DEFAULT 0,

                expire_at_ms INTEGER
                    NOT NULL
                    DEFAULT 0,

                status TEXT
                    NOT NULL
                    DEFAULT 'active',

                panel_comment TEXT,

                created_at TEXT
                    NOT NULL,

                updated_at TEXT
                    NOT NULL,

                enabled INTEGER
                    NOT NULL
                    DEFAULT 1,

                group_name TEXT,

                limit_ip INTEGER
                    NOT NULL
                    DEFAULT 0
            )
            """
        )


        con.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_clients_seller_rep_id

            ON clients(
                seller_rep_id
            )
            """
        )


        con.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_clients_email

            ON clients(
                email
            )
            """
        )


        con.execute(
            """
            CREATE TABLE IF NOT EXISTS traffic_ledger (

                client_id INTEGER
                    PRIMARY KEY,

                last_panel_up INTEGER
                    NOT NULL
                    DEFAULT 0,

                last_panel_down INTEGER
                    NOT NULL
                    DEFAULT 0,

                last_panel_total INTEGER
                    NOT NULL
                    DEFAULT 0,

                cumulative_used_bytes INTEGER
                    NOT NULL
                    DEFAULT 0,

                reset_detected_count INTEGER
                    NOT NULL
                    DEFAULT 0,

                last_reset_detected_at TEXT,

                last_seen_at TEXT,

                last_panel_used_bytes INTEGER
                    DEFAULT 0
            )
            """
        )


        con.commit()


def safe_json_list(
    value,
) -> list[int]:

    if value is None:
        return []


    try:

        parsed = json.loads(
            str(value)
        )

        if not isinstance(
            parsed,
            list,
        ):
            return []


        result: list[int] = []


        for item in parsed:

            try:
                result.append(
                    int(item)
                )

            except (
                ValueError,
                TypeError,
            ):
                pass


        return result

    except Exception:

        return []


def parse_datetime(
    value,
):

    if not value:
        return None


    try:

        text = str(value)


        if text.endswith("Z"):

            text = (
                text[:-1]
                +
                "+00:00"
            )


        result = datetime.fromisoformat(
            text
        )


        if result.tzinfo is None:

            result = result.replace(
                tzinfo=timezone.utc
            )


        return result

    except Exception:

        return None


def age_label(
    value,
) -> str:

    created = parse_datetime(
        value
    )


    if not created:
        return "—"


    now = datetime.now(
        timezone.utc
    )


    seconds = max(
        0,
        int(
            (
                now
                -
                created
            ).total_seconds()
        ),
    )


    if seconds < 60:

        return f"{seconds}s"


    minutes = seconds // 60


    if minutes < 60:

        return f"{minutes}m"


    hours = minutes // 60


    if hours < 24:

        return f"{hours}h"


    days = hours // 24


    if days < 30:

        return f"{days}d"


    months = days // 30


    if months < 12:

        return f"{months}mo"


    years = days // 365

    return f"{years}y"


def expiry_label(
    expire_at_ms: int,
) -> str:

    if expire_at_ms < 0:

        days = max(
            1,
            int(abs(expire_at_ms) // 86_400_000),
        )

        return (
            f"After first use · {days} day"
            if days == 1
            else f"After first use · {days} days"
        )

    if expire_at_ms == 0:

        return "Never"


    now_ms = int(
        time.time()
        * 1000
    )


    delta_ms = (
        expire_at_ms
        -
        now_ms
    )


    if delta_ms <= 0:

        return "Expired"


    seconds = int(
        delta_ms / 1000
    )


    days = seconds // 86400


    if days > 0:

        return (
            f"{days} day"
            if days == 1
            else f"{days} days"
        )


    hours = (
        seconds
        % 86400
    ) // 3600


    if hours > 0:

        return (
            f"{hours} hour"
            if hours == 1
            else f"{hours} hours"
        )


    minutes = max(
        1,
        seconds // 60
    )


    return (
        f"{minutes} minute"
        if minutes == 1
        else f"{minutes} minutes"
    )


def build_status(
    enabled: bool,
    status_value,
    expire_at_ms: int,
):

    now_ms = int(
        time.time()
        * 1000
    )


    if not enabled:

        return (
            "Disabled",
            "disabled",
        )


    if (
        expire_at_ms > 0
        and
        expire_at_ms <= now_ms
    ):

        return (
            "Expired",
            "expired",
        )


    normalized = str(
        status_value
        or "active"
    ).strip().lower()


    if normalized in (
        "disabled",
        "inactive",
        "blocked",
    ):

        return (
            "Disabled",
            "disabled",
        )


    if normalized in (
        "hold",
        "on_hold",
        "paused",
    ):

        return (
            "On Hold",
            "hold",
        )


    return (
        "Active",
        "active",
    )


@router.get("/users")
def reseller_users(
    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):

    ensure_users_schema()


    reseller = get_reseller_from_session(
        xui_session
    )


    reseller_id = int(
        reseller["id"]
    )


    # Keep this endpoint fresh even if the background task is delayed.
    from backend.reseller_live_quota import (
        ensure_live_schema,
        sync_if_due,
    )
    ensure_live_schema()
    sync_if_due()


    with connect_db() as con:

        rows = con.execute(
            """
            SELECT

                c.id,
                c.email,

                c.customer_name,

                c.service_type,

                c.inbound_ids,

                c.total_limit_bytes,

                c.expire_at_ms,

                c.status,

                c.panel_comment,

                c.created_at,
                c.updated_at,

                c.enabled,

                c.limit_ip,

                COALESCE(
                    c.is_online,
                    0
                ) AS is_online,

                c.last_online_at,

                COALESCE(
                    c.own_limit_exhausted,
                    0
                ) AS own_limit_exhausted,

                COALESCE(
                    c.panel_used_bytes,
                    l.last_panel_used_bytes,
                    l.last_panel_total,
                    0
                ) AS panel_used_live_bytes,

                COALESCE(
                    l.last_panel_used_bytes,
                    l.last_panel_total,
                    0
                ) AS panel_used_bytes,

                COALESCE(
                    l.cumulative_used_bytes,
                    0
                ) AS cumulative_used_bytes,

                l.last_seen_at

            FROM clients c

            LEFT JOIN traffic_ledger l
              ON l.client_id = c.id

            WHERE c.seller_rep_id = ?

            ORDER BY
                c.created_at DESC,
                c.id DESC
            """,
            (
                reseller_id,
            ),
        ).fetchall()


    users = []


    total = 0
    active = 0
    disabled = 0
    expired = 0
    on_hold = 0


    for row in rows:

        row_status = str(
            row["status"]
            or ""
        ).lower()


        if row_status == "deleted":

            continue


        enabled = bool(
            row["enabled"]
        )


        expire_at_ms = int(
            row["expire_at_ms"]
            or 0
        )


        status_label, status_code = (
            build_status(
                enabled,
                row["status"],
                expire_at_ms,
            )
        )


        if status_code == "active":
            active += 1

        elif status_code == "disabled":
            disabled += 1

        elif status_code == "expired":
            expired += 1

        elif status_code == "hold":
            on_hold += 1


        total += 1


        limit_bytes = max(
            0,
            int(
                row["total_limit_bytes"]
                or 0
            ),
        )


        panel_used_bytes = max(
            0,
            int(
                row["panel_used_live_bytes"]
                or row["panel_used_bytes"]
                or 0
            ),
        )


        cumulative_used_bytes = max(
            0,
            int(
                row["cumulative_used_bytes"]
                or 0
            ),
        )


        if limit_bytes > 0:

            usage_percent = min(
                100.0,

                (
                    panel_used_bytes
                    /
                    limit_bytes
                )
                *
                100,
            )

        else:

            usage_percent = 0.0


        users.append(
            {
                "id":
                    int(row["id"]),

                "username":
                    row["email"],

                "customer_name":
                    row["customer_name"],

                "service_type":
                    row["service_type"],

                "status":
                    status_label,

                "status_code":
                    status_code,

                "enabled":
                    enabled,

                "online":
                    bool(
                        row["is_online"]
                    ),

                "inbound_ids":
                    safe_json_list(
                        row["inbound_ids"]
                    ),

                "limit_ip":
                    int(
                        row["limit_ip"]
                        or 0
                    ),

                "traffic_limit_bytes":
                    limit_bytes,

                "used_bytes":
                    panel_used_bytes,

                "total_used_bytes":
                    cumulative_used_bytes,

                "usage_percent":
                    round(
                        usage_percent,
                        4
                    ),

                "expire_at_ms":
                    expire_at_ms,

                "expires_in":
                    expiry_label(
                        expire_at_ms
                    ),

                "created_at":
                    row["created_at"],

                "updated_at":
                    row["updated_at"],

                "age":
                    age_label(
                        row["created_at"]
                    ),

                "last_online_at":
                    row["last_online_at"],

                "comment":
                    row["panel_comment"],
            }
        )


    online = sum(
        1
        for user in users
        if user.get("online")
    )


    return {
        "ok": True,

        "summary": {
            "total":
                total,

            "active":
                active,

            "online":
                online,

            "disabled":
                disabled,

            "expired":
                expired,

            "on_hold":
                on_hold,
        },

        "users":
            users,
    }
