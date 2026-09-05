from __future__ import annotations

import math
import os
import threading
import time

from collections import deque
from fastapi import HTTPException


WINDOW_SECONDS = max(
    1,
    int(
        os.getenv(
            "API_RATE_LIMIT_WINDOW_SECONDS",
            "60",
        )
    ),
)

READ_LIMIT = max(
    1,
    int(
        os.getenv(
            "API_RATE_LIMIT_READ",
            "120",
        )
    ),
)

WRITE_LIMIT = max(
    1,
    int(
        os.getenv(
            "API_RATE_LIMIT_WRITE",
            "30",
        )
    ),
)


WRITE_METHODS = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}


_lock = threading.Lock()

_buckets: dict[
    tuple[str, str],
    deque[float],
] = {}

_last_cleanup = 0.0


def _cleanup(
    now: float,
) -> None:

    global _last_cleanup

    if (
        now - _last_cleanup
        < WINDOW_SECONDS * 5
    ):
        return

    cutoff = (
        now - WINDOW_SECONDS
    )

    stale = []

    for key, bucket in _buckets.items():

        while (
            bucket
            and
            bucket[0] <= cutoff
        ):
            bucket.popleft()

        if not bucket:
            stale.append(key)

    for key in stale:
        _buckets.pop(
            key,
            None,
        )

    _last_cleanup = now


def enforce_api_rate_limit(
    identity: str,
    method: str,
) -> None:

    method = str(
        method
        or "GET"
    ).upper()

    category = (
        "write"
        if method in WRITE_METHODS
        else "read"
    )

    limit = (
        WRITE_LIMIT
        if category == "write"
        else READ_LIMIT
    )

    now = time.monotonic()

    cutoff = (
        now - WINDOW_SECONDS
    )

    bucket_key = (
        str(identity),
        category,
    )

    with _lock:

        _cleanup(now)

        bucket = _buckets.setdefault(
            bucket_key,
            deque(),
        )

        while (
            bucket
            and
            bucket[0] <= cutoff
        ):
            bucket.popleft()

        if len(bucket) >= limit:

            retry_after = max(
                1,
                math.ceil(
                    (
                        bucket[0]
                        + WINDOW_SECONDS
                    )
                    - now
                ),
            )

            raise HTTPException(
                status_code=429,
                detail=(
                    "API rate limit exceeded. "
                    f"Maximum {limit} "
                    f"{category} requests "
                    f"per {WINDOW_SECONDS} seconds."
                ),
                headers={
                    "Retry-After":
                        str(retry_after),
                },
            )

        bucket.append(now)


def rate_limit_policy() -> dict:

    return {
        "window_seconds":
            WINDOW_SECONDS,

        "read_requests":
            READ_LIMIT,

        "write_requests":
            WRITE_LIMIT,
    }
