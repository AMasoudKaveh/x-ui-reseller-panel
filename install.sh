#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"
VENV="$BACKEND_DIR/.venv"
SERVICE_NAME="xui-reseller-panel"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NGINX_SITE="/etc/nginx/sites-available/${SERVICE_NAME}"
NGINX_LINK="/etc/nginx/sites-enabled/${SERVICE_NAME}"
INTERNAL_PORT=8000
DEFAULT_PUBLIC_PORT=8088

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root: sudo bash install.sh"
  exit 1
fi

if [[ ! -f "$APP_DIR/package.json" || ! -f "$BACKEND_DIR/main.py" ]]; then
  echo "Run install.sh from the project root."
  exit 1
fi

prompt_nonempty() {
  local prompt="$1" value=""
  while [[ -z "$value" ]]; do
    read -r -p "$prompt" value
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
  done
  printf '%s' "$value"
}

prompt_port() {
  local value=""
  while true; do
    read -r -p "Public panel port [$DEFAULT_PUBLIC_PORT]: " value
    value="${value:-$DEFAULT_PUBLIC_PORT}"
    if [[ "$value" =~ ^[0-9]+$ ]] && (( value >= 1 && value <= 65535 )); then
      if [[ "$value" == "$INTERNAL_PORT" ]]; then
        echo "Port $INTERNAL_PORT is reserved for the internal backend. Choose another port."
        continue
      fi
      printf '%s' "$value"
      return
    fi
    echo "Enter a valid TCP port between 1 and 65535."
  done
}

set_env_value() {
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
if not found:
    out.append(f'{key}={value}')
p.write_text('\n'.join(out).rstrip()+'\n', encoding='utf-8')
PY
}

public_ip() {
  local ip
  ip="$(hostname -I 2>/dev/null | tr ' ' '\n' | awk '/^[0-9]+\./ {print; exit}')"
  printf '%s' "${ip:-SERVER-IP}"
}

echo "============================================================"
echo " X-UI Reseller Panel Installer"
echo "============================================================"
echo

echo "[1/9] Installing system dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl ca-certificates gnupg python3 python3-venv python3-pip build-essential nginx git zip

NODE_OK=0
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  if [[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] && (( NODE_MAJOR >= 20 )); then
    NODE_OK=1
  fi
fi

if (( NODE_OK == 0 )); then
  echo "Installing Node.js 20 LTS..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

echo "Node: $(node -v)"
echo "npm:  $(npm -v)"

echo
echo "[2/9] Creating Python environment..."
if [[ ! -x "$VENV/bin/python" ]]; then
  rm -rf "$VENV"
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

echo
PUBLIC_PORT="$(prompt_port)"
XUI_BASE_URL="$(prompt_nonempty 'Full X-UI URL (include web base path): ')"
XUI_BASE_URL="${XUI_BASE_URL%/}"

read -r -s -p "X-UI API token (blank = use username/password): " XUI_API_TOKEN
echo

XUI_USERNAME=""
XUI_PASSWORD=""

if [[ -n "$XUI_API_TOKEN" ]]; then
  echo "X-UI authentication mode: API token"
else
  echo "X-UI authentication mode: username/password"

  read -r -p "X-UI username: " XUI_USERNAME
  while [[ -z "$XUI_USERNAME" ]]; do
    echo "X-UI username is required when API token is not provided."
    read -r -p "X-UI username: " XUI_USERNAME
  done

  read -r -s -p "X-UI password: " XUI_PASSWORD
  echo
  while [[ -z "$XUI_PASSWORD" ]]; do
    echo "X-UI password is required when API token is not provided."
    read -r -s -p "X-UI password: " XUI_PASSWORD
    echo
  done
fi

read -r -p "Verify X-UI TLS certificate? [y/N]: " VERIFY_REPLY
case "${VERIFY_REPLY:-N}" in
  y|Y|yes|YES) XUI_VERIFY_TLS=true ;;
  *) XUI_VERIFY_TLS=false ;;
esac

