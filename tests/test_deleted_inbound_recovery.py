import json
import sqlite3
import unittest
from unittest.mock import patch

import backend.reseller_create_user as create_user


class DeletedInboundRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE representatives(
              id INTEGER PRIMARY KEY,
              allowed_inbound_ids TEXT
            );
            INSERT INTO representatives(id, allowed_inbound_ids)
            VALUES(14, '[1, 2, 3, 10]');
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_deleted_inbounds_are_filtered_and_persistently_pruned(self):
        with patch.object(create_user, "connect_db", return_value=self.connection):
            allowed = create_user.allowed_inbound_ids(14, [1, 10, 11])

        self.assertEqual(allowed, [1, 10])
        row = self.connection.execute(
            "SELECT allowed_inbound_ids FROM representatives WHERE id=14"
        ).fetchone()
        self.assertEqual(json.loads(row["allowed_inbound_ids"]), [1, 10])

    def test_empty_assignment_keeps_all_live_inbounds_behavior(self):
        self.connection.execute(
            "UPDATE representatives SET allowed_inbound_ids='' WHERE id=14"
        )
        with patch.object(create_user, "connect_db", return_value=self.connection):
            allowed = create_user.allowed_inbound_ids(14, [1, 10, 11])

        self.assertEqual(allowed, [1, 10, 11])


if __name__ == "__main__":
    unittest.main()
