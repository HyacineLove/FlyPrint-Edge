import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse


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
    """Process-memory holder for one Site Portal file session and Provider directory."""

    _required_fields = {
        "terminal_session_id", "site_portal_code", "cloud_user_id",
        "external_user_id", "display_name", "providers", "claim_base_url",
        "file_session_token", "file_session_expires_at",
    }

    def __init__(self):
        self._lock = threading.RLock()
        self._active: Optional[Dict[str, Any]] = None

    @staticmethod
    def _providers(value: Any) -> Optional[Dict[str, Dict[str, str]]]:
        if not isinstance(value, list) or not value:
            return None
        result: Dict[str, Dict[str, str]] = {}
        for item in value:
            if not isinstance(item, dict):
                return None
            provider_id = str(item.get("provider_id") or "").strip()
            display_name = str(item.get("display_name") or "").strip()
            if not provider_id or not display_name or provider_id in result:
                return None
            if item.get("prp_base_url") or item.get("file_base_url"):
                return None
            result[provider_id] = {"provider_id": provider_id, "display_name": display_name}
        return result

    def bind(self, active_terminal_session_id: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("terminal_session_id") != active_terminal_session_id:
            return False
        required = self._required_fields - {"providers"}
        if not required.issubset(payload) or not all(str(payload.get(field) or "").strip() for field in required):
            return False
        if payload.get("access_token"):
            return False
        providers = self._providers(payload.get("providers"))
        expires_at = _parse_utc_timestamp(payload.get("file_session_expires_at"))
        parsed = urlparse(str(payload.get("claim_base_url") or "").strip())
        if (
            not providers
            or not expires_at
            or expires_at <= datetime.now(timezone.utc)
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            return False
        claim_base_url = str(payload["claim_base_url"]).strip().rstrip("/")
        with self._lock:
            if self._active and self._active.get("terminal_session_id") != active_terminal_session_id:
                return False
            self._active = {
                "terminal_session_id": active_terminal_session_id,
                "site_portal_code": str(payload["site_portal_code"]),
                "site_portal_display_name": str(payload.get("site_portal_display_name") or "").strip(),
                "cloud_user_id": str(payload["cloud_user_id"]),
                "external_user_id": str(payload["external_user_id"]),
                "display_name": str(payload["display_name"]),
                "providers": providers,
                "claim_base_url": claim_base_url,
                "file_session_token": str(payload["file_session_token"]),
                "file_session_expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            }
            return True

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            if not self._active:
                return {"active": False}
            expires_at = _parse_utc_timestamp(self._active.get("file_session_expires_at"))
            if not expires_at or expires_at <= datetime.now(timezone.utc):
                self._active = None
                return {"active": False}
            return {
                "active": True, "terminal_session_id": self._active["terminal_session_id"],
                "site_portal_code": self._active["site_portal_code"],
                "site_portal_display_name": self._active["site_portal_display_name"],
                "cloud_user_id": self._active["cloud_user_id"],
                "external_user_id": self._active["external_user_id"],
                "display_name": self._active["display_name"],
                "providers": [
                    {"provider_id": provider["provider_id"], "display_name": provider["display_name"]}
                    for provider in self._active["providers"].values()
                ],
            }

    def get_access_context(self, terminal_session_id: str, provider_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._active or self._active.get("terminal_session_id") != terminal_session_id:
                return None
            expires_at = _parse_utc_timestamp(self._active.get("file_session_expires_at"))
            if not expires_at or expires_at <= datetime.now(timezone.utc):
                self._active = None
                return None
            providers = self._active["providers"]
            selected = providers.get(provider_id) if provider_id else next(iter(providers.values()), None)
            if not selected:
                return None
            return {
                "portal_base_url": self._active["claim_base_url"],
                "file_session_token": self._active["file_session_token"],
                "provider_id": selected["provider_id"],
            }

    def clear(self, terminal_session_id: Optional[str] = None) -> bool:
        with self._lock:
            if not self._active:
                return False
            if terminal_session_id and self._active.get("terminal_session_id") != terminal_session_id:
                return False
            self._active = None
            return True
