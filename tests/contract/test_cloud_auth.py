import threading
import time
import unittest
from unittest.mock import Mock, patch

from cloud_auth import CloudAuthClient


class CloudAuthClientTests(unittest.TestCase):
    def test_requests_exact_node_runtime_scopes(self):
        response = Mock(status_code=200)
        response.json.return_value = {"access_token": "token", "expires_in": 3600}
        client = CloudAuthClient("http://cloud.example.com/auth/token", "edge-1", "secret")

        with patch("cloud_auth.requests.post", return_value=response) as post:
            self.assertEqual("token", client.get_access_token())

        self.assertEqual(
            "edge:register edge:printer edge:heartbeat",
            post.call_args.kwargs["data"]["scope"],
        )

    def test_concurrent_refresh_performs_one_request(self):
        response = Mock(status_code=200)
        response.json.return_value = {"access_token": "token", "expires_in": 3600}
        client = CloudAuthClient("http://cloud.example.com/auth/token", "edge-1", "secret")
        def request(_url, **_kwargs):
            time.sleep(0.02)
            return response

        with patch("cloud_auth.requests.post", side_effect=request) as post:
            threads = [threading.Thread(target=client.get_access_token) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())
        self.assertEqual(1, post.call_count)


if __name__ == "__main__":
    unittest.main()
