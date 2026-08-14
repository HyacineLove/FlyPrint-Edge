import os
import sys
import unittest
from copy import deepcopy
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config_service import ConfigService


class InMemoryConfigRepo:
    def __init__(self, config):
        self.config = deepcopy(config)

    def get_full_config(self):
        return deepcopy(self.config)

    def replace_full_config(self, config):
        self.config = deepcopy(config)

    def save_config(self):
        return None


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

    def test_merge_ignores_unknown_settings_fields(self):
        merged = self.service.merge_update(self.raw, {
            "settings": {
                "max_pages": -1,
                "max_document_pages": 8,
            },
        })

        self.assertNotIn("max_pages", merged["settings"])
        self.assertEqual(8, merged["settings"]["max_document_pages"])

    def test_cloud_health_preflight_uses_base_url_only(self):
        with patch("config_service.requests.get") as get:
            get.return_value.status_code = 200
            result = self.service.test_cloud_connection({"cloud": {"base_url": "http://cloud.example.com"}})
        self.assertTrue(result["success"])
        get.assert_called_once()

    def test_cloud_url_change_is_saved_when_target_cloud_is_temporarily_unavailable(self):
        repo = InMemoryConfigRepo({
            "cloud": {
                "base_url": "https://old-cloud.example.com",
                "credential_blob": "opaque",
                "node_id": "node-1",
                "node_name": "terminal-1",
                "location": "site-a",
                "heartbeat_interval": 30,
            },
            "settings": {},
            "network": {"bind_address": "127.0.0.1", "port": 7860},
        })
        service = ConfigService(repo)
        cloud_service = type("CloudServiceStub", (), {})()
        cloud_service.reconfigure = lambda config, preserve_node_id: {
            "success": True,
            "registered": True,
            "connected": False,
            "message": "waiting for cloud connection",
        }

        with patch.object(
            service,
            "test_cloud_connection",
            return_value={"success": False, "message": "target cloud unavailable"},
        ):
            result = service.save_and_apply(
                {"cloud": {"base_url": "https://new-cloud.example.com"}},
                cloud_service=cloud_service,
            )

        self.assertTrue(result["success"])
        self.assertEqual("https://new-cloud.example.com", repo.config["cloud"]["base_url"])
        self.assertEqual("node-1", repo.config["cloud"]["node_id"])

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

    def test_validate_rejects_non_loopback_bind_address(self):
        errors = self.service.validate({
            "cloud": {}, "settings": {},
            "network": {"bind_address": "0.0.0.0", "port": 7860},
        })
        self.assertIn("network.bind_address must be loopback-only", errors)

    def test_validate_accepts_ipv6_loopback(self):
        errors = self.service.validate({
            "cloud": {}, "settings": {},
            "network": {"bind_address": "::1", "port": 7860},
        })
        self.assertNotIn("network.bind_address must be loopback-only", errors)

    def test_validate_rejects_hostname_even_if_it_usually_resolves_locally(self):
        errors = self.service.validate({
            "cloud": {}, "settings": {},
            "network": {"bind_address": "localhost", "port": 7860},
        })
        self.assertIn("network.bind_address must be loopback-only", errors)


if __name__ == "__main__":
    unittest.main()
