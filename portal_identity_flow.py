import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from portal_session import _parse_utc_timestamp
from site_portal_client import SitePortalProtocolError


logger = logging.getLogger(__name__)


class PortalIdentityFlow:
    def __init__(self, interactive_sessions, portal_sessions, site_portal_client):
        self._interactive_sessions = interactive_sessions
        self._portal_sessions = portal_sessions
        self._client = site_portal_client

    def handle_ready(self, payload: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        required = {
            "site_portal_code",
            "claim_base_url",
            "claim_code",
            "terminal_session_id",
            "cloud_user_id",
            "expires_at",
        }
        if not required.issubset(payload) or not all(str(payload.get(field) or "").strip() for field in required):
            return None
        active = self._interactive_sessions.get_active_session() or {}
        session_id = str(payload["terminal_session_id"])
        if active.get("session_id") != session_id:
            return None
        ticket_hash = active.get("terminal_ticket_hash")
        if not isinstance(ticket_hash, str) or len(ticket_hash) != 64:
            return None
        ready_expires_at = _parse_utc_timestamp(payload.get("expires_at"))
        if not ready_expires_at or ready_expires_at <= datetime.now(timezone.utc):
            return None
        portal_display_name = str(payload.get("site_portal_display_name") or "").strip()
        if not portal_display_name:
            portal_display_name = str(payload["site_portal_code"])
            logger.warning(
                "Cloud portal_session_ready missing site_portal_display_name; using site_portal_code=%s until Cloud is upgraded",
                portal_display_name,
            )

        claimed = self._client.redeem(
            str(payload["claim_base_url"]),
            str(payload["claim_code"]),
            str(payload["site_portal_code"]),
            str(node_id or ""),
            session_id,
        )
        bound_payload = {
            **claimed,
            "site_portal_display_name": portal_display_name,
            "terminal_session_id": session_id,
            "cloud_user_id": str(payload["cloud_user_id"]),
        }
        if not self._portal_sessions.bind(session_id, bound_payload):
            raise SitePortalProtocolError("领取结果无法绑定当前终端会话")
        if not self._interactive_sessions.bind_portal_identity({
            "terminal_session_id": session_id,
            "site_portal_code": bound_payload["site_portal_code"],
            "site_portal_display_name": bound_payload["site_portal_display_name"],
            "cloud_user_id": bound_payload["cloud_user_id"],
            "external_user_id": bound_payload["external_user_id"],
            "display_name": bound_payload["display_name"],
        }):
            self._portal_sessions.clear(session_id)
            raise SitePortalProtocolError("当前终端会话已变化")
        return self._portal_sessions.snapshot()
