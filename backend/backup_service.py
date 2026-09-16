from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from backend import reseller_profile
from backend.version import app_version
from backend.xui_client import ENV_PATH, XUIClient, XUIError, read_env_file, reload_env_file


BACKUP_FORMAT = "xui-reseller-panel-backup"
BACKUP_FORMAT_VERSION = 2
MAX_RESTORE_BYTES = 512 * 1024 * 1024
STAGE_TTL_SECONDS = 30 * 60
SAFETY_BACKUP_KEEP = 10
CORE_TABLES = {"admins", "representatives", "auth_sessions"}
EXPECTED_DATA_TABLES = {
    "admins", "representatives", "auth_sessions", "admin_settings", "clients",
    "traffic_ledger", "traffic_events", "deleted_representatives",
    "deleted_client_usage", "api_keys", "api_audit_logs",
    "api_renew_idempotency",
    "admin_api_keys", "admin_api_audit_logs",
}
PORTABLE_RUNTIME_KEYS = (
    "PUBLIC_LINK_REWRITE", "PUBLIC_CONFIG_HOST", "PUBLIC_CONFIG_PORT",
    "PUBLIC_REALITY_SID", "PUBLIC_SUB_BASE_URL",
)

DATA_DIR = Path(__file__).resolve().parent / "data"
SAFETY_DIR = DATA_DIR / "backups"
STAGING_DIR = DATA_DIR / "restore-staging"
RESTORE_LOCK = threading.Lock()
RESTORE_ACTIVE = threading.Event()
MAINTENANCE_LOCK_PATH = Path("/run/lock/xui-reseller-panel-maintenance.lock")


@dataclass(frozen=True)
class StagedRestore:
    token: str
    path: Path
    admin_id: int
    created_at: float
    inspection: dict[str, Any]


_staged: dict[str, StagedRestore] = {}
_staged_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_snapshot_to(path: Path) -> Path:
    path = Path(path)
    with contextlib.closing(reseller_profile.connect_db()) as source:
        with contextlib.closing(sqlite3.connect(path)) as target:
            source.backup(target)
            target.commit()
    return path


def _connection_from_env() -> dict[str, Any]:
    values = read_env_file()
    runtime_settings = {
        key: str(os.environ.get(key, values.get(key, "")))
        for key in PORTABLE_RUNTIME_KEYS
    }
    return {
        "base_url": str(os.environ.get("XUI_BASE_URL", values.get("XUI_BASE_URL", ""))).rstrip("/"),
        "api_token": str(os.environ.get("XUI_API_TOKEN", values.get("XUI_API_TOKEN", ""))),
        "username": str(os.environ.get("XUI_USERNAME", values.get("XUI_USERNAME", ""))),
        "password": str(os.environ.get("XUI_PASSWORD", values.get("XUI_PASSWORD", ""))),
        "verify_tls": str(os.environ.get("XUI_VERIFY_TLS", values.get("XUI_VERIFY_TLS", "false"))).lower() in {"1", "true", "yes", "on"},
        "default_inbound_ids": str(os.environ.get("DEFAULT_INBOUND_IDS", values.get("DEFAULT_INBOUND_IDS", ""))),
        "runtime_settings": runtime_settings,
    }


def connection_summary() -> dict[str, str]:
    value = _connection_from_env()
    return {
        "base_url": str(value.get("base_url") or ""),
        "auth_mode": "token" if value.get("api_token") else "password",
    }


def _table_summary(db_path: Path) -> tuple[list[str], dict[str, int]]:
    with contextlib.closing(sqlite3.connect(db_path)) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise ValueError("Backup database failed integrity check")
        tables = sorted(
            str(row[0]) for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        )
        missing = sorted(CORE_TABLES - set(tables))
        if missing:
            raise ValueError("Backup is missing required tables: " + ", ".join(missing))
        counts: dict[str, int] = {}
        for table in tables:
            safe_name = table.replace('"', '""')
            counts[table] = int(con.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0])
        return tables, counts


def _ensure_complete_schema() -> None:
    # A newly generated v2 backup always has every application data table,
    # even when a feature (for example API keys) has not been used yet.
    from backend import admin_representatives as admin_reps
    from backend.admin_api_v1 import ensure_admin_api_schema
    from backend.admin_settings import ensure_settings_schema
    from backend.api_v1 import ensure_api_schema
    from backend.reseller_live_quota import ensure_live_schema
    from backend.reseller_users import ensure_users_schema

    admin_reps.ensure_admin_schema()
    ensure_users_schema()
    ensure_live_schema()
    ensure_api_schema()
    ensure_admin_api_schema()
    ensure_settings_schema()


