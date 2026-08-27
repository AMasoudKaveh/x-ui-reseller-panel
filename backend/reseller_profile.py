from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "auth.db"

SESSION_COOKIE = "xui_session"



router = APIRouter(
    prefix="/api/reseller",
    tags=["Reseller"]
)


def connect_db() -> sqlite3.Connection:

    con = sqlite3.connect(DB_PATH, timeout=30.0)

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 30000")

    return con


def ensure_profile_schema() -> None:

    with connect_db() as con:

        table = con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'representatives'
            """
        ).fetchone()

        if not table:

            raise RuntimeError(
                "representatives table does not exist"
            )


        columns = {
            row["name"]
            for row in con.execute(
                """
                PRAGMA table_info(representatives)
                """
            ).fetchall()
        }


        if "quota_bytes" not in columns:

            con.execute(
                """
                ALTER TABLE representatives
                ADD COLUMN quota_bytes
                INTEGER NOT NULL DEFAULT 0
                """
            )


        if "used_bytes" not in columns:

            con.execute(
                """
                ALTER TABLE representatives
                ADD COLUMN used_bytes
                INTEGER NOT NULL DEFAULT 0
                """
            )


        if "total_users" not in columns:

            con.execute(
                """
                ALTER TABLE representatives
                ADD COLUMN total_users
                INTEGER NOT NULL DEFAULT 0
                """
            )

        con.commit()


def get_reseller_from_session(
    token: str | None
) -> sqlite3.Row:

    if not token:

        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )


    now = int(time.time())


    with connect_db() as con:

        session = con.execute(
            """
            SELECT
                role,
                account_id,
                expires_at

            FROM auth_sessions

            WHERE token = ?
            """,
            (token,),
        ).fetchone()


        if not session:

            raise HTTPException(
                status_code=401,
                detail="Invalid session",
            )


        if int(session["expires_at"]) <= now:

            con.execute(
                """
                DELETE FROM auth_sessions
                WHERE token = ?
                """,
                (token,),
            )

            con.commit()

            raise HTTPException(
                status_code=401,
                detail="Session expired",
            )


        if session["role"] != "reseller":

            raise HTTPException(
                status_code=403,
                detail="Reseller access required",
            )


        reseller = con.execute(
            """
            SELECT
                id,
                username,
                status,
                quota_bytes,
                used_bytes,
                total_users

            FROM representatives

            WHERE id = ?
            """,
            (
                int(session["account_id"]),
            ),
        ).fetchone()


        if not reseller:

            raise HTTPException(
                status_code=404,
                detail="Representative not found",
            )


        if str(
            reseller["status"]
        ).lower() != "active":

            raise HTTPException(
                status_code=403,
                detail="Representative account is inactive",
            )


        return reseller


@router.get("/profile")
def reseller_profile(
    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):

    ensure_profile_schema()

    reseller = get_reseller_from_session(
        xui_session
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
        quota_bytes - used_bytes,
    )


    if quota_bytes > 0:

        usage_percent = min(
            100.0,
            (
                used_bytes
                / quota_bytes
            )
            * 100,
        )

    else:

        usage_percent = 0.0


    return {

        "ok": True,

        "profile": {

            "id":
                int(reseller["id"]),

            "username":
                reseller["username"],

            "role":
                "reseller",

            "display_role":
                "operator",

            "status":
                reseller["status"],

            "quota_bytes":
                quota_bytes,

            "used_bytes":
                used_bytes,

            "remaining_bytes":
                remaining_bytes,

            "usage_percent":
                round(
                    usage_percent,
                    4
                ),

            "total_users":
                int(
                    reseller["total_users"]
                    or 0
                ),
        }
    }
