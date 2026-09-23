from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend import admin_settings, reseller_profile, subscription_proxy, subscription_proxy_config
from backend.reseller_user_actions import subscription_url


class SubscriptionBrandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "auth.db"
        self.old_db = reseller_profile.DB_PATH
        self.old_nginx_path = subscription_proxy_config.NGINX_CONFIG_PATH
        reseller_profile.DB_PATH = self.db_path
        with sqlite3.connect(self.db_path) as con:
            con.executescript(
                """
                CREATE TABLE representatives(
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    status TEXT,
                    created_at INTEGER
                );
                CREATE TABLE clients(
                    id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL,
                    sub_id TEXT,
                    seller_rep_id INTEGER,
                    status TEXT DEFAULT 'active'
                );
                INSERT INTO representatives VALUES(1,'alpha','hash','active',1);
                INSERT INTO representatives VALUES(2,'space','hash','active',1);
                INSERT INTO clients VALUES(10,'a@example.test','subAlpha',1,'active');
                INSERT INTO clients VALUES(20,'b@example.test','subSpace',2,'active');
                """
            )

    def tearDown(self) -> None:
        reseller_profile.DB_PATH = self.old_db
        subscription_proxy_config.NGINX_CONFIG_PATH = self.old_nginx_path
        self.temp.cleanup()

    def test_backward_compatible_migration_adds_empty_brand(self) -> None:
        reseller_profile.ensure_profile_schema()
        with sqlite3.connect(self.db_path) as con:
            columns = {row[1] for row in con.execute("PRAGMA table_info(representatives)")}
            brands = [row[0] for row in con.execute("SELECT subscription_brand FROM representatives ORDER BY id")]
        self.assertIn("subscription_brand", columns)
        self.assertEqual(brands, ["", ""])

    def test_owner_mapping_keeps_representative_brands_separate(self) -> None:
        reseller_profile.ensure_profile_schema()
        with sqlite3.connect(self.db_path) as con:
            con.execute("UPDATE representatives SET subscription_brand='Alpha VPN' WHERE id=1")
            con.execute("UPDATE representatives SET subscription_brand='Space VPN' WHERE id=2")
            con.commit()
        self.assertEqual(subscription_proxy._client_owner("subAlpha")["subscription_brand"], "Alpha VPN")
        self.assertEqual(subscription_proxy._client_owner("subSpace")["subscription_brand"], "Space VPN")

    def test_profile_headers_are_preserved_and_only_title_is_overridden(self) -> None:
        upstream = SimpleNamespace(
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Subscription-Userinfo": "upload=1; download=2; total=3; expire=4",
                "Profile-Update-Interval": "12",
                "Profile-Title": "Gohari",
            }
        )
        headers = subscription_proxy._response_headers(upstream, "Alpha VPN")
        self.assertEqual(headers["Subscription-Userinfo"], upstream.headers["Subscription-Userinfo"])
        self.assertEqual(headers["Profile-Update-Interval"], "12")
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(headers["Profile-Title"], "base64:QWxwaGEgVlBO")
        self.assertEqual(headers["X-Reseller-Subscription-Proxy"], "1")

    def test_empty_brand_keeps_original_profile_title(self) -> None:
        upstream = SimpleNamespace(headers={"Profile-Title": "Gohari", "Content-Type": "text/plain"})
        headers = subscription_proxy._response_headers(upstream, "")
        self.assertEqual(headers["Profile-Title"], "Gohari")
        self.assertEqual(headers["X-Reseller-Subscription-Proxy"], "1")

    def test_xui_key_value_settings_shape_is_detected(self) -> None:
        settings = [
            {"key": "subPort", "value": "2096"},
            {"key": "subCertFile", "value": "/etc/ssl/fullchain.pem"},
            {"key": "subKeyFile", "value": "/etc/ssl/privkey.pem"},
        ]
        self.assertEqual(admin_settings._find_int_by_keys(settings, {"subport"}), 2096)
        self.assertEqual(
            admin_settings._find_text_by_keys(settings, {"subcertfile"}),
            "/etc/ssl/fullchain.pem",
        )

    def test_crlf_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            reseller_profile.normalize_subscription_brand("Alpha\r\nInjected: value")
        self.assertEqual(caught.exception.status_code, 400)

    def test_admin_public_subscription_proxy_is_the_canonical_link(self) -> None:
        with patch(
            "backend.admin_settings.public_subscription_override",
            return_value="https://pro.gsmbax.net:2096/sub/subAlpha",
        ):
            result = subscription_url([], "subAlpha", "http://91.107.253.206/")
        self.assertEqual(result, "https://pro.gsmbax.net:2096/sub/subAlpha")

    def test_both_subscription_proxy_routes_are_registered(self) -> None:
        paths = {route.path for route in subscription_proxy.router.routes}
        self.assertIn("/api/subscriptions/{sub_id}", paths)
        self.assertIn("/sub/{sub_id}", paths)

    def test_public_proxy_has_no_default_port(self) -> None:
        with patch.object(admin_settings, "_get_setting", side_effect=lambda key, default="": {
            "subscription_proxy_host": "sub.example.com",
            "subscription_proxy_port": "0",
        }.get(key, default)):
            self.assertEqual(admin_settings.public_subscription_override("subAlpha"), "")

    def test_nginx_listener_uses_the_admin_selected_port(self) -> None:
        certificate = self.root / "fullchain.pem"
        private_key = self.root / "privkey.pem"
        certificate.write_text("certificate", encoding="utf-8")
        private_key.write_text("private-key", encoding="utf-8")
        rendered = subscription_proxy_config.render_nginx_config(
            "sub.example.com", 18443, str(certificate), str(private_key)
        )
        self.assertIn("listen 18443 ssl;", rendered)
        self.assertIn("server_name sub.example.com;", rendered)
        self.assertIn("location /sub/", rendered)


if __name__ == "__main__":
    unittest.main()
