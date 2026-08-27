[README.md](https://github.com/user-attachments/files/31534339/README-public.md)
# X-UI Reseller Panel

A modern web-based **Admin & Reseller Management Panel for X-UI / 3X-UI**.

X-UI Reseller Panel provides a separate management interface for administrators and resellers while using your existing X-UI server as the source of truth for inbounds, clients, traffic usage, and account status.

It is designed for server owners who want to give resellers controlled access to create and manage users without giving them direct access to the main X-UI panel.

> Public repository: https://github.com/AMasoudKaveh/x-ui-reseller-panel

---

## Features

### Admin Panel

- Dedicated administrator dashboard
- Create, edit, and remove reseller accounts
- Assign traffic quota to each reseller
- Restrict each reseller to selected X-UI inbounds
- View all VPN clients
- View X-UI inbounds
- Monitor online users
- View live traffic usage
- Manage reseller traffic consumption
- Manage external proxy settings
- Change administrator credentials
- Backup local panel database
- Light and dark interface support

### Reseller Panel

- Separate reseller login
- Create VPN users
- Modify existing users
- Delete users
- Reset client usage
- Revoke subscription links
- View online users
- View remaining reseller traffic
- Access only authorized inbounds
- Automatic traffic synchronization with X-UI

### Traffic & Quota Management

The reseller quota is calculated from actual client traffic usage.

When a reseller reaches the assigned quota:

- Reseller access can be restricted
- Eligible reseller clients can be disabled automatically
- Clients disabled for unrelated reasons remain unchanged
- After quota recharge, only clients disabled because of reseller quota are restored

Historical traffic usage is preserved even when clients or reseller accounts are removed.

---

## X-UI Integration

The panel connects directly to your existing **X-UI / 3X-UI** installation.

Supported authentication methods:

- X-UI API Token
- X-UI Username / Password

The installer performs a real X-UI connection test before completing installation.

Your X-UI URL must include the full **Web Base Path**.

Example:

```text
https://example.com:2053/my-xui-path/
```

Do not manually add API paths such as:

```text
/panel/api/
/panel/api/inbounds/
```

The backend handles the required API paths internally.

---

## Requirements

Recommended environment:

- Ubuntu 22.04 or Ubuntu 24.04
- Root access
- Existing X-UI / 3X-UI installation
- Internet access

The installer prepares the required runtime environment, including:

- Git
- Python virtual environment
- Backend dependencies
- Node.js / frontend dependencies
- Production frontend build
- Systemd service
- Nginx configuration

---

# Quick Installation

Because this repository is public, **no GitHub account, SSH key, Deploy Key, or access token is required**.

Run the following commands on a fresh server as `root`:

```bash
apt update
apt install -y git

cd /opt
git clone https://github.com/AMasoudKaveh/x-ui-reseller-panel.git
cd x-ui-reseller-panel

chmod +x install.sh manage.sh
bash install.sh
```

The installer will guide you through the rest of the setup.

---

# Installer Configuration

## 1. Public Panel Port

Choose the public port used to access the panel.

Example:

```text
8080
```

---

## 2. X-UI URL

Enter the complete URL of your X-UI panel, including its Web Base Path.

Example:

```text
https://example.com:2053/my-xui-path/
```

---

## 3. X-UI Authentication

The installer supports two authentication methods.

### API Token

When prompted:

```text
X-UI API token (blank = use username/password):
```

Enter your X-UI API Token.

If a token is provided, X-UI username/password authentication is not required.

### Username / Password

If you do not use an API Token, leave the token field blank.

The installer will then ask for:

```text
X-UI username:
X-UI password:
```

---

## 4. TLS Verification

When prompted:

```text
Verify X-UI TLS certificate? [y/N]:
```

Use:

```text
y
```

if your X-UI address uses a valid trusted SSL/TLS certificate.

Use:

```text
n
```

if the X-UI installation uses a self-signed or otherwise untrusted certificate.

---

## 5. Administrator Account

On the first installation, the installer asks you to create the administrator account:

```text
Initial admin username:
Initial admin password:
Repeat admin password:
```

Administrator passwords are stored securely as hashes and cannot be displayed in plaintext.

---

## 6. X-UI Connection Test

Before installation continues, the installer performs an actual connection test against the configured X-UI server.

If the test fails, installation stops so you can correct:

- X-UI URL
- Web Base Path
- API Token
- Username / Password
- TLS verification settings

---

# Accessing the Panel

After installation, replace `SERVER-IP` and `PANEL-PORT` with your server information.

## Admin Panel

```text
http://SERVER-IP:PANEL-PORT/#/admin/login
```

Example:

```text
http://192.0.2.10:8080/#/admin/login
```

## Reseller Panel

```text
http://SERVER-IP:PANEL-PORT/#/reseller/login
```

Example:

```text
http://192.0.2.10:8080/#/reseller/login
```

---

# Panel Management

After installation, run:

```bash
xui-panel
```

The management menu includes:

```text
1) Show status / panel links
2) Restart panel
3) Live backend logs
4) Admin username/password
5) X-UI connection settings
6) Change public panel port
7) Backup local database
8) Rebuild frontend
9) Update from GitHub
10) Uninstall panel completely
0) Exit
```

---

## Show Status / Panel Links

Run:

```bash
xui-panel
```

Select:

```text
1
```

This displays:

- Backend status
- Nginx status
- Public panel port
- Admin login URL
- Reseller login URL
- X-UI URL
- X-UI authentication information

Sensitive passwords and API tokens are never displayed.

---

## Restart Panel

Run:

```bash
xui-panel
```

Select:

```text
2
```

Or manually:

```bash
systemctl restart xui-reseller-panel
```

---

## Live Backend Logs

Run:

```bash
xui-panel
```

Select:

```text
3
```

Or manually:

```bash
journalctl -u xui-reseller-panel -f
```

---

## Change Admin Username / Password

Run:

```bash
xui-panel
```

Select:

```text
4
```

You can update the administrator username and password.

The current password cannot be displayed because it is stored as a secure password hash.

---

## Change X-UI Connection Settings

Run:

```bash
xui-panel
```

Select:

```text
5
```

You can update:

- X-UI URL
- Authentication mode
- X-UI API Token
- X-UI username/password
- TLS verification

New settings are tested before replacing the currently working configuration.

If the connection test fails, the previous settings are restored.

---

## Change Public Panel Port

Run:

```bash
xui-panel
```

Select:

```text
6
```

The panel updates the Nginx configuration automatically.

---

# Backup

To create a backup of the local panel database:

```bash
xui-panel
```

Select:

```text
7
```

It is recommended to create backups before major updates or server changes.

---

# Rebuild Frontend

Run:

```bash
xui-panel
```

Select:

```text
8
```

This rebuilds the frontend and restarts the required services.

---

# Updating from GitHub

Because the repository is public, installed servers can update directly from GitHub without SSH keys or Deploy Keys.

Run:

```bash
xui-panel
```

Select:

```text
9
```

The updater pulls the latest version from:

```text
https://github.com/AMasoudKaveh/x-ui-reseller-panel
```

and rebuilds the frontend.

To check the currently installed Git revision:

```bash
cd /opt/xui-reseller-panel
git log --oneline -1
```

If needed, you can also update manually:

```bash
cd /opt/xui-reseller-panel
git pull origin main
npm ci
npm run build
systemctl restart xui-reseller-panel
nginx -t && systemctl reload nginx
```

---

# Uninstallation

Run:

```bash
xui-panel
```

Select:

```text
10
```

The uninstall process removes:

- X-UI Reseller Panel application
- Systemd service
- Related Nginx configuration

The main X-UI / 3X-UI installation is **not removed**.

---

# External Proxy Support

Administrators can configure external connection information for individual inbounds.

Supported fields include:

- External Host
- External Port
- Reality SID

When no external proxy configuration is defined, the original X-UI connection information is used.

This allows generated client configurations to use another public host, tunnel, or proxy endpoint while keeping X-UI as the backend source.

---

# Architecture

## Frontend

- React
- TypeScript
- Vite

## Backend

- FastAPI
- Python
- SQLite

## Production Runtime

- Nginx
- Uvicorn
- Systemd

X-UI remains the source of truth for:

- Inbounds
- VPN clients
- Client traffic
- Client status

The reseller panel stores its own reseller and management data separately.

---

# Project Structure

```text
x-ui-reseller-panel/
├── backend/
│   ├── main.py
│   ├── xui_client.py
│   ├── reseller_live_quota.py
│   ├── admin_cli.py
│   ├── requirements.txt
│   ├── .env.example
│   └── data/
│
├── src/
│   ├── components/
│   ├── pages/
│   └── shell/
│
├── install.sh
├── manage.sh
├── package.json
├── vite.config.ts
└── README.md
```

---

# Security

Sensitive runtime files must never be committed to GitHub.

The repository is configured to exclude files such as:

```text
backend/.env
backend/.venv/
backend/data/*.db
node_modules/
dist/
__pycache__/
```

Recommendations:

- Never publish your X-UI API Token
- Never publish X-UI credentials
- Never commit `backend/.env`
- Never commit production databases
- Never commit SSH private keys
- Keep regular backups
- Use a valid TLS certificate whenever possible
- Secure SSH access to your server
- Use appropriate firewall rules

---

# Troubleshooting

## Backend Status

```bash
systemctl status xui-reseller-panel
```

## Backend Logs

```bash
journalctl -u xui-reseller-panel -f
```

## Test Nginx Configuration

```bash
nginx -t
```

## Restart Nginx

```bash
systemctl restart nginx
```

## Check Installed Version

```bash
cd /opt/xui-reseller-panel
git log --oneline -1
```

---

# Support & Contact

If you find a bug or want to suggest a feature, opening a GitHub Issue is preferred so the discussion can help other users.

### GitHub

https://github.com/AMasoudKaveh/x-ui-reseller-panel

### Telegram

https://t.me/masoud_kve

---

# Disclaimer

This project is an independent management interface designed to work with X-UI / 3X-UI environments.

It is **not an official X-UI or 3X-UI project**.

Use it responsibly and review your server configuration before deploying it in production.

---

# Author

**Masoud Kaveh**

GitHub:  
https://github.com/AMasoudKaveh

Telegram:  
https://t.me/masoud_kve

---

If this project is useful to you, consider giving the repository a ⭐ on GitHub.
