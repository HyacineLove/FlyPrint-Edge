import asyncio
import unittest
from unittest.mock import patch

import main
from interactive_session import InteractiveSessionManager
from portal_identity_flow import PortalIdentityFlow
from portal_session import PortalSessionManager


class FakeSitePortalClient:
    def __init__(self):
        self.calls = []

    def redeem(self, claim_base_url, claim_code, site_portal_code, node_id, terminal_session_id):
        self.calls.append({
            "claim_base_url": claim_base_url,
            "claim_code": claim_code,
            "site_portal_code": site_portal_code,
            "node_id": node_id,
            "terminal_session_id": terminal_session_id,
        })
        return {
            "site_portal_code": site_portal_code,
            "external_user_id": "external-user-1",
            "display_name": "张老师",
            "providers": [{"provider_id": "prp-a", "display_name": "文件库 A"}],
            "file_session_token": "portal-file-session",
            "file_session_expires_at": "2099-07-30T12:05:00Z",
        }


class PortalIdentityFlowTests(unittest.TestCase):
    def setUp(self):
        self.interactive = InteractiveSessionManager()
        self.portal_sessions = PortalSessionManager()
        self.client = FakeSitePortalClient()
        self.flow = PortalIdentityFlow(self.interactive, self.portal_sessions, self.client)
        self.session = self.interactive.start_session(upload_token="bridge-token")
        self.interactive.apply_occupied({
            "terminal_session_id": self.session["session_id"],
            "terminal_ticket_hash": "a" * 64,
        })

    def ready_message(self, session_id=None):
        return {
            "site_portal_code": "official",
            "site_portal_display_name": "\u5b98\u65b9\u6253\u5370\u670d\u52a1",
            "claim_base_url": "https://portal.example.test",
            "claim_code": "claim-code-1",
            "terminal_session_id": session_id or self.session["session_id"],
            "cloud_user_id": "cloud-user-1",
            "expires_at": "2099-07-30T12:05:00Z",
        }

    def test_ready_message_for_other_terminal_session_is_not_claimed(self):
        result = self.flow.handle_ready(self.ready_message("other-session"), "edge-1")

        self.assertIsNone(result)
        self.assertEqual([], self.client.calls)
        self.assertEqual({"active": False}, self.portal_sessions.snapshot())

    def test_ready_message_claims_and_returns_public_identity_only(self):
        result = self.flow.handle_ready(self.ready_message(), "edge-1")

        self.assertEqual(1, len(self.client.calls))
        self.assertEqual("external-user-1", result["external_user_id"])
        self.assertEqual("\u5b98\u65b9\u6253\u5370\u670d\u52a1", result["site_portal_display_name"])
        self.assertEqual("identity_ready", self.interactive.build_snapshot()["state"])
        self.assertNotIn("access_token", result)
        self.assertNotIn("file_session_token", result)
        self.assertNotIn("portal-file-session", str(result))
        self.assertEqual(
            "portal-file-session",
            self.portal_sessions.get_access_context(self.session["session_id"])["file_session_token"],
        )
        self.assertEqual(
            "https://portal.example.test",
            self.portal_sessions.get_access_context(self.session["session_id"])["portal_base_url"],
        )

    def test_ready_message_without_cloud_display_name_uses_portal_code(self):
        message = self.ready_message()
        del message["site_portal_display_name"]

        result = self.flow.handle_ready(message, "edge-1")

        self.assertEqual("official", result["site_portal_display_name"])
        self.assertEqual(1, len(self.client.calls))

    def test_main_replaces_claim_message_with_public_snapshot(self):
        class FakeFlow:
            def handle_ready(self, payload, node_id):
                self.payload = payload
                self.node_id = node_id
                return {
                    "active": True,
                    "site_portal_code": "official",
                    "site_portal_display_name": "\u5b98\u65b9\u6253\u5370\u670d\u52a1",
                    "external_user_id": "external-user-1",
                    "display_name": "张老师",
                }

        flow = FakeFlow()
        with patch.object(main, "portal_identity_flow", flow, create=True), \
             patch.object(main, "node_id", "edge-1"):
            result = main._enrich_message_with_session({
                "type": "portal_session_ready",
                "data": self.ready_message(),
            })

        self.assertEqual("portal_session_ready", result["type"])
        self.assertEqual("external-user-1", result["data"]["external_user_id"])
        self.assertEqual("\u5b98\u65b9\u6253\u5370\u670d\u52a1", result["data"]["site_portal_display_name"])
        self.assertNotIn("claim_code", result["data"])
        self.assertEqual("edge-1", flow.node_id)

    def test_main_announces_claiming_before_redeeming_login_result(self):
        class FakeFlow:
            def handle_ready(self, payload, node_id):
                return {
                    "active": True,
                    "terminal_session_id": payload["terminal_session_id"],
                    "site_portal_code": "official",
                    "site_portal_display_name": "官方打印服务",
                    "external_user_id": "external-user-1",
                    "display_name": "张老师",
                }

        queue = asyncio.Queue()
        with patch.object(main, "portal_identity_flow", FakeFlow(), create=True), \
             patch.object(main, "node_id", "edge-1"), \
             patch.object(main, "main_loop", None), \
             patch.object(main, "sse_clients", [queue]), \
             patch.object(main.interactive_session_manager, "get_active_session", return_value={"session_id": self.session["session_id"]}):
            main.handle_cloud_message({"type": "portal_session_ready", "data": self.ready_message()})

        claiming = queue.get_nowait()
        ready = queue.get_nowait()
        self.assertEqual("portal_session_claiming", claiming["type"])
        self.assertEqual({"terminal_session_id": self.session["session_id"]}, claiming["data"])
        self.assertEqual("portal_session_ready", ready["type"])


if __name__ == "__main__":
    unittest.main()
