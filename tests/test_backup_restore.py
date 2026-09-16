from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import backup_service
from backend import reseller_profile
from backend import xui_client


class BackupRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "auth.db"
        self.env_path = self.root / ".env"
        self.env_path.write_text(
            "XUI_BASE_URL=https://old.example/panel\n"
            "XUI_API_TOKEN=old-token\n"
            "XUI_USERNAME=\nXUI_PASSWORD=\nXUI_VERIFY_TLS=true\n",
            encoding="utf-8",
        )
        con = sqlite3.connect(self.db_path)
        con.executescript(
            """
            CREATE TABLE admins(id INTEGER PRIMARY KEY,username TEXT UNIQUE,password_hash TEXT,is_active INTEGER,created_at INTEGER);
            CREATE TABLE representatives(id INTEGER PRIMARY KEY,username TEXT UNIQUE,password_hash TEXT,status TEXT,created_at INTEGER);
            CREATE TABLE auth_sessions(token TEXT PRIMARY KEY,role TEXT,account_id INTEGER,expires_at INTEGER,created_at INTEGER);
            CREATE TABLE admin_settings(key TEXT PRIMARY KEY,value TEXT,updated_at TEXT);
            INSERT INTO admins VALUES(1,'admin','hash',1,1);
            INSERT INTO representatives VALUES(7,'original','hash','active',1);
            INSERT INTO auth_sessions VALUES('session','admin',1,4102444800,1);
            INSERT INTO admin_settings VALUES('site_title','original','now');
            """
        )
        con.commit()
        con.close()
        self.old_db = reseller_profile.DB_PATH
        self.old_env = xui_client.ENV_PATH
        self.old_backup_env = backup_service.ENV_PATH
        self.old_safety = backup_service.SAFETY_DIR
        self.old_staging = backup_service.STAGING_DIR
        reseller_profile.DB_PATH = self.db_path
        xui_client.ENV_PATH = self.env_path
        backup_service.ENV_PATH = self.env_path
        backup_service.SAFETY_DIR = self.root / "safety"
        backup_service.STAGING_DIR = self.root / "staging"

    def tearDown(self) -> None:
        reseller_profile.DB_PATH = self.old_db
        xui_client.ENV_PATH = self.old_env
        backup_service.ENV_PATH = self.old_backup_env
        backup_service.SAFETY_DIR = self.old_safety
        backup_service.STAGING_DIR = self.old_staging
        self.temp.cleanup()

    def test_package_contains_database_manifest_and_connection(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            package = backup_service.create_backup_package()
        upload = self.root / "backup.xuibak"
        upload.write_bytes(package)
        preview = backup_service.stage_backup(upload, admin_id=1)
        self.assertFalse(preview["legacy"])
        self.assertTrue(preview["has_backup_connection"])
        self.assertEqual(preview["backup_xui_url"], "https://old.example/panel")
        self.assertEqual(preview["row_counts"]["representatives"], 1)

    def test_restore_round_trip_and_connection_choice(self) -> None:
        package = backup_service.create_backup_package()
        con = sqlite3.connect(self.db_path)
        con.execute("UPDATE representatives SET username='mutated' WHERE id=7")
        con.execute("UPDATE admin_settings SET value='mutated' WHERE key='site_title'")
        con.commit()
        con.close()
        self.env_path.write_text("XUI_BASE_URL=https://current.example\nXUI_API_TOKEN=current-token\n", encoding="utf-8")
        upload = self.root / "backup.xuibak"
        upload.write_bytes(package)
        preview = backup_service.stage_backup(upload, admin_id=1)
        with patch.object(
            backup_service,
            "validate_connection",
            side_effect=lambda value: {"connection": value, "inbounds": 3},
        ):
            result = backup_service.apply_restore(
                token=preview["restore_token"], admin_id=1, connection_mode="backup"
            )
        self.assertTrue(result["ok"])
        con = sqlite3.connect(self.db_path)
        self.assertEqual(con.execute("SELECT username FROM representatives WHERE id=7").fetchone()[0], "original")
        self.assertEqual(con.execute("SELECT value FROM admin_settings WHERE key='site_title'").fetchone()[0], "original")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0], 0)
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        con.close()
        restored_env = xui_client.read_env_file()
        self.assertEqual(restored_env["XUI_BASE_URL"], "https://old.example/panel")
        self.assertEqual(restored_env["XUI_API_TOKEN"], "old-token")
        self.assertTrue(list((self.root / "safety").glob("before-restore-*.sqlite3")))

    def test_corrupt_package_is_rejected(self) -> None:
        upload = self.root / "bad.xuibak"
        upload.write_bytes(b"not a backup")
        with self.assertRaises(ValueError):
            backup_service.stage_backup(upload, admin_id=1)

    def test_failed_restore_rolls_back_database_and_environment(self) -> None:
        package = backup_service.create_backup_package()
        con = sqlite3.connect(self.db_path)
        con.execute("UPDATE representatives SET username='pre-restore-current' WHERE id=7")
        con.commit()
        con.close()
        self.env_path.write_text("XUI_BASE_URL=https://current.example\nXUI_API_TOKEN=current-token\n", encoding="utf-8")
        upload = self.root / "rollback.xuibak"
        upload.write_bytes(package)
        preview = backup_service.stage_backup(upload, admin_id=1)
        with patch.object(
            backup_service,
            "validate_connection",
            side_effect=lambda value: {"connection": value, "inbounds": 1},
        ), patch.object(backup_service, "_post_restore_check", side_effect=RuntimeError("forced check failure")):
            with self.assertRaises(RuntimeError):
                backup_service.apply_restore(
                    token=preview["restore_token"], admin_id=1, connection_mode="backup"
                )
        con = sqlite3.connect(self.db_path)
        self.assertEqual(
            con.execute("SELECT username FROM representatives WHERE id=7").fetchone()[0],
            "pre-restore-current",
        )
        con.close()
        restored_env = xui_client.read_env_file()
        self.assertEqual(restored_env["XUI_BASE_URL"], "https://current.example")
        self.assertEqual(restored_env["XUI_API_TOKEN"], "current-token")


if __name__ == "__main__":
    unittest.main()
