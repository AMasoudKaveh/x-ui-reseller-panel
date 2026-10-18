from __future__ import annotations

import sqlite3
from types import TracebackType


class ClosingConnection(sqlite3.Connection):
    """A sqlite connection whose context manager also closes the descriptor.

    sqlite3.Connection.__exit__ only commits or rolls back; it does not close
    the connection. The application consistently uses ``with connect_db()``
    and therefore needs closing semantics to avoid leaking database/WAL file
    descriptors in the long-running API and quota worker process.
    """

    def __enter__(self) -> ClosingConnection:
        return super().__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()
