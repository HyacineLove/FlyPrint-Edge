import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from prp_client import PRPClient, PRPClientError


PDF_BYTES = b"%PDF-1.4\nslice-2-edge-client\n%%EOF\n"
PDF_SHA256 = "4ab35fde902ba92c294658d2f8e10ae15f0200798f4770d73b00d21d4fbd3877"


class _PRPHandler(BaseHTTPRequestHandler):
    mode = "valid"
    seen_authorization = ""
    seen_query = ""

    def do_GET(self):
        parsed = urlsplit(self.path)
        type(self).seen_authorization = self.headers.get("Authorization", "")
        type(self).seen_query = parsed.query
        if parsed.path == "/api/v1/files":
            if type(self).mode == "bad_pagination":
                body = {"items": [], "page": "1", "page_size": 20, "total": 0}
            else:
                body = {
                    "items": [{
                        "id": "file-1", "name": "sample.pdf",
                        "media_type": "application/pdf", "size": len(PDF_BYTES),
                        "sha256": PDF_SHA256,
                        "created_at": "2026-07-30T12:00:00Z",
                        "expires_at": "2026-08-06T12:00:00Z",
                        "last_downloaded_at": None,
                    }],
                    "page": int(parse_qs(parsed.query)["page"][0]),
                    "page_size": int(parse_qs(parsed.query)["page_size"][0]),
                    "total": 1,
                }
            self._json(body)
            return
        if parsed.path == "/api/v1/files/file-1/content":
            declared_length = len(PDF_BYTES) + (1 if type(self).mode == "wrong_length" else 0)
            declared_hash = "0" * 64 if type(self).mode == "wrong_hash" else PDF_SHA256
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(declared_length))
            self.send_header("X-Content-SHA256", declared_hash)
            disposition = (
                "attachment; filename*=utf-8''Kimi%E5%8F%91%E7%A5%A8.pdf"
                if type(self).mode == "unicode_filename"
                else 'attachment; filename="sample.pdf"'
            )
            self.send_header("Content-Disposition", disposition)
            self.end_headers()
            self.wfile.write(PDF_BYTES)
            return
        self.send_error(404)

    def _json(self, value):
        raw = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        return


class PRPClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _PRPHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        _PRPHandler.mode = "valid"
        _PRPHandler.seen_authorization = ""
        _PRPHandler.seen_query = ""
        self.client = PRPClient()
        self.access = {"prp_base_url": self.base_url, "access_token": "private-prp-token"}

    def test_list_uses_authorization_header_and_never_query_token(self):
        result = self.client.list_files(self.access, 1, 20)
        self.assertEqual(1, result["total"])
        self.assertEqual("Bearer private-prp-token", _PRPHandler.seen_authorization)
        self.assertNotIn("private-prp-token", _PRPHandler.seen_query)

    def test_list_rejects_invalid_pagination_shape(self):
        _PRPHandler.mode = "bad_pagination"
        with self.assertRaises(PRPClientError):
            self.client.list_files(self.access, 1, 20)

    def test_download_rejects_wrong_length_and_removes_partial_file(self):
        _PRPHandler.mode = "wrong_length"
        self._assert_failed_download_removes_partial("content_length_mismatch")

    def test_download_rejects_wrong_sha256_and_removes_partial_file(self):
        _PRPHandler.mode = "wrong_hash"
        self._assert_failed_download_removes_partial("content_hash_mismatch")

    def test_download_verifies_and_atomically_publishes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.pdf"
            metadata = self.client.download_file(self.access, "file-1", destination)
            self.assertEqual(PDF_BYTES, destination.read_bytes())
            self.assertEqual(PDF_SHA256, metadata["sha256"])
            self.assertEqual("sample.pdf", metadata["name"])
            self.assertFalse(Path(str(destination) + ".part").exists())

    def test_download_accepts_utf8_filename_parameter(self):
        _PRPHandler.mode = "unicode_filename"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.pdf"
            metadata = self.client.download_file(self.access, "file-1", destination)

        self.assertEqual("Kimi发票.pdf", metadata["name"])

    def test_base_url_rejects_userinfo_query_and_fragment(self):
        for base_url in (
            "http://user:pass@example.test",
            "https://example.test?token=value",
            "https://example.test#fragment",
        ):
            with self.subTest(base_url=base_url), self.assertRaises(PRPClientError):
                self.client.list_files(
                    {"prp_base_url": base_url, "access_token": "private-prp-token"}, 1, 20
                )

    def _assert_failed_download_removes_partial(self, expected_code):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.pdf"
            with self.assertRaisesRegex(PRPClientError, expected_code):
                self.client.download_file(self.access, "file-1", destination)
            self.assertFalse(destination.exists())
            self.assertFalse(Path(str(destination) + ".part").exists())


if __name__ == "__main__":
    unittest.main()
