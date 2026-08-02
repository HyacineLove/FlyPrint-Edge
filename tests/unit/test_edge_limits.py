import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from edge_limits import (
    DEFAULT_MAX_DOCUMENT_PAGES,
    normalize_local_limits,
    validate_file_size,
    validate_page_count,
)


class EdgeLimitTests(unittest.TestCase):
    def test_normalize_local_limits_uses_safe_edge_defaults(self):
        limits = normalize_local_limits({})

        self.assertEqual(DEFAULT_MAX_DOCUMENT_PAGES, limits["max_document_pages"])
        self.assertEqual(0, limits["max_file_size_bytes"])
        self.assertEqual(0, limits["max_list_items"])

    def test_normalize_local_limits_keeps_configured_values(self):
        limits = normalize_local_limits({
            "max_file_size_bytes": "1048576",
            "max_document_pages": "8",
            "max_list_items": "12",
        })

        self.assertEqual(1048576, limits["max_file_size_bytes"])
        self.assertEqual(8, limits["max_document_pages"])
        self.assertEqual(12, limits["max_list_items"])

    def test_validate_file_size_rejects_oversized_local_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.pdf"
            path.write_bytes(b"0123456789")

            message = validate_file_size(path, {"max_file_size_bytes": 5})

        self.assertEqual("文件超过 Edge 本地大小限制", message)

    def test_validate_page_count_rejects_document_over_local_limit(self):
        message = validate_page_count(6, {"max_document_pages": 5})

        self.assertEqual("文件页数超过 Edge 本地页数限制", message)


if __name__ == "__main__":
    unittest.main()
