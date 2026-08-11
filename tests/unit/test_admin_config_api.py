import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import main


class DummyConfig:
    def __init__(self):
        self.config = {"managed_printers": [], "cloud": {"base_url": "", "credential_blob": "", "node_name": "", "location": "", "heartbeat_interval": 30}, "settings": {}, "network": {"bind_address": "127.0.0.1", "port": 7860}}
    def get_full_config(self): return self.config
    def replace_full_config(self, value): self.config = value
    def save_config(self): pass


class DummyPrinterManager:
    def __init__(self): self.config = DummyConfig()


class DummyCloud:
    def __init__(self): self.node_id = None; self.calls = []
    def activate(self, base_url, activation_code):
        self.calls.append((base_url, activation_code)); self.node_id = "node-1"; return {"success": True, "node_id": self.node_id}
    def get_status(self): return {"configured": False, "registered": False, "node_id": None, "websocket": {"connected": False}}
    def unbind(self):
        self.calls.append(("unbind",)); self.node_id = None
        return {"success": True, "message": "已解除本机绑定"}


class Request:
    def __init__(self, payload): self.payload = payload
    async def json(self): return self.payload


class AdminConfigApiTests(unittest.TestCase):
    def test_public_config_does_not_return_credentials(self):
        manager = DummyPrinterManager()
        manager.config.config["cloud"].update({"credential_blob": "opaque", "node_id": "node-1", "client_secret": "legacy"})
        with patch.object(main, "printer_manager", manager):
            payload = asyncio.run(main.get_admin_config())
        self.assertTrue(payload["cloud"]["activated"])
        self.assertNotIn("credential_blob", payload["cloud"])
        self.assertNotIn("client_secret", payload["cloud"])

    def test_activation_delegates_to_cloud_service(self):
        cloud = DummyCloud()
        with patch.object(main, "cloud_service", cloud), patch.object(main, "broadcast_sse_event", new=AsyncMock()):
            response = asyncio.run(main.activate_cloud_node(Request({"base_url": "http://cloud.example.com", "activation_code": "ABC"})))
        self.assertTrue(response["success"])
        self.assertEqual(cloud.calls, [("http://cloud.example.com", "ABC")])

    def test_unbind_delegates_to_cloud_service(self):
        cloud = DummyCloud()
        with patch.object(main, "cloud_service", cloud), patch.object(main, "broadcast_sse_event", new=AsyncMock()):
            response = asyncio.run(main.unbind_cloud_node())
        self.assertTrue(response["success"])
        self.assertEqual(cloud.calls, [("unbind",)])

    def test_unbind_clears_active_interactive_resources(self):
        cloud = DummyCloud()
        interactive = MagicMock()
        interactive.get_active_session.return_value = {"session_id": "session-1"}
        selections = MagicMock()
        portal = MagicMock()
        file_manager = MagicMock()
        with (
            patch.object(main, "cloud_service", cloud),
            patch.object(main, "interactive_session_manager", interactive),
            patch.object(main, "prp_file_selection_manager", selections),
            patch.object(main, "portal_session_manager", portal),
            patch.object(main, "get_file_manager", return_value=file_manager),
            patch.object(main, "_report_terminal_session_state"),
            patch.object(main, "broadcast_sse_event", new=AsyncMock()),
        ):
            response = asyncio.run(main.unbind_cloud_node())

        self.assertTrue(response["success"])
        interactive.clear_session.assert_called_once_with("session-1")
        selections.clear_session.assert_called_once_with("session-1")
        portal.clear.assert_called_once_with("session-1")
        file_manager.release_preview_session.assert_called_once_with("session-1", reason="cloud_unbind")


if __name__ == "__main__":
    unittest.main()
