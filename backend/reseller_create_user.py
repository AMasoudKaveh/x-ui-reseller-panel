from __future__ import annotations

import json
import re
import secrets

from datetime import (
    datetime,
    timedelta,
    time as dt_time,
)

from fastapi import (
    APIRouter,
    Cookie,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
)

from backend.reseller_profile import (
    SESSION_COOKIE,
    connect_db,
    get_reseller_from_session,
)

from backend.reseller_users import (
    ensure_users_schema,
)

from backend.xui_client import (
    XUIClient,
    XUIError,
)


router = APIRouter(
    prefix="/api/reseller",
    tags=["Reseller Create User"],
)


USERNAME_RE = re.compile(
    r"^[A-Za-z0-9_.@-]{1,64}$"
)


class CreateUserBody(
    BaseModel
):

    username: str

    traffic_gb: float = Field(
        default=0,
        ge=0,
        le=100000,
    )

    # Exact megabyte input for small quotas. When present it takes precedence
    # over traffic_gb, while traffic_gb remains supported for older clients.
    traffic_mb: int | None = Field(
        default=None,
        ge=1,
        le=100000000,
    )

    expiry_date: str = ""


    start_after_first_use: bool = False

    start_after_days: int = Field(
        default=0,
        ge=0,
        le=3650,
    )
    enabled: bool = True

    comment: str = ""

    inbound_ids: list[int] = []

    limit_ip: int = Field(
        default=0,
        ge=0,
        le=1000,
    )

    telegram_user_id: str = ""

    sub_id: str = ""
    group_name: str = ""
    hwid_limit: int = Field(default=0, ge=0, le=1000)
    traffic_reset: int = Field(default=0, ge=0, le=31)
    auto_renew: int = Field(default=0, ge=0, le=3650)
    renew_on_day: int = Field(default=0, ge=0, le=31)
    max_renewals: int = Field(default=0, ge=0, le=1000)


class BulkCreateUserBody(BaseModel):
    inbound_ids: list[int] = Field(default_factory=list)
    method: str = "random"
    username_prefix: str = "user"
    number_of_clients: int = Field(default=1, ge=1, le=100)
    subscription_id: str = ""
    group: str = ""
    hwid_limit: int = Field(default=0, ge=0, le=1000)
    comment: str = ""
    limit_ip: int = Field(default=0, ge=0, le=1000)
    traffic_gb: float = Field(default=0, ge=0, le=100000)
    start_after_first_use: bool = False
    duration_days: int = Field(default=0, ge=0, le=3650)
    auto_renew: int = Field(default=0, ge=0, le=3650)
    renew_on_day: int = Field(default=0, ge=0, le=31)
    max_renewals: int = Field(default=0, ge=0, le=1000)
    traffic_reset: int = Field(default=0, ge=0, le=31)
    enabled: bool = True


def gb_to_bytes(
    value: float,
) -> int:

    return int(
        float(
            value
            or 0
        )
        *
        1024
        *
        1024
        *
        1024
    )


def mb_to_bytes(
    value: int,
) -> int:

    return int(value) * 1024 * 1024


def expiry_to_ms(
    value: str,
) -> int:

    value = str(
        value
        or ""
    ).strip()


    if not value:
        return 0


    try:

        day = datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()


        end_of_day = datetime.combine(
            day,
            dt_time(
                hour=23,
                minute=59,
                second=59,
            ),
        )


        return int(
            end_of_day.timestamp()
            *
            1000
        )


    except Exception:

        raise HTTPException(
            status_code=400,
            detail="Invalid expiry date",
        )


def resolve_expiry_ms(
    expiry_date: str,
    start_after_first_use: bool = False,
    start_after_days: int = 0,
) -> int:
    if bool(start_after_first_use):
        days = int(start_after_days or 0)
        if days <= 0:
            raise HTTPException(
                status_code=400,
                detail="Start After First Use requires at least 1 day",
            )
        return -(days * 86_400_000)

    return expiry_to_ms(expiry_date)


