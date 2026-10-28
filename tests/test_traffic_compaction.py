from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import backend.reseller_live_quota as quota
from backend.backup_service import _compact_portable_history
from backend.xui_client import XUIClient
from scripts.compact_traffic_history import compact


def seed(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE traffic_ledger(
                client_id INTEGER PRIMARY KEY,
                cumulative_used_bytes INTEGER NOT NULL
            );
            CREATE TABLE traffic_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                client_id INTEGER,
                email TEXT,
                owner_rep_id INTEGER,
                seller_rep_id INTEGER,
                prev_panel_total INTEGER NOT NULL DEFAULT 0,
                current_panel_total INTEGER NOT NULL DEFAULT 0,
                delta_bytes INTEGER NOT NULL DEFAULT 0,
                cumulative_after INTEGER NOT NULL DEFAULT 0,
                event_type TEXT NOT NULL DEFAULT 'normal_delta'
            );
            INSERT INTO traffic_ledger VALUES(1, 600);
            INSERT INTO traffic_events(created_at,client_id,owner_rep_id,seller_rep_id,delta_bytes)
            VALUES
              ('2026-10-26T10:00:00',1,1,2,100),
              ('2026-10-26T10:00:10',1,1,2,200),
              ('2026-10-27T10:00:00',1,1,2,300);
            """
        )


class TrafficCompactionTests(unittest.TestCase):
    def test_migration_preserves_delta_and_never_changes_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "auth.db"
            seed(path)
            compact(path, vacuum=False)
            with sqlite3.connect(path) as con:
                self.assertEqual(con.execute("SELECT cumulative_used_bytes FROM traffic_ledger").fetchone()[0], 600)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM traffic_events").fetchone()[0], 0)
                self.assertEqual(con.execute("SELECT SUM(delta_bytes) FROM traffic_daily").fetchone()[0], 600)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM traffic_daily").fetchone()[0], 2)

    def test_portable_backup_compacts_raw_history(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.db"
            seed(path)
            _compact_portable_history(path)
            with sqlite3.connect(path) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM traffic_events").fetchone()[0], 0)
                self.assertEqual(con.execute("SELECT SUM(delta_bytes) FROM traffic_daily").fetchone()[0], 600)
                self.assertEqual(con.execute("SELECT cumulative_used_bytes FROM traffic_ledger").fetchone()[0], 600)

    def test_missing_bulk_client_does_not_make_per_client_request(self) -> None:
        class NoRequestClient:
            def request(self, *_args, **_kwargs):
                raise AssertionError("per-client request must not be made")

        quota._STEP7B_PANEL_SNAPSHOT = {}
        result = quota.panel_client_state(
            NoRequestClient(),
            {
                "email": "deleted-user",
                "enabled": 1,
                "panel_used_bytes": 123,
                "total_limit_bytes": 1000,
                "expire_at_ms": 456,
            },
            set(),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["panel_used_bytes"], 123)
        self.assertFalse(result["online"])

    def test_direct_client_state_uses_authoritative_used_traffic(self) -> None:
        class OneClient:
            def get_client(self, email):
                return {
                    "success": True,
                    "obj": {
                        "usedTraffic": 987654,
                        "client": {
                            "email": email,
                            "enable": True,
                            "totalGB": 5_000_000,
                            "expiryTime": 123456789,
                        },
                    },
                }

        result = quota._direct_client_state(
            OneClient(),
            {
                "email": "one-user",
                "enabled": 1,
                "total_limit_bytes": 1,
                "expire_at_ms": 2,
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["panel_used_bytes"], 987654)
        self.assertEqual(result["total_limit_bytes"], 5_000_000)
        self.assertEqual(result["expiry_ms"], 123456789)

    def test_modern_create_does_not_send_redundant_attach(self) -> None:
        client = object.__new__(XUIClient)
        client.default_inbound_ids = []
        client.request = lambda *_args, **_kwargs: {"success": True}
        client.get_client = lambda email: {
            "success": True,
            "obj": {
                "client": {"email": email},
                "inboundIds": [1, 2],
            },
        }
        client.attach = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("modern create must not attach twice")
        )

        result = client.add_client(
            email="new-user",
            total_bytes=1000,
            limit_ip=0,
            expiry_ms=0,
            comment="",
            group_name="test",
            inbound_ids=[1, 2],
            enabled=True,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["attach"]["skipped"])


if __name__ == "__main__":
    unittest.main()
