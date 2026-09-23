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
from backend.subscription_upstream import resolve_upstream_subscription_url


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
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_response_headers(upstream, brand),
    )
