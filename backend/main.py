from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, FastAPI, HTTPException, Response
from pydantic import BaseModel

from backend.xui_client import env_bool, env_string


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "auth.db"

SESSION_COOKIE = "xui_session"
SESSION_TTL_SECONDS = 12 * 60 * 60

PBKDF2_ROUNDS = 200_000


# Production bootstrap is only used when the database has no admin account.
# Keep these values in backend/.env or the process environment, never in source.
ADMIN_BOOTSTRAP_USERNAME = env_string("ADMIN_BOOTSTRAP_USERNAME")
ADMIN_BOOTSTRAP_PASSWORD = env_string("ADMIN_BOOTSTRAP_PASSWORD")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)


class LoginBody(BaseModel):
    username: str
    password: str


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 30000")
    return con


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ROUNDS,
    ).hex()

    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False

    try:
        algorithm, salt, expected = stored.split("$", 2)

        if algorithm != "pbkdf2_sha256":
            return False

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ROUNDS,
        ).hex()

        return hmac.compare_digest(actual, expected)

    except (ValueError, TypeError):
        return False


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with db() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );


            CREATE TABLE IF NOT EXISTS representatives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at INTEGER NOT NULL
            );


            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,

                role TEXT NOT NULL
                CHECK(role IN ('admin', 'reseller')),

                account_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            """
        )

        now = int(time.time())

        # Bootstrap the first admin only on a fresh database.
        admin = con.execute(
            "SELECT id FROM admins ORDER BY id LIMIT 1"
        ).fetchone()

        if not admin:
            username = ADMIN_BOOTSTRAP_USERNAME.strip()
            password = ADMIN_BOOTSTRAP_PASSWORD

            if not username or len(password) < 8:
                raise RuntimeError(
                    "Fresh database requires ADMIN_BOOTSTRAP_USERNAME and "
                    "ADMIN_BOOTSTRAP_PASSWORD (minimum 8 characters) in backend/.env "
                    "or the process environment."
                )

            con.execute(
                """
                INSERT INTO admins(
                    username,
                    password_hash,
                    is_active,
                    created_at
                )
                VALUES(?, ?, 1, ?)
                """,
                (username, hash_password(password), now),
            )

        # Remove expired sessions.
        con.execute(
            """
            DELETE FROM auth_sessions
            WHERE expires_at <= ?
            """,
            (now,),
        )

        con.commit()


def create_session(
    response: Response,
    role: str,
    account_id: int,
) -> None:

    token = secrets.token_urlsafe(48)

    now = int(time.time())
    expires_at = now + SESSION_TTL_SECONDS

    with db() as con:

        con.execute(
            """
            DELETE FROM auth_sessions
            WHERE expires_at <= ?
            """,
            (now,),
        )

        con.execute(
            """
            INSERT INTO auth_sessions(
                token,
                role,
                account_id,
                expires_at,
                created_at
            )
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                token,
                role,
                account_id,
                expires_at,
                now,
            ),
        )

        con.commit()


    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/",
    )


def read_session(token: str | None):
    if not token:
        return None

    now = int(time.time())

    with db() as con:

        session = con.execute(
            """
            SELECT
                token,
                role,
                account_id,
                expires_at
            FROM auth_sessions
            WHERE token = ?
            """,
            (token,),
        ).fetchone()

        if not session:
            return None

        if int(session["expires_at"]) <= now:

            con.execute(
                """
                DELETE FROM auth_sessions
                WHERE token = ?
                """,
                (token,),
            )

            con.commit()

            return None

        return session


@asynccontextmanager
async def lifespan(_: FastAPI):

    init_db()

    # Start quota/traffic enforcement inside the lifespan. FastAPI does not
    # run @app.on_event startup handlers when a lifespan handler is supplied.
    from backend.reseller_live_quota import (
        start_background_sync,
        stop_background_sync,
    )

    start_background_sync()

    try:
        yield
    finally:
        await stop_background_sync()


