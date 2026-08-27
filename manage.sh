#!/usr/bin/env bash
set -Eeuo pipefail

SELF="$(readlink -f "${BASH_SOURCE[0]}")"
APP_DIR="$(cd "$(dirname "$SELF")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"
VENV="$BACKEND_DIR/.venv"
SERVICE_NAME="xui-reseller-panel"
NGINX_SITE="/etc/nginx/sites-available/${SERVICE_NAME}"
NGINX_LINK="/etc/nginx/sites-enabled/${SERVICE_NAME}"
INTERNAL_PORT=8000
BACKUP_DIR="/var/backups/xui-reseller-panel"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run with sudo/root: sudo xui-panel"
  exit 1
fi

get_env() {
  local key="$1"
  python3 - "$ENV_FILE" "$key" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); key=sys.argv[2]
if not p.exists():
    print(""); raise SystemExit
for line in p.read_text(encoding='utf-8', errors='ignore').splitlines():
    if line.startswith(key+'='):
        print(line.split('=',1)[1]); break
else:
    print("")
PY
}

set_env() {
  local key="$1" value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); key=sys.argv[2]; value=sys.argv[3]
lines=p.read_text(encoding='utf-8', errors='ignore').splitlines() if p.exists() else []
out=[]; found=False
for line in lines:
    if line.startswith(key+'='):
        out.append(f'{key}={value}'); found=True
    else:
        out.append(line)
if not found: out.append(f'{key}={value}')
p.write_text('\n'.join(out).rstrip()+'\n', encoding='utf-8')
PY
  chmod 600 "$ENV_FILE"
}

public_ip() {
  hostname -I 2>/dev/null | tr ' ' '\n' | awk '/^[0-9]+\./ {print; exit}'
}

current_port() {
  local p
  p="$(get_env PANEL_PUBLIC_PORT)"
  [[ "$p" =~ ^[0-9]+$ ]] || p=8088
  printf '%s' "$p"
}

write_nginx() {
  local port="$1"
  cat > "$NGINX_SITE" <<EOF
server {
    listen $port default_server;
    listen [::]:$port default_server;
    server_name _;

    root $APP_DIR/dist;
    index index.html;
    client_max_body_size 100M;

    location /api/ {
        proxy_pass http://127.0.0.1:$INTERNAL_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        proxy_buffering off;
    }

    location /assets/ {
        try_files \$uri =404;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files \$uri \$uri/ /index.html;
        add_header Cache-Control "no-cache";
    }
}
EOF
  ln -sfn "$NGINX_SITE" "$NGINX_LINK"
}

pause() {
  echo
  read -r -p "Press Enter to continue..." _
}

show_status() {
  local port ip xui user token
  port="$(current_port)"
  ip="$(public_ip)"; ip="${ip:-SERVER-IP}"
  xui="$(get_env XUI_BASE_URL)"
  user="$(get_env XUI_USERNAME)"
  token="$(get_env XUI_API_TOKEN)"
  echo
  echo "Panel status"
  echo "--------------------------------------------"
  echo "Backend: $(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)"
  echo "Nginx:   $(systemctl is-active nginx 2>/dev/null || true)"
  echo "Port:    $port"
  echo "Admin:   http://$ip:$port/#/admin/login"
  echo "Reseller:http://$ip:$port/#/reseller/login"
  echo "X-UI URL: $xui"
  if [[ -n "$token" ]]; then
    echo "X-UI auth: API token"
    echo "X-UI API token: <hidden>"
  else
    echo "X-UI auth: username/password"
    echo "X-UI user: ${user:-<not set>}"
    echo "X-UI password: <hidden>"
  fi
  echo
  if [[ -x "$VENV/bin/python" && -f "$BACKEND_DIR/data/auth.db" ]]; then
    PYTHONPATH="$APP_DIR" "$VENV/bin/python" -m backend.admin_cli show || true
  fi
}

