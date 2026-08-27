from __future__ import annotations

import contextlib
import json
import os
import secrets
import uuid

from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import urllib3


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def read_env_file() -> dict[str, str]:

    result: dict[str, str] = {}

    if not ENV_PATH.exists():
        return result

    for raw in ENV_PATH.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines():

        line = raw.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split(
            "=",
            1,
        )

        key = key.strip()
        value = value.strip()

        if (
            len(value) >= 2
            and
            (
                (
                    value.startswith('"')
                    and
                    value.endswith('"')
                )
                or
                (
                    value.startswith("'")
                    and
                    value.endswith("'")
                )
            )
        ):
            value = value[1:-1]

        result[key] = value

    return result


ENV = read_env_file()


def env_string(
    key: str,
    default: str = "",
) -> str:

    return str(
        os.environ.get(
            key,
            ENV.get(
                key,
                default,
            ),
        )
        or ""
    ).strip()


def env_bool(
    key: str,
    default: bool = False,
) -> bool:

    fallback = (
        "true"
        if default
        else "false"
    )

    value = env_string(
        key,
        fallback,
    ).lower()

    return value in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def int_list(
    value,
) -> list[int]:

    output: list[int] = []

    if value is None:
        return output

    if isinstance(
        value,
        (list, tuple, set),
    ):
        values = value

    else:

        text = str(value)

        for separator in [
            ",",
            ";",
            "|",
            " ",
        ]:
            text = text.replace(
                separator,
                " ",
            )

        values = text.split()

    for item in values:

        try:
            number = int(item)

        except (
            ValueError,
            TypeError,
        ):
            continue

        if (
            number > 0
            and
            number not in output
        ):
            output.append(number)

    return output


XUI_BASE_URL = env_string(
    "XUI_BASE_URL"
).rstrip("/")

XUI_API_TOKEN = env_string(
    "XUI_API_TOKEN"
)

XUI_USERNAME = env_string(
    "XUI_USERNAME"
)

XUI_PASSWORD = env_string(
    "XUI_PASSWORD"
)

XUI_VERIFY_TLS = env_bool(
    "XUI_VERIFY_TLS",
    False,
)

DEFAULT_INBOUND_IDS = int_list(
    env_string(
        "DEFAULT_INBOUND_IDS"
    )
)


if not XUI_VERIFY_TLS:

    urllib3.disable_warnings(
        urllib3.exceptions
        .InsecureRequestWarning
    )


class XUIError(
    RuntimeError
):
    pass


def unwrap_list(
    data: Any,
) -> list:

    if isinstance(
        data,
        list,
    ):
        return data

    if not isinstance(
        data,
        dict,
    ):
        return []

    for key in (
        "obj",
        "data",
        "result",
        "items",
        "list",
        "inbounds",
    ):

        value = data.get(key)

        if isinstance(
            value,
            list,
        ):
            return value

    return []


