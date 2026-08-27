from __future__ import annotations

import argparse
import hashlib
import secrets
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "auth.db"
PBKDF2_ROUNDS = 200_000


def db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")
    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ROUNDS,
    ).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def current_admin() -> sqlite3.Row:
    with db() as con:
        row = con.execute(
            "SELECT id,username,is_active,created_at FROM admins ORDER BY id LIMIT 1"
        ).fetchone()
    if not row:
        raise SystemExit("No admin account exists yet")
    return row


def cmd_show(_: argparse.Namespace) -> None:
    row = current_admin()
    print(f"username={row['username']}")
    print(f"active={1 if int(row['is_active'] or 0) else 0}")
    print("password=stored-securely-as-hash")


def cmd_update(args: argparse.Namespace) -> None:
    row = current_admin()
    username = (args.username or str(row["username"])).strip()
    if not username or len(username) > 64:
        raise SystemExit("Username must be 1-64 characters")

    password = args.password or ""
    if password and len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")

    with db() as con:
        duplicate = con.execute(
            "SELECT id FROM admins WHERE username=? AND id<>?",
            (username, int(row["id"])),
        ).fetchone()
        if duplicate:
            raise SystemExit("Another admin already uses that username")

        if password:
            con.execute(
                "UPDATE admins SET username=?,password_hash=? WHERE id=?",
                (username, hash_password(password), int(row["id"])),
            )
        else:
            con.execute(
                "UPDATE admins SET username=? WHERE id=?",
                (username, int(row["id"])),
            )

        con.execute("DELETE FROM auth_sessions WHERE role='admin'")
        con.commit()

    print(f"Admin updated: {username}")
    if password:
        print("Password changed. Existing admin sessions were logged out.")
    else:
        print("Username changed. Existing admin sessions were logged out.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local admin account management")
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show")
    show.set_defaults(func=cmd_show)

    update = sub.add_parser("update")
    update.add_argument("--username", default="")
    update.add_argument("--password", default="")
    update.set_defaults(func=cmd_update)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
