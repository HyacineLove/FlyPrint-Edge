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
            "prp_base_url": "https://prp.example.test",
            "access_token": "private-token",
            "access_token_expires_at": "2099-07-30T12:05:00Z",
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
        self.assertEqual("identity_ready", self.interactive.build_snapshot()["state"])
        self.assertNotIn("access_token", result)
        self.assertNotIn("private-token", str(result))
        self.assertEqual(
            "private-token",
            self.portal_sessions.get_access_context(self.session["session_id"])["access_token"],
        )

    def test_main_replaces_claim_message_with_public_snapshot(self):
        class FakeFlow:
            def handle_ready(self, payload, node_id):
                self.payload = payload
                self.node_id = node_id
                return {
                    "active": True,
                    "site_portal_code": "official",
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
        self.assertNotIn("claim_code", result["data"])
        self.assertEqual("edge-1", flow.node_id)


if __name__ == "__main__":
    unittest.main()