class XUIClient:

    def __init__(
        self,
    ) -> None:

        if not XUI_BASE_URL:

            raise XUIError(
                "XUI_BASE_URL is not configured in backend/.env"
            )

        self.base = (
            XUI_BASE_URL
            .rstrip("/")
        )

        self.session = (
            requests.Session()
        )

        self.session.verify = (
            XUI_VERIFY_TLS
        )

        self.logged_in = False

        if XUI_API_TOKEN:

            self.session.headers.update(
                {
                    "Authorization":
                        f"Bearer {XUI_API_TOKEN}",

                    "X-API-Token":
                        XUI_API_TOKEN,

                    "X-Token":
                        XUI_API_TOKEN,
                }
            )


    def login(
        self,
    ) -> None:

        if XUI_API_TOKEN:

            self.logged_in = True
            return


        if (
            not XUI_USERNAME
            or
            not XUI_PASSWORD
        ):

            raise XUIError(
                "Set XUI_API_TOKEN or XUI_USERNAME/XUI_PASSWORD in backend/.env"
            )


        attempts = []


        for path in (
            "/login",
            "/panel/api/login",
        ):

            for payload in (
                {
                    "username":
                        XUI_USERNAME,

                    "password":
                        XUI_PASSWORD,
                },

                {
                    "userName":
                        XUI_USERNAME,

                    "password":
                        XUI_PASSWORD,
                },
            ):

                try:

                    response = (
                        self.session.post(
                            self.base + path,
                            json=payload,
                            timeout=20,
                            verify=XUI_VERIFY_TLS,
                        )
                    )

                    if response.status_code < 400:

                        self.logged_in = True
                        return

                    attempts.append(
                        f"{path}: HTTP {response.status_code}"
                    )

                except Exception as exc:

                    attempts.append(
                        f"{path}: {exc}"
                    )


        # Standard x-ui form login fallback.

        try:

            response = (
                self.session.post(
                    self.base + "/login",
                    data={
                        "username":
                            XUI_USERNAME,

                        "password":
                            XUI_PASSWORD,
                    },
                    timeout=20,
                    verify=XUI_VERIFY_TLS,
                )
            )

            if response.status_code < 400:

                self.logged_in = True
                return

            attempts.append(
                "form /login: "
                f"HTTP {response.status_code}"
            )

        except Exception as exc:

            attempts.append(
                f"form /login: {exc}"
            )


        raise XUIError(
            "x-ui login failed: "
            +
            " | ".join(
                attempts[-6:]
            )
        )


    def request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> Any:

        if (
            not self.logged_in
            and
            not XUI_API_TOKEN
        ):
            self.login()


        url = (
            self.base
            +
            path
        )


        response = (
            self.session.request(
                method,
                url,
                timeout=30,
                verify=XUI_VERIFY_TLS,
                **kwargs,
            )
        )


        if (
            response.status_code
            in (401, 403)
            and
            not XUI_API_TOKEN
        ):

            self.logged_in = False

            self.login()

            response = (
                self.session.request(
                    method,
                    url,
                    timeout=30,
                    verify=XUI_VERIFY_TLS,
                    **kwargs,
                )
            )


        text = response.text


        try:

            data = response.json()

        except Exception:

            data = {
                "raw":
                    text
            }


        if response.status_code >= 400:

            raise XUIError(
                f"{method} {path} "
                f"HTTP {response.status_code}: "
                f"{text[:700]}"
            )


        if (
            isinstance(
                data,
                dict,
            )
            and
            data.get(
                "success"
            )
            is False
        ):

            message = (
                data.get("msg")
                or
                data.get("message")
                or
                data.get("detail")
                or
                text
            )

            raise XUIError(
                f"{method} {path}: "
                f"{message}"
            )


        return data


    def inbounds(
        self,
    ) -> list[dict]:

        data = self.request(
            "GET",
            "/panel/api/inbounds/list",
        )


        rows = unwrap_list(
            data
        )


        output = []


        for row in rows:

            if not isinstance(
                row,
                dict,
            ):
                continue


            try:

                inbound_id = int(
                    row.get("id")
                    or 0
                )

            except Exception:

                continue


            if inbound_id <= 0:
                continue


            stream = row.get(
                "streamSettings"
            )


            if isinstance(
                stream,
                str,
            ):

                with contextlib.suppress(
                    Exception
                ):

                    stream = json.loads(
                        stream
                    )


            if not isinstance(
                stream,
                dict,
            ):
                stream = {}


            port = int(
                row.get("port")
                or 0
            )


            protocol = str(
                row.get("protocol")
                or ""
            ).lower()


            network = str(
                stream.get("network")
                or
                row.get("network")
                or ""
            ).lower()


            security = str(
                stream.get("security")
                or
                row.get("security")
                or ""
            ).lower()


            remark = str(
                row.get("remark")
                or
                row.get("tag")
                or
                ""
            ).strip()


            label = (
                remark
                or
                f"in-{port}-{network or protocol or 'tcp'}"
            )


            output.append(
                {
                    "id":
                        inbound_id,

                    "label":
                        label,

                    "remark":
                        remark,

                    "port":
                        port,

                    "protocol":
                        protocol,

                    "network":
                        network,

                    "security":
                        security,

                    "enabled":
                        bool(
                            row.get(
                                "enable",
                                row.get(
                                    "enabled",
                                    True,
                                ),
                            )
                        ),
                }
            )


        return output


    def attach(
        self,
        email: str,
        inbound_ids: list[int],
    ) -> dict:

        ids = int_list(
            inbound_ids
        )


        if not ids:

            return {
                "ok": True,
                "skipped": True,
            }


        errors = []


        for payload in (

            {
                "inboundIds":
                    ids
            },

            {
                "inbound_ids":
                    ids
            },

            {
                "ids":
                    ids
            },

            {
                "inbounds":
                    ids
            },

        ):

            try:

                result = self.request(
                    "POST",

                    "/panel/api/clients/"
                    +
                    quote(
                        email,
                        safe="",
                    )
                    +
                    "/attach",

                    json=payload,
                )

                return {
                    "ok": True,
                    "response": result,
                }

            except Exception as exc:

                errors.append(
                    str(exc)
                )


        return {
            "ok": False,
            "errors": errors,
        }


    def get_client(
        self,
        email: str,
    ) -> Any:

        return self.request(
            "GET",

            "/panel/api/clients/get/"
            +
            quote(
                email,
                safe="",
            ),
        )


    def add_client(
        self,
        *,
        email: str,
        total_bytes: int,
        limit_ip: int,
        expiry_ms: int,
        comment: str,
        group_name: str,
        inbound_ids: list[int],
        enabled: bool,
        tg_id: int = 0,
    ) -> dict:

        email = str(
            email
            or ""
        ).strip()


        if not email:

            raise XUIError(
                "Client username is empty"
            )


        ids = int_list(
            inbound_ids
        )


        if not ids:

            ids = list(
                DEFAULT_INBOUND_IDS
            )


        if not ids:

            raise XUIError(
                "At least one inbound is required"
            )


        client_uuid = str(
            uuid.uuid4()
        )


        sub_id = (
            secrets
            .token_urlsafe(9)
            .replace("-", "")
            .replace("_", "")
            [:12]
        )


        client = {

            "id":
                client_uuid,

            "uuid":
                client_uuid,

            "password":
                client_uuid,

            "email":
                email,

            "flow":
                "",

            "limitIp":
                max(
                    0,
                    int(
                        limit_ip
                        or 0
                    ),
                ),

            "totalGB":
                max(
                    0,
                    int(
                        total_bytes
                        or 0
                    ),
                ),

            "expiryTime":
                max(
                    0,
                    int(
                        expiry_ms
                        or 0
                    ),
                ),

            "enable":
                bool(enabled),

            "tgId":
                max(
                    0,
                    int(
                        tg_id
                        or 0
                    ),
                ),

            "subId":
                sub_id,

            "reset":
                0,

            "comment":
                str(
                    comment
                    or ""
                ),
        }


        errors = []


        modern_attempts = [

            (
                "client_inboundIds",

                {
                    "client":
                        dict(client),

                    "inboundIds":
                        ids,

                    "group":
                        group_name,
                },
            ),


            (
                "client_inbound_ids",

                {
                    "client":
                        dict(client),

                    "inbound_ids":
                        ids,

                    "group":
                        group_name,
                },
            ),


            (
                "top_level",

                {
                    **client,

                    "inboundIds":
                        ids,

                    "inbound_ids":
                        ids,

                    "group":
                        group_name,
                },
            ),

        ]


        for (
            method_name,
            payload,
        ) in modern_attempts:

            try:

                response = (
                    self.request(
                        "POST",
                        "/panel/api/clients/add",
                        json=payload,
                    )
                )


                attach_result = (
                    self.attach(
                        email,
                        ids,
                    )
                )


                return {

                    "ok":
                        True,

                    "method":
                        method_name,

                    "response":
                        response,

                    "attach":
                        attach_result,

                    "uuid":
                        client_uuid,

                    "sub_id":
                        sub_id,

                    "email":
                        email,

                    "inbound_ids":
                        ids,
                }


            except Exception as exc:

                errors.append(
                    f"{method_name}: {exc}"
                )


        #
        # Classic 3x-ui fallback.
        #

        legacy_payload = {

            "id":
                int(
                    ids[0]
                ),

            "settings":
                json.dumps(
                    {
                        "clients": [
                            client
                        ]
                    },
                    ensure_ascii=False,
                    separators=(
                        ",",
                        ":",
                    ),
                ),
        }


        try:

            response = self.request(
                "POST",
                "/panel/api/inbounds/addClient",
                json=legacy_payload,
            )


            attach_result = (
                self.attach(
                    email,
                    ids,
                )
            )


            return {

                "ok":
                    True,

                "method":
                    "legacy_inbounds_addClient",

                "response":
                    response,

                "attach":
                    attach_result,

                "uuid":
                    client_uuid,

                "sub_id":
                    sub_id,

                "email":
                    email,

                "inbound_ids":
                    ids,
            }


        except Exception as exc:

            errors.append(
                "legacy_inbounds_addClient: "
                +
                str(exc)
            )


        raise XUIError(

            "x-ui create client failed after all supported API variants:`n"
            +
            "`n".join(
                errors[-8:]
            )
        )
