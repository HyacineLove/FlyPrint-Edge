from typing import Any, Dict
from urllib.parse import urlparse

import requests

from portal_session import _parse_utc_timestamp


class SitePortalProtocolError(RuntimeError):
    pass


class SitePortalClient:
    def __init__(self, session=None, timeout: float = 8.0, verify_ssl: bool = True):
        self._session = session or requests.Session()
        self._timeout = timeout
        self.verify_ssl = bool(verify_ssl)

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
        try:
            response = self._session.post(
                self._claim_url(claim_base_url),
                json={
                    "claim_code": claim_code,
                    "site_portal_code": site_portal_code,
                    "node_id": node_id,
                    "terminal_session_id": terminal_session_id,
                },
                verify=self.verify_ssl,
                timeout=self._timeout,
                # Claim code is a one-time bearer proof.  A 307/308 redirect
                # would replay the complete POST body to another origin.
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise SitePortalProtocolError("Site Portal 领取请求失败") from exc
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
            "providers",
            "file_session_token",
            "file_session_expires_at",
        }
        if not isinstance(payload, dict) or not required.issubset(payload):
            raise SitePortalProtocolError("Site Portal 领取响应不完整")
        if payload.get("site_portal_code") != site_portal_code:
            raise SitePortalProtocolError("Site Portal 领取响应来源不匹配")
        providers = payload.get("providers")
        if not isinstance(providers, list) or not providers:
            raise SitePortalProtocolError("PRP Provider 列表无效")
        seen = set()
        for provider in providers:
            if not isinstance(provider, dict):
                raise SitePortalProtocolError("PRP Provider 列表无效")
            provider_id = str(provider.get("provider_id") or "").strip()
            display_name = str(provider.get("display_name") or "").strip()
            if not provider_id or provider_id in seen or not display_name:
                raise SitePortalProtocolError("PRP Provider 列表无效")
            if provider.get("prp_base_url") or provider.get("file_base_url"):
                raise SitePortalProtocolError("PRP Provider 地址不得下发给 Edge")
            seen.add(provider_id)
        if not _parse_utc_timestamp(payload.get("file_session_expires_at")):
            raise SitePortalProtocolError("文件会话有效期无效")
        if not all(str(payload.get(field) or "").strip() for field in required - {"providers"}):
            raise SitePortalProtocolError("Site Portal 领取响应包含空字段")
        if payload.get("access_token"):
            raise SitePortalProtocolError("领取响应不得包含 SSO 访问令牌")
        return dict(payload)

    def end_session(self, portal_base_url: str, file_session_token: str) -> int:
        raw = str(portal_base_url or "").strip().rstrip("/")
        parsed = urlparse(raw)
        token = str(file_session_token or "").strip()
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or not token:
            raise SitePortalProtocolError("Site Portal 会话结束地址无效")
        try:
            response = self._session.post(
                raw + "/api/session/end",
                headers={"Authorization": f"Bearer {token}"},
                verify=self.verify_ssl,
                timeout=self._timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise SitePortalProtocolError("Site Portal 结束会话失败") from exc
        if response.status_code not in {204, 401}:
            raise SitePortalProtocolError(f"Site Portal 拒绝结束会话: HTTP {response.status_code}")
        return response.status_code