change_admin() {
  echo
  echo "Current admin account:"
  PYTHONPATH="$APP_DIR" "$VENV/bin/python" -m backend.admin_cli show
  local current new_user p1 p2 args
  current="$(PYTHONPATH="$APP_DIR" "$VENV/bin/python" -m backend.admin_cli show | sed -n 's/^username=//p')"
  read -r -p "New username [$current]: " new_user
  new_user="${new_user:-$current}"
  echo "Current password cannot be displayed because it is stored as a secure hash."
  read -r -s -p "New password (blank = keep current): " p1
  echo
  if [[ -n "$p1" ]]; then
    if (( ${#p1} < 8 )); then
      echo "Password must be at least 8 characters."
      return 1
    fi
    read -r -s -p "Repeat new password: " p2
    echo
    if [[ "$p1" != "$p2" ]]; then
      echo "Passwords do not match."
      return 1
    fi
    PYTHONPATH="$APP_DIR" "$VENV/bin/python" -m backend.admin_cli update --username "$new_user" --password "$p1"
  else
    PYTHONPATH="$APP_DIR" "$VENV/bin/python" -m backend.admin_cli update --username "$new_user"
  fi
  systemctl restart "$SERVICE_NAME"
}

change_xui() {
  local old_env base token user pass verify reply mode
  local current_mode current_token current_user current_pass current_verify

  old_env="$(mktemp)"
  cp "$ENV_FILE" "$old_env"

  current_token="$(get_env XUI_API_TOKEN)"
  current_user="$(get_env XUI_USERNAME)"
  current_pass="$(get_env XUI_PASSWORD)"
  current_verify="$(get_env XUI_VERIFY_TLS)"

  if [[ -n "$current_token" ]]; then
    current_mode="token"
  else
    current_mode="password"
  fi

  echo
  echo "Current X-UI URL: $(get_env XUI_BASE_URL)"
  echo "Current authentication mode: $current_mode"

  if [[ "$current_mode" == "token" ]]; then
    echo "Current X-UI API token: <hidden>"
  else
    echo "Current X-UI username: ${current_user:-<not set>}"
    echo "Current X-UI password: <hidden>"
  fi

  echo
  read -r -p "New full X-UI URL [keep current]: " base
  base="${base:-$(get_env XUI_BASE_URL)}"
  base="${base%/}"

  echo
  read -r -p "Authentication mode [token/password, Enter=$current_mode]: " mode
  mode="${mode:-$current_mode}"

  case "$mode" in
    token|TOKEN|Token)
      read -r -s -p "New X-UI API token [blank = keep current token]: " token
      echo

      if [[ -z "$token" ]]; then
        if [[ "$current_mode" == "token" && -n "$current_token" ]]; then
          token="$current_token"
        else
          echo "API token is required for token authentication."
          rm -f "$old_env"
          return 1
        fi
      fi

      user=""
      pass=""
      ;;

    password|PASSWORD|Password|user|USER|User)
      token=""

      read -r -p "New X-UI username [${current_user:-required}]: " user
      user="${user:-$current_user}"

      if [[ -z "$user" ]]; then
        echo "X-UI username is required."
        rm -f "$old_env"
        return 1
      fi

      read -r -s -p "New X-UI password [blank = keep current]: " pass
      echo

      if [[ -z "$pass" ]]; then
        pass="$current_pass"
      fi

      if [[ -z "$pass" ]]; then
        echo "X-UI password is required."
        rm -f "$old_env"
        return 1
      fi
      ;;

    *)
      echo "Invalid authentication mode. Use token or password."
      rm -f "$old_env"
      return 1
      ;;
  esac

  echo
  read -r -p "Verify TLS certificate? [y/n, Enter=keep $current_verify]: " reply

  case "$reply" in
    "")
      verify="${current_verify:-false}"
      ;;
    y|Y|yes|YES)
      verify=true
      ;;
    n|N|no|NO)
      verify=false
      ;;
    *)
      echo "Invalid TLS option."
      rm -f "$old_env"
      return 1
      ;;
  esac

  set_env XUI_BASE_URL "$base"
  set_env XUI_API_TOKEN "$token"
  set_env XUI_USERNAME "$user"
  set_env XUI_PASSWORD "$pass"
  set_env XUI_VERIFY_TLS "$verify"

  echo
  echo "Testing X-UI connection..."

  if PYTHONPATH="$APP_DIR" "$VENV/bin/python" -m backend.xui_probe; then
    rm -f "$old_env"
    systemctl restart "$SERVICE_NAME"
    echo "X-UI connection updated."
  else
    cp "$old_env" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    rm -f "$old_env"
    echo "Connection test failed; previous settings restored."
    return 1
  fi
}

