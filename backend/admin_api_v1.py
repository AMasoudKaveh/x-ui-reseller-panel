from __future__ import annotations

import hashlib
import json
import secrets
import time

from contextlib import contextmanager
from dataclasses import dataclass

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Security,
)

from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse

from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from pydantic import BaseModel, Field

from backend.reseller_profile import (
    SESSION_COOKIE,
    connect_db,
)

from backend.admin_representatives import (
    RepresentativeCreateBody,
    RepresentativeUpdateBody,
    admin_inbounds,
    create_representative,
    ensure_admin_schema,
    get_rep,
    list_representatives,
    rep_payload,
    require_admin,
    update_representative,
)


GB = 1024 ** 3


router = APIRouter(
    prefix="/api/admin/v1",
    tags=["Admin Public API v1"],
)

management_router = APIRouter(
    prefix="/api/admin/api-keys",
    tags=["Admin API Keys"],
)


docs_router = APIRouter(
    tags=["Admin Public API Documentation"],
)


ADMIN_SCOPES = (
    "profile:read",
    "representatives:read",
    "representatives:create",
    "representatives:update",
    "inbounds:read",
)


admin_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="AdminBearerAuth",
    description="Administrator API Key",
)


@dataclass(frozen=True)
class AdminApiPrincipal:
    admin_id: int
    admin_username: str
    api_key_id: int
    api_key_name: str
    scopes: frozenset[str]


class CreateAdminApiKeyBody(BaseModel):
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


class AdminRepresentativeCreateBody(BaseModel):
    username: str

    password: str

    quota_gb: float = Field(
        default=0,
        ge=0,
        le=10000000,
    )

    inbound_ids: list[int] = Field(
        default_factory=list
    )

    status: str = "Active"


class AdminRepresentativePatchBody(BaseModel):
    username: str | None = None

    password: str | None = None

    quota_gb: float | None = Field(
        default=None,
        ge=0,
        le=10000000,
    )

    inbound_ids: list[int] | None = None

    status: str | None = None


def gb_to_bytes(value: float) -> int:
    return max(
        0,
        int(
            float(value)
            * GB
        ),
    )


def bytes_to_gb(value: int) -> float:
    return round(
        max(
            0,
            int(value or 0),
        )
        / GB,
        4,
    )


def friendly_representative(
    representative: dict,
) -> dict:

    data = dict(
        representative
        or {}
    )

    quota_bytes = max(
        0,
        int(
            data.get(
                "quota_bytes",
                0,
            )
            or 0
        ),
    )

    used_bytes = max(
        0,
        int(
            data.get(
                "used_bytes",
                0,
            )
            or 0
        ),
    )

    unlimited = quota_bytes <= 0

    remaining_bytes = (
        None
        if unlimited
        else max(
            0,
            quota_bytes
            - used_bytes,
        )
    )

    data.update(
        {
            "quota_gb":
                bytes_to_gb(
                    quota_bytes
                ),

            "used_gb":
                bytes_to_gb(
                    used_bytes
                ),

            "quota_unlimited":
                unlimited,

            "remaining_bytes":
                remaining_bytes,

            "remaining_gb":
                (
                    None
                    if remaining_bytes
                    is None
                    else bytes_to_gb(
                        remaining_bytes
                    )
                ),
        }
    )

    return data


def ensure_admin_api_schema() -> None:

    ensure_admin_schema()

    with connect_db() as con:

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS
            admin_api_keys(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                admin_id INTEGER NOT NULL,

                name TEXT NOT NULL,

                key_prefix TEXT NOT NULL,

                key_hash TEXT NOT NULL UNIQUE,

                scopes TEXT NOT NULL
                    DEFAULT '[]',

                is_active INTEGER NOT NULL
                    DEFAULT 1,

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
            idx_admin_api_keys_admin_id
            ON admin_api_keys(
                admin_id
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS
            admin_api_audit_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                admin_id INTEGER NOT NULL,

                api_key_id INTEGER,

                action TEXT NOT NULL,

                representative_id INTEGER,

                details TEXT,

                success INTEGER NOT NULL
                    DEFAULT 1,

                created_at INTEGER NOT NULL
            )
            """
        )

        con.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_admin_api_audit_created
            ON admin_api_audit_logs(
                admin_id,
                created_at
            )
            """
        )

        con.commit()


