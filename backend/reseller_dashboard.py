from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import psutil
from fastapi import APIRouter, Cookie

from backend.reseller_profile import (
    SESSION_COOKIE,
    connect_db,
    ensure_profile_schema,
    get_reseller_from_session,
)


router = APIRouter(
    prefix="/api/reseller",
    tags=["Reseller Dashboard"],
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


def table_columns(
    con: sqlite3.Connection,
    table_name: str,
) -> set[str]:

    if not table_exists(
        con,
        table_name,
    ):
        return set()

    rows = con.execute(
        f"""
        PRAGMA table_info({table_name})
        """
    ).fetchall()

    return {
        str(row["name"])
        for row in rows
    }


def get_system_stats():

    cpu_percent = float(
        psutil.cpu_percent(
            interval=0.10
        )
    )

    cpu_cores = int(
        psutil.cpu_count(
            logical=True
        )
        or 0
    )

    memory = psutil.virtual_memory()

    disk_root = (
        Path.cwd().anchor
        or "/"
    )

    try:
        disk = psutil.disk_usage(
            disk_root
        )
    except Exception:
        disk = psutil.disk_usage(
            "/"
        )

    network = psutil.net_io_counters()

    boot_time = float(
        psutil.boot_time()
    )

    uptime_seconds = max(
        0,
        int(
            time.time()
            - boot_time
        ),
    )

    return {
        "cpu_percent":
            round(cpu_percent, 1),

        "cpu_cores":
            cpu_cores,

        "ram_used_bytes":
            int(memory.used),

        "ram_total_bytes":
            int(memory.total),

        "ram_percent":
            round(
                float(memory.percent),
                1
            ),

        "disk_used_bytes":
            int(disk.used),

        "disk_total_bytes":
            int(disk.total),

        "disk_percent":
            round(
                float(disk.percent),
                1
            ),

        "network_upload_bytes":
            int(network.bytes_sent),

        "network_download_bytes":
            int(network.bytes_recv),

        "network_total_bytes":
            int(
                network.bytes_sent
                +
                network.bytes_recv
            ),

        "uptime_seconds":
            uptime_seconds,
    }


def get_user_stats(
    con: sqlite3.Connection,
    reseller_id: int,
    fallback_total: int,
):

    if not table_exists(
        con,
        "clients",
    ):

        return {
            "total":
                fallback_total,

            "active":
                fallback_total,

            "online":
                0,

            "expired":
                0,

            "limited":
                0,

            "on_hold":
                0,

            "disabled":
                0,
        }


    columns = table_columns(
        con,
        "clients",
    )


    if "seller_rep_id" not in columns:

        return {
            "total":
                fallback_total,

            "active":
                fallback_total,

            "online":
                0,

            "expired":
                0,

            "limited":
                0,

            "on_hold":
                0,

            "disabled":
                0,
        }


    rows = con.execute(
        """
        SELECT *
        FROM clients
        WHERE seller_rep_id = ?
        """,
        (reseller_id,),
    ).fetchall()


    now_ms = int(
        time.time() * 1000
    )


    total = 0
    active = 0
    expired = 0
    on_hold = 0
    disabled = 0


    for row in rows:

        data = dict(row)

        status = str(
            data.get("status")
            or ""
        ).lower()


        if status == "deleted":
            continue


        total += 1


        enabled = True

        if "enabled" in columns:
            enabled = bool(
                data.get("enabled")
            )


        expire_at_ms = int(
            data.get(
                "expire_at_ms"
            )
            or 0
        )


        is_expired = (
            expire_at_ms > 0
            and
            expire_at_ms <= now_ms
        )


        is_hold = status in (
            "hold",
            "on_hold",
            "paused",
        )


        is_disabled = (
            not enabled
            or
            status in (
                "disabled",
                "inactive",
                "blocked",
            )
        )


        if is_expired:
            expired += 1


        if is_hold:
            on_hold += 1


        if is_disabled:
            disabled += 1


        if (
            enabled
            and
            not is_expired
            and
            not is_hold
            and
            not is_disabled
        ):
            active += 1


    limited = 0


    if (
        table_exists(
            con,
            "traffic_ledger",
        )
        and
        "total_limit_bytes"
        in columns
    ):

        try:

            limited_row = con.execute(
                """
                SELECT COUNT(*) AS total

                FROM clients c

                LEFT JOIN traffic_ledger l
                  ON l.client_id = c.id

                WHERE c.seller_rep_id = ?

                  AND COALESCE(
                    c.total_limit_bytes,
                    0
                  ) > 0

                  AND COALESCE(
                    l.cumulative_used_bytes,
                    0
                  ) >= c.total_limit_bytes

                  AND COALESCE(
                    c.status,
                    ''
                  ) != 'deleted'
                """,
                (reseller_id,),
            ).fetchone()

            limited = int(
                limited_row["total"]
                or 0
            )

        except Exception:
            limited = 0


    online = sum(
        1
        for row in rows
        if int(
            dict(row).get("is_online")
            or 0
        )
    )


    return {
        "total":
            total,

        "active":
            active,

        "online":
            online,

        "expired":
            expired,

        "limited":
            limited,

        "on_hold":
            on_hold,

        "disabled":
            disabled,
    }


def get_usage_history(
    con: sqlite3.Connection,
    reseller_id: int,
):

    today = datetime.now().date()

    days = [
        today
        - timedelta(days=index)

        for index in reversed(
            range(7)
        )
    ]


    totals = {
        day.isoformat(): 0
        for day in days
    }


    if table_exists(
        con,
        "traffic_events",
    ):

        columns = table_columns(
            con,
            "traffic_events",
        )


        required = {
            "created_at",
            "seller_rep_id",
            "delta_bytes",
        }


        if required.issubset(
            columns
        ):

            first_day = days[0].isoformat()


            try:

                rows = con.execute(
                    """
                    SELECT
                        substr(
                            created_at,
                            1,
                            10
                        ) AS event_day,

                        SUM(
                            CASE
                                WHEN delta_bytes > 0
                                THEN delta_bytes
                                ELSE 0
                            END
                        ) AS total_bytes

                    FROM traffic_events

                    WHERE seller_rep_id = ?

                      AND substr(
                            created_at,
                            1,
                            10
                          ) >= ?

                    GROUP BY
                        substr(
                            created_at,
                            1,
                            10
                        )
                    """,
                    (
                        reseller_id,
                        first_day,
                    ),
                ).fetchall()


                for row in rows:

                    event_day = str(
                        row["event_day"]
                        or ""
                    )


                    if event_day in totals:

                        totals[event_day] = max(
                            0,
                            int(
                                row["total_bytes"]
                                or 0
                            ),
                        )

            except Exception:
                pass


    return [
        {
            "date":
                day.isoformat(),

            "label":
                day.strftime(
                    "%m/%d"
                ),

            "bytes":
                totals[
                    day.isoformat()
                ],
        }

        for day in days
    ]


@router.get("/dashboard")
def reseller_dashboard(
    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):

    ensure_profile_schema()


    reseller = get_reseller_from_session(
        xui_session
    )


    reseller_id = int(
        reseller["id"]
    )


    quota_bytes = max(
        0,
        int(
            reseller["quota_bytes"]
            or 0
        ),
    )


    used_bytes = max(
        0,
        int(
            reseller["used_bytes"]
            or 0
        ),
    )


    remaining_bytes = max(
        0,
        quota_bytes
        -
        used_bytes,
    )


    with connect_db() as con:

        user_stats = get_user_stats(
            con,
            reseller_id,
            int(
                reseller["total_users"]
                or 0
            ),
        )


        usage_history = get_usage_history(
            con,
            reseller_id,
        )


    if quota_bytes > 0:

        quota_percent = min(
            100.0,

            (
                used_bytes
                /
                quota_bytes
            )
            *
            100,
        )

    else:
        quota_percent = 0.0


    return {
        "ok": True,

        "dashboard": {

            "reseller": {
                "id":
                    reseller_id,

                "username":
                    reseller["username"],

                "status":
                    reseller["status"],

                "quota_bytes":
                    quota_bytes,

                "used_bytes":
                    used_bytes,

                "remaining_bytes":
                    remaining_bytes,

                "quota_percent":
                    round(
                        quota_percent,
                        4
                    ),
            },

            "system":
                get_system_stats(),

            "users":
                user_stats,

            "usage":
                usage_history,
        }
    }
