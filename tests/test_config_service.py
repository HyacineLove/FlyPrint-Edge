import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_service import ConfigService


class ConfigServiceTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"cloud": {"base_url": "http://cloud.example.com", "credential_blob": "opaque", "node_id": "node-1", "client_secret": "legacy-secret"}, "settings": {}, "network": {"bind_address": "127.0.0.1", "port": 7860}}
        self.service = ConfigService(None)

    def test_public_config_never_exposes_credential_material(self):
        payload = self.service.build_public_config(self.raw)
        self.assertTrue(payload["cloud"]["activated"])
        self.assertNotIn("credential_blob", payload["cloud"])
        self.assertNotIn("client_secret", payload["cloud"])

    def test_merge_ignores_manual_credential_fields(self):
        merged = self.service.merge_update(self.raw, {"cloud": {"client_secret": "attacker", "base_url": "http://new.example.com"}})
        self.assertEqual(merged["cloud"]["credential_blob"], "opaque")
        self.assertNotIn("client_secret", merged["cloud"])
        self.assertEqual(merged["cloud"]["base_url"], "http://new.example.com")

    def test_cloud_health_preflight_uses_base_url_only(self):
        with patch("config_service.requests.get") as get:
            get.return_value.status_code = 200
            result = self.service.test_cloud_connection({"cloud": {"base_url": "http://cloud.example.com"}})
        self.assertTrue(result["success"])
        get.assert_called_once()

    def test_public_config_exposes_normalized_edge_limits(self):
        payload = self.service.build_public_config({
            "cloud": {},
            "settings": {
                "max_file_size_bytes": "1048576",
                "max_document_pages": "8",
                "max_list_items": "12",
            },
            "network": {"bind_address": "127.0.0.1", "port": 7860},
        })

        self.assertEqual(1048576, payload["settings"]["max_file_size_bytes"])
        self.assertEqual(8, payload["settings"]["max_document_pages"])
        self.assertEqual(12, payload["settings"]["max_list_items"])

    def test_validate_rejects_negative_edge_limits(self):
        errors = self.service.validate({
            "cloud": {},
            "settings": {
                "max_file_size_bytes": -1,
                "max_document_pages": -1,
                "max_list_items": -1,
            },
            "network": {"bind_address": "127.0.0.1", "port": 7860},
        })

        self.assertIn("settings.max_file_size_bytes must be an integer >= 0", errors)
        self.assertIn("settings.max_document_pages must be an integer >= 0", errors)
        self.assertIn("settings.max_list_items must be an integer >= 0", errors)


if __name__ == "__main__":
    unittest.main()