def write_backup_package(destination: Path) -> Path:
    _ensure_complete_schema()
    with tempfile.TemporaryDirectory(prefix="xui-panel-package-") as td:
        db_path = Path(td) / "database.sqlite3"
        _sqlite_snapshot_to(db_path)
        tables, counts = _table_summary(db_path)
        connection = _connection_from_env()
        manifest = {
            "format": BACKUP_FORMAT,
            "format_version": BACKUP_FORMAT_VERSION,
            "app_version": app_version(),
            "created_at": _utc_now(),
            "database_sha256": _sha256_file(db_path),
            "database_bytes": db_path.stat().st_size,
            "tables": tables,
            "row_counts": counts,
            "contains_xui_connection": bool(connection.get("base_url")),
        }
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.write(db_path, arcname="database.sqlite3")
            archive.writestr("xui-connection.json", json.dumps(connection, ensure_ascii=False, indent=2))
        with contextlib.suppress(OSError):
            os.chmod(destination, 0o600)
    return destination


def create_backup_package() -> bytes:
    fd, name = tempfile.mkstemp(prefix="xui-panel-backup-", suffix=".xuibak")
    os.close(fd)
    try:
        write_backup_package(Path(name))
        return Path(name).read_bytes()
    finally:
        with contextlib.suppress(OSError):
            os.unlink(name)


def write_download_backup(destination: Path) -> Path:
    if not RESTORE_LOCK.acquire(blocking=False):
        raise RuntimeError("Another backup or restore operation is already running")
    process_lock = None
    try:
        process_lock = _acquire_process_maintenance_lock()
        return write_backup_package(destination)
    finally:
        if process_lock:
            process_lock.close()
        RESTORE_LOCK.release()


