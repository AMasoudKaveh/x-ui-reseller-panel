from __future__ import annotations

import base64
import contextlib
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import requests
from fastapi import APIRouter, HTTPException, Request, Response

from backend.reseller_profile import connect_db, ensure_profile_schema, normalize_subscription_brand
from backend.reseller_users import ensure_users_schema
from backend.xui_client import XUIClient
from backend.subscription_upstream import (
    detect_xui_subscription_settings,
    resolve_upstream_subscription_url,
)


router = APIRouter(tags=["Subscriptions"])

SUB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,128}$")
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
    "set-cookie",
}
OWNER_QUERY_KEYS = {"rep_id", "representative_id", "seller_rep_id", "owner_rep_id"}


def _extract_links(value) -> list[str]:
    links: list[str] = []

    def walk(item) -> None:
        if isinstance(item, str):
            text = item.strip()
            if text.lower().startswith(("http://", "https://")) and text not in links:
                links.append(text)
            return
        if isinstance(item, dict):
            for nested in item.values():
                walk(nested)
            return
        if isinstance(item, (list, tuple)):
            for nested in item:
                walk(nested)

    walk(value)
    return links


def _is_matching_subscription_url(url: str, sub_id: str) -> bool:
    with contextlib.suppress(Exception):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        segments = [unquote(part) for part in parsed.path.split("/") if part]
        return len(segments) >= 2 and segments[-2].lower() == "sub" and segments[-1] == sub_id
    return False


def _client_owner(sub_id: str) -> dict:
    ensure_users_schema()
    ensure_profile_schema()
    with connect_db() as con:
        rows = con.execute(
            """
            SELECT
                c.id,
                c.email,
                c.seller_rep_id,
                COALESCE(r.subscription_brand, '') AS subscription_brand
            FROM clients c
            LEFT JOIN representatives r ON r.id = c.seller_rep_id
            WHERE c.sub_id = ?
              AND COALESCE(c.status, '') != 'deleted'
            ORDER BY c.id
            LIMIT 2
            """,
            (sub_id,),
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail="Subscription mapping is ambiguous")
    return dict(rows[0])


def _upstream_subscription_url(client: dict, sub_id: str, xui: XUIClient) -> str:
    email = str(client.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=502, detail="Subscription client mapping is incomplete")

    payloads = []
    with contextlib.suppress(Exception):
        payloads.append(xui.request("GET", "/panel/api/clients/links/" + quote(email, safe="")))
    with contextlib.suppress(Exception):
        payloads.append(xui.get_client(email))

    for payload in payloads:
        for link in _extract_links(payload):
            if _is_matching_subscription_url(link, sub_id):
                return link

    # Newer x-ui versions may not expose the original subscription URL
    # through the client links API. Detect the real subscription service
    # from x-ui settings instead. No x-ui setting is modified here.
    detected_url = resolve_upstream_subscription_url(
        sub_id,
        xui=xui,
    )

    if detected_url:
        return detected_url

    raise HTTPException(
        status_code=502,
        detail="Original x-ui subscription URL was not found",
    )


def _forward_query(upstream_url: str, request: Request) -> str:
    incoming = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key.lower() not in OWNER_QUERY_KEYS
    ]
    if not incoming:
        return upstream_url
    parsed = urlsplit(upstream_url)
    query = parse_qsl(parsed.query, keep_blank_values=True) + incoming
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _profile_title_header(brand: str) -> str:
    brand = normalize_subscription_brand(brand)
    if not brand:
        return ""
    encoded = base64.b64encode(brand.encode("utf-8")).decode("ascii")
    return "base64:" + encoded


def _response_headers(upstream: requests.Response, brand: str) -> dict[str, str]:
    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    headers["X-Reseller-Subscription-Proxy"] = "1"
    if brand:
        for key in list(headers):
            if key.lower() == "profile-title":
                del headers[key]
        headers["Profile-Title"] = _profile_title_header(brand)
    return headers



