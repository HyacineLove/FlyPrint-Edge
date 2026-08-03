import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _parse_utc_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


class PortalSessionManager:
    """Process-memory holder for the active Site Portal identity and PRP credential."""

    _required_fields = {
        "terminal_session_id",
        "site_portal_code",
        "cloud_user_id",
        "external_user_id",
        "display_name",
        "prp_base_url",
        "access_token",
        "access_token_expires_at",
    }

    def __init__(self):
        self._lock = threading.RLock()
        self._active: Optional[Dict[str, Any]] = None

    def bind(self, active_terminal_session_id: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict) or not self._required_fields.issubset(payload):
            return False
        if payload.get("terminal_session_id") != active_terminal_session_id:
            return False
        if not all(str(payload.get(field) or "").strip() for field in self._required_fields):
            return False
        expires_at = _parse_utc_timestamp(payload.get("access_token_expires_at"))
        if not expires_at or expires_at <= datetime.now(timezone.utc):
            return False

        with self._lock:
            if self._active and self._active.get("terminal_session_id") != active_terminal_session_id:
                return False
            self._active = {
                "terminal_session_id": active_terminal_session_id,
                "site_portal_code": str(payload["site_portal_code"]),
                "cloud_user_id": str(payload["cloud_user_id"]),
                "external_user_id": str(payload["external_user_id"]),
                "display_name": str(payload["display_name"]),
                "prp_base_url": str(payload["prp_base_url"]).rstrip("/"),
                "access_token": str(payload["access_token"]),
                "access_token_expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            }
            return True

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            if not self._active:
                return {"active": False}
            expires_at = _parse_utc_timestamp(self._active.get("access_token_expires_at"))
            if not expires_at or expires_at <= datetime.now(timezone.utc):
                # 凭证已过期：与 get_access_context 一致地清空会话，避免 UI 显示已登录而实际不可用
                self._active = None
                return {"active": False}
            return {
                "active": True,
                "terminal_session_id": self._active["terminal_session_id"],
                "site_portal_code": self._active["site_portal_code"],
                "cloud_user_id": self._active["cloud_user_id"],
                "external_user_id": self._active["external_user_id"],
                "display_name": self._active["display_name"],
            }

    def get_access_context(self, terminal_session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._active or self._active.get("terminal_session_id") != terminal_session_id:
                return None
            expires_at = _parse_utc_timestamp(self._active.get("access_token_expires_at"))
            if not expires_at or expires_at <= datetime.now(timezone.utc):
                self._active = None
                return None
            return deepcopy(self._active)

    def clear(self, terminal_session_id: Optional[str] = None) -> bool:
        with self._lock:
            if not self._active:
                return False
            if terminal_session_id and self._active.get("terminal_session_id") != terminal_session_id:
                return False
            self._active = None
            return True