def _read_package(path: Path, extract_db_to: Path | None = None) -> dict[str, Any]:
    with path.open("rb") as source:
        header = source.read(16)
    if header == b"SQLite format 3\x00":
        db_path = extract_db_to or path
        if extract_db_to:
            shutil.copyfile(path, extract_db_to)
        tables, counts = _table_summary(db_path)
        return {
            "legacy": True,
            "manifest": {
                "format": "legacy-sqlite", "format_version": 1,
                "app_version": "unknown", "created_at": None,
                "tables": tables, "row_counts": counts,
                "contains_xui_connection": False,
            },
            "connection": None,
        }

    temp_created = extract_db_to is None
    if extract_db_to:
        db_path = Path(extract_db_to)
    else:
        fd, temp_name = tempfile.mkstemp(prefix="xui-panel-inspect-", suffix=".sqlite3")
        os.close(fd)
        db_path = Path(temp_name)
    try:
        try:
            with zipfile.ZipFile(path, "r") as archive:
                names = set(archive.namelist())
                required = {"manifest.json", "database.sqlite3", "xui-connection.json"}
                if not required.issubset(names):
                    raise ValueError("Backup package is incomplete")
                if archive.getinfo("manifest.json").file_size > 1024 * 1024:
                    raise ValueError("Backup manifest is too large")
                if archive.getinfo("xui-connection.json").file_size > 64 * 1024:
                    raise ValueError("Backup connection metadata is too large")
                if archive.getinfo("database.sqlite3").file_size > MAX_RESTORE_BYTES:
                    raise ValueError("Backup database is too large")
                manifest = json.loads(archive.read("manifest.json"))
                if manifest.get("format") != BACKUP_FORMAT:
                    raise ValueError("Unsupported backup format")
                if int(manifest.get("format_version") or 0) > BACKUP_FORMAT_VERSION:
                    raise ValueError("Backup was created by a newer unsupported panel version")
                digest = hashlib.sha256()
                with archive.open("database.sqlite3", "r") as source, db_path.open("wb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        output.write(chunk)
                if digest.hexdigest() != str(manifest.get("database_sha256") or ""):
                    raise ValueError("Backup checksum validation failed")
                connection = json.loads(archive.read("xui-connection.json"))
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
            raise ValueError("Backup package is invalid or corrupted") from exc
        tables, counts = _table_summary(db_path)
    finally:
        if temp_created:
            with contextlib.suppress(OSError):
                db_path.unlink()
    declared_tables = set(manifest.get("tables") or [])
    if declared_tables and declared_tables != set(tables):
        raise ValueError("Backup table manifest does not match the database")
    if int(manifest.get("format_version") or 0) >= 2:
        missing = sorted(EXPECTED_DATA_TABLES - set(tables))
        if missing:
            raise ValueError("Backup is incomplete; missing application tables: " + ", ".join(missing))
    manifest["tables"] = tables
    manifest["row_counts"] = counts
    return {"legacy": False, "manifest": manifest, "connection": connection}


def _cleanup_staging() -> None:
    cutoff = time.time() - STAGE_TTL_SECONDS
    with _staged_lock:
        expired = [token for token, item in _staged.items() if item.created_at < cutoff]
        for token in expired:
            item = _staged.pop(token)
            with contextlib.suppress(OSError):
                item.path.unlink()
        active_paths = {item.path for item in _staged.values()}
    if STAGING_DIR.exists():
        for path in STAGING_DIR.glob("*.upload"):
            with contextlib.suppress(OSError):
                if path not in active_paths and path.stat().st_mtime < cutoff:
                    path.unlink()


def restore_in_progress() -> bool:
    return RESTORE_ACTIVE.is_set()


def _acquire_process_maintenance_lock():
    if os.name == "nt":
        return None
    import fcntl
    MAINTENANCE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = MAINTENANCE_LOCK_PATH.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("Another panel maintenance operation is already running")
    return handle


def stage_backup(path: Path, admin_id: int) -> dict[str, Any]:
    _cleanup_staging()
    info = _read_package(path)
    manifest = info["manifest"]
    connection = info.get("connection") or {}
    token = secrets.token_urlsafe(32)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    destination = STAGING_DIR / f"{token}.upload"
    # Upload temp directories can live on another filesystem (/tmp vs /opt).
    shutil.move(str(path), str(destination))
    with contextlib.suppress(OSError):
        os.chmod(destination, 0o600)
    preview = {
        "restore_token": token,
        "legacy": bool(info["legacy"]),
        "app_version": manifest.get("app_version"),
        "created_at": manifest.get("created_at"),
        "tables": manifest.get("tables") or [],
        "row_counts": manifest.get("row_counts") or {},
        "has_backup_connection": bool(connection.get("base_url")),
        "backup_xui_url": str(connection.get("base_url") or ""),
        "expires_in_seconds": STAGE_TTL_SECONDS,
    }
    with _staged_lock:
        _staged[token] = StagedRestore(token, destination, int(admin_id), time.time(), preview)
    return preview


def _get_stage(token: str, admin_id: int) -> StagedRestore:
    _cleanup_staging()
    with _staged_lock:
        item = _staged.get(str(token))
    if not item or item.admin_id != int(admin_id):
        raise ValueError("Restore confirmation expired; inspect the backup again")
    return item


def _discard_stage(token: str) -> None:
    with _staged_lock:
        item = _staged.pop(str(token), None)
    if item:
        with contextlib.suppress(OSError):
            item.path.unlink()


def _write_env_connection(connection: dict[str, Any]) -> None:
    current = read_env_file()
    mapping = {
        "XUI_BASE_URL": str(connection.get("base_url") or "").rstrip("/"),
        "XUI_API_TOKEN": str(connection.get("api_token") or ""),
        "XUI_USERNAME": str(connection.get("username") or ""),
        "XUI_PASSWORD": str(connection.get("password") or ""),
        "XUI_VERIFY_TLS": "true" if bool(connection.get("verify_tls")) else "false",
        "DEFAULT_INBOUND_IDS": str(connection.get("default_inbound_ids") or ""),
    }
    runtime_settings = connection.get("runtime_settings")
    if isinstance(runtime_settings, dict):
        for key in PORTABLE_RUNTIME_KEYS:
            value = str(runtime_settings.get(key) or "")
            if "\n" in value or "\r" in value:
                raise ValueError(f"Invalid runtime setting: {key}")
            mapping[key] = value
    current.update(mapping)
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text("\n".join(f"{key}={value}" for key, value in current.items()).rstrip() + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(ENV_PATH, 0o600)
    reload_env_file()


def validate_connection(connection: dict[str, Any]) -> dict[str, Any]:
    base_url = str(connection.get("base_url") or "").strip().rstrip("/")
    token = str(connection.get("api_token") or "").strip()
    username = str(connection.get("username") or "").strip()
    password = str(connection.get("password") or "")
    if any("\n" in value or "\r" in value for value in (base_url, token, username, password)):
        raise ValueError("X-UI connection values must not contain line breaks")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("X-UI URL must start with http:// or https://")
    if not token and not (username and password):
        raise ValueError("X-UI API token or username/password is required")
    candidate = dict(connection)
    candidate["base_url"] = base_url
    candidate["api_token"] = token
    try:
        client = XUIClient(
            base_url=base_url, api_token=token, username=username, password=password,
            verify_tls=bool(connection.get("verify_tls")),
        )
        rows = client.inbounds()
    except (XUIError, Exception) as exc:
        raise ValueError(f"X-UI connection validation failed: {exc}") from exc
    return {"connection": candidate, "inbounds": len(rows)}


def _save_safety_backup() -> Path:
    SAFETY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = SAFETY_DIR / f"before-restore-{stamp}.sqlite3"
    _sqlite_snapshot_to(path)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    backups = sorted(SAFETY_DIR.glob("before-restore-*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[SAFETY_BACKUP_KEEP:]:
        with contextlib.suppress(OSError):
            old.unlink()
    return path


def _restore_database(source_path: Path) -> None:
    with contextlib.closing(sqlite3.connect(source_path)) as source:
        with contextlib.closing(reseller_profile.connect_db()) as target:
            source.backup(target)
            target.commit()


def restore_database_from_package_for_rollback(package_path: Path) -> None:
    """Restore only SQLite data from a trusted local safety package."""
    fd, name = tempfile.mkstemp(prefix="xui-update-rollback-", suffix=".sqlite3")
    os.close(fd)
    path = Path(name)
    try:
        _read_package(Path(package_path), path)
        _restore_database(path)
        _post_restore_check()
    finally:
        with contextlib.suppress(OSError):
            path.unlink()


def _post_restore_check() -> None:
    with contextlib.closing(reseller_profile.connect_db()) as con:
        result = con.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError("Restored database failed integrity check")
        tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = CORE_TABLES - tables
        if missing:
            raise RuntimeError("Restored database is missing: " + ", ".join(sorted(missing)))


def apply_restore(
    *, token: str, admin_id: int,
    connection_mode: Literal["backup", "current", "new"],
    new_connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not RESTORE_LOCK.acquire(blocking=False):
        raise RuntimeError("Another backup or restore operation is already running")
    RESTORE_ACTIVE.set()
    item: StagedRestore | None = None
    db_temp: Path | None = None
    sync_lock: threading.Lock | None = None
    sync_lock_acquired = False
    process_lock = None
    restore_started = False
    env_before = ENV_PATH.read_bytes() if ENV_PATH.exists() else None
    safety: Path | None = None
    try:
        process_lock = _acquire_process_maintenance_lock()
        item = _get_stage(token, admin_id)
        fd, db_name = tempfile.mkstemp(prefix="xui-restore-db-", suffix=".sqlite3")
        os.close(fd)
        db_temp = Path(db_name)
        info = _read_package(item.path, db_temp)
        backup_connection = info.get("connection") or {}
        current_connection = _connection_from_env()
        if connection_mode == "backup":
            if not backup_connection.get("base_url"):
                raise ValueError("This backup does not contain X-UI connection settings")
            chosen = backup_connection
        elif connection_mode == "new":
            chosen = dict(new_connection or {})
        elif connection_mode == "current":
            chosen = current_connection
        else:
            raise ValueError("Invalid X-UI connection choice")

        # Public link/proxy behavior belongs to the restored panel data. Keep
        # destination-only infrastructure values (port/cookie mode) untouched.
        chosen["runtime_settings"] = backup_connection.get("runtime_settings") or {}

        validation = validate_connection(chosen)
        chosen = validation["connection"]
        from backend import reseller_live_quota as live_quota
        sync_lock = live_quota._SYNC_LOCK
        if not sync_lock.acquire(timeout=30):
            raise RuntimeError("Traffic synchronization is busy; try the restore again")
        sync_lock_acquired = True
        safety = _save_safety_backup()
        restore_started = True
        _restore_database(db_temp)

        # Import lazily to avoid circular module initialization.
        from backend import admin_representatives as admin_reps
        from backend.admin_settings import ensure_settings_schema
        from backend.reseller_live_quota import ensure_live_schema
        from backend.reseller_users import ensure_users_schema
        from backend.api_v1 import ensure_api_schema
        from backend.admin_api_v1 import ensure_admin_api_schema

        admin_reps.ensure_admin_schema()
        ensure_users_schema()
        ensure_live_schema()
        ensure_api_schema()
        ensure_admin_api_schema()
        ensure_settings_schema()
        with reseller_profile.connect_db() as con:
            con.execute("DELETE FROM auth_sessions")
            con.commit()
        _write_env_connection(chosen)
        _post_restore_check()
        return {
            "ok": True,
            "relogin_required": True,
            "safety_backup": safety.name,
            "xui_url": chosen.get("base_url"),
            "xui_inbounds": validation["inbounds"],
        }
    except Exception:
        if safety and safety.exists():
            with contextlib.suppress(Exception):
                _restore_database(safety)
        try:
            if env_before is None:
                with contextlib.suppress(OSError):
                    ENV_PATH.unlink()
            else:
                ENV_PATH.write_bytes(env_before)
            reload_env_file()
        except Exception:
            pass
        raise
    finally:
        if item and restore_started:
            _discard_stage(item.token)
        if db_temp:
            with contextlib.suppress(OSError):
                db_temp.unlink()
        if sync_lock and sync_lock_acquired:
            sync_lock.release()
        RESTORE_ACTIVE.clear()
        if process_lock:
            process_lock.close()
        RESTORE_LOCK.release()
