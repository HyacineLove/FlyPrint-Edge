import unittest
from unittest.mock import Mock, patch

from print_authorization_client import (
    PrintAuthorizationClient,
    PrintAuthorizationTransportError,
)


class PrintAuthorizationClientTests(unittest.TestCase):
    def setUp(self):
        self.auth = Mock()
        self.auth.get_auth_headers.return_value = {
            "Authorization": "Bearer node-token",
            "Content-Type": "application/json",
        }
        self.client = PrintAuthorizationClient(
            "https://cloud.example.test/",
            "edge-1",
            self.auth,
        )
        self.payload = {
            "confirmation_id": "confirm-1",
            "terminal_session_id": "session-1",
            "site_portal_code": "official",
            "local_file_id": "file-1",
            "file_display_name": "document.pdf",
            "page_count": 3,
            "copies": 2,
            "paper_size": "A4",
            "color_mode": "color",
            "duplex_mode": "longedge",
            "printer_id": "11111111-1111-1111-1111-111111111111",
        }

    def test_posts_exact_authorization_contract(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "allowed": True,
            "job_id": "job-1",
            "reserved_quota": 8,
            "quota_balance": 42,
        }
        with patch("print_authorization_client.requests.post", return_value=response) as post:
            result = self.client.authorize(self.payload)

        self.assertTrue(result["allowed"])
        post.assert_called_once_with(
            "https://cloud.example.test/api/v1/edge/edge-1/print-authorizations",
            json=self.payload,
            headers={
                "Authorization": "Bearer node-token",
                "Content-Type": "application/json",
            },
            timeout=10,
        )

    def test_returns_stable_cloud_denial_without_changing_decision(self):
        response = Mock(status_code=409)
        response.json.return_value = {
            "allowed": False,
            "error_code": "print_quota_insufficient",
            "message": "quota insufficient",
        }
        with patch("print_authorization_client.requests.post", return_value=response):
            result = self.client.authorize(self.payload)

        self.assertEqual("print_quota_insufficient", result["error_code"])
        self.assertNotIn("job_id", result)

    def test_ambiguous_transport_failure_does_not_create_another_request(self):
        with patch(
            "print_authorization_client.requests.post",
            side_effect=TimeoutError("timeout"),
        ) as post:
            with self.assertRaises(PrintAuthorizationTransportError):
                self.client.authorize(self.payload)
        self.assertEqual(1, post.call_count)
        self.assertEqual("confirm-1", self.payload["confirmation_id"])


if __name__ == "__main__":
    unittest.main()
