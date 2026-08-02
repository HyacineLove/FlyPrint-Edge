import tempfile
import unittest
from pathlib import Path

from prp_file_selection import PRPFileSelectionManager


class PRPFileSelectionManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manager = PRPFileSelectionManager(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_bind_replaces_and_deletes_previous_unconfirmed_source(self):
        first = self.manager.destination_for("session-1", "file-1")
        first.write_bytes(b"first")
        self.manager.bind("session-1", self._metadata("file-1"), first)

        second = self.manager.destination_for("session-1", "file-2")
        second.write_bytes(b"second")
        self.manager.bind("session-1", self._metadata("file-2"), second)

        self.assertFalse(first.exists())
        self.assertEqual(second, self.manager.get_source("session-1", "file-2"))

    def test_clear_session_deletes_source_and_empty_directory(self):
        source = self.manager.destination_for("session-1", "file-1")
        source.write_bytes(b"source")
        self.manager.bind("session-1", self._metadata("file-1"), source)

        self.assertTrue(self.manager.clear_session("session-1"))
        self.assertFalse(source.exists())
        self.assertFalse(source.parent.exists())

    def test_public_snapshot_never_exposes_local_path_or_access_token(self):
        source = self.manager.destination_for("session-1", "file-1")
        source.write_bytes(b"source")
        metadata = self._metadata("file-1")
        metadata["access_token"] = "must-not-survive"
        self.manager.bind("session-1", metadata, source)

        snapshot = self.manager.snapshot("session-1")
        self.assertNotIn("path", snapshot)
        self.assertNotIn("local_path", snapshot)
        self.assertNotIn("access_token", snapshot)
        self.assertEqual("prp", snapshot["source_origin"])

    @staticmethod
    def _metadata(file_id):
        return {
            "id": file_id,
            "name": "sample.pdf",
            "media_type": "application/pdf",
            "size": 6,
            "sha256": "0" * 64,
        }


if __name__ == "__main__":
    unittest.main()
