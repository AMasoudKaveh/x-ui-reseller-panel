import sqlite3

from backend import reseller_live_quota as quota


def _make_xui_db(path):
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE client_traffics(
            id INTEGER PRIMARY KEY,
            inbound_id INTEGER,
            enable NUMERIC,
            email TEXT,
            up INTEGER,
            down INTEGER,
            expiry_time INTEGER,
            total INTEGER,
            last_online INTEGER
        )
        """
    )
    con.executemany(
        """
        INSERT INTO client_traffics(
            inbound_id, enable, email, up, down,
            expiry_time, total, last_online
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        [
            (1, 1, "alice", 100, 200, 5000, 1000, quota.now_ms()),
            (2, 1, "alice", 100, 200, 5000, 1000, quota.now_ms()),
            (3, 0, "bob", 10, 20, 6000, 2000, 0),
        ],
    )
    con.commit()
    con.close()


def test_sqlite_snapshot_is_read_only_and_does_not_duplicate_inbounds(tmp_path, monkeypatch):
    db_path = tmp_path / "x-ui.db"
    _make_xui_db(db_path)
    monkeypatch.setattr(quota, "_xui_db_path", lambda: str(db_path))

    snapshot, online, errors = quota._step7b_sqlite_snapshot(["alice", "bob"])

    assert errors == []
    assert snapshot["alice"]["panel_used_bytes"] == 300
    assert snapshot["alice"]["inbound_ids"] == [1, 2]
    assert snapshot["bob"]["panel_used_bytes"] == 30
    assert snapshot["bob"]["enabled"] is False
    assert "alice" in online


def test_sqlite_snapshot_rejects_unrelated_local_database(tmp_path, monkeypatch):
    db_path = tmp_path / "x-ui.db"
    _make_xui_db(db_path)
    monkeypatch.setattr(quota, "_xui_db_path", lambda: str(db_path))

    assert quota._step7b_sqlite_snapshot(["remote-a", "remote-b"]) is None
