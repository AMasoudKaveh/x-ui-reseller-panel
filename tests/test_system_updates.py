from __future__ import annotations

import unittest

from backend.system_updates import _version_tuple


class SystemUpdateTests(unittest.TestCase):
    def test_semantic_versions_are_compared_numerically(self) -> None:
        self.assertGreater(_version_tuple("1.10.0"), _version_tuple("1.9.9"))
        self.assertEqual(_version_tuple("v2.3.4")[:3], (2, 3, 4))


if __name__ == "__main__":
    unittest.main()