def normalize_inbound_ids(
    values,
) -> list[int]:

    output = []


    for value in values or []:

        try:
            number = int(value)

        except Exception:
            continue


        if (
            number > 0
            and
            number not in output
        ):
            output.append(number)


    return output


def allowed_inbound_ids(
    reseller_id: int,
    panel_ids: list[int],
) -> list[int]:

    #
    # Future-compatible:
    # when Admin adds allowed_inbound_ids
    # to representatives, enforcement
    # automatically activates here.
    #

    with connect_db() as con:

        columns = {
            str(row["name"])

            for row in con.execute(
                """
                PRAGMA table_info(
                    representatives
                )
                """
            ).fetchall()
        }


        if (
            "allowed_inbound_ids"
            not in columns
        ):

            return panel_ids


        row = con.execute(
            """
            SELECT allowed_inbound_ids

            FROM representatives

            WHERE id = ?
            """,
            (
                reseller_id,
            ),
        ).fetchone()


    if not row:
        return []


    raw = row[
        "allowed_inbound_ids"
    ]


    if not raw:
        return panel_ids


    try:

        parsed = json.loads(
            str(raw)
        )

    except Exception:

        parsed = []


    allowed = normalize_inbound_ids(
        parsed
    )

    live_allowed = [
        item

        for item in panel_ids

        if item in allowed
    ]

    # An inbound may be deleted directly in x-ui while it is still assigned
    # to one or more representatives locally. Heal that stale assignment on
    # read so future forms and API operations only carry live inbound IDs.
    if live_allowed != allowed:
        with connect_db() as con:
            con.execute(
                """
                UPDATE representatives
                SET allowed_inbound_ids = ?
                WHERE id = ?
                """,
                (
                    json.dumps(live_allowed),
                    reseller_id,
                ),
            )
            con.commit()

    return live_allowed


@router.get("/xui/status")
def xui_status(
    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):

    get_reseller_from_session(
        xui_session
    )


    try:

        client = XUIClient()

        rows = client.inbounds()


        return {
            "ok": True,
            "connected": True,
            "inbound_count":
                len(rows),
        }


    except Exception as exc:

        return {
            "ok": False,
            "connected": False,
            "error": str(exc),
        }


@router.get("/inbounds")
def reseller_inbounds(
    xui_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
):

    reseller = get_reseller_from_session(
        xui_session
    )


    reseller_id = int(
        reseller["id"]
    )


    try:

        rows = (
            XUIClient()
            .inbounds()
        )


    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to load x-ui inbounds: "
                +
                str(exc)
            ),
        )


    panel_ids = [
        int(row["id"])

        for row in rows

        if int(
            row.get("id")
            or 0
        ) > 0
    ]


    allowed = set(
        allowed_inbound_ids(
            reseller_id,
            panel_ids,
        )
    )


    output = [

        row

        for row in rows

        if (
            int(
                row.get("id")
                or 0
            )
            in allowed

            and
            bool(
                row.get(
                    "enabled",
                    True,
                )
            )
        )
    ]


    return {
        "ok": True,
        "inbounds": output,
    }


