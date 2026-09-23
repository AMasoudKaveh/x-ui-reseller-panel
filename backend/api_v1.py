from __future__ import annotations

import hashlib
import json
import secrets
import time

from datetime import datetime, timedelta

from contextlib import contextmanager
from dataclasses import dataclass

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Request,
    Security,
)

from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html

from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from pydantic import BaseModel, Field

from backend.api_rate_limit import enforce_api_rate_limit
from backend.version import app_version

from backend.reseller_profile import (
    SESSION_COOKIE,
    connect_db,
    ensure_profile_schema,
    get_reseller_from_session,
)

from backend.reseller_users import (
    reseller_users,
)

from backend.reseller_create_user import (
    CreateUserBody,
    create_reseller_user,
    reseller_inbounds,
)

from backend.reseller_user_actions import (
    ModifyUserBody,
    ToggleBody,
    modify_user,
    remove_user,
    reset_usage,
    revoke_subscription,
    toggle_user,
    user_access,
    user_details,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Public API v1"],
)

management_router = APIRouter(
    prefix="/api/reseller/api-keys",
    tags=["Reseller API Keys"],
)


docs_router = APIRouter(
    tags=["Public API Documentation"],
)


api_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Reseller API Key",
)


FULL_SCOPES = (
    "profile:read",
    "inbounds:read",
    "users:read",
    "users:create",
    "users:update",
    "users:reset",
    "users:revoke",
    "users:delete",
)


@dataclass(frozen=True)
class ApiPrincipal:
    representative_id: int
    representative_username: str
    api_key_id: int
    api_key_name: str
    scopes: frozenset[str]


class CreateApiKeyBody(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=64,
    )

    scopes: list[str] | None = None

    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
    )


class ApiRenewUserBody(BaseModel):
    traffic_gb: float | None = Field(
        default=None,
        gt=0,
        le=100000,
        description="Traffic to add to the user's current total limit.",
    )

    days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="New validity period starting from renewal time.",
    )

    start_after_first_use: bool = Field(
        default=False,
        description=(
            "When true, validity starts after the user's "
            "first use instead of immediately."
        ),
    )

    enable: bool = Field(
        default=True,
        description="Enable the user after renewal.",
    )


class ApiModifyUserBody(BaseModel):
    traffic_gb: float | None = Field(
        default=None,
        ge=0,
        le=100000,
    )

    expiry_date: str | None = None

    start_after_first_use: bool | None = None

    start_after_days: int | None = Field(
        default=None,
        ge=0,
        le=3650,
    )

    enabled: bool | None = None

    comment: str | None = None

    inbound_ids: list[int] | None = None

    limit_ip: int | None = Field(
        default=None,
        ge=0,
        le=1000,
    )

    telegram_user_id: str | None = None


def ensure_api_schema() -> None:
    ensure_profile_schema()

    with connect_db() as con:

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                representative_id INTEGER NOT NULL,

                name TEXT NOT NULL,

                key_prefix TEXT NOT NULL,

                key_hash TEXT NOT NULL UNIQUE,

                scopes TEXT NOT NULL DEFAULT '[]',

                is_active INTEGER NOT NULL DEFAULT 1,

                created_at INTEGER NOT NULL,

                last_used_at INTEGER,

                expires_at INTEGER,

                revoked_at INTEGER
            )
            """
        )

        con.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_api_keys_representative_id
            ON api_keys(representative_id)
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS api_audit_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                representative_id INTEGER NOT NULL,

                api_key_id INTEGER,

                action TEXT NOT NULL,

                client_id INTEGER,

                details TEXT,

                success INTEGER NOT NULL DEFAULT 1,

                created_at INTEGER NOT NULL
            )
            """
        )

        con.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_api_audit_rep_created
            ON api_audit_logs(
                representative_id,
                created_at
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS api_renew_idempotency(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                representative_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,

                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,

                status TEXT NOT NULL
                    DEFAULT 'pending',

                response_json TEXT,

                created_at INTEGER NOT NULL,
                completed_at INTEGER,

                UNIQUE(
                    representative_id,
                    idempotency_key
                )
            )
            """
        )

        con.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_api_renew_idempotency_client
            ON api_renew_idempotency(
                representative_id,
                client_id
            )
            """
        )

        con.commit()


