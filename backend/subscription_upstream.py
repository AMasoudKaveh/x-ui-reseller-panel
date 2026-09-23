from __future__ import annotations

import contextlib
import json
import re
import time
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from backend.xui_client import XUIClient, env_string


CACHE_TTL_SECONDS = 60.0
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


PORT_KEYS = {
    "subport",
    "subscriptionport",
    "subwebport",
    "sublistenport",
    "subscriptionlistenport",
}

PATH_KEYS = {
    "subpath",
    "subscriptionpath",
}

DOMAIN_KEYS = {
    "subdomain",
    "subscriptiondomain",
}

CERT_KEYS = {
    "subcertfile",
    "subscriptioncertfile",
    "subcertificatefile",
}

KEY_KEYS = {
    "subkeyfile",
    "subscriptionkeyfile",
    "subprivatekeyfile",
}

URI_KEYS = {
    "suburi",
    "subscriptionuri",
    "subscriptionurl",
}

ENABLE_KEYS = {
    "subenable",
    "subscriptionenable",
    "subscriptionenabled",
}

ALL_KEYS = (
    PORT_KEYS
    | PATH_KEYS
    | DOMAIN_KEYS
    | CERT_KEYS
    | KEY_KEYS
    | URI_KEYS
    | ENABLE_KEYS
)

SETTINGS_ATTEMPTS = (
    ("POST", "/panel/api/setting/all"),
    ("GET", "/panel/api/setting/all"),
    ("POST", "/panel/api/settings/all"),
    ("GET", "/panel/api/settings/all"),
    ("POST", "/panel/api/setting/getAll"),
    ("GET", "/panel/api/setting/getAll"),
    ("GET", "/panel/api/server/getConfigJson"),
    ("POST", "/panel/api/server/getConfigJson"),
)