def _public_proxy_subscription_url(sub_id: str) -> str:
    """
    Return the public branded subscription URL stored by this panel.

    This intentionally reads only our local reseller-panel settings and
    never changes x-ui settings.
    """
    token = str(sub_id or "").strip()

    if not token:
        return ""

    try:
        with connect_db() as con:
            exists = con.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type='table'
                  AND name='admin_settings'
                """
            ).fetchone()

            if not exists:
                return ""

            rows = con.execute(
                """
                SELECT key, value
                FROM admin_settings
                WHERE key IN (
                    'subscription_proxy_host',
                    'subscription_proxy_port'
                )
                """
            ).fetchall()

        values = {
            str(row[0]): str(row[1] or "").strip()
            for row in rows
        }

        host = values.get(
            "subscription_proxy_host",
            "",
        ).strip()

        port = int(
            values.get(
                "subscription_proxy_port",
                "0",
            )
            or 0
        )

        if not host or not 1 <= port <= 65535:
            return ""

        return (
            f"https://{host}:{port}/sub/"
            + quote(token, safe="")
        )

    except Exception:
        return ""


def _replace_url_variants(
    text: str,
    source: str,
    target: str,
) -> str:
    if not source or not target or source == target:
        return text

    variants = (
        (
            source,
            target,
        ),
        (
            source.replace("/", r"\/"),
            target.replace("/", r"\/"),
        ),
        (
            quote(source, safe=""),
            quote(target, safe=""),
        ),
    )

    for old, new in variants:
        if old:
            text = text.replace(
                old,
                new,
            )

    return text


def _rewrite_public_body(
    content: bytes,
    content_type: str,
    upstream_url: str,
    public_url: str,
) -> tuple[bytes, bool]:
    """
    Rewrite only browser-oriented textual responses.

    Raw text/plain subscription bodies are intentionally untouched.
    """
    content_type_lower = str(
        content_type or ""
    ).lower()

    textual = any(
        item in content_type_lower
        for item in (
            "text/html",
            "application/json",
            "application/javascript",
            "text/javascript",
        )
    )

    if not textual or not public_url:
        return content, False

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content, False

    original = text

    try:
        upstream = urlsplit(
            upstream_url
        )

        public = urlsplit(
            public_url
        )

        upstream_clean = urlunsplit(
            (
                upstream.scheme,
                upstream.netloc,
                upstream.path,
                "",
                "",
            )
        )

        public_clean = urlunsplit(
            (
                public.scheme,
                public.netloc,
                public.path,
                "",
                "",
            )
        )

        # Rewrite the actual subscription URL used by copy/QR buttons.
        text = _replace_url_variants(
            text,
            upstream_clean,
            public_clean,
        )

        # Some x-ui versions include the full request including query params.
        text = _replace_url_variants(
            text,
            upstream_url,
            public_url,
        )

        if "text/html" in content_type_lower:
            upstream_prefix = (
                upstream.path.rsplit("/", 1)[0]
                or "/"
            ).rstrip("/")

            public_prefix = (
                public.path.rsplit("/", 1)[0]
                or "/sub"
            ).rstrip("/")

            if not public_prefix:
                public_prefix = "/sub"

            # x-ui subscription-page static files are rooted below
            # its configured subscription path. Route them through
            # our public /sub/assets/ path instead.
            if (
                upstream_prefix
                and upstream_prefix != public_prefix
            ):
                old_assets = (
                    upstream_prefix
                    + "/assets/"
                )

                new_assets = (
                    public_prefix
                    + "/assets/"
                )

                for attribute in (
                    "src",
                    "href",
                ):
                    text = text.replace(
                        f'{attribute}="{old_assets}',
                        f'{attribute}="{new_assets}',
                    )

                    text = text.replace(
                        f"{attribute}='{old_assets}",
                        f"{attribute}='{new_assets}",
                    )

                # x-ui exposes this variable to the subscription SPA.
                text = text.replace(
                    f'window.X_UI_BASE_PATH="{upstream_prefix}/";',
                    f'window.X_UI_BASE_PATH="{public_prefix}/";',
                )

                text = text.replace(
                    f"window.X_UI_BASE_PATH='{upstream_prefix}/';",
                    f"window.X_UI_BASE_PATH='{public_prefix}/';",
                )

    except Exception:
        # A rewrite failure must never break the working raw subscription.
        return content, False

    if text == original:
        return content, False

    return (
        text.encode("utf-8"),
        True,
    )


def _safe_asset_path(asset_path: str) -> str:
    raw_parts = str(
        asset_path or ""
    ).split("/")

    parts: list[str] = []

    for raw in raw_parts:
        decoded = unquote(raw)

        if (
            not decoded
            or decoded in {".", ".."}
            or "\\" in decoded
            or "\x00" in decoded
        ):
            raise HTTPException(
                status_code=404,
                detail="Asset not found",
            )

        parts.append(
            quote(
                decoded,
                safe="._-~@",
            )
        )

    if not parts:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    return "/".join(parts)


def _subscription_asset_upstream_url(
    asset_path: str,
    xui: XUIClient,
) -> str:
    detected = detect_xui_subscription_settings(
        xui
    )

    base_url = str(
        detected.get("base_url")
        or ""
    ).strip()

    if not base_url:
        raise HTTPException(
            status_code=502,
            detail="x-ui subscription service was not detected",
        )

    parsed = urlsplit(
        base_url
    )

    safe_path = _safe_asset_path(
        asset_path
    )

    path = (
        parsed.path.rstrip("/")
        + "/assets/"
        + safe_path
    )

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            "",
            "",
        )
    )


def _browser_proxy_headers(
    request: Request,
) -> dict[str, str]:
    headers = {
        "Accept": request.headers.get(
            "accept",
            "*/*",
        ),
        "Accept-Encoding": "identity",
        "User-Agent": request.headers.get(
            "user-agent",
            "x-ui-reseller-subscription-proxy/1.0",
        ),
    }

    for name, upstream_name in (
        (
            "accept-language",
            "Accept-Language",
        ),
        (
            "range",
            "Range",
        ),
        (
            "if-none-match",
            "If-None-Match",
        ),
        (
            "if-modified-since",
            "If-Modified-Since",
        ),
    ):
        value = request.headers.get(
            name
        )

        if value:
            headers[upstream_name] = value

    return headers


@router.get("/sub/assets/{asset_path:path}")
def proxy_subscription_asset(
    asset_path: str,
    request: Request,
):
    """
    Serve x-ui's own subscription-page JS/CSS/fonts through the branded
    subscription origin.

    Only the detected x-ui subscription assets directory is reachable.
    """
    xui = XUIClient()

    upstream_url = _forward_query(
        _subscription_asset_upstream_url(
            asset_path,
            xui,
        ),
        request,
    )

    try:
        upstream = requests.get(
            upstream_url,
            headers=_browser_proxy_headers(
                request
            ),
            timeout=(5, 30),
            verify=xui.verify_tls,
            allow_redirects=False,
        )

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch x-ui subscription asset",
        ) from exc

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_response_headers(
            upstream,
            "",
        ),
    )


@router.get("/api/subscriptions/{sub_id}")
@router.get("/sub/{sub_id}")
def proxy_subscription(sub_id: str, request: Request):
    token = str(sub_id or "").strip()
    if not SUB_ID_RE.fullmatch(token):
        raise HTTPException(status_code=404, detail="Subscription not found")

    client = _client_owner(token)
    xui = XUIClient()
    upstream_url = _forward_query(_upstream_subscription_url(client, token, xui), request)
    request_headers = {
        "Accept": request.headers.get("accept", "*/*"),
        "Accept-Encoding": "identity",
        "User-Agent": request.headers.get("user-agent", "x-ui-reseller-subscription-proxy/1.0"),
    }

    try:
        upstream = requests.get(
            upstream_url,
            headers=request_headers,
            timeout=(5, 30),
            verify=xui.verify_tls,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Unable to fetch x-ui subscription") from exc

    brand = str(client.get("subscription_brand") or "")

    public_url = _public_proxy_subscription_url(
        token
    )

    content, rewritten = _rewrite_public_body(
        upstream.content,
        upstream.headers.get(
            "content-type",
            "",
        ),
        upstream_url,
        public_url,
    )

    response_headers = _response_headers(
        upstream,
        brand,
    )

    if rewritten:
        # Upstream validators belong to the original, unmodified body.
        # Do not let a browser cache them against our rewritten response.
        for header_name in list(
            response_headers
        ):
            if header_name.lower() in {
                "etag",
                "content-md5",
            }:
                response_headers.pop(
                    header_name,
                    None,
                )

    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=response_headers,
    )
