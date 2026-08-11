import unittest

from portal_session import PortalSessionManager


class PortalSessionManagerTests(unittest.TestCase):
    def test_bind_rejects_different_terminal_session(self):
        manager = PortalSessionManager()

        bound = manager.bind("session-1", {
            "terminal_session_id": "session-2",
            "site_portal_code": "official",
            "cloud_user_id": "cloud-user-1",
            "external_user_id": "external-user-1",
            "display_name": "张老师",
            "prp_base_url": "https://prp.example.test",
            "access_token": "private-token",
            "access_token_expires_at": "2026-07-30T12:05:00Z",
        })

        self.assertFalse(bound)
        self.assertEqual({"active": False}, manager.snapshot())

    def test_public_snapshot_never_exposes_access_token(self):
        manager = PortalSessionManager()
        self.assertTrue(manager.bind("session-1", {
            "terminal_session_id": "session-1",
            "site_portal_code": "official",
            "cloud_user_id": "cloud-user-1",
            "external_user_id": "external-user-1",
            "display_name": "张老师",
            "prp_base_url": "https://prp.example.test",
            "access_token": "private-token",
            "access_token_expires_at": "2099-07-30T12:05:00Z",
        }))

        snapshot = manager.snapshot()

        self.assertTrue(snapshot["active"])
        self.assertEqual("external-user-1", snapshot["external_user_id"])
        self.assertNotIn("access_token", snapshot)
        self.assertNotIn("prp_access_token", snapshot)
        self.assertEqual("private-token", manager.get_access_context("session-1")["access_token"])

    def test_clear_removes_private_access_context(self):
        manager = PortalSessionManager()
        manager.bind("session-1", {
            "terminal_session_id": "session-1",
            "site_portal_code": "official",
            "cloud_user_id": "cloud-user-1",
            "external_user_id": "external-user-1",
            "display_name": "张老师",
            "prp_base_url": "https://prp.example.test",
            "access_token": "private-token",
            "access_token_expires_at": "2099-07-30T12:05:00Z",
        })

        self.assertTrue(manager.clear("session-1"))
        self.assertIsNone(manager.get_access_context("session-1"))
        self.assertEqual({"active": False}, manager.snapshot())

    def test_one_token_has_isolated_provider_contexts_and_safe_snapshot(self):
        manager = PortalSessionManager()
        self.assertTrue(manager.bind("session-1", {
            "terminal_session_id": "session-1",
            "site_portal_code": "official",
            "cloud_user_id": "cloud-user-1",
            "external_user_id": "external-user-1",
            "display_name": "Test User",
            "access_token": "shared-sso-token",
            "access_token_expires_at": "2099-07-30T12:05:00Z",
            "providers": [
                {"provider_id": "prp-a", "display_name": "System A", "prp_base_url": "https://a.example.test"},
                {"provider_id": "prp-b", "display_name": "System B", "prp_base_url": "https://b.example.test"},
            ],
        }))

        snapshot = manager.snapshot()
        self.assertEqual(["prp-a", "prp-b"], [item["provider_id"] for item in snapshot["providers"]])
        self.assertNotIn("prp_base_url", snapshot["providers"][0])
        self.assertNotIn("shared-sso-token", str(snapshot))
        self.assertEqual("shared-sso-token", manager.get_access_context("session-1", "prp-a")["access_token"])
        self.assertEqual("https://a.example.test", manager.get_access_context("session-1", "prp-a")["prp_base_url"])
        self.assertEqual("https://b.example.test", manager.get_access_context("session-1", "prp-b")["prp_base_url"])


if __name__ == "__main__":
    unittest.main()
