from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path


def scalar(con: sqlite3.Connection, sql: str) -> int:
    row = con.execute(sql).fetchone()
    return int((row or (0,))[0] or 0)


def compact(db_path: Path, *, vacuum: bool) -> None:
    started = time.monotonic()
    con = sqlite3.connect(db_path, timeout=120)
    try:
        con.execute("PRAGMA busy_timeout=120000")
        con.execute(
            """CREATE TABLE IF NOT EXISTS traffic_daily(
                event_day TEXT NOT NULL,
                owner_rep_id INTEGER NOT NULL DEFAULT 0,
                seller_rep_id INTEGER NOT NULL DEFAULT 0,
                delta_bytes INTEGER NOT NULL DEFAULT 0,
                event_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(event_day, owner_rep_id, seller_rep_id)
            )"""
        )
        con.execute(
            """CREATE INDEX IF NOT EXISTS idx_traffic_daily_seller_day
               ON traffic_daily(seller_rep_id, event_day)"""
        )

        old_daily_sum = scalar(con, "SELECT COALESCE(SUM(delta_bytes),0) FROM traffic_daily")
        event_sum = scalar(
            con,
            "SELECT COALESCE(SUM(CASE WHEN delta_bytes>0 THEN delta_bytes ELSE 0 END),0) FROM traffic_events",
        )
        event_count = scalar(con, "SELECT COUNT(*) FROM traffic_events")
        expected = old_daily_sum + event_sum

        con.execute("BEGIN IMMEDIATE")
        con.execute(
            """INSERT INTO traffic_daily(
                   event_day, owner_rep_id, seller_rep_id,
                   delta_bytes, event_count
               )
               SELECT substr(created_at,1,10),
                      COALESCE(owner_rep_id,0),
                      COALESCE(seller_rep_id,0),
                      COALESCE(SUM(CASE WHEN delta_bytes>0 THEN delta_bytes ELSE 0 END),0),
                      COUNT(*)
               FROM traffic_events
               WHERE length(created_at)>=10
               GROUP BY substr(created_at,1,10),
                        COALESCE(owner_rep_id,0),
                        COALESCE(seller_rep_id,0)
               ON CONFLICT(event_day, owner_rep_id, seller_rep_id)
               DO UPDATE SET
                   delta_bytes=traffic_daily.delta_bytes+excluded.delta_bytes,
                   event_count=traffic_daily.event_count+excluded.event_count"""
        )
        actual = scalar(con, "SELECT COALESCE(SUM(delta_bytes),0) FROM traffic_daily")
        if actual != expected:
            con.rollback()
            raise RuntimeError(
                f"traffic total mismatch: expected {expected}, got {actual}; nothing was deleted"
            )
        con.execute("DELETE FROM traffic_events")
        con.commit()

        remaining = scalar(con, "SELECT COUNT(*) FROM traffic_events")
        if remaining != 0:
            raise RuntimeError(f"raw event cleanup incomplete: {remaining} rows remain")
        if vacuum:
            con.execute("VACUUM")
        con.execute("PRAGMA optimize")
        print(
            "traffic history compacted safely:",
            f"raw_rows={event_count}",
            f"preserved_delta_bytes={actual}",
            f"daily_rows={scalar(con, 'SELECT COUNT(*) FROM traffic_daily')}",
            f"seconds={time.monotonic() - started:.2f}",
        )
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate raw traffic history without changing cumulative quota ledgers."
    )
    parser.add_argument("database", type=Path)
    parser.add_argument("--vacuum", action="store_true")
    args = parser.parse_args()
    compact(args.database.resolve(), vacuum=args.vacuum)


if __name__ == "__main__":
    main()