change_port() {
  local old new backup
  old="$(current_port)"
  read -r -p "New public panel port [$old]: " new
  new="${new:-$old}"
  if ! [[ "$new" =~ ^[0-9]+$ ]] || (( new < 1 || new > 65535 )); then
    echo "Invalid port."
    return 1
  fi
  if [[ "$new" == "$INTERNAL_PORT" ]]; then
    echo "Port $INTERNAL_PORT is reserved for the backend."
    return 1
  fi
  if [[ "$new" == "$old" ]]; then
    echo "Port unchanged."
    return
  fi
  backup="$(mktemp)"
  [[ -f "$NGINX_SITE" ]] && cp "$NGINX_SITE" "$backup" || : > "$backup"
  write_nginx "$new"
  if nginx -t; then
    set_env PANEL_PUBLIC_PORT "$new"
    systemctl reload nginx
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
      ufw allow "$new/tcp" >/dev/null || true
    fi
    echo "Panel port changed to $new."
    echo "Admin: http://$(public_ip):$new/#/admin/login"
  else
    cp "$backup" "$NGINX_SITE"
    nginx -t || true
    echo "Nginx rejected the new config; old port was restored."
    rm -f "$backup"
    return 1
  fi
  rm -f "$backup"
}

backup_db() {
  mkdir -p "$BACKUP_DIR"
  local out
  out="$BACKUP_DIR/xui-panel-$(date +%Y%m%d-%H%M%S).db"
  "$VENV/bin/python" - "$BACKEND_DIR/data/auth.db" "$out" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
    s.backup(d)
print(dst)
PY
  chmod 600 "$out"
  echo "Backup created: $out"
}

rebuild_frontend() {
  cd "$APP_DIR"
  npm ci
  npm run build
  nginx -t
  systemctl reload nginx
  echo "Frontend rebuilt successfully."
}

update_from_git() {
  if [[ ! -d "$APP_DIR/.git" ]]; then
    echo "This installation is not a Git checkout."
    return 1
  fi
  cd "$APP_DIR"
  git pull --ff-only
  "$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
  npm ci
  npm run build
  systemctl restart "$SERVICE_NAME"
  nginx -t && systemctl reload nginx
  echo "Update complete."
}

uninstall_panel() {
  echo
  echo "WARNING: this removes the service, Nginx config and application directory."
  echo "The primary X-UI panel is NOT modified."
  read -r -p "Type REMOVE to continue: " confirm
  [[ "$confirm" == "REMOVE" ]] || { echo "Cancelled."; return; }

  read -r -p "Create one final local DB backup first? [Y/n]: " b
  case "${b:-Y}" in n|N|no|NO) ;; *) [[ -f "$BACKEND_DIR/data/auth.db" ]] && backup_db || true ;; esac

  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload
  systemctl reset-failed 2>/dev/null || true

  rm -f "$NGINX_LINK" "$NGINX_SITE"
  rm -f /usr/local/bin/xui-panel
  nginx -t >/dev/null 2>&1 && systemctl reload nginx || true

  read -r -p "Also remove saved backups in $BACKUP_DIR? [y/N]: " rb
  case "${rb:-N}" in y|Y|yes|YES) rm -rf "$BACKUP_DIR" ;; esac

  echo "Removing $APP_DIR ..."
  rm -rf "$APP_DIR"
  echo "Panel removed."
  exit 0
}

while true; do
  clear || true
  echo "============================================================"
  echo " X-UI Reseller Panel Management"
  echo "============================================================"
  echo "1) Show status / panel links"
  echo "2) Restart panel"
  echo "3) Live backend logs"
  echo "4) Admin username/password"
  echo "5) X-UI connection settings"
  echo "6) Change public panel port"
  echo "7) Backup local database"
  echo "8) Rebuild frontend"
  echo "9) Update from GitHub"
  echo "10) Uninstall panel completely"
  echo "0) Exit"
  echo
  read -r -p "Select: " choice
  case "$choice" in
    1) show_status; pause ;;
    2) systemctl restart "$SERVICE_NAME"; echo "Restarted."; pause ;;
    3) journalctl -u "$SERVICE_NAME" -f ;;
    4) change_admin || true; pause ;;
    5) change_xui || true; pause ;;
    6) change_port || true; pause ;;
    7) backup_db || true; pause ;;
    8) rebuild_frontend || true; pause ;;
    9) update_from_git || true; pause ;;
    10) uninstall_panel ;;
    0) exit 0 ;;
    *) echo "Invalid selection."; sleep 1 ;;
  esac
done