def hash_api_key(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()



def renew_request_hash(
    client_id: int,
    body: ApiRenewUserBody,
) -> str:

    raw = json.dumps(
        {
            "client_id": int(client_id),
            "body": body.model_dump(
                mode="json"
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def reserve_renew_idempotency(
    principal: ApiPrincipal,
    client_id: int,
    idempotency_key: str,
    request_hash: str,
):

    ensure_api_schema()

    key = str(
        idempotency_key or ""
    ).strip()

    if not key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required",
        )

    if len(key) > 128:
        raise HTTPException(
            status_code=400,
            detail=(
                "Idempotency-Key must be "
                "128 characters or fewer"
            ),
        )

    with connect_db() as con:

        #
        # Serialize competing renewals so two simultaneous
        # requests cannot both reserve the same key.
        #
        con.execute("BEGIN IMMEDIATE")

        row = con.execute(
            """
            SELECT
                client_id,
                request_hash,
                status,
                response_json

            FROM api_renew_idempotency

            WHERE representative_id=?
              AND idempotency_key=?

            LIMIT 1
            """,
            (
                principal.representative_id,
                key,
            ),
        ).fetchone()

        if row:

            if (
                int(row["client_id"])
                != int(client_id)
                or
                str(row["request_hash"])
                != request_hash
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Idempotency-Key was already used "
                        "for a different renewal request"
                    ),
                )

            if (
                str(row["status"]) == "completed"
                and row["response_json"]
            ):
                try:
                    return json.loads(
                        str(
                            row["response_json"]
                        )
                    )
                except Exception:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Stored idempotent response "
                            "could not be decoded"
                        ),
                    )

            raise HTTPException(
                status_code=409,
                detail=(
                    "This renewal request is already "
                    "being processed or its final state "
                    "could not be confirmed"
                ),
            )

        con.execute(
            """
            INSERT INTO api_renew_idempotency(
                representative_id,
                client_id,
                idempotency_key,
                request_hash,
                status,
                created_at
            )
            VALUES(?,?,?,?, 'pending', ?)
            """,
            (
                principal.representative_id,
                int(client_id),
                key,
                request_hash,
                int(time.time()),
            ),
        )

        con.commit()

    return None


def complete_renew_idempotency(
    principal: ApiPrincipal,
    idempotency_key: str,
    response,
) -> None:

    with connect_db() as con:

        con.execute(
            """
            UPDATE api_renew_idempotency

            SET
                status='completed',
                response_json=?,
                completed_at=?

            WHERE representative_id=?
              AND idempotency_key=?
            """,
            (
                json.dumps(
                    response,
                    ensure_ascii=False,
                ),
                int(time.time()),
                principal.representative_id,
                idempotency_key,
            ),
        )

        con.commit()


def normalize_scopes(
    values: list[str] | None,
) -> list[str]:

    if values is None:
        return list(FULL_SCOPES)

    output: list[str] = []

    for value in values:
        scope = str(value or "").strip()

        if scope not in FULL_SCOPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid API scope: {scope}",
            )

        if scope not in output:
            output.append(scope)

    if not output:
        raise HTTPException(
            status_code=400,
            detail="At least one API scope is required",
        )

    return output


