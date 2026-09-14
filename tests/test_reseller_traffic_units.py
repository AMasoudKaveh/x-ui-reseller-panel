import unittest

from backend.reseller_create_user import CreateUserBody, gb_to_bytes, mb_to_bytes


class TrafficUnitTests(unittest.TestCase):
    def test_exact_megabyte_quota_is_never_zero(self):
        body = CreateUserBody(username="trial", traffic_gb=0.1, traffic_mb=100)

        self.assertEqual(body.traffic_mb, 100)
        self.assertEqual(mb_to_bytes(body.traffic_mb), 100 * 1024 * 1024)
        self.assertGreater(mb_to_bytes(1), 0)

    def test_legacy_gigabyte_conversion_stays_supported(self):
        self.assertEqual(gb_to_bytes(1), 1024 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
