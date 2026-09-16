from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, Cookie, Query

import backend.admin_representatives as admin_reps
from backend.reseller_profile import SESSION_COOKIE
from backend.version import PROJECT_ROOT, app_version


router = APIRouter(prefix="/api/admin/system", tags=["Admin System"])
GITHUB_REPOSITORY = "AMasoudKaveh/x-ui-reseller-panel"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
RELEASE_PAGE = f"https://github.com/{GITHUB_REPOSITORY}/releases"
CACHE_SECONDS = 6 * 60 * 60
TAG_RE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
STATE_FILE = PROJECT_ROOT / "backend" / "data" / "update-state.json"
_cache_lock = threading.Lock()
_cache: tuple[float, dict[str, Any]] | None = None


def _version_tuple(value: str) -> tuple[int, int, int, str]:
    text = str(value or "").strip().lstrip("v")
    core, _, suffix = text.partition("-")
    parts = core.split(".")
    try:
        numbers = tuple(int(parts[index]) if index < len(parts) else 0 for index in range(3))
    except ValueError:
        numbers = (0, 0, 0)
    return numbers[0], numbers[1], numbers[2], suffix


def _current_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


def _read_state() -> dict[str, Any] | None:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _fetch_latest_release(force: bool = False) -> dict[str, Any]:
    global _cache
    now = time.monotonic()
    with _cache_lock:
        if not force and _cache and now - _cache[0] < CACHE_SECONDS:
            return dict(_cache[1])
    response = requests.get(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "x-ui-reseller-panel-update-checker"},
        timeout=8,
    )
    if response.status_code == 404:
        result = {"available": False, "latest_version": None, "message": "No published release yet"}
    else:
        response.raise_for_status()
        payload = response.json()
        tag = str(payload.get("tag_name") or "").strip()
        if not TAG_RE.fullmatch(tag):
            raise RuntimeError("The latest GitHub release has an invalid version tag")
        latest = tag.lstrip("v")
        result = {
            "available": _version_tuple(latest) > _version_tuple(app_version()),
            "latest_version": latest,
            "tag": tag,
            "name": str(payload.get("name") or tag),
            "published_at": payload.get("published_at"),
            "changelog": str(payload.get("body") or "")[:8000],
            "release_url": str(payload.get("html_url") or RELEASE_PAGE),
        }
    with _cache_lock:
        _cache = (now, dict(result))
    return result


@router.get("/update-status")
def update_status(
    refresh: bool = Query(default=False),
    xui_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
):
    admin_reps.require_admin(xui_session)
    result: dict[str, Any] = {
        "ok": True,
        "current_version": app_version(),
        "current_commit": _current_commit(),
        "repository": GITHUB_REPOSITORY,
        "release_url": RELEASE_PAGE,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "update_command": "sudo xui-panel --update",
        "update_state": _read_state(),
    }
    try:
        result.update(_fetch_latest_release(force=refresh))
        if result.get("tag"):
            result["update_command"] = f"sudo xui-panel --update {result['tag']}"
        result["check_error"] = None
    except Exception as exc:
        result.update({"available": False, "latest_version": None, "check_error": str(exc)})
    return result
