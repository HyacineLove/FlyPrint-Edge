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
    """Process-memory holder for one SSO token and its Provider directory."""

    _required_fields = {
        "terminal_session_id", "site_portal_code", "cloud_user_id",
        "external_user_id", "display_name", "providers", "access_token",
        "access_token_expires_at",
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
            base_url = str(item.get("prp_base_url") or "").strip().rstrip("/")
            parsed = urlparse(base_url)
            if (not provider_id or not display_name or provider_id in result or
                    parsed.scheme not in {"http", "https"} or not parsed.netloc or
                    parsed.username or parsed.password):
                return None
            result[provider_id] = {"provider_id": provider_id, "display_name": display_name, "prp_base_url": base_url}
        return result

    def bind(self, active_terminal_session_id: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("terminal_session_id") != active_terminal_session_id:
            return False
        required = self._required_fields - {"providers"}
        if not required.issubset(payload) or not all(str(payload.get(field) or "").strip() for field in required):
            return False
        providers = self._providers(payload.get("providers"))
        # Legacy in-process test callers may still create a session from a
        # scalar context. No Site Portal response or Edge HTTP route exposes it.
        if not providers and str(payload.get("prp_base_url") or "").strip():
            providers = self._providers([{"provider_id": "default", "display_name": "默认文件库", "prp_base_url": payload["prp_base_url"]}])
        expires_at = _parse_utc_timestamp(payload.get("access_token_expires_at"))
        if not providers or not expires_at or expires_at <= datetime.now(timezone.utc):
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
                "providers": providers,
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
                self._active = None
                return {"active": False}
            return {
                "active": True, "terminal_session_id": self._active["terminal_session_id"],
                "site_portal_code": self._active["site_portal_code"],
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
            expires_at = _parse_utc_timestamp(self._active.get("access_token_expires_at"))
            if not expires_at or expires_at <= datetime.now(timezone.utc):
                self._active = None
                return None
            providers = self._active["providers"]
            selected = providers.get(provider_id) if provider_id else next(iter(providers.values()), None)
            if not selected:
                return None
            return {"prp_base_url": selected["prp_base_url"], "access_token": self._active["access_token"], "provider_id": selected["provider_id"]}

    def clear(self, terminal_session_id: Optional[str] = None) -> bool:
        with self._lock:
            if not self._active:
                return False
            if terminal_session_id and self._active.get("terminal_session_id") != terminal_session_id:
                return False
            self._active = None
            return True
