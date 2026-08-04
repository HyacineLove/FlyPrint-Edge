import unittest

from download_security import validate_download_url


class DownloadSecurityTests(unittest.TestCase):
    def test_relative_and_cloud_origin_urls_are_allowed(self):
        self.assertEqual(
            "https://cloud.example.test/api/v1/files/f1",
            validate_download_url("/api/v1/files/f1", "https://cloud.example.test"),
        )

    def test_external_preview_origin_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://attacker.example/x", "https://cloud.example.test")

    def test_presigned_external_origin_is_allowed(self):
        url = "https://storage.example/x?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc"
        self.assertEqual(url, validate_download_url(url, "https://cloud.example.test", allow_signed_url=True))

    def test_credentials_and_fragment_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://user:pass@cloud.example.test/x", "https://cloud.example.test")
        with self.assertRaises(ValueError):
            validate_download_url("https://cloud.example.test/x#fragment", "https://cloud.example.test")