def _fold(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _find_value(value: Any, wanted: set[str]) -> Any:
    if isinstance(value, dict):
        key_name = value.get("key") or value.get("name")

        if key_name is not None and _fold(key_name) in wanted:
            if "value" in value:
                return value.get("value")

        for key, nested in value.items():
            if _fold(key) in wanted and not isinstance(nested, (dict, list)):
                return nested

        for nested in value.values():
            found = _find_value(nested, wanted)
            if found is not None:
                return found

    elif isinstance(value, list):
        for nested in value:
            found = _find_value(nested, wanted)
            if found is not None:
                return found

    elif isinstance(value, str):
        text = value.strip()

        if text.startswith(("{", "[")):
            with contextlib.suppress(Exception):
                return _find_value(json.loads(text), wanted)

    return None


def _as_int(value: Any) -> int:
    with contextlib.suppress(Exception):
        number = int(float(value))

        if 1 <= number <= 65535:
            return number

    return 0


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()

    if text in {"1", "true", "yes", "on", "enabled"}:
        return True

    if text in {"0", "false", "no", "off", "disabled"}:
        return False

    return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_path(value: str) -> str:
    text = _text(value)

    if not text:
        return ""

    if "://" in text:
        with contextlib.suppress(Exception):
            text = urlsplit(text).path

    text = "/" + text.strip("/")

    if text == "/":
        return ""

    return text


def _settings_payload(xui: XUIClient) -> tuple[Any, str]:
    for method, path in SETTINGS_ATTEMPTS:
        try:
            if method == "POST":
                data = xui.request(
                    method,
                    path,
                    json={},
                )
            else:
                data = xui.request(
                    method,
                    path,
                )
        except Exception:
            continue

        if any(
            _find_value(data, {key}) is not None
            for key in ALL_KEYS
        ):
            return data, f"{method} {path}"

    return {}, ""


def detect_xui_subscription_settings(
    xui: XUIClient | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    client = xui or XUIClient()

    cache_key = str(
        getattr(client, "base_url", "")
        or getattr(client, "base", "")
        or "default"
    )

    now = time.monotonic()

    if not force:
        cached = _CACHE.get(cache_key)

        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return dict(cached[1])

    data, source = _settings_payload(client)

    port = _as_int(
        _find_value(data, PORT_KEYS)
    )

    path = _normalize_path(
        _text(
            _find_value(data, PATH_KEYS)
        )
    )

    raw_domain = _text(
        _find_value(data, DOMAIN_KEYS)
    )

    certificate_path = _text(
        _find_value(data, CERT_KEYS)
    )

    key_path = _text(
        _find_value(data, KEY_KEYS)
    )

    sub_uri = _text(
        _find_value(data, URI_KEYS)
    )

    enabled = _as_bool(
        _find_value(data, ENABLE_KEYS),
        True,
    )

    scheme = ""
    host = ""
    uri_port = 0
    uri_path = ""

    if sub_uri.lower().startswith(
        ("http://", "https://")
    ):
        with contextlib.suppress(Exception):
            parsed_uri = urlsplit(sub_uri)

            scheme = parsed_uri.scheme
            host = parsed_uri.hostname or ""

            if parsed_uri.port:
                uri_port = int(parsed_uri.port)

            uri_path = _normalize_path(
                parsed_uri.path
            )

    if not host and raw_domain:
        domain_value = raw_domain

        if "://" not in domain_value:
            domain_value = "//" + domain_value

        with contextlib.suppress(Exception):
            parsed_domain = urlsplit(
                domain_value
            )

            host = (
                parsed_domain.hostname
                or raw_domain
            )

    if not host:
        with contextlib.suppress(Exception):
            parsed_panel = urlsplit(
                str(client.base_url)
            )

            host = (
                parsed_panel.hostname
                or ""
            )

    if not port and uri_port:
        port = uri_port

    if not path:
        if uri_path:
            path = uri_path
        elif (
            sub_uri
            and not sub_uri.lower().startswith(
                ("http://", "https://")
            )
        ):
            path = _normalize_path(
                sub_uri
            )

    if not scheme:
        scheme = (
            "https"
            if certificate_path or key_path
            else "http"
        )

    base_url = ""

    if enabled and host and port and path:
        authority = f"{host}:{port}"

        base_url = urlunsplit(
            (
                scheme,
                authority,
                path.rstrip("/"),
                "",
                "",
            )
        )

    result = {
        "enabled": enabled,
        "port": port,
        "path": path,
        "domain": raw_domain,
        "host": host,
        "scheme": scheme,
        "certificate_path": certificate_path,
        "key_path": key_path,
        "sub_uri": sub_uri,
        "base_url": base_url,
        "source": source,
    }

    _CACHE[cache_key] = (
        now,
        dict(result),
    )

    return result


def _append_subscription_id(
    base_url: str,
    sub_id: str,
) -> str:
    base = str(base_url or "").strip()

    token = quote(
        str(sub_id or "").strip(),
        safe="",
    )

    if not base or not token:
        return ""

    replacements = (
        "{sub_id}",
        "{subId}",
        "{subid}",
    )

    for marker in replacements:
        if marker in base:
            return base.replace(
                marker,
                token,
            )

    return (
        base.rstrip("/")
        + "/"
        + token
    )


def manual_subscription_url(
    sub_id: str,
) -> str:
    base = env_string(
        "PUBLIC_SUB_BASE_URL"
    ).strip()

    if not base:
        return ""

    with contextlib.suppress(Exception):
        parsed = urlsplit(base)

        if (
            parsed.scheme
            not in {"http", "https"}
            or not parsed.netloc
        ):
            return ""

        path = parsed.path.rstrip("/")

        # Backwards compatibility:
        # PUBLIC_SUB_BASE_URL=https://host:port
        # historically means https://host:port/sub/<id>
        if not path:
            path = "/sub"

        normalized = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                path,
                parsed.query,
                parsed.fragment,
            )
        )

        return _append_subscription_id(
            normalized,
            sub_id,
        )

    return ""


def resolve_upstream_subscription_url(
    sub_id: str,
    *,
    xui: XUIClient | None = None,
    force: bool = False,
) -> str:
    token = str(sub_id or "").strip()

    if not token:
        return ""

    with contextlib.suppress(Exception):
        detected = detect_xui_subscription_settings(
            xui,
            force=force,
        )

        if (
            detected.get("enabled")
            and detected.get("base_url")
        ):
            return _append_subscription_id(
                str(
                    detected["base_url"]
                ),
                token,
            )

    return manual_subscription_url(
        token
    )
