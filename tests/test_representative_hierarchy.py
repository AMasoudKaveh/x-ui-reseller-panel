import sqlite3
import unittest
from unittest.mock import patch

import backend.reseller_live_quota as quota_module
from backend.reseller_live_quota import representative_usage_tree


class RepresentativeHierarchyUsageTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript(
            """
            CREATE TABLE representatives(id INTEGER PRIMARY KEY,parent_rep_id INTEGER,deleted_at TEXT);
            CREATE TABLE clients(id INTEGER PRIMARY KEY,seller_rep_id INTEGER,status TEXT);
            CREATE TABLE traffic_ledger(client_id INTEGER PRIMARY KEY,cumulative_used_bytes INTEGER);
            CREATE TABLE deleted_client_usage_v2(
              id INTEGER PRIMARY KEY,email TEXT,seller_rep_id INTEGER,cumulative_used_bytes INTEGER
            );
            INSERT INTO representatives(id,parent_rep_id) VALUES(1,NULL),(2,1),(3,2);
            INSERT INTO clients(id,seller_rep_id,status) VALUES(11,1,'active'),(12,2,'active'),(13,3,'active');
            INSERT INTO traffic_ledger VALUES(11,10),(12,20),(13,30);
            """
        )

    def tearDown(self):
        self.con.close()

    def test_usage_is_recorded_once_and_rolled_up_to_every_ancestor(self):
        direct, subtree, descendants = representative_usage_tree(self.con)
        self.assertEqual(direct, {1: 10, 2: 20, 3: 30})
        self.assertEqual(subtree, {1: 60, 2: 50, 3: 30})
        self.assertEqual(descendants[1], [2, 3])

    def test_deleted_lifecycle_remains_in_direct_and_parent_usage(self):
        self.con.execute(
            "INSERT INTO deleted_client_usage_v2(email,seller_rep_id,cumulative_used_bytes) VALUES('old',3,7)"
        )
        direct, subtree, _ = representative_usage_tree(self.con)
        self.assertEqual(direct[3], 37)
        self.assertEqual(subtree[2], 57)
        self.assertEqual(subtree[1], 67)

    def test_sibling_usage_does_not_leak_between_branches(self):
        self.con.execute("INSERT INTO representatives(id,parent_rep_id) VALUES(4,1)")
        self.con.execute("INSERT INTO clients(id,seller_rep_id,status) VALUES(14,4,'active')")
        self.con.execute("INSERT INTO traffic_ledger VALUES(14,9)")
        _, subtree, _ = representative_usage_tree(self.con)
        self.assertEqual(subtree[2], 50)
        self.assertEqual(subtree[4], 9)
        self.assertEqual(subtree[1], 69)

    def test_deleted_sub_representative_usage_still_rolls_up(self):
        self.con.execute("UPDATE representatives SET deleted_at='2026-01-01' WHERE id=3")
        self.con.execute("DELETE FROM clients WHERE seller_rep_id=3")
        self.con.execute("INSERT INTO deleted_client_usage_v2(email,seller_rep_id,cumulative_used_bytes) VALUES('deleted-z',3,30)")
        _, subtree, _ = representative_usage_tree(self.con)
        self.assertEqual(subtree[2], 50)
        self.assertEqual(subtree[1], 60)

    def test_quota_lock_cascades_down_but_never_up(self):
        uri = "file:hierarchy_quota_test?mode=memory&cache=shared"
        anchor = sqlite3.connect(uri, uri=True)
        try:

            def connect():
                con = sqlite3.connect(uri, uri=True)
                con.row_factory = sqlite3.Row
                return con

            with connect() as con:
                con.executescript(
                    """
                    CREATE TABLE representatives(
                      id INTEGER PRIMARY KEY,parent_rep_id INTEGER,deleted_at TEXT,
                      status TEXT,quota_bytes INTEGER,used_bytes INTEGER DEFAULT 0,
                      direct_used_bytes INTEGER DEFAULT 0,descendant_used_bytes INTEGER DEFAULT 0,
                      usage_baseline_bytes INTEGER DEFAULT 0,quota_locked INTEGER DEFAULT 0,
                      quota_locked_at TEXT,quota_prev_status TEXT,quota_last_reconciled_at TEXT,
                      ancestor_locked INTEGER DEFAULT 0,ancestor_locked_by INTEGER,updated_at TEXT);
                    CREATE TABLE clients(id INTEGER PRIMARY KEY,seller_rep_id INTEGER,status TEXT,
                      rep_quota_hold INTEGER DEFAULT 0);
                    CREATE TABLE traffic_ledger(client_id INTEGER PRIMARY KEY,cumulative_used_bytes INTEGER);
                    CREATE TABLE deleted_client_usage_v2(
                      id INTEGER PRIMARY KEY,email TEXT,seller_rep_id INTEGER,cumulative_used_bytes INTEGER);
                    CREATE TABLE auth_sessions(token TEXT,role TEXT,account_id INTEGER);
                    INSERT INTO representatives(id,parent_rep_id,status,quota_bytes) VALUES
                      (1,NULL,'active',100),(2,1,'active',50),(3,2,'active',500);
                    INSERT INTO deleted_client_usage_v2(email,seller_rep_id,cumulative_used_bytes)
                      VALUES('usage-y',2,50);
                    """
                )

            with patch.object(quota_module, "connect_db", connect), patch.object(quota_module, "ensure_live_schema", lambda: None):
                quota_module.reconcile_quotas(object())

            with connect() as con:
                x = dict(con.execute("SELECT * FROM representatives WHERE id=1").fetchone())
                y = dict(con.execute("SELECT * FROM representatives WHERE id=2").fetchone())
                z = dict(con.execute("SELECT * FROM representatives WHERE id=3").fetchone())
            self.assertEqual(x["used_bytes"], 50)
            self.assertEqual(x["quota_locked"], 0)
            self.assertEqual(y["quota_locked"], 1)
            self.assertEqual(z["ancestor_locked"], 1)
            self.assertEqual(z["ancestor_locked_by"], 2)

            with connect() as con:
                con.execute("UPDATE representatives SET quota_bytes=100,usage_baseline_bytes=50 WHERE id=2")
                con.execute("INSERT INTO deleted_client_usage_v2(email,seller_rep_id,cumulative_used_bytes) VALUES('new-y',2,10)")
                con.commit()
            with patch.object(quota_module, "connect_db", connect), patch.object(quota_module, "ensure_live_schema", lambda: None):
                quota_module.reconcile_quotas(object())
            with connect() as con:
                x = dict(con.execute("SELECT * FROM representatives WHERE id=1").fetchone())
                y = dict(con.execute("SELECT * FROM representatives WHERE id=2").fetchone())
                z = dict(con.execute("SELECT * FROM representatives WHERE id=3").fetchone())
            self.assertEqual(x["used_bytes"], 60)  # Parent never loses Y's pre-reset 50.
            self.assertEqual(y["used_bytes"], 10)  # Y starts a new quota period.
            self.assertEqual(y["quota_locked"], 0)
            self.assertEqual(z["ancestor_locked"], 0)
        finally:
            anchor.close()


if __name__ == "__main__":
    unittest.main()
