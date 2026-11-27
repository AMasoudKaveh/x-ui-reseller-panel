"""Account validity and user-count enforcement for representative trees."""

from contextlib import contextmanager
import os
import time

from fastapi import HTTPException

from backend import reseller_profile


def lineage(con, rep_id):
    return con.execute(
        """WITH RECURSIVE parents(id, parent_rep_id, client_limit, rep_expires_at) AS (
               SELECT id, parent_rep_id, client_limit, rep_expires_at
               FROM representatives WHERE id=?
               UNION
               SELECT r.id, r.parent_rep_id, r.client_limit, r.rep_expires_at
               FROM representatives r JOIN parents p ON r.id=p.parent_rep_id
           ) SELECT * FROM parents""",
        (rep_id,),
    ).fetchall()


def expired(con, rep_id):
    now = int(time.time())
    return any(0 < row["rep_expires_at"] <= now for row in lineage(con, rep_id))


def client_count(con, rep_id):
    return int(con.execute(
        """WITH RECURSIVE tree(id) AS (
               SELECT ?
               UNION
               SELECT r.id FROM representatives r JOIN tree ON r.parent_rep_id=tree.id
           )
           SELECT count(*) FROM clients c JOIN tree ON c.seller_rep_id=tree.id
           WHERE COALESCE(c.status,'')!='deleted'""",
        (rep_id,),
    ).fetchone()[0])


@contextmanager
def creation_slot(rep_id):
    # Lock the tree until the X-UI create and the matching local insert finish.
    # The OS releases the lock if the worker exits.
    with reseller_profile.connect_db() as con:
        parents = lineage(con, rep_id)
    if not any(row["client_limit"] for row in parents):
        yield
        return
    root_id = next((r["id"] for r in parents if not r["parent_rep_id"]), rep_id)
    lock_path = reseller_profile.DB_PATH.with_name(f".rep-create-{root_id}.lock")
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            def acquire():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        timeout = time.monotonic() + 15
        while True:
            try:
                acquire()
                break
            except OSError:
                if time.monotonic() >= timeout:
                    raise HTTPException(503, "Another user creation is in progress. Try again shortly.")
                time.sleep(0.05)
        with reseller_profile.connect_db() as con:
            if expired(con, rep_id):
                raise HTTPException(403, "Representative account has expired")
            for rep in lineage(con, rep_id):
                limit = rep["client_limit"]
                if limit and client_count(con, rep["id"]) >= limit:
                    raise HTTPException(409, f"User limit reached ({limit}). Delete a user or ask the admin to increase the limit.")
        yield
