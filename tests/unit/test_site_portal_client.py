import unittest
import requests

from site_portal_client import SitePortalClient, SitePortalProtocolError


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class FailingSession:
    def post(self, url, **kwargs):
        raise requests.ConnectionError("offline")


class SitePortalClientTests(unittest.TestCase):
    def test_redeem_posts_bound_context_once(self):
        session = FakeSession(FakeResponse(payload={
            "site_portal_code": "official",
            "external_user_id": "external-user-1",
            "display_name": "张老师",
            "providers": [{"provider_id": "prp-a", "display_name": "文件库 A", "prp_base_url": "https://prp.example.test"}],
            "access_token": "private-token",
            "access_token_expires_at": "2099-07-30T12:05:00Z",
        }))
        client = SitePortalClient(session=session, timeout=3)

        result = client.redeem(
            "https://portal.example.test",
            "claim-code-1",
            "official",
            "edge-1",
            "session-1",
        )

        self.assertEqual("external-user-1", result["external_user_id"])
        self.assertEqual(1, len(session.calls))
        url, options = session.calls[0]
        self.assertEqual("https://portal.example.test/api/claims/redeem", url)
        self.assertEqual("claim-code-1", options["json"]["claim_code"])
        self.assertEqual(3, options["timeout"])

    def test_redeem_maps_network_error_to_protocol_error(self):
        client = SitePortalClient(session=FailingSession())
        with self.assertRaises(SitePortalProtocolError):
            client.redeem("https://portal.example.test", "claim-code-1", "official", "edge-1", "session-1")

    def test_redeem_rejects_incomplete_response(self):
        client = SitePortalClient(session=FakeSession(FakeResponse(payload={
            "external_user_id": "external-user-1",
        })))

        with self.assertRaises(SitePortalProtocolError):
            client.redeem(
                "https://portal.example.test", "claim-code-1",
                "official", "edge-1", "session-1",
            )

    def test_redeem_rejects_non_http_claim_base_without_request(self):
        session = FakeSession(FakeResponse())
        client = SitePortalClient(session=session)

        with self.assertRaises(SitePortalProtocolError):
            client.redeem(
                "file:///tmp/portal", "claim-code-1",
                "official", "edge-1", "session-1",
            )

        self.assertEqual([], session.calls)


if __name__ == "__main__":
    unittest.main()