ADMIN_USERNAME=""
ADMIN_PASSWORD=""
if [[ ! -f "$BACKEND_DIR/data/auth.db" ]]; then
  ADMIN_USERNAME="$(prompt_nonempty 'Initial admin username: ')"
  while true; do
    read -r -s -p "Initial admin password (minimum 8 characters): " ADMIN_PASSWORD
    echo
    if (( ${#ADMIN_PASSWORD} >= 8 )); then break; fi
    echo "Password must be at least 8 characters."
  done
  read -r -s -p "Repeat admin password: " ADMIN_PASSWORD_2
  echo
  if [[ "$ADMIN_PASSWORD" != "$ADMIN_PASSWORD_2" ]]; then
    echo "Passwords do not match. Installation stopped."
    exit 1
  fi
else
  echo "Existing local database detected; current admin account will be preserved."
fi

mkdir -p "$BACKEND_DIR/data"
chmod 755 "$BACKEND_DIR/data"

cat > "$ENV_FILE" <<EOF
XUI_BASE_URL=$XUI_BASE_URL
XUI_API_TOKEN=$XUI_API_TOKEN
XUI_USERNAME=$XUI_USERNAME
XUI_PASSWORD=$XUI_PASSWORD
XUI_VERIFY_TLS=$XUI_VERIFY_TLS
DEFAULT_INBOUND_IDS=
POLL_SECONDS=10
ADMIN_BOOTSTRAP_USERNAME=$ADMIN_USERNAME
ADMIN_BOOTSTRAP_PASSWORD=$ADMIN_PASSWORD
SESSION_COOKIE_SECURE=false
ENABLE_LIVE_PROBE=false
PANEL_PUBLIC_PORT=$PUBLIC_PORT
EOF
chmod 600 "$ENV_FILE"

echo
echo "[3/9] Testing X-UI connection..."
if ! PYTHONPATH="$APP_DIR" "$VENV/bin/python" -m backend.xui_probe; then
  echo
  echo "X-UI connection test failed. Installation will not continue."
  echo "Edit backend/.env or rerun install.sh with the correct panel URL/credentials."
  exit 1
fi

echo
echo "[4/9] Installing frontend dependencies and building..."
cd "$APP_DIR"
npm ci
npm run build

echo
echo "[5/9] Creating backend systemd service..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=XUI Reseller Panel Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment=PYTHONPATH=$APP_DIR
ExecStart=$VENV/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port $INTERNAL_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null

echo
echo "[6/9] Configuring Nginx on public port $PUBLIC_PORT..."
rm -f /etc/nginx/sites-enabled/default
cat > "$NGINX_SITE" <<EOF
server {
    listen $PUBLIC_PORT default_server;
    listen [::]:$PUBLIC_PORT default_server;
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
nginx -t
systemctl enable nginx >/dev/null
systemctl reload nginx || systemctl restart nginx

echo
echo "[7/9] Starting backend..."
systemctl restart "$SERVICE_NAME"

READY=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$INTERNAL_PORT/docs" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if (( READY == 0 )); then
  echo "Backend failed to start. Recent log:"
  journalctl -u "$SERVICE_NAME" -n 80 --no-pager
  exit 1
fi

if ! curl -fsS "http://127.0.0.1:$PUBLIC_PORT/" >/dev/null; then
  echo "Nginx frontend check failed."
  exit 1
fi

# Once the fresh admin was inserted into the DB, remove the plaintext bootstrap
# credentials from the environment file.  Future password changes are stored as
# hashes in SQLite.
if [[ -n "$ADMIN_USERNAME" ]]; then
  set_env_value ADMIN_BOOTSTRAP_USERNAME ""
  set_env_value ADMIN_BOOTSTRAP_PASSWORD ""
  systemctl restart "$SERVICE_NAME"
fi

echo
echo "[8/9] Installing management command..."
chmod +x "$APP_DIR/manage.sh" "$APP_DIR/install.sh"
ln -sfn "$APP_DIR/manage.sh" /usr/local/bin/xui-panel

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  ufw allow "$PUBLIC_PORT/tcp" >/dev/null || true
fi

echo
echo "[9/9] Final checks..."
systemctl is-active --quiet "$SERVICE_NAME"
systemctl is-active --quiet nginx

IP="$(public_ip)"
echo
echo "============================================================"
echo " INSTALLATION COMPLETE"
echo "============================================================"
echo "Admin:    http://$IP:$PUBLIC_PORT/#/admin/login"
echo "Reseller: http://$IP:$PUBLIC_PORT/#/reseller/login"
echo
echo "Management menu: sudo xui-panel"
echo "Backend service: $SERVICE_NAME"
echo "Public port: $PUBLIC_PORT"
echo "TLS/domain: disabled by design in this release"