def hash_admin_api_key(
    value: str,
) -> str:

    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


def normalize_admin_scopes(
    scopes: list[str] | None,
) -> list[str]:

    if scopes is None:
        return list(
            ADMIN_SCOPES
        )

    output: list[str] = []

    for raw_scope in scopes:

        scope = str(
            raw_scope
            or ""
        ).strip()

        if scope not in ADMIN_SCOPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid admin API scope: "
                    f"{scope}"
                ),
            )

        if scope not in output:
            output.append(
                scope
            )

    if not output:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one API "
                "scope is required"
            ),
        )

    return output


def require_admin_api_key(
    credentials:
        HTTPAuthorizationCredentials
        | None
        = Security(
            admin_bearer
        ),
) -> AdminApiPrincipal:

    ensure_admin_api_schema()

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing Authorization "
                "header"
            ),
        )

    if (
        str(
            credentials.scheme
        ).lower()
        != "bearer"
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Use Authorization: "
                "Bearer <ADMIN_API_KEY>"
            ),
        )

    token = str(
        credentials.credentials
        or ""
    ).strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin API key",
        )

    token_hash = (
        hash_admin_api_key(
            token
        )
    )

    now = int(
        time.time()
    )

    with connect_db() as con:

        row = con.execute(
            """
            SELECT
                k.id,
                k.admin_id,
                k.name,
                k.scopes,
                k.is_active,
                k.expires_at,
                k.revoked_at,

                a.username
                    AS admin_username,

                a.is_active
                    AS admin_is_active

            FROM admin_api_keys k

            JOIN admins a
              ON a.id = k.admin_id

            WHERE k.key_hash = ?

            LIMIT 1
            """,
            (
                token_hash,
            ),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Invalid admin API key"
                ),
            )

        if (
            not bool(
                row["is_active"]
            )
            or
            row["revoked_at"]
            is not None
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Admin API key is revoked"
                ),
            )

        if not bool(
            row["admin_is_active"]
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Admin account is inactive"
                ),
            )

        expires_at = (
            row["expires_at"]
        )

        if (
            expires_at is not None
            and
            int(expires_at)
            <= now
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Admin API key has expired"
                ),
            )

        try:

            raw_scopes = json.loads(
                str(
                    row["scopes"]
                    or "[]"
                )
            )

        except Exception:

            raw_scopes = []

        scopes = frozenset(
            str(item)
            for item
            in raw_scopes
            if str(item)
            in ADMIN_SCOPES
        )

        con.execute(
            """
            UPDATE admin_api_keys

            SET last_used_at=?

            WHERE id=?
            """,
            (
                now,
                int(
                    row["id"]
                ),
            ),
        )

        con.commit()

    return AdminApiPrincipal(
        admin_id=int(
            row["admin_id"]
        ),

        admin_username=str(
            row["admin_username"]
        ),

        api_key_id=int(
            row["id"]
        ),

        api_key_name=str(
            row["name"]
        ),

        scopes=scopes,
    )


def require_admin_scope(
    scope: str,
):

    def dependency(
        principal:
            AdminApiPrincipal
            = Depends(
                require_admin_api_key
            ),
    ) -> AdminApiPrincipal:

        if scope not in principal.scopes:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Admin API key does "
                    "not have required "
                    f"scope: {scope}"
                ),
            )

        return principal

    return dependency


