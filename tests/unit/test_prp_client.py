import base64
import hashlib
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import zipfile

from prp_client import PRPClient, PRPClientError


PDF_BYTES = b"%PDF-1.4\nslice-2-edge-client\n%%EOF\n"
PDF_SHA256 = "4ab35fde902ba92c294658d2f8e10ae15f0200798f4770d73b00d21d4fbd3877"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _docx_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"></w:document>',
        )
    return buffer.getvalue()


DOCX_BYTES = _docx_bytes()


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
                name, media_type, content = type(self)._file_response()
                body = {
                    "items": [{
                        "id": "file-1", "name": name,
                        "media_type": media_type, "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
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
            name, media_type, content = type(self)._file_response()
            declared_length = len(content) + (1 if type(self).mode == "wrong_length" else 0)
            declared_hash = "0" * 64 if type(self).mode == "wrong_hash" else hashlib.sha256(content).hexdigest()
            self.send_response(200)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(declared_length))
            self.send_header("X-Content-SHA256", declared_hash)
            disposition = (
                "attachment; filename*=utf-8''Kimi%E5%8F%91%E7%A5%A8.pdf"
                if type(self).mode == "unicode_filename"
                else f'attachment; filename="{name}"'
            )
            self.send_header("Content-Disposition", disposition)
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_error(404)

    def _json(self, value):
        raw = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    @classmethod
    def _file_response(cls):
        if cls.mode == "png":
            return "sample.png", "image/png", PNG_BYTES
        if cls.mode == "docx":
            return (
                "sample.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                DOCX_BYTES,
            )
        return "sample.pdf", "application/pdf", PDF_BYTES

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

    def test_list_enforces_a_total_deadline_while_reading_a_slow_response(self):
        class SlowResponse:
            status_code = 200
            headers = {"Content-Length": "100"}

            def iter_content(self, chunk_size):
                del chunk_size
                yield b'{"items":[],'
                time.sleep(0.03)
                yield b'"page":1,"page_size":20,"total":0}'

            def close(self):
                return None

        class SlowSession:
            def get(self, *_args, **_kwargs):
                return SlowResponse()

        client = PRPClient(
            session=SlowSession(),
            connect_timeout=1,
            read_timeout=1,
            total_timeout=0.01,
        )

        with self.assertRaisesRegex(PRPClientError, "prp_list_timeout"):
            client.list_files(self.access, 1, 20)

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

    def test_download_honors_a_smaller_edge_file_size_limit_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.pdf"
            with self.assertRaisesRegex(PRPClientError, "edge_file_size_exceeded"):
                self.client.download_file(self.access, "file-1", destination, max_file_size_bytes=5)
            self.assertFalse(destination.exists())
            self.assertFalse(Path(str(destination) + ".part").exists())

    def test_download_accepts_utf8_filename_parameter(self):
        _PRPHandler.mode = "unicode_filename"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.pdf"
            metadata = self.client.download_file(self.access, "file-1", destination)

        self.assertEqual("Kimi发票.pdf", metadata["name"])

    def test_list_accepts_supported_image_and_docx_metadata(self):
        for mode, expected_type in (
            ("png", "image/png"),
            ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ):
            with self.subTest(mode=mode):
                _PRPHandler.mode = mode
                result = self.client.list_files(self.access, 1, 20)
                self.assertEqual(expected_type, result["items"][0]["media_type"])

    def test_download_publishes_with_validated_source_extension(self):
        for mode, expected_bytes, expected_suffix in (
            ("png", PNG_BYTES, ".png"),
            ("docx", DOCX_BYTES, ".docx"),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                _PRPHandler.mode = mode
                destination = Path(directory) / "file-1.source"
                metadata = self.client.download_file(self.access, "file-1", destination)
                published = Path(metadata["path"])
                self.assertEqual(expected_suffix, published.suffix)
                self.assertEqual(expected_bytes, published.read_bytes())
                self.assertFalse(destination.exists())

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
