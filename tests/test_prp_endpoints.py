import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import main
from interactive_session import InteractiveSessionManager
from portal_session import PortalSessionManager
from prp_client import PRPClientError
from prp_file_selection import PRPFileSelectionManager


class _Request:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class _FakePRPClient:
    def __init__(self, fail=False):
        self.fail = fail

    def list_files(self, _access, page, page_size):
        return {"items": [], "page": page, "page_size": page_size, "total": 0}

    def download_file(self, _access, file_id, destination):
        if self.fail:
            Path(str(destination) + ".part").write_bytes(b"partial")
            raise PRPClientError("content_hash_mismatch")
        destination.write_bytes(b"%PDF-test")
        return {
            "id": file_id, "name": "sample.pdf", "media_type": "application/pdf",
            "size": 9, "sha256": "0" * 64, "path": str(destination),
        }


class PRPEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.interactive = InteractiveSessionManager()
        session = self.interactive.start_session()
        self.session_id = session["session_id"]
        self.portal = PortalSessionManager()
        self.portal.bind(self.session_id, {
            "terminal_session_id": self.session_id, "site_portal_code": "official",
            "cloud_user_id": "cloud-1", "external_user_id": "external-1",
            "display_name": "User", "prp_base_url": "https://prp.example.test",
            "access_token": "private-token",
            "access_token_expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=5)
            ).isoformat(),
        })
        self.selections = PRPFileSelectionManager(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_list_requires_current_portal_session(self):
        with patch.object(main, "interactive_session_manager", self.interactive), \
             patch.object(main, "portal_session_manager", self.portal):
            response = asyncio.run(main.list_prp_files("wrong-session"))
        self.assertEqual(401, response.status_code)

    def test_select_downloads_and_binds_only_current_session(self):
        with patch.object(main, "interactive_session_manager", self.interactive), \
             patch.object(main, "portal_session_manager", self.portal), \
             patch.object(main, "prp_file_selection_manager", self.selections), \
             patch.object(main, "prp_client", _FakePRPClient()):
            response = asyncio.run(
                main.select_prp_file("file-1", _Request({"session_id": self.session_id}))
            )
        self.assertTrue(response["success"])
        self.assertEqual("prp", self.interactive.build_snapshot()["source_origin"])

    def test_select_failure_keeps_identity_ready_and_deletes_partial_source(self):
        self.interactive.bind_portal_identity({
            "terminal_session_id": self.session_id, "site_portal_code": "official",
            "cloud_user_id": "cloud-1", "external_user_id": "external-1",
            "display_name": "User",
        })
        with patch.object(main, "interactive_session_manager", self.interactive), \
             patch.object(main, "portal_session_manager", self.portal), \
             patch.object(main, "prp_file_selection_manager", self.selections), \
             patch.object(main, "prp_client", _FakePRPClient(fail=True)):
            response = asyncio.run(
                main.select_prp_file("file-1", _Request({"session_id": self.session_id}))
            )
        self.assertEqual(502, response.status_code)
        self.assertEqual("identity_ready", self.interactive.build_snapshot()["state"])
        destination = self.selections.destination_for(self.session_id, "file-1")
        self.assertFalse(Path(str(destination) + ".part").exists())

    def test_clear_selection_preserves_portal_session_and_releases_preview(self):
        self.interactive.bind_portal_identity({
            "terminal_session_id": self.session_id, "site_portal_code": "official",
            "cloud_user_id": "cloud-1", "external_user_id": "external-1",
            "display_name": "User",
        })
        preview_manager = Mock()
        with patch.object(main, "interactive_session_manager", self.interactive), \
             patch.object(main, "portal_session_manager", self.portal), \
             patch.object(main, "prp_file_selection_manager", self.selections), \
             patch.object(main, "prp_client", _FakePRPClient()), \
             patch.object(main, "get_file_manager", return_value=preview_manager):
            asyncio.run(
                main.select_prp_file("file-1", _Request({"session_id": self.session_id}))
            )
            response = asyncio.run(
                main.clear_prp_selection(_Request({"session_id": self.session_id}))
            )

        self.assertTrue(response["success"])
        self.assertEqual("identity_ready", self.interactive.build_snapshot()["state"])
        self.assertIsNotNone(self.portal.get_access_context(self.session_id))
        self.assertEqual({}, self.selections.snapshot(self.session_id))
        preview_manager.release_preview_resource.assert_called_once_with(
            "file-1", reason="prp_deselect"
        )


if __name__ == "__main__":
    unittest.main()
