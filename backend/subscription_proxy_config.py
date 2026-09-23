from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import tempfile
import threading
from pathlib import Path


NGINX_CONFIG_PATH = Path(
    os.getenv(
        "SUBSCRIPTION_PROXY_NGINX_CONFIG",
        "/etc/nginx/conf.d/xui-reseller-panel-subscription.conf",
    )
)
BACKEND_PORT = 8000
_config_lock = threading.Lock()


class SubscriptionProxyConfigError(RuntimeError):
    pass


def _safe_nginx_value(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not text or any(char in text for char in ("\r", "\n", ";", "{", "}", '"')):
        raise SubscriptionProxyConfigError(f"{label} is invalid")
    return text


def _certificate_file(value: str, label: str) -> str:
    text = _safe_nginx_value(value, label)
    path = Path(text)
    if not path.is_absolute() or not path.is_file():
        raise SubscriptionProxyConfigError(f"{label} does not exist on this server")
    return str(path)


def port_is_available(port: int, current_port: int = 0) -> bool:
    if int(port) == int(current_port or 0):
        return True
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def render_nginx_config(host: str, port: int, certificate_path: str, key_path: str) -> str:
    if not 1 <= int(port) <= 65535:
        raise SubscriptionProxyConfigError("Subscription proxy port is invalid")
    safe_host = _safe_nginx_value(host, "Subscription proxy host")
    cert = _certificate_file(certificate_path, "TLS certificate path")
    key = _certificate_file(key_path, "TLS private key path")
    return f"""# Managed by x-ui-reseller-panel. Do not edit manually.
server {{
    listen {int(port)} ssl;
    listen [::]:{int(port)} ssl;
    server_name {safe_host};

    ssl_certificate "{cert}";
    ssl_certificate_key "{key}";
    ssl_protocols TLSv1.2 TLSv1.3;

    location /sub/ {{
        proxy_pass http://127.0.0.1:{BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        proxy_buffering off;
    }}

    location / {{
        return 404;
    }}
}}
"""


def _run(command: list[str]) -> None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SubscriptionProxyConfigError(f"Unable to run {' '.join(command)}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise SubscriptionProxyConfigError(detail[-800:])


def _restore(previous: bytes | None) -> None:
    if previous is None:
        NGINX_CONFIG_PATH.unlink(missing_ok=True)
    else:
        NGINX_CONFIG_PATH.write_bytes(previous)
    with contextlib.suppress(Exception):
        _run(["nginx", "-t"])
        _run(["systemctl", "reload", "nginx"])


def apply_nginx_config(
    *,
    host: str,
    port: int,
    certificate_path: str,
    key_path: str,
    current_port: int = 0,
) -> None:
    with _config_lock:
        previous = NGINX_CONFIG_PATH.read_bytes() if NGINX_CONFIG_PATH.exists() else None

        if not host and not port:
            NGINX_CONFIG_PATH.unlink(missing_ok=True)
            try:
                _run(["nginx", "-t"])
                _run(["systemctl", "reload", "nginx"])
            except Exception:
                _restore(previous)
                raise
            return

        if not port_is_available(port, current_port):
            raise SubscriptionProxyConfigError(f"Port {port} is already in use")

        rendered = render_nginx_config(host, port, certificate_path, key_path)
        NGINX_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=NGINX_CONFIG_PATH.name + ".",
            suffix=".tmp",
            dir=str(NGINX_CONFIG_PATH.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, NGINX_CONFIG_PATH)
            try:
                _run(["nginx", "-t"])
                _run(["systemctl", "reload", "nginx"])
            except Exception:
                _restore(previous)
                raise
        finally:
            Path(temp_name).unlink(missing_ok=True)