@router.post("/users")
def create_reseller_user(
    body: CreateUserBody,

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


    username = str(
        body.username
        or ""
    ).strip()


    if not username:

        raise HTTPException(
            status_code=400,
            detail="Username is required",
        )


    if not USERNAME_RE.fullmatch(
        username
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Username can only contain "
                "English letters, numbers, "
                "dot, underscore, dash and @"
            ),
        )


    with connect_db() as con:

        existing = con.execute(
            """
            SELECT id

            FROM clients

            WHERE email = ?

              AND COALESCE(
                    status,
                    ''
                  ) != 'deleted'
            """,
            (
                username,
            ),
        ).fetchone()


    if existing:

        raise HTTPException(
            status_code=409,
            detail="This username already exists",
        )


    try:

        xui = XUIClient()

        panel_inbounds = (
            xui.inbounds()
        )


    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "Cannot connect to x-ui: "
                +
                str(exc)
            ),
        )


    panel_ids = [

        int(row["id"])

        for row in panel_inbounds

        if int(
            row.get("id")
            or 0
        ) > 0
    ]


    allowed = set(
        allowed_inbound_ids(
            reseller_id,
            panel_ids,
        )
    )


    requested_ids = (
        normalize_inbound_ids(
            body.inbound_ids
        )
    )


    if not requested_ids:

        raise HTTPException(
            status_code=400,
            detail=(
                "Select at least one inbound"
            ),
        )


    invalid_ids = [

        inbound_id

        for inbound_id
        in requested_ids

        if inbound_id
        not in allowed
    ]


    if invalid_ids:

        raise HTTPException(
            status_code=403,
            detail=(
                "One or more selected "
                "inbounds are not allowed"
            ),
        )


    expiry_ms = resolve_expiry_ms(
        body.expiry_date,
        body.start_after_first_use,
        body.start_after_days,
    )


    total_bytes = (
        mb_to_bytes(body.traffic_mb)
        if body.traffic_mb is not None
        else gb_to_bytes(body.traffic_gb)
    )


    tg_id = 0


    if str(
        body.telegram_user_id
        or ""
    ).strip().isdigit():

        tg_id = int(
            str(
                body.telegram_user_id
            ).strip()
        )


    internal_comment = (
        "reseller-panel"
        f" | seller_rep={reseller_id}"
        f" | username={username}"
    )


    if body.comment.strip():

        internal_comment += (
            " | "
            +
            body.comment.strip()
        )


    group_name = body.group_name.strip() or f"rep_{reseller_id}"


    #
    # X-UI FIRST.
    # If X-UI rejects creation,
    # no local user is inserted.
    #

    try:

        result = xui.add_client(

            email=username,

            total_bytes=
                total_bytes,

            limit_ip=
                body.limit_ip,

            expiry_ms=
                expiry_ms,

            comment=
                internal_comment,

            group_name=
                group_name,

            inbound_ids=
                requested_ids,

            enabled=
                body.enabled,

            tg_id=
                tg_id,

            sub_id=body.sub_id,
            hwid_limit=body.hwid_limit,
            reset=body.traffic_reset,
            auto_renew=body.auto_renew,
            renew_on_day=body.renew_on_day,
            max_renewals=body.max_renewals,
        )


    except XUIError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "x-ui create failed: "
                +
                str(exc)
            ),
        )


    client_uuid = str(
        result.get("uuid")
        or ""
    )


    sub_id = str(
        result.get("sub_id")
        or ""
    )


    actual_inbound_ids = (
        normalize_inbound_ids(
            result.get(
                "inbound_ids"
            )
            or
            requested_ids
        )
    )


    now = datetime.now().isoformat(
        sep=" ",
        timespec="seconds",
    )


    try:

        with connect_db() as con:

            cursor = con.execute(
                """
                INSERT INTO clients (

                    email,
                    uuid,
                    sub_id,

                    owner_rep_id,
                    seller_rep_id,

                    customer_name,

                    service_type,

                    inbound_ids,

                    total_limit_bytes,

                    expire_at_ms,

                    status,

                    enabled,

                    panel_comment,

                    group_name,

                    limit_ip,

                    created_at,
                    updated_at

                )

                VALUES (
                    ?, ?, ?,
                    ?, ?,
                    ?,
                    'normal',
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?, ?
                )
                """,
                (
                    username,

                    client_uuid,

                    sub_id,

                    reseller_id,
                    reseller_id,

                    username,

                    json.dumps(
                        actual_inbound_ids
                    ),

                    total_bytes,

                    expiry_ms,

                    (
                        "active"
                        if body.enabled
                        else "disabled"
                    ),

                    (
                        1
                        if body.enabled
                        else 0
                    ),

                    internal_comment,

                    group_name,

                    int(
                        body.limit_ip
                        or 0
                    ),

                    now,
                    now,
                ),
            )


            client_id = int(
                cursor.lastrowid
            )


            con.execute(
                """
                INSERT OR IGNORE INTO
                traffic_ledger (

                    client_id,

                    cumulative_used_bytes,

                    last_panel_used_bytes,

                    last_seen_at

                )

                VALUES (
                    ?,
                    0,
                    0,
                    NULL
                )
                """,
                (
                    client_id,
                ),
            )


            con.execute(
                """
                UPDATE representatives

                SET total_users = (

                    SELECT COUNT(*)

                    FROM clients

                    WHERE seller_rep_id = ?

                      AND COALESCE(
                            status,
                            ''
                          ) != 'deleted'
                )

                WHERE id = ?
                """,
                (
                    reseller_id,
                    reseller_id,
                ),
            )


            con.commit()


    except Exception as exc:

        #
        # X-UI succeeded but DB did not.
        # Do not silently delete a real VPN user.
        #

        raise HTTPException(
            status_code=500,
            detail=(
                "User was created in x-ui "
                "but local database save failed: "
                +
                str(exc)
            ),
        )


    panel_confirmation = result.get(
        "confirmation"
    )


    try:

        if panel_confirmation is None:
            panel_confirmation = (
                xui.get_client(
                    username
                )
            )

    except Exception:
        pass


    return {

        "ok": True,

        "user": {

            "id":
                client_id,

            "username":
                username,

            "uuid":
                client_uuid,

            "sub_id":
                sub_id,

            "inbound_ids":
                actual_inbound_ids,

            "traffic_limit_bytes":
                total_bytes,

            "expire_at_ms":
                expiry_ms,

            "enabled":
                body.enabled,
        },

        "xui": {

            "method":
                result.get("method"),

            "confirmed":
                panel_confirmation
                is not None,
        },
    }


