from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import main, reseller_profile


class DatabaseConnectionLifecycleTests(unittest.TestCase):
    @staticmethod
    def assert_closed(connection: sqlite3.Connection) -> None:
        with unittest.TestCase().assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_main_database_context_closes_connection(self) -> None:
        with patch.object(main, "DB_PATH", Path(":memory:")):
            with main.db() as connection:
                self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
            self.assert_closed(connection)

    def test_shared_database_context_closes_connection(self) -> None:
        with patch.object(reseller_profile, "DB_PATH", Path(":memory:")):
            with reseller_profile.connect_db() as connection:
                self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
            self.assert_closed(connection)


if __name__ == "__main__":
    unittest.main()