def require_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(
        api_bearer
    ),
) -> ApiPrincipal:

    ensure_api_schema()

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )

    if (
        str(credentials.scheme).lower()
        != "bearer"
    ):
        raise HTTPException(
            status_code=401,
            detail="Use Authorization: Bearer <API_KEY>",
        )

    token = str(
        credentials.credentials
        or ""
    ).strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )
    token_hash = hash_api_key(token)
    now = int(time.time())

    with connect_db() as con:

        row = con.execute(
            """
            SELECT
                k.id,
                k.representative_id,
                k.name,
                k.scopes,
                k.is_active,
                k.expires_at,
                k.revoked_at,

                r.username AS representative_username,
                r.status AS representative_status

            FROM api_keys k

            JOIN representatives r
              ON r.id = k.representative_id

            WHERE k.key_hash = ?

            LIMIT 1
            """,
            (token_hash,),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
            )

        if (
            not bool(row["is_active"])
            or row["revoked_at"] is not None
        ):
            raise HTTPException(
                status_code=401,
                detail="API key is revoked",
            )

        expires_at = row["expires_at"]

        if (
            expires_at is not None
            and int(expires_at) <= now
        ):
            raise HTTPException(
                status_code=401,
                detail="API key has expired",
            )

        if (
            str(
                row["representative_status"]
                or ""
            ).lower()
            != "active"
        ):
            raise HTTPException(
                status_code=403,
                detail="Representative account is inactive",
            )

        try:
            raw_scopes = json.loads(
                str(row["scopes"] or "[]")
            )
        except Exception:
            raw_scopes = []

        scopes = frozenset(
            str(item)
            for item in raw_scopes
            if str(item) in FULL_SCOPES
        )


        enforce_api_rate_limit(
            identity=f"reseller:{int(row['id'])}",
            method=request.method,
        )

        con.execute(
            """
            UPDATE api_keys
            SET last_used_at=?
            WHERE id=?
            """,
            (
                now,
                int(row["id"]),
            ),
        )

        con.commit()

    return ApiPrincipal(
        representative_id=int(
            row["representative_id"]
        ),
        representative_username=str(
            row["representative_username"]
        ),
        api_key_id=int(row["id"]),
        api_key_name=str(row["name"]),
        scopes=scopes,
    )


def require_scope(scope: str):

    def dependency(
        principal: ApiPrincipal = Depends(
            require_api_key
        ),
    ) -> ApiPrincipal:

        if scope not in principal.scopes:
            raise HTTPException(
                status_code=403,
                detail=(
                    "API key does not have "
                    f"required scope: {scope}"
                ),
            )

        return principal

    return dependency


@contextmanager
def temporary_reseller_session(
    representative_id: int,
):

    token = (
        "api_v1_"
        + secrets.token_urlsafe(32)
    )

    now = int(time.time())
    expires_at = now + 120

    with connect_db() as con:
        con.execute(
            """
            INSERT INTO auth_sessions(
                token,
                role,
                account_id,
                expires_at,
                created_at
            )
            VALUES(?, 'reseller', ?, ?, ?)
            """,
            (
                token,
                int(representative_id),
                expires_at,
                now,
            ),
        )
        con.commit()

    try:
        yield token

    finally:
        with connect_db() as con:
            con.execute(
                """
                DELETE FROM auth_sessions
                WHERE token=?
                """,
                (token,),
            )
            con.commit()