def _bulk_username(prefix: str, method: str, index: int) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.@-]", "-", str(prefix or "user").strip()).strip("-") or "user"
    if str(method or "random").lower() == "sequential":
        suffix = f"{index + 1:03d}"
    else:
        suffix = secrets.token_hex(4)
    return f"{clean}-{suffix}"[:64]


@router.post("/users/bulk")
def bulk_create_reseller_users(
    body: BulkCreateUserBody,
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    get_reseller_from_session(xui_session)
    if not normalize_inbound_ids(body.inbound_ids):
        raise HTTPException(status_code=400, detail="Select at least one inbound")

    method = str(body.method or "random").lower()
    if method not in {"random", "sequential"}:
        raise HTTPException(status_code=400, detail="Method must be Random or Sequential")

    expiry_date = ""
    if body.duration_days and not body.start_after_first_use:
        expiry_date = (datetime.now().date() + timedelta(days=body.duration_days)).isoformat()

    created: list[dict] = []
    errors: list[dict] = []
    for index in range(body.number_of_clients):
        username = _bulk_username(body.username_prefix, method, index)
        requested_sub = str(body.subscription_id or "").strip()
        sub_id = requested_sub if body.number_of_clients == 1 else (f"{requested_sub}{index + 1}" if requested_sub else "")
        try:
            result = create_reseller_user(
                CreateUserBody(
                    username=username,
                    traffic_gb=body.traffic_gb,
                    expiry_date=expiry_date,
                    start_after_first_use=body.start_after_first_use,
                    start_after_days=body.duration_days if body.start_after_first_use else 0,
                    enabled=body.enabled,
                    comment=body.comment,
                    inbound_ids=body.inbound_ids,
                    limit_ip=body.limit_ip,
                    sub_id=sub_id,
                    group_name=body.group,
                    hwid_limit=body.hwid_limit,
                    traffic_reset=body.traffic_reset,
                    auto_renew=body.auto_renew,
                    renew_on_day=body.renew_on_day,
                    max_renewals=body.max_renewals,
                ),
                xui_session,
            )
            created.append(result["user"])
        except HTTPException as exc:
            errors.append({"username": username, "detail": str(exc.detail)})
        except Exception as exc:
            errors.append({"username": username, "detail": str(exc)})

    return {"ok": not errors, "created": created, "errors": errors}
