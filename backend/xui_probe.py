from __future__ import annotations

import sys

from backend.xui_client import XUIClient


def main() -> int:
    try:
        rows = XUIClient().inbounds()
    except Exception as exc:
        print(f"X-UI connection failed: {exc}")
        return 1

    print("X-UI connection: OK")
    print(f"Inbounds detected: {len(rows)}")
    for row in rows[:10]:
        print(f" - #{row.get('id')} {row.get('name') or row.get('remark') or ''} :{row.get('port') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
