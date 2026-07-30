"""Strict PRP HTTP client used only with an active Site Portal session."""

from __future__ import annotations

import hashlib
import os
import re
from email.message import Message
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter

from edge_limits import DEFAULT_MAX_PRP_DOWNLOAD_BYTES


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class PRPClientError(RuntimeError):
    """A stable PRP protocol or transport failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class PRPClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        max_download_bytes: int = DEFAULT_MAX_PRP_DOWNLOAD_BYTES,
    ) -> None:
        if connect_timeout <= 0 or read_timeout <= 0 or max_download_bytes <= 0:
            raise ValueError("PRP client limits must be positive")
        self._session = session or requests.Session()
        if session is None:
            adapter = HTTPAdapter(pool_connections=2, pool_maxsize=4, max_retries=0)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
        self._timeout = (connect_timeout, read_timeout)
        self._max_download_bytes = max_download_bytes

    def list_files(
        self, access_context: Dict[str, Any], page: int, page_size: int
    ) -> Dict[str, Any]:
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise PRPClientError("invalid_pagination")
        if (
            not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or page_size < 1
            or page_size > 50
        ):
            raise PRPClientError("invalid_pagination")
        base_url, token = self._access(access_context)
        try:
            response = self._session.get(
                base_url + "/api/v1/files",
                params={"page": page, "page_size": page_size},
                headers={"Authorization": "Bearer " + token},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise PRPClientError("prp_unavailable") from exc
        if response.status_code != 200:
            raise PRPClientError("prp_list_failed")
        if len(response.content) > 1 << 20:
            raise PRPClientError("prp_response_too_large")
        try:
            payload = response.json()
        except ValueError as exc:
            raise PRPClientError("invalid_prp_response") from exc
        self._validate_file_list(payload, page, page_size)
        return payload

    def download_file(
        self, access_context: Dict[str, Any], file_id: str, destination: Path
    ) -> Dict[str, Any]:
        if not isinstance(file_id, str) or not _FILE_ID_RE.fullmatch(file_id):
            raise PRPClientError("file_not_found")
        if not isinstance(destination, Path) or not destination.parent.is_dir():
            raise PRPClientError("invalid_destination")
        base_url, token = self._access(access_context)
        partial = destination.with_name(destination.name + ".part")
        partial.unlink(missing_ok=True)
        response = None
        try:
            response = self._session.get(
                base_url + "/api/v1/files/" + file_id + "/content",
                headers={"Authorization": "Bearer " + token},
                timeout=self._timeout,
                stream=True,
            )
            if response.status_code != 200:
                raise PRPClientError(
                    "file_not_found" if response.status_code == 404 else "prp_download_failed"
                )
            declared_length = self._required_length(response)
            declared_hash = response.headers.get("X-Content-SHA256", "")
            if not _SHA256_RE.fullmatch(declared_hash):
                raise PRPClientError("invalid_prp_response")
            media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
            if media_type != "application/pdf":
                raise PRPClientError("unsupported_file_type")
            name = self._download_name(response.headers.get("Content-Disposition", ""))

            digest = hashlib.sha256()
            size = 0
            try:
                with partial.open("xb") as output:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > self._max_download_bytes:
                            raise PRPClientError("file_too_large")
                        output.write(chunk)
                        digest.update(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            except requests.RequestException as exc:
                if size != declared_length:
                    raise PRPClientError("content_length_mismatch") from exc
                raise PRPClientError("prp_download_failed") from exc
            if size != declared_length:
                raise PRPClientError("content_length_mismatch")
            if digest.hexdigest() != declared_hash:
                raise PRPClientError("content_hash_mismatch")
            os.replace(partial, destination)
            return {
                "id": file_id,
                "name": name,
                "media_type": media_type,
                "size": size,
                "sha256": declared_hash,
                "path": str(destination),
            }
        except PRPClientError:
            partial.unlink(missing_ok=True)
            raise
        except (OSError, requests.RequestException) as exc:
            partial.unlink(missing_ok=True)
            raise PRPClientError("prp_download_failed") from exc
        finally:
            if response is not None:
                response.close()

    @staticmethod
    def _access(access_context: Dict[str, Any]) -> tuple[str, str]:
        if not isinstance(access_context, dict):
            raise PRPClientError("portal_session_invalid")
        raw_base = access_context.get("prp_base_url")
        token = access_context.get("access_token")
        if not isinstance(raw_base, str) or not isinstance(token, str) or not token:
            raise PRPClientError("portal_session_invalid")
        parsed = urlsplit(raw_base.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise PRPClientError("invalid_prp_base_url")
        base_url = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
        )
        return base_url, token

    @staticmethod
    def _validate_file_list(payload: Any, page: int, page_size: int) -> None:
        if not isinstance(payload, dict) or set(payload) != {
            "items", "page", "page_size", "total"
        }:
            raise PRPClientError("invalid_prp_response")
        if (
            payload["page"] != page
            or isinstance(payload["page"], bool)
            or payload["page_size"] != page_size
            or isinstance(payload["page_size"], bool)
            or not isinstance(payload["total"], int)
            or isinstance(payload["total"], bool)
            or payload["total"] < 0
            or not isinstance(payload["items"], list)
        ):
            raise PRPClientError("invalid_prp_response")
        for item in payload["items"]:
            PRPClient._validate_file_item(item)

    @staticmethod
    def _validate_file_item(item: Any) -> None:
        required = {
            "id", "name", "media_type", "size", "sha256",
            "created_at", "expires_at", "last_downloaded_at",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise PRPClientError("invalid_prp_response")
        if (
            not isinstance(item["id"], str)
            or not _FILE_ID_RE.fullmatch(item["id"])
            or not isinstance(item["name"], str)
            or not item["name"]
            or item["media_type"] != "application/pdf"
            or not isinstance(item["size"], int)
            or isinstance(item["size"], bool)
            or item["size"] < 0
            or not isinstance(item["sha256"], str)
            or not _SHA256_RE.fullmatch(item["sha256"])
            or not isinstance(item["created_at"], str)
            or not isinstance(item["expires_at"], str)
            or (
                item["last_downloaded_at"] is not None
                and not isinstance(item["last_downloaded_at"], str)
            )
        ):
            raise PRPClientError("invalid_prp_response")

    def _required_length(self, response: requests.Response) -> int:
        raw = response.headers.get("Content-Length", "")
        try:
            length = int(raw)
        except ValueError as exc:
            raise PRPClientError("invalid_prp_response") from exc
        if length < 0:
            raise PRPClientError("invalid_prp_response")
        if length > self._max_download_bytes:
            raise PRPClientError("file_too_large")
        return length

    @staticmethod
    def _download_name(disposition: str) -> str:
        message = Message()
        message["Content-Disposition"] = disposition
        name = message.get_param("filename", header="Content-Disposition")
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise PRPClientError("invalid_prp_response")
        return name
