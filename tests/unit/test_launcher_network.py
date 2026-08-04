import unittest

from launcher import resolve_local_base_url


class LauncherNetworkTests(unittest.TestCase):
    def test_loopback_addresses_are_used(self):
        self.assertEqual(
            "http://127.0.0.1:7860",
            resolve_local_base_url({"network": {"bind_address": "127.0.0.1", "port": 7860}}),
        )
        self.assertEqual(
            "http://[::1]:7860",
            resolve_local_base_url({"network": {"bind_address": "::1", "port": 7860}}),
        )

    def test_non_loopback_address_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_local_base_url({"network": {"bind_address": "0.0.0.0", "port": 7860}})


if __name__ == "__main__":
    unittest.main()
