import unittest
from unittest.mock import Mock, patch

from cloud_api_client import CloudAPIClient


class CloudAPIClientTests(unittest.TestCase):
    def test_printer_registration_reports_failure_when_all_requests_fail(self):
        auth = Mock()
        auth.get_auth_headers.return_value = {"Authorization": "Bearer token"}
        client = CloudAPIClient("https://cloud.example.test", auth)
        client.node_id = "node-1"
        response = Mock(status_code=500, text="failed")
        with patch("cloud_api_client.requests.post", return_value=response):
            result = client.register_printers([{"name": "P1", "ipp_uri": "ipp://p1"}])
        self.assertFalse(result["success"])
        self.assertEqual(1, result["failed_count"])


if __name__ == "__main__":
    unittest.main()