app = FastAPI(
    title="x-ui Local Auth API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def health():

    return {
        "ok": True
    }


@app.post("/api/auth/admin/login")
def admin_login(
    body: LoginBody,
    response: Response,
):

    username = body.username.strip()

    with db() as con:

        row = con.execute(
            """
            SELECT
                id,
                username,
                password_hash,
                is_active
            FROM admins
            WHERE username = ?
            """,
            (username,),
        ).fetchone()


    if not row or not verify_password(
        body.password,
        row["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )


    if not bool(row["is_active"]):

        raise HTTPException(
            status_code=403,
            detail="Admin account is inactive",
        )


    create_session(
        response=response,
        role="admin",
        account_id=int(row["id"]),
    )


    return {
        "ok": True,

        "user": {
            "username": row["username"],
            "role": "admin",
        }
    }


@app.post("/api/auth/reseller/login")
def reseller_login(
    body: LoginBody,
    response: Response,
):

    username = body.username.strip()

    with db() as con:

        row = con.execute(
            """
            SELECT
                id,
                username,
                password_hash,
                status
            FROM representatives
            WHERE username = ?
            """,
            (username,),
        ).fetchone()


    if not row or not verify_password(
        body.password,
        row["password_hash"],
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )


    if str(row["status"]).lower() != "active":

        raise HTTPException(
            status_code=403,
            detail="Representative account is inactive",
        )


    create_session(
        response=response,
        role="reseller",
        account_id=int(row["id"]),
    )


    return {
        "ok": True,

        "user": {
            "username": row["username"],
            "role": "reseller",
        }
    }


@app.get("/api/auth/me")
def me(
    xui_session: str | None = Cookie(default=None),
):

    session = read_session(xui_session)

    if not session:

        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )


    role = str(session["role"])
    account_id = int(session["account_id"])


    with db() as con:

        if role == "admin":

            account = con.execute(
                """
                SELECT
                    username,
                    is_active
                FROM admins
                WHERE id = ?
                """,
                (account_id,),
            ).fetchone()


            if not account or not bool(account["is_active"]):

                raise HTTPException(
                    status_code=401,
                    detail="Session is no longer valid",
                )


        else:

            account = con.execute(
                """
                SELECT
                    username,
                    status
                FROM representatives
                WHERE id = ?
                """,
                (account_id,),
            ).fetchone()


            if (
                not account
                or str(account["status"]).lower()
                != "active"
            ):

                raise HTTPException(
                    status_code=401,
                    detail="Session is no longer valid",
                )


    return {
        "ok": True,

        "user": {
            "username": account["username"],
            "role": role,
        }
    }


@app.post("/api/auth/logout")
def logout(
    response: Response,
    xui_session: str | None = Cookie(default=None),
):

    if xui_session:

        with db() as con:

            con.execute(
                """
                DELETE FROM auth_sessions
                WHERE token = ?
                """,
                (xui_session,),
            )

            con.commit()


    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
    )


    return {
        "ok": True
    }
# === RESELLER PROFILE ROUTER ===

from backend.reseller_profile import (
    router as reseller_profile_router
)

app.include_router(
    reseller_profile_router
)


# === RESELLER DASHBOARD ROUTER ===

from backend.reseller_dashboard import (
    router as reseller_dashboard_router
)

app.include_router(
    reseller_dashboard_router
)


# === RESELLER USERS ROUTER ===

from backend.reseller_users import (
    router as reseller_users_router
)

app.include_router(
    reseller_users_router
)


# === RESELLER CREATE USER XUI ROUTER ===

from backend.reseller_create_user import (
    router as reseller_create_user_router
)

app.include_router(
    reseller_create_user_router
)

# === RESELLER ALL USER ACTIONS ROUTER ===

from backend.reseller_user_actions import (
    router as reseller_user_actions_router
)

app.include_router(
    reseller_user_actions_router
)

# === RESELLER LIVE TRAFFIC + QUOTA ROUTER ===

from backend.reseller_live_quota import (
    router as reseller_live_quota_router,
)

app.include_router(
    reseller_live_quota_router
)



# === ADMIN REPRESENTATIVES ROUTER ===
from backend.admin_representatives import (
    router as admin_representatives_router
)

app.include_router(
    admin_representatives_router
)
# === END ADMIN REPRESENTATIVES ROUTER ===

# === ADMIN DASHBOARD ROUTER ===
from backend.admin_dashboard import (
    router as admin_dashboard_router
)

app.include_router(
    admin_dashboard_router
)
# === END ADMIN DASHBOARD ROUTER ===

# === ADMIN CLIENTS ROUTER ===
from backend.admin_clients import (
    router as admin_clients_router
)

app.include_router(
    admin_clients_router
)
# === END ADMIN CLIENTS ROUTER ===

# === ADMIN SETTINGS ROUTER ===
from backend.admin_settings import (
    router as admin_settings_router
)

app.include_router(
    admin_settings_router
)
# === END ADMIN SETTINGS ROUTER ===
