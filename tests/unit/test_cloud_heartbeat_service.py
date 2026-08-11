import unittest
from unittest.mock import Mock, patch

from cloud_heartbeat_service import HeartbeatService


class CloudHeartbeatServiceTests(unittest.TestCase):
    def test_force_heartbeat_uses_configured_tls_verification(self):
        response = Mock(status_code=200)
        service = HeartbeatService(
            websocket_client=None,
            node_id="node-1",
            base_url="https://cloud.example.test",
            verify_ssl=False,
        )

        with patch("cloud_heartbeat_service.requests.get", return_value=response) as get:
            result = service.force_heartbeat()

        self.assertTrue(result["success"])
        get.assert_called_once_with(
            "https://cloud.example.test/health",
            verify=False,
            timeout=5,
        )


if __name__ == "__main__":
    unittest.main()