def audit(
    principal: ApiPrincipal,
    action: str,
    *,
    client_id: int | None = None,
    details: dict | None = None,
    success: bool = True,
) -> None:

    ensure_api_schema()

    with connect_db() as con:
        con.execute(
            """
            INSERT INTO api_audit_logs(
                representative_id,
                api_key_id,
                action,
                client_id,
                details,
                success,
                created_at
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                principal.representative_id,
                principal.api_key_id,
                action,
                client_id,
                json.dumps(
                    details or {},
                    ensure_ascii=False,
                ),
                1 if success else 0,
                int(time.time()),
            ),
        )
        con.commit()


def call_panel_route(
    principal: ApiPrincipal,
    action: str,
    callback,
    *,
    client_id: int | None = None,
):

    try:
        with temporary_reseller_session(
            principal.representative_id
        ) as token:
            result = callback(token)

        audit(
            principal,
            action,
            client_id=client_id,
            success=True,
        )

        return result

    except Exception as exc:

        audit(
            principal,
            action,
            client_id=client_id,
            details={
                "error": str(exc),
            },
            success=False,
        )

        raise


# =========================================================
# API KEY MANAGEMENT
# These routes use the normal reseller web-panel cookie.
# =========================================================


@management_router.get("")
def list_api_keys(
    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):

    ensure_api_schema()

    reseller = get_reseller_from_session(
        xui_session
    )

    rep_id = int(reseller["id"])

    with connect_db() as con:
        rows = con.execute(
            """
            SELECT
                id,
                name,
                key_prefix,
                scopes,
                is_active,
                created_at,
                last_used_at,
                expires_at,
                revoked_at

            FROM api_keys

            WHERE representative_id=?

            ORDER BY id DESC
            """,
            (rep_id,),
        ).fetchall()

    keys = []

    for row in rows:

        try:
            scopes = json.loads(
                str(row["scopes"] or "[]")
            )
        except Exception:
            scopes = []

        keys.append(
            {
                "id": int(row["id"]),
                "name": row["name"],
                "key_prefix":
                    row["key_prefix"],
                "scopes": scopes,
                "active": (
                    bool(row["is_active"])
                    and row["revoked_at"]
                    is None
                ),
                "created_at":
                    row["created_at"],
                "last_used_at":
                    row["last_used_at"],
                "expires_at":
                    row["expires_at"],
                "revoked_at":
                    row["revoked_at"],
            }
        )

    return {
        "ok": True,
        "keys": keys,
        "available_scopes":
            list(FULL_SCOPES),
    }


@management_router.post("")
def create_api_key(
    body: CreateApiKeyBody,

    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):

    ensure_api_schema()

    reseller = get_reseller_from_session(
        xui_session
    )

    rep_id = int(reseller["id"])

    name = body.name.strip()

    scopes = normalize_scopes(
        body.scopes
    )

    raw_key = (
        "xui_live_"
        + secrets.token_urlsafe(32)
    )

    prefix = raw_key[:18]
    key_hash = hash_api_key(raw_key)

    now = int(time.time())

    expires_at = None

    if body.expires_in_days:
        expires_at = (
            now
            +
            int(body.expires_in_days)
            * 86400
        )

    with connect_db() as con:

        cursor = con.execute(
            """
            INSERT INTO api_keys(
                representative_id,
                name,
                key_prefix,
                key_hash,
                scopes,
                is_active,
                created_at,
                expires_at
            )
            VALUES(?,?,?,?,?,1,?,?)
            """,
            (
                rep_id,
                name,
                prefix,
                key_hash,
                json.dumps(scopes),
                now,
                expires_at,
            ),
        )

        key_id = int(
            cursor.lastrowid
        )

        con.commit()

    return {
        "ok": True,

        "api_key": {
            "id": key_id,
            "name": name,
            "token": raw_key,
            "key_prefix": prefix,
            "scopes": scopes,
            "expires_at": expires_at,
        },

        "warning":
            "This token is shown only once.",
    }


@management_router.post("/{key_id}/revoke")
def revoke_api_key(
    key_id: int,

    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):

    ensure_api_schema()

    reseller = get_reseller_from_session(
        xui_session
    )

    rep_id = int(reseller["id"])
    now = int(time.time())

    with connect_db() as con:

        row = con.execute(
            """
            SELECT id
            FROM api_keys
            WHERE id=?
              AND representative_id=?
            """,
            (
                int(key_id),
                rep_id,
            ),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="API key not found",
            )

        con.execute(
            """
            UPDATE api_keys
            SET
                is_active=0,
                revoked_at=?
            WHERE id=?
              AND representative_id=?
            """,
            (
                now,
                int(key_id),
                rep_id,
            ),
        )

        con.commit()

    return {
        "ok": True,
        "revoked": int(key_id),
    }


# =========================================================
# PUBLIC API V1
# =========================================================


@router.get("/me")
def api_me(
    principal: ApiPrincipal = Depends(
        require_scope("profile:read")
    ),
):

    ensure_profile_schema()

    with connect_db() as con:

        rep = con.execute(
            """
            SELECT
                id,
                username,
                status,
                quota_bytes,
                used_bytes,
                total_users

            FROM representatives

            WHERE id=?
            """,
            (
                principal.representative_id,
            ),
        ).fetchone()

    if not rep:
        raise HTTPException(
            status_code=404,
            detail="Representative not found",
        )

    quota = max(
        0,
        int(rep["quota_bytes"] or 0),
    )

    used = max(
        0,
        int(rep["used_bytes"] or 0),
    )

    return {
        "ok": True,

        "data": {
            "id": int(rep["id"]),
            "username": rep["username"],
            "status": rep["status"],

            "quota_bytes": quota,
            "used_bytes": used,
            "remaining_bytes":
                max(0, quota - used),

            "total_users":
                int(rep["total_users"] or 0),

            "api_key": {
                "id":
                    principal.api_key_id,
                "name":
                    principal.api_key_name,
                "scopes":
                    sorted(principal.scopes),
            },
        },
    }


@router.get("/inbounds")
def api_inbounds(
    principal: ApiPrincipal = Depends(
        require_scope("inbounds:read")
    ),
):

    return call_panel_route(
        principal,
        "inbounds.list",
        lambda token:
            reseller_inbounds(
                xui_session=token
            ),
    )


@router.get("/users")
def api_users(
    principal: ApiPrincipal = Depends(
        require_scope("users:read")
    ),
):

    return call_panel_route(
        principal,
        "users.list",
        lambda token:
            reseller_users(
                xui_session=token
            ),
    )


@router.get("/users/online")
def api_online_users(
    principal: ApiPrincipal = Depends(
        require_scope("users:read")
    ),
):

    result = call_panel_route(
        principal,
        "users.online",
        lambda token:
            reseller_users(
                xui_session=token
            ),
    )

    users = [
        user
        for user in result.get(
            "users",
            [],
        )
        if bool(user.get("online"))
    ]

    return {
        "ok": True,
        "total": len(users),
        "users": users,
    }


@router.post("/users")
def api_create_user(
    body: CreateUserBody,

    principal: ApiPrincipal = Depends(
        require_scope("users:create")
    ),
):

    return call_panel_route(
        principal,
        "users.create",
        lambda token:
            create_reseller_user(
                body=body,
                xui_session=token,
            ),
    )


@router.get("/users/{client_id}")
def api_user_details(
    client_id: int,

    principal: ApiPrincipal = Depends(
        require_scope("users:read")
    ),
):

    return call_panel_route(
        principal,
        "users.details",
        lambda token:
            user_details(
                client_id=client_id,
                xui_session=token,
            ),
        client_id=client_id,
    )


@router.put("/users/{client_id}")
def api_modify_user(
    client_id: int,
    body: ModifyUserBody,

    principal: ApiPrincipal = Depends(
        require_scope("users:update")
    ),
):

    return call_panel_route(
        principal,
        "users.update",
        lambda token:
            modify_user(
                client_id=client_id,
                body=body,
                xui_session=token,
            ),
        client_id=client_id,
    )


@router.patch("/users/{client_id}")
def api_patch_user(
    client_id: int,
    body: ApiModifyUserBody,

    principal: ApiPrincipal = Depends(
        require_scope("users:update")
    ),
):

    if not body.model_fields_set:
        raise HTTPException(
            status_code=400,
            detail="No fields supplied for update",
        )

    def perform(token: str):

        current_result = user_details(
            client_id=client_id,
            xui_session=token,
        )

        current = current_result.get(
            "user",
            {},
        )

        if not current:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        current_start_after_first_use = bool(
            current.get(
                "start_after_first_use",
                False,
            )
        )

        current_start_after_days = int(
            current.get(
                "start_after_days",
                0,
            )
            or 0
        )

        #
        # If expiry_date is explicitly supplied,
        # switch from Start After First Use to
        # a normal absolute expiry unless caller
        # explicitly says otherwise.
        #
        if (
            "expiry_date"
            in body.model_fields_set
            and
            "start_after_first_use"
            not in body.model_fields_set
        ):
            effective_start_after_first_use = False

        elif (
            "start_after_days"
            in body.model_fields_set
            and
            "start_after_first_use"
            not in body.model_fields_set
        ):
            effective_start_after_first_use = True

        else:
            effective_start_after_first_use = (
                current_start_after_first_use
                if body.start_after_first_use is None
                else body.start_after_first_use
            )

        effective_start_after_days = (
            current_start_after_days
            if body.start_after_days is None
            else body.start_after_days
        )

        if (
            effective_start_after_first_use
            and effective_start_after_days <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "start_after_days must be at least 1 "
                    "when start_after_first_use is true"
                ),
            )

        payload = ModifyUserBody(
            traffic_gb=(
                float(
                    current.get(
                        "traffic_gb",
                        0,
                    )
                    or 0
                )
                if body.traffic_gb is None
                else body.traffic_gb
            ),

            expiry_date=(
                str(
                    current.get(
                        "expiry_date",
                        "",
                    )
                    or ""
                )
                if body.expiry_date is None
                else body.expiry_date
            ),

            start_after_first_use=(
                effective_start_after_first_use
            ),

            start_after_days=(
                effective_start_after_days
            ),

            enabled=(
                bool(
                    current.get(
                        "enabled",
                        True,
                    )
                )
                if body.enabled is None
                else body.enabled
            ),

            comment=(
                str(
                    current.get(
                        "comment",
                        "",
                    )
                    or ""
                )
                if body.comment is None
                else body.comment
            ),

            inbound_ids=(
                list(
                    current.get(
                        "inbound_ids",
                        [],
                    )
                    or []
                )
                if body.inbound_ids is None
                else body.inbound_ids
            ),

            limit_ip=(
                int(
                    current.get(
                        "limit_ip",
                        0,
                    )
                    or 0
                )
                if body.limit_ip is None
                else body.limit_ip
            ),

            telegram_user_id=(
                str(
                    current.get(
                        "telegram_user_id",
                        "",
                    )
                    or ""
                )
                if body.telegram_user_id is None
                else body.telegram_user_id
            ),
        )

        return modify_user(
            client_id=client_id,
            body=payload,
            xui_session=token,
        )

    return call_panel_route(
        principal,
        "users.patch",
        perform,
        client_id=client_id,
    )


@router.post("/users/{client_id}/renew")
def api_renew_user(
    client_id: int,
    body: ApiRenewUserBody,

    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
    ),

    principal: ApiPrincipal = Depends(
        require_scope("users:update")
    ),
):

    if (
        body.traffic_gb is None
        and body.days is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one of traffic_gb or days "
                "must be supplied"
            ),
        )

    if (
        body.start_after_first_use
        and body.days is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "days is required when "
                "start_after_first_use is true"
            ),
        )

    clean_idempotency_key = str(
        idempotency_key
    ).strip()

    request_hash = renew_request_hash(
        client_id,
        body,
    )

    def perform(token: str):

        current_result = user_details(
            client_id=client_id,
            xui_session=token,
        )

        current = current_result.get(
            "user",
            {},
        )

        if not current:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        current_traffic_gb = max(
            0.0,
            float(
                current.get(
                    "traffic_gb",
                    0,
                )
                or 0
            ),
        )

        added_traffic_gb = (
            float(body.traffic_gb)
            if body.traffic_gb is not None
            else 0.0
        )

        new_traffic_gb = (
            current_traffic_gb
            + added_traffic_gb
        )


        #
        # Expiry
        #
        # If days is supplied, renewal starts
        # from NOW, not from the old expiry.
        #
        if body.days is not None:

            if body.start_after_first_use:

                new_expiry_date = ""
                new_start_after_first_use = True
                new_start_after_days = int(
                    body.days
                )

            else:

                new_expiry_date = (
                    datetime.now()
                    + timedelta(
                        days=int(body.days)
                    )
                ).strftime(
                    "%Y-%m-%d"
                )

                new_start_after_first_use = False
                new_start_after_days = 0

        else:

            new_expiry_date = str(
                current.get(
                    "expiry_date",
                    "",
                )
                or ""
            )

            new_start_after_first_use = bool(
                current.get(
                    "start_after_first_use",
                    False,
                )
            )

            new_start_after_days = int(
                current.get(
                    "start_after_days",
                    0,
                )
                or 0
            )


        payload = ModifyUserBody(
            traffic_gb=new_traffic_gb,

            expiry_date=new_expiry_date,

            start_after_first_use=(
                new_start_after_first_use
            ),

            start_after_days=(
                new_start_after_days
            ),

            enabled=bool(
                body.enable
            ),

            comment=str(
                current.get(
                    "comment",
                    "",
                )
                or ""
            ),

            inbound_ids=list(
                current.get(
                    "inbound_ids",
                    [],
                )
                or []
            ),

            limit_ip=int(
                current.get(
                    "limit_ip",
                    0,
                )
                or 0
            ),

            telegram_user_id=str(
                current.get(
                    "telegram_user_id",
                    "",
                )
                or ""
            ),
        )


        #
        # All safe validation/read work is complete.
        # Reserve immediately before the real mutation.
        #
        replay = reserve_renew_idempotency(
            principal,
            client_id,
            clean_idempotency_key,
            request_hash,
        )

        if replay is not None:
            return replay


        modify_result = modify_user(
            client_id=client_id,
            body=payload,
            xui_session=token,
        )


        response = {
            "ok": True,

            "renewal": {
                "client_id":
                    int(client_id),

                "username":
                    current.get(
                        "username"
                    ),

                "previous_traffic_gb":
                    round(
                        current_traffic_gb,
                        4,
                    ),

                "added_traffic_gb":
                    round(
                        added_traffic_gb,
                        4,
                    ),

                "new_traffic_gb":
                    round(
                        new_traffic_gb,
                        4,
                    ),

                "days":
                    body.days,

                "start_after_first_use":
                    new_start_after_first_use,

                "expiry_date":
                    new_expiry_date,

                "enabled":
                    bool(body.enable),
            },

            "panel_result":
                modify_result,
        }

        complete_renew_idempotency(
            principal,
            clean_idempotency_key,
            response,
        )

        return response


    return call_panel_route(
        principal,
        "users.renew",
        perform,
        client_id=client_id,
    )


@router.post("/users/{client_id}/enable")
def api_enable_user(
    client_id: int,

    principal: ApiPrincipal = Depends(
        require_scope("users:update")
    ),
):

    return call_panel_route(
        principal,
        "users.enable",
        lambda token:
            toggle_user(
                client_id=client_id,
                body=ToggleBody(
                    enabled=True
                ),
                xui_session=token,
            ),
        client_id=client_id,
    )


@router.post("/users/{client_id}/disable")
def api_disable_user(
    client_id: int,

    principal: ApiPrincipal = Depends(
        require_scope("users:update")
    ),
):

    return call_panel_route(
        principal,
        "users.disable",
        lambda token:
            toggle_user(
                client_id=client_id,
                body=ToggleBody(
                    enabled=False
                ),
                xui_session=token,
            ),
        client_id=client_id,
    )


@router.post("/users/{client_id}/reset-usage")
def api_reset_user_usage(
    client_id: int,

    principal: ApiPrincipal = Depends(
        require_scope("users:reset")
    ),
):

    return call_panel_route(
        principal,
        "users.reset_usage",
        lambda token:
            reset_usage(
                client_id=client_id,
                xui_session=token,
            ),
        client_id=client_id,
    )


@router.post("/users/{client_id}/revoke-subscription")
def api_revoke_subscription(
    client_id: int,

    principal: ApiPrincipal = Depends(
        require_scope("users:revoke")
    ),
):

    return call_panel_route(
        principal,
        "users.revoke_subscription",
        lambda token:
            revoke_subscription(
                client_id=client_id,
                xui_session=token,
            ),
        client_id=client_id,
    )


@router.get("/users/{client_id}/access")
def api_user_access(
    client_id: int,

    request: Request,

    principal: ApiPrincipal = Depends(
        require_scope("users:read")
    ),
):

    return call_panel_route(
        principal,
        "users.access",
        lambda token:
            user_access(
                client_id=client_id,
                request=request,
                xui_session=token,
            ),
        client_id=client_id,
    )


@router.delete("/users/{client_id}")
def api_delete_user(
    client_id: int,

    principal: ApiPrincipal = Depends(
        require_scope("users:delete")
    ),
):

    return call_panel_route(
        principal,
        "users.delete",
        lambda token:
            remove_user(
                client_id=client_id,
                xui_session=token,
            ),
        client_id=client_id,
    )



# =========================================================
# PUBLIC API DOCUMENTATION
# =========================================================


@docs_router.get(
    "/api/v1/openapi.json",
    include_in_schema=False,
)
def public_api_openapi(
    request: Request,
):
    schema = get_openapi(
        title="X-UI Reseller Public API",
        version=app_version(),
        description=(
            "Public API for reseller integrations. "
            "Authenticate using Authorization: "
            "Bearer <API_KEY>."
        ),
        routes=router.routes,
    )

    schema["components"] = schema.get(
        "components",
        {},
    )

    schema["components"][
        "securitySchemes"
    ] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "API Key",
        }
    }


    #
    # Friendly documentation metadata
    #
    operations = {
        ("GET", "/api/v1/me"): {
            "summary": "Reseller account",
            "description": (
                "Returns the authenticated reseller account, "
                "traffic quota, used traffic and remaining traffic."
            ),
        },

        ("GET", "/api/v1/inbounds"): {
            "summary": "List allowed inbounds",
            "description": (
                "Returns only the inbounds available to "
                "the authenticated reseller."
            ),
        },

        ("GET", "/api/v1/users"): {
            "summary": "List users",
            "description": (
                "Returns reseller users with current status "
                "and usage information."
            ),
        },

        ("GET", "/api/v1/users/online"): {
            "summary": "List online users",
            "description": (
                "Returns only currently online reseller users."
            ),
        },

        ("POST", "/api/v1/users"): {
            "summary": "Create user",
            "description": (
                "Creates a new user using the same rules "
                "and permissions as the reseller panel."
            ),
        },

        ("GET", "/api/v1/users/{client_id}"): {
            "summary": "Get user",
            "description": (
                "Returns full details for one reseller user."
            ),
        },

        ("PUT", "/api/v1/users/{client_id}"): {
            "summary": "Replace user settings",
            "description": (
                "Full update. Intended for clients that send "
                "the complete user configuration."
            ),
        },

        ("PATCH", "/api/v1/users/{client_id}"): {
            "summary": "Update user",
            "description": (
                "Partial update. Only supplied fields are changed. "
                "Use this for renewals and normal API integrations."
            ),
        },

        ("DELETE", "/api/v1/users/{client_id}"): {
            "summary": "Delete user",
            "description": (
                "Deletes the reseller user using the same "
                "logic as the panel."
            ),
        },

        ("POST", "/api/v1/users/{client_id}/renew"): {
            "summary": "Renew user",
            "description": (
                "Adds traffic to the user's current traffic limit "
                "and optionally renews validity. "
                "traffic_gb is ADDITIVE here. "
                "For example, if the current limit is 10 GB and "
                "traffic_gb is 10, the new limit becomes 20 GB. "
                "A unique Idempotency-Key header is required so "
                "the same renewal cannot be applied twice."
            ),
        },

        ("POST", "/api/v1/users/{client_id}/enable"): {
            "summary": "Enable user",
            "description": "Enables the selected user.",
        },

        ("POST", "/api/v1/users/{client_id}/disable"): {
            "summary": "Disable user",
            "description": "Disables the selected user.",
        },

        ("POST", "/api/v1/users/{client_id}/reset-usage"): {
            "summary": "Reset user usage",
            "description": (
                "Resets the user's current traffic usage. "
                "Representative historical usage accounting "
                "continues according to panel rules."
            ),
        },

        ("POST", "/api/v1/users/{client_id}/revoke-subscription"): {
            "summary": "Revoke subscription",
            "description": (
                "Rotates/revokes the user's subscription access "
                "using the panel's existing revoke logic."
            ),
        },

        ("GET", "/api/v1/users/{client_id}/access"): {
            "summary": "Get user access",
            "description": (
                "Returns access/subscription information "
                "available to the reseller."
            ),
        },
    }

    for (method, path), metadata in operations.items():
        operation = (
            schema
            .get("paths", {})
            .get(path, {})
            .get(method.lower())
        )

        if operation:
            operation.update(metadata)


    #
    # Request examples
    #
    components = schema.get(
        "components",
        {},
    ).get(
        "schemas",
        {},
    )

    create_schema = components.get(
        "CreateUserBody"
    )

    if create_schema is not None:
        create_schema["example"] = {
            "username": "customer_001",
            "traffic_gb": 30,
            "expiry_date": "",
            "start_after_first_use": True,
            "start_after_days": 30,
            "enabled": True,
            "comment": "Telegram customer",
            "inbound_ids": [1, 2],
            "limit_ip": 2,
            "telegram_user_id": "123456789",
        }

    patch_schema = components.get(
        "ApiModifyUserBody"
    )

    if patch_schema is not None:
        patch_schema["example"] = {
            "traffic_gb": 50,
            "limit_ip": 2,
        }


    renew_schema = components.get(
        "ApiRenewUserBody"
    )

    if renew_schema is not None:
        renew_schema["example"] = {
            "traffic_gb": 10,
            "days": 30,
            "start_after_first_use": False,
            "enable": True,
        }

    for path_data in schema.get(
        "paths",
        {},
    ).values():

        for operation in path_data.values():

            if not isinstance(
                operation,
                dict,
            ):
                continue

            operation["security"] = [
                {
                    "BearerAuth": []
                }
            ]

    return JSONResponse(schema)


@docs_router.get(
    "/api/v1/docs",
    include_in_schema=False,
)
def public_api_docs():

    return get_swagger_ui_html(
        openapi_url="/api/v1/openapi.json",
        title="X-UI Reseller Public API",
        swagger_ui_parameters={
            "persistAuthorization": True,
        },
    )
