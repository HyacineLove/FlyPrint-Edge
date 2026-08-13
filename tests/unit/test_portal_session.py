import unittest

from portal_session import PortalSessionManager


def _payload(session_id="session-1", **overrides):
    value = {
        "terminal_session_id": session_id,
        "site_portal_code": "official",
        "cloud_user_id": "cloud-user-1",
        "external_user_id": "external-user-1",
        "display_name": "张老师",
        "claim_base_url": "https://portal.example.test",
        "file_session_token": "portal-file-session",
        "file_session_expires_at": "2099-07-30T12:05:00Z",
        "providers": [{"provider_id": "prp-a", "display_name": "文件库 A"}],
    }
    value.update(overrides)
    return value


class PortalSessionManagerTests(unittest.TestCase):
    def test_bind_rejects_different_terminal_session(self):
        manager = PortalSessionManager()

        bound = manager.bind("session-1", _payload("session-2"))

        self.assertFalse(bound)
        self.assertEqual({"active": False}, manager.snapshot())

    def test_public_snapshot_never_exposes_file_session_token(self):
        manager = PortalSessionManager()
        self.assertTrue(manager.bind("session-1", _payload()))

        snapshot = manager.snapshot()

        self.assertTrue(snapshot["active"])
        self.assertEqual("external-user-1", snapshot["external_user_id"])
        self.assertNotIn("file_session_token", snapshot)
        self.assertNotIn("access_token", snapshot)
        self.assertNotIn("claim_base_url", snapshot)
        self.assertEqual(
            "portal-file-session",
            manager.get_access_context("session-1")["file_session_token"],
        )
        self.assertEqual(
            "https://portal.example.test",
            manager.get_access_context("session-1")["portal_base_url"],
        )

    def test_clear_removes_private_access_context(self):
        manager = PortalSessionManager()
        manager.bind("session-1", _payload())

        self.assertTrue(manager.clear("session-1"))
        self.assertIsNone(manager.get_access_context("session-1"))
        self.assertEqual({"active": False}, manager.snapshot())

    def test_one_session_has_isolated_provider_ids_and_safe_snapshot(self):
        manager = PortalSessionManager()
        self.assertTrue(manager.bind("session-1", _payload(
            display_name="Test User",
            providers=[
                {"provider_id": "prp-a", "display_name": "System A"},
                {"provider_id": "prp-b", "display_name": "System B"},
            ],
        )))

        snapshot = manager.snapshot()
        self.assertEqual(["prp-a", "prp-b"], [item["provider_id"] for item in snapshot["providers"]])
        self.assertNotIn("prp_base_url", snapshot["providers"][0])
        self.assertNotIn("portal-file-session", str(snapshot))
        self.assertEqual("portal-file-session", manager.get_access_context("session-1", "prp-a")["file_session_token"])
        self.assertEqual("prp-a", manager.get_access_context("session-1", "prp-a")["provider_id"])
        self.assertEqual("prp-b", manager.get_access_context("session-1", "prp-b")["provider_id"])
        self.assertEqual(
            "https://portal.example.test",
            manager.get_access_context("session-1", "prp-a")["portal_base_url"],
        )

    def test_bind_rejects_sso_token_payload(self):
        manager = PortalSessionManager()
        self.assertFalse(manager.bind("session-1", _payload(access_token="sso-token")))


if __name__ == "__main__":
    unittest.main()
