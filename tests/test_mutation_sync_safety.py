import sqlite3
import unittest
from unittest.mock import patch

import backend.reseller_live_quota as quota


def _shared_db(name: str, rows: list[tuple[int, str]]):
    uri = f"file:{name}?mode=memory&cache=shared"
    anchor = sqlite3.connect(uri, uri=True)
    anchor.row_factory = sqlite3.Row
    anchor.execute("CREATE TABLE clients(id INTEGER PRIMARY KEY,email TEXT,status TEXT)")
    anchor.executemany(
        "INSERT INTO clients(id,email,status) VALUES(?,?,'active')",
        rows,
    )
    anchor.commit()

    def connect():
        con = sqlite3.connect(uri, uri=True)
        con.row_factory = sqlite3.Row
        return con

    return anchor, connect


class MutationSyncSafetyTests(unittest.TestCase):
    def test_verified_sync_survives_unrelated_quota_reconcile_failure(self):
        anchor, connect = _shared_db("mutation_reconcile", [(7, "alice")])
        state = {
            "email": "alice",
            "panel_used_bytes": 123,
            "panel_up_bytes": 20,
            "panel_down_bytes": 103,
            "total_limit_bytes": 1000,
            "expiry_ms": 0,
            "enabled": True,
            "panel": {},
        }
        try:
            with (
                patch.object(quota, "connect_db", connect),
                patch.object(quota, "ensure_live_schema", lambda: None),
                patch.object(quota, "XUIClient", lambda: object()),
                patch.object(quota, "_step7b_sqlite_snapshot", lambda _emails: ({"alice": state}, set(), [])),
                patch.object(quota, "sync_one_client", lambda *_args, **_kwargs: {"id": 7, "panel_ok": True}),
                patch.object(quota, "_reconcile_quotas_serialized", side_effect=RuntimeError("stale unrelated user")),
            ):
                result = quota.sync_client_for_mutation(7)
        finally:
            anchor.close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["quota"]["warning"], "quota_reconcile_failed")

    def test_case_insensitive_duplicate_is_never_charged_as_another_user(self):
        anchor, connect = _shared_db(
            "mutation_duplicate",
            [(7, "Test"), (8, "test")],
        )
        try:
            with (
                patch.object(quota, "connect_db", connect),
                patch.object(quota, "ensure_live_schema", lambda: None),
            ):
                result = quota.sync_client_for_mutation(7)
        finally:
            anchor.close()

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "duplicate_case_insensitive_username")
        self.assertEqual(result["conflicting_client_ids"], [7, 8])

