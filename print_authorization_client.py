"""Edge 发起 Site Portal 打印授权所需的最小 Cloud 客户端。"""

from typing import Any

import requests


class PrintAuthorizationTransportError(RuntimeError):
    """授权结果不明确，调用方只能使用原 confirmation_id 重试。"""


class PrintAuthorizationClient:
    def __init__(self, base_url: str, node_id: str, auth_client, timeout: int = 10, verify_ssl: bool = True):
        self.base_url = str(base_url or "").rstrip("/")
        self.node_id = str(node_id or "")
        self.auth_client = auth_client
        self.timeout = timeout
        self.verify_ssl = bool(verify_ssl)

    def authorize(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = self.auth_client.get_auth_headers()
        if not headers.get("Authorization"):
            raise PrintAuthorizationTransportError("node authorization is unavailable")

        url = f"{self.base_url}/api/v1/edge/{self.node_id}/print-authorizations"
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            result = response.json()
        except Exception as exc:
            raise PrintAuthorizationTransportError(
                "cloud print authorization result is unknown"
            ) from exc

        if not isinstance(result, dict):
            raise PrintAuthorizationTransportError("invalid cloud authorization response")
        if response.status_code == 200 and result.get("allowed") is True:
            return result
        if 400 <= response.status_code < 500 and result.get("allowed") is False:
            return result
        raise PrintAuthorizationTransportError(
            f"unexpected cloud authorization status: {response.status_code}"
        )
