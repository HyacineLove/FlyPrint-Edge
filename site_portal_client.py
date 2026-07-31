from typing import Any, Dict
from urllib.parse import urlparse

import requests

from portal_session import _parse_utc_timestamp


class SitePortalProtocolError(RuntimeError):
    pass


class SitePortalClient:
    def __init__(self, session=None, timeout: float = 8.0):
        self._session = session or requests.Session()
        self._timeout = timeout

    @staticmethod
    def _claim_url(claim_base_url: str) -> str:
        raw = str(claim_base_url or "").strip()
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise SitePortalProtocolError("Site Portal 领取地址无效")
        return raw.rstrip("/") + "/api/claims/redeem"

    def redeem(
        self,
        claim_base_url: str,
        claim_code: str,
        site_portal_code: str,
        node_id: str,
        terminal_session_id: str,
    ) -> Dict[str, Any]:
        response = self._session.post(
            self._claim_url(claim_base_url),
            json={
                "claim_code": claim_code,
                "site_portal_code": site_portal_code,
                "node_id": node_id,
                "terminal_session_id": terminal_session_id,
            },
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise SitePortalProtocolError(f"Site Portal 拒绝领取: HTTP {response.status_code}")
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise SitePortalProtocolError("Site Portal 领取响应不是有效 JSON") from exc
        required = {
            "site_portal_code",
            "external_user_id",
            "display_name",
            "prp_base_url",
            "access_token",
            "access_token_expires_at",
        }
        if not isinstance(payload, dict) or not required.issubset(payload):
            raise SitePortalProtocolError("Site Portal 领取响应不完整")
        if payload.get("site_portal_code") != site_portal_code:
            raise SitePortalProtocolError("Site Portal 领取响应来源不匹配")
        prp = urlparse(str(payload.get("prp_base_url") or ""))
        if prp.scheme not in {"http", "https"} or not prp.netloc or prp.username or prp.password:
            raise SitePortalProtocolError("PRP 地址无效")
        if not _parse_utc_timestamp(payload.get("access_token_expires_at")):
            raise SitePortalProtocolError("PRP 访问凭证有效期无效")
        if not all(str(payload.get(field) or "").strip() for field in required):
            raise SitePortalProtocolError("Site Portal 领取响应包含空字段")
        return dict(payload)
