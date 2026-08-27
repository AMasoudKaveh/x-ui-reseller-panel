[README.md](https://github.com/user-attachments/files/31534158/README.1.md)
# X-UI Reseller Panel

A modern web-based **Admin & Reseller Management Panel for X-UI / 3X-UI**.

X-UI Reseller Panel provides a separate management interface for administrators and resellers while using your existing X-UI server as the source of truth for inbounds, clients, traffic usage, and account status.

It is designed for server owners who want to give resellers controlled access to create and manage users without giving them direct access to the main X-UI panel.

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

The installer performs an X-UI connection test before completing the installation.

Your X-UI URL must include the full Web Base Path.

Example:

```text
https://example.com:2053/my-xui-path/
```

Do **not** manually add API paths such as:

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
- Git

The installer prepares the required runtime environment, including:

- Python virtual environment
- Backend dependencies
- Frontend dependencies
- Production frontend build
- Systemd service
- Nginx configuration

---

# Installation

## 1. Install Git

```bash
apt update
apt install -y git
```

## 2. Clone the Repository

```bash
cd /opt
git clone https://github.com/AMasoudKaveh/x-ui-reseller-panel.git
cd x-ui-reseller-panel
```

Make the installer and management scripts executable:

```bash
chmod +x install.sh manage.sh
```

## 3. Run the Installer

```bash
bash install.sh
```

The installer will guide you through the required configuration.

---

## Installation Options

### Public Panel Port

Choose the public port used to access the panel.

Example:

```text
8080
```

After installation, the panel will be available on that port.

### X-UI URL

Enter the complete URL of your X-UI panel, including its Web Base Path.

Example:

```text
https://example.com:2053/my-xui-path/
```

### X-UI Authentication

The installer supports:

#### API Token

Enter your X-UI API Token when prompted.

If you provide an API Token, username/password authentication is not required.

#### Username / Password

Leave the API Token field blank and the installer will ask for:

```text
X-UI username
X-UI password
```

### TLS Verification

If your X-UI domain uses a valid SSL/TLS certificate, enable TLS verification.

If your X-UI installation uses a self-signed or otherwise untrusted certificate, TLS verification may need to be disabled.

### Initial Administrator Account

On the first installation, the installer will ask you to create an administrator account.

You will be asked for:

```text
Initial admin username
Initial admin password
```

Administrator passwords are stored securely as password hashes and are never displayed in plaintext.

---

## X-UI Connection Test

Before installation continues, the installer performs an actual connection test against X-UI.

If the connection test fails, the installer stops so you can correct the X-UI URL, authentication details, or TLS settings.

---

# Accessing the Panel

After installation, use the public panel port you selected.

## Administrator Login

```text
http://SERVER-IP:PANEL-PORT/#/admin/login
```

Example:

```text
http://192.0.2.10:8080/#/admin/login
```

## Reseller Login

```text
http://SERVER-IP:PANEL-PORT/#/reseller/login
```

Example:

```text
http://192.0.2.10:8080/#/reseller/login
```

---

# Management Menu

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

## Show Status and Panel Links

Run:

```bash
xui-panel
```

Then select:

```text
1
```

This displays information such as:

- Backend service status
- Nginx status
- Public panel port
- Admin login URL
- Reseller login URL
- Current X-UI URL
- Current X-UI authentication mode

Sensitive passwords and API tokens are not displayed.

---

## Restart the Panel

Open the management menu:

```bash
xui-panel
```

Select:

```text
2
```

Or restart the backend manually:

```bash
systemctl restart xui-reseller-panel
```

---

## View Backend Logs

Open the management menu:

```bash
xui-panel
```

Select:

```text
3
```

Or use:

```bash
journalctl -u xui-reseller-panel -f
```

---

## Change Administrator Credentials

Run:

```bash
xui-panel
```

Select:

```text
4
```

You can change:

- Admin username
- Admin password

The current password cannot be displayed because it is stored as a secure hash.

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
- API Token
- Username / Password
- TLS verification

The new configuration is tested before replacing the existing working configuration.

If the connection test fails, the previous X-UI settings are restored.

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

Enter the new public port.

The Nginx configuration is updated automatically.

---

# Backup

The panel uses a local SQLite database for panel-specific management data.

To create a backup:

```bash
xui-panel
```

Select:

```text
7
```

It is strongly recommended to create a backup before major updates or server changes.

---

# Rebuild Frontend

If frontend files have changed, run:

```bash
xui-panel
```

Select:

```text
8
```

The frontend will be rebuilt and the required services restarted.

---

# Updating

To update an installed panel from GitHub:

```bash
xui-panel
```

Select:

```text
9
```

The updater retrieves the latest project version and rebuilds the frontend.

You can check the currently installed Git revision with:

```bash
cd /opt/xui-reseller-panel
git log --oneline -1
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

The uninstall process removes the reseller panel, its Systemd service, and its Nginx configuration.

The primary X-UI / 3X-UI installation is **not** removed.

The management script asks for confirmation before deleting the panel.

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

The reseller panel stores its own management and reseller-related information separately.

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

# Security Notes

Sensitive runtime files should never be committed to Git.

The repository is configured to exclude files such as:

```text
backend/.env
backend/.venv/
backend/data/*.db
node_modules/
dist/
__pycache__/
```

Important recommendations:

- Never publish your X-UI API Token
- Never publish X-UI credentials
- Never commit `backend/.env`
- Never commit production databases
- Never commit SSH private keys
- Keep regular backups
- Use a valid TLS certificate whenever possible
- Secure SSH access to your server
- Use firewall rules appropriate for your environment

---

# Troubleshooting

## Check Backend Status

```bash
systemctl status xui-reseller-panel
```

## Follow Backend Logs

```bash
journalctl -u xui-reseller-panel -f
```

## Check Nginx Configuration

```bash
nginx -t
```

## Restart Nginx

```bash
systemctl restart nginx
```

## Check Current Version

```bash
cd /opt/xui-reseller-panel
git log --oneline -1
```

---

# Support & Contact

If you find a bug or want to suggest a feature, opening a GitHub Issue is preferred so the discussion can help other users too.

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