@contextmanager
def temporary_admin_session(
    admin_id: int,
):

    token = (
        "admin_api_v1_"
        + secrets.token_urlsafe(
            32
        )
    )

    now = int(
        time.time()
    )

    expires_at = (
        now + 120
    )

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

            VALUES(
                ?,
                'admin',
                ?,
                ?,
                ?
            )
            """,
            (
                token,
                int(admin_id),
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
                (
                    token,
                ),
            )

            con.commit()


def admin_api_audit(
    principal:
        AdminApiPrincipal,

    action: str,

    *,
    representative_id:
        int | None = None,

    success: bool = True,

    details:
        dict | None = None,
) -> None:

    ensure_admin_api_schema()

    with connect_db() as con:

        con.execute(
            """
            INSERT INTO
            admin_api_audit_logs(
                admin_id,
                api_key_id,
                action,
                representative_id,
                details,
                success,
                created_at
            )

            VALUES(
                ?,?,?,?,?,?,?
            )
            """,
            (
                principal.admin_id,
                principal.api_key_id,
                action,
                representative_id,
                json.dumps(
                    details or {},
                    ensure_ascii=False,
                ),
                1
                if success
                else 0,
                int(
                    time.time()
                ),
            ),
        )

        con.commit()


def call_admin_panel_route(
    principal:
        AdminApiPrincipal,

    action: str,

    callback,

    *,
    representative_id:
        int | None = None,
):

    try:

        with temporary_admin_session(
            principal.admin_id
        ) as token:

            result = callback(
                token
            )

        admin_api_audit(
            principal,
            action,
            representative_id=
                representative_id,
            success=True,
        )

        return result

    except Exception as exc:

        admin_api_audit(
            principal,
            action,
            representative_id=
                representative_id,
            success=False,
            details={
                "error":
                    str(exc)
            },
        )

        raise


# =========================================================
# ADMIN API KEY MANAGEMENT
# Uses the normal admin web-session cookie.
# =========================================================


@management_router.get("")
def list_admin_api_keys(
    xui_session:
        str | None
        = Cookie(
            default=None,
            alias=SESSION_COOKIE,
        ),
):

    ensure_admin_api_schema()

    admin = require_admin(
        xui_session
    )

    admin_id = int(
        admin["id"]
    )

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

            FROM admin_api_keys

            WHERE admin_id=?

            ORDER BY id DESC
            """,
            (
                admin_id,
            ),
        ).fetchall()

    keys = []

    for row in rows:

        try:
            scopes = json.loads(
                str(
                    row["scopes"]
                    or "[]"
                )
            )

        except Exception:
            scopes = []

        keys.append(
            {
                "id":
                    int(
                        row["id"]
                    ),

                "name":
                    row["name"],

                "key_prefix":
                    row["key_prefix"],

                "scopes":
                    scopes,

                "active":
                    (
                        bool(
                            row["is_active"]
                        )
                        and
                        row["revoked_at"]
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
            list(
                ADMIN_SCOPES
            ),
    }


@management_router.post("")
def create_admin_api_key(
    body:
        CreateAdminApiKeyBody,

    xui_session:
        str | None
        = Cookie(
            default=None,
            alias=SESSION_COOKIE,
        ),
):

    ensure_admin_api_schema()

    admin = require_admin(
        xui_session
    )

    admin_id = int(
        admin["id"]
    )

    name = body.name.strip()

    scopes = (
        normalize_admin_scopes(
            body.scopes
        )
    )

    raw_key = (
        "xui_admin_"
        + secrets.token_urlsafe(
            32
        )
    )

    key_prefix = (
        raw_key[:20]
    )

    key_hash = (
        hash_admin_api_key(
            raw_key
        )
    )

    now = int(
        time.time()
    )

    expires_at = None

    if body.expires_in_days:

        expires_at = (
            now
            +
            int(
                body.expires_in_days
            )
            * 86400
        )

    with connect_db() as con:

        cursor = con.execute(
            """
            INSERT INTO admin_api_keys(
                admin_id,
                name,
                key_prefix,
                key_hash,
                scopes,
                is_active,
                created_at,
                expires_at
            )

            VALUES(
                ?,?,?,?,?,1,?,?
            )
            """,
            (
                admin_id,
                name,
                key_prefix,
                key_hash,
                json.dumps(
                    scopes
                ),
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
            "id":
                key_id,

            "name":
                name,

            "token":
                raw_key,

            "key_prefix":
                key_prefix,

            "scopes":
                scopes,

            "expires_at":
                expires_at,
        },

        "warning":
            "This token is shown only once.",
    }


@management_router.post(
    "/{key_id}/revoke"
)
def revoke_admin_api_key(
    key_id: int,

    xui_session:
        str | None
        = Cookie(
            default=None,
            alias=SESSION_COOKIE,
        ),
):

    ensure_admin_api_schema()

    admin = require_admin(
        xui_session
    )

    admin_id = int(
        admin["id"]
    )

    now = int(
        time.time()
    )

    with connect_db() as con:

        row = con.execute(
            """
            SELECT id

            FROM admin_api_keys

            WHERE id=?
              AND admin_id=?
            """,
            (
                int(key_id),
                admin_id,
            ),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Admin API key "
                    "not found"
                ),
            )

        con.execute(
            """
            UPDATE admin_api_keys

            SET
                is_active=0,
                revoked_at=?

            WHERE id=?
              AND admin_id=?
            """,
            (
                now,
                int(key_id),
                admin_id,
            ),
        )

        con.commit()

    return {
        "ok": True,
        "revoked":
            int(key_id),
    }


# =========================================================
# ADMIN PUBLIC API V1
# =========================================================


@router.get("/me")
def admin_api_me(
    principal:
        AdminApiPrincipal
        = Depends(
            require_admin_scope(
                "profile:read"
            )
        ),
):

    return {
        "ok": True,

        "data": {
            "id":
                principal.admin_id,

            "username":
                principal.admin_username,

            "role":
                "admin",

            "api_key": {
                "id":
                    principal.api_key_id,

                "name":
                    principal.api_key_name,

                "scopes":
                    sorted(
                        principal.scopes
                    ),
            },
        },
    }


@router.get("/inbounds")
def admin_api_inbounds(
    principal:
        AdminApiPrincipal
        = Depends(
            require_admin_scope(
                "inbounds:read"
            )
        ),
):

    return call_admin_panel_route(
        principal,
        "inbounds.list",

        lambda token:
            admin_inbounds(
                xui_session=token
            ),
    )


@router.get("/representatives")
def admin_api_representatives(
    principal:
        AdminApiPrincipal
        = Depends(
            require_admin_scope(
                "representatives:read"
            )
        ),
):

    result = call_admin_panel_route(
        principal,
        "representatives.list",

        lambda token:
            list_representatives(
                xui_session=token
            ),
    )

    representatives = [
        friendly_representative(
            item
        )
        for item
        in result.get(
            "representatives",
            [],
        )
    ]

    return {
        "ok": True,

        "representatives":
            representatives,

        "archived_used_bytes":
            int(
                result.get(
                    "archived_used_bytes",
                    0,
                )
                or 0
            ),
    }


def admin_rep_detail_from_panel(
    token: str,
    rep_id: int,
):

    require_admin(
        token
    )

    ensure_admin_schema()

    with connect_db() as con:

        current = get_rep(
            con,
            rep_id,
        )

        if (
            str(
                current.get(
                    "status"
                )
                or ""
            ).lower()
            == "deleted"
            or
            current.get(
                "deleted_at"
            )
        ):
            raise HTTPException(
                status_code=404,
                detail=(
                    "Representative not found"
                ),
            )

        representative = (
            rep_payload(
                con,
                current,
            )
        )

        con.commit()

    return {
        "ok": True,
        "representative":
            friendly_representative(
                representative
            ),
    }


@router.get(
    "/representatives/{rep_id}"
)
def admin_api_representative(
    rep_id: int,

    principal:
        AdminApiPrincipal
        = Depends(
            require_admin_scope(
                "representatives:read"
            )
        ),
):

    return call_admin_panel_route(
        principal,
        "representatives.details",

        lambda token:
            admin_rep_detail_from_panel(
                token,
                rep_id,
            ),

        representative_id=
            rep_id,
    )


@router.post("/representatives")
def admin_api_create_representative(
    body:
        AdminRepresentativeCreateBody,

    principal:
        AdminApiPrincipal
        = Depends(
            require_admin_scope(
                "representatives:create"
            )
        ),
):

    payload = RepresentativeCreateBody(
        username=
            body.username,

        password=
            body.password,

        quota_bytes=
            gb_to_bytes(
                body.quota_gb
            ),

        status=
            body.status,

        inbound_ids=
            body.inbound_ids,
    )

    result = call_admin_panel_route(
        principal,
        "representatives.create",

        lambda token:
            create_representative(
                body=payload,
                xui_session=token,
            ),
    )

    if result.get(
        "representative"
    ):
        result[
            "representative"
        ] = friendly_representative(
            result[
                "representative"
            ]
        )

    return result


@router.patch(
    "/representatives/{rep_id}"
)
def admin_api_patch_representative(
    rep_id: int,

    body:
        AdminRepresentativePatchBody,

    principal:
        AdminApiPrincipal
        = Depends(
            require_admin_scope(
                "representatives:update"
            )
        ),
):

    if not body.model_fields_set:
        raise HTTPException(
            status_code=400,
            detail=(
                "No fields supplied "
                "for update"
            ),
        )

    def perform(
        token: str,
    ):

        detail = (
            admin_rep_detail_from_panel(
                token,
                rep_id,
            )
        )

        current = detail[
            "representative"
        ]

        quota_bytes = (
            int(
                current.get(
                    "quota_bytes",
                    0,
                )
                or 0
            )
            if body.quota_gb
            is None

            else gb_to_bytes(
                body.quota_gb
            )
        )

        payload = (
            RepresentativeUpdateBody(
                username=(
                    str(
                        current.get(
                            "username",
                            "",
                        )
                    )
                    if body.username
                    is None

                    else body.username
                ),

                password=(
                    ""
                    if body.password
                    is None

                    else body.password
                ),

                quota_bytes=
                    quota_bytes,

                status=(
                    str(
                        current.get(
                            "status",
                            "Active",
                        )
                    )
                    if body.status
                    is None

                    else body.status
                ),

                inbound_ids=(
                    list(
                        current.get(
                            "inbound_ids",
                            [],
                        )
                        or []
                    )
                    if body.inbound_ids
                    is None

                    else body.inbound_ids
                ),
            )
        )

        result = update_representative(
            rep_id=rep_id,
            body=payload,
            xui_session=token,
        )

        if result.get(
            "representative"
        ):
            result[
                "representative"
            ] = friendly_representative(
                result[
                    "representative"
                ]
            )

        return result

    return call_admin_panel_route(
        principal,
        "representatives.update",
        perform,

        representative_id=
            rep_id,
    )



# =========================================================
# ADMIN PUBLIC API DOCUMENTATION
# =========================================================


@docs_router.get(
    "/api/admin/v1/openapi.json",
    include_in_schema=False,
)
def admin_public_api_openapi(
    request: Request,
):
    schema = get_openapi(
        title="X-UI Admin Public API",
        version="1.0.0",
        description=(
            "Public API for administrator integrations. "
            "Authenticate using Authorization: "
            "Bearer <ADMIN_API_KEY>."
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
        "AdminBearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Admin API Key",
        }
    }

    return JSONResponse(schema)


@docs_router.get(
    "/api/admin/v1/docs",
    include_in_schema=False,
)
def admin_public_api_docs():
    return get_swagger_ui_html(
        openapi_url=(
            "/api/admin/v1/openapi.json"
        ),
        title="X-UI Admin Public API",
        swagger_ui_parameters={
            "persistAuthorization": True,
        },
    )
