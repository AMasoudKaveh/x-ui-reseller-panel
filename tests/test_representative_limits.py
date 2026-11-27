import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi import HTTPException

from backend import reseller_profile
from backend.representative_limits import client_count, creation_slot, expired


class RepresentativeLimitsTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(reseller_profile, "DB_PATH", Path(tmp) / "auth.db"))
        with reseller_profile.connect_db() as con:
            con.executescript("""
                CREATE TABLE representatives(
                    id INTEGER PRIMARY KEY, parent_rep_id INTEGER,
                    client_limit INTEGER, rep_expires_at INTEGER
                );
                CREATE TABLE clients(id INTEGER PRIMARY KEY, seller_rep_id INTEGER, status TEXT);
                INSERT INTO representatives VALUES (1,NULL,2,0), (2,1,0,0), (3,NULL,0,0);
                INSERT INTO clients VALUES (11,1,'active'), (12,2,'disabled'), (13,3,'active');
            """)

    def test_limit_counts_disabled_clients_and_descendants(self):
        with self.assertRaises(HTTPException) as error:
            with creation_slot(2):
                self.fail("An exhausted parent must block creation")
        self.assertEqual(error.exception.status_code, 409)
        with creation_slot(3):
            pass

    def test_deleted_user_frees_slot_and_limit_can_be_raised(self):
        with reseller_profile.connect_db() as con:
            con.execute("DELETE FROM clients WHERE id=12")
            con.commit()
            self.assertEqual(client_count(con, 1), 1)
        with creation_slot(1):
            with reseller_profile.connect_db() as con:
                con.execute("INSERT INTO clients VALUES (14,1,'active')")
                con.execute("UPDATE representatives SET client_limit=3 WHERE id=1")
                con.commit()
        with creation_slot(2):
            pass

    def test_parent_expiry_is_inherited(self):
        with reseller_profile.connect_db() as con:
            con.execute("UPDATE representatives SET rep_expires_at=1 WHERE id=1")
            con.commit()
            self.assertTrue(expired(con, 2))
            self.assertFalse(expired(con, 3))

    def test_two_creators_cannot_take_the_same_last_slot(self):
        with reseller_profile.connect_db() as con:
            con.execute("DELETE FROM clients WHERE id=12")
            con.commit()
        entered = Event()

        def create():
            entered.set()
            try:
                with creation_slot(2):
                    return 200
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor() as executor:
            with creation_slot(1):
                second = executor.submit(create)
                self.assertTrue(entered.wait(2))
                with reseller_profile.connect_db() as con:
                    con.execute("INSERT INTO clients VALUES (14,1,'active')")
                    con.commit()
            self.assertEqual(second.result(timeout=5), 409)
