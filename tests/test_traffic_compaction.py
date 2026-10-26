from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import backend.reseller_live_quota as quota
from backend.backup_service import _compact_portable_history
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


if __name__ == "__main__":
    unittest.main()
