# X-UI Unified Admin / Reseller Panel

Production-oriented FastAPI + React control panel that uses the primary x-ui panel as the infrastructure source of truth.

## Fresh Ubuntu install

Recommended: Ubuntu 22.04/24.04 and root access.

```bash
git clone <YOUR_REPOSITORY_URL> /opt/xui-reseller-panel
cd /opt/xui-reseller-panel
sudo bash install.sh
```

The installer asks for:

- Public panel port (default `8088`)
- Full x-ui URL, including its web base path
- x-ui username and password
- TLS verification preference for the x-ui connection
- Initial admin username and password on a fresh database

Installation stops if the x-ui connection test fails. It then builds the frontend, creates a local Python venv, configures systemd and Nginx, and prints the admin/reseller URLs.

This release intentionally uses plain HTTP on the selected public port. Domain/TLS is not required.

## Management menu

After installation:

```bash
sudo xui-panel
```

Menu features:

1. Status and current panel links
2. Restart backend
3. Live backend logs
4. Show current admin username / change admin username or password
5. Change x-ui URL/username/password and test before saving
6. Change public panel port
7. Create safe SQLite backup
8. Rebuild frontend
9. Update from GitHub when installed from a git checkout
10. Completely uninstall the panel

Admin passwords are stored as PBKDF2 hashes and therefore cannot be displayed. They can be reset from the management menu or the Admin Settings web UI.

## Runtime files not committed to Git

- `backend/.env`
- `backend/.venv/`
- `backend/data/*` (except `.gitkeep`)
- `node_modules/`
- `dist/`

Use `backend/.env.example` only as a template.

## Services

Backend service:

```bash
systemctl status xui-reseller-panel
journalctl -u xui-reseller-panel -f
```

Nginx serves the built frontend and proxies `/api/` to `127.0.0.1:8000`.

## Representative deletion

Removing a representative now permanently removes the active representative and its local client rows after safely disabling eligible x-ui clients. Historical cumulative traffic is archived in local history tables, so global consumed traffic does not decrease simply because a representative was removed.
