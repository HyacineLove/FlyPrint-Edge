"""Strict PRP HTTP client used only with an active Site Portal session."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from email.message import Message
from email.utils import collapse_rfc2231_value
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit
import zipfile

import requests
from requests.adapters import HTTPAdapter

from edge_limits import DEFAULT_MAX_PRP_DOWNLOAD_BYTES


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_LIST_RESPONSE_BYTES = 1 << 20
_MEDIA_EXTENSIONS = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
}


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
        total_timeout: float = 35.0,
        max_download_bytes: int = DEFAULT_MAX_PRP_DOWNLOAD_BYTES,
    ) -> None:
        if (
            connect_timeout <= 0
            or read_timeout <= 0
            or total_timeout <= 0
            or max_download_bytes <= 0
        ):
            raise ValueError("PRP client limits must be positive")
        self._session = session or requests.Session()
        if session is None:
            adapter = HTTPAdapter(pool_connections=2, pool_maxsize=4, max_retries=0)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
        self._timeout = (connect_timeout, read_timeout)
        self._list_total_timeout = total_timeout
        self._max_download_bytes = max_download_bytes

    @staticmethod
    def _failure_code(response, fallback: str) -> str:
        if response.status_code != 401:
            return fallback
        try:
            body = response.json()
            code = body.get("error", {}).get("code") if isinstance(body, dict) else ""
            if isinstance(code, str) and code in {"auth_required", "token_expired", "token_invalid"}:
                return code
        except (ValueError, requests.RequestException):
            pass
        return "auth_required"

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
        started_at = time.monotonic()
        response = None
        try:
            response = self._session.get(
                base_url + "/api/v1/files",
                params={"page": page, "page_size": page_size},
                headers={"Authorization": "Bearer " + token},
                timeout=(
                    min(self._timeout[0], self._list_total_timeout),
                    min(self._timeout[1], self._list_total_timeout),
                ),
                stream=True,
            )
        except requests.RequestException as exc:
            raise PRPClientError("prp_unavailable") from exc
        try:
            if response.status_code != 200:
                raise PRPClientError(self._failure_code(response, "prp_list_failed"))
            declared_length = response.headers.get("Content-Length")
            if declared_length:
                try:
                    if int(declared_length) > _MAX_LIST_RESPONSE_BYTES:
                        raise PRPClientError("prp_response_too_large")
                except ValueError as exc:
                    raise PRPClientError("invalid_prp_response") from exc

            body = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if time.monotonic() - started_at > self._list_total_timeout:
                    raise PRPClientError("prp_list_timeout")
                if not chunk:
                    continue
                body.extend(chunk)
                if len(body) > _MAX_LIST_RESPONSE_BYTES:
                    raise PRPClientError("prp_response_too_large")
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise PRPClientError("invalid_prp_response") from exc
            self._validate_file_list(payload, page, page_size)
            return payload
        except requests.RequestException as exc:
            raise PRPClientError("prp_unavailable") from exc
        finally:
            response.close()

    def download_file(
        self,
        access_context: Dict[str, Any],
        file_id: str,
        destination: Path,
        max_file_size_bytes: int | None = None,
    ) -> Dict[str, Any]:
        if not isinstance(file_id, str) or not _FILE_ID_RE.fullmatch(file_id):
            raise PRPClientError("file_not_found")
        if not isinstance(destination, Path) or not destination.parent.is_dir():
            raise PRPClientError("invalid_destination")
        edge_limit = (
            max_file_size_bytes
            if isinstance(max_file_size_bytes, int)
            and not isinstance(max_file_size_bytes, bool)
            and max_file_size_bytes > 0
            else None
        )
        max_download_bytes = min(self._max_download_bytes, edge_limit) if edge_limit else self._max_download_bytes
        size_limit_code = "edge_file_size_exceeded" if edge_limit and edge_limit <= self._max_download_bytes else "file_too_large"
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
                    "file_not_found" if response.status_code == 404 else self._failure_code(response, "prp_download_failed")
                )
            declared_length = self._required_length(response, max_download_bytes, size_limit_code)
            declared_hash = response.headers.get("X-Content-SHA256", "")
            if not _SHA256_RE.fullmatch(declared_hash):
                raise PRPClientError("invalid_prp_response")
            media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
            name = self._download_name(response.headers.get("Content-Disposition", ""))
            extension = Path(name).suffix.lower()
            if extension not in _MEDIA_EXTENSIONS.get(media_type, set()):
                raise PRPClientError("unsupported_file_type")

            digest = hashlib.sha256()
            size = 0
            try:
                with partial.open("xb") as output:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > max_download_bytes:
                            raise PRPClientError(size_limit_code)
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
            self._validate_download_content(partial, media_type)
            published = destination.with_suffix(extension)
            os.replace(partial, published)
            return {
                "id": file_id,
                "name": name,
                "media_type": media_type,
                "size": size,
                "sha256": declared_hash,
                "path": str(published),
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
            or Path(item["name"]).suffix.lower()
            not in _MEDIA_EXTENSIONS.get(item["media_type"], set())
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

    def _required_length(self, response: requests.Response, max_download_bytes: int, size_limit_code: str) -> int:
        raw = response.headers.get("Content-Length", "")
        try:
            length = int(raw)
        except ValueError as exc:
            raise PRPClientError("invalid_prp_response") from exc
        if length < 0:
            raise PRPClientError("invalid_prp_response")
        if length > max_download_bytes:
            raise PRPClientError(size_limit_code)
        return length

    @staticmethod
    def _download_name(disposition: str) -> str:
        message = Message()
        message["Content-Disposition"] = disposition
        name = message.get_param("filename", header="Content-Disposition")
        if isinstance(name, tuple):
            try:
                name = collapse_rfc2231_value(name, errors="strict")
            except (LookupError, UnicodeError) as exc:
                raise PRPClientError("invalid_prp_response") from exc
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise PRPClientError("invalid_prp_response")
        return name

    @staticmethod
    def _validate_download_content(path: Path, media_type: str) -> None:
        if media_type == "application/pdf":
            with path.open("rb") as source:
                signature = source.read(5)
            if signature != b"%PDF-":
                raise PRPClientError("unsupported_file_type")
            return
        if media_type == "image/png":
            with path.open("rb") as source:
                signature = source.read(8)
            if signature != b"\x89PNG\r\n\x1a\n":
                raise PRPClientError("unsupported_file_type")
            return
        if media_type == "image/jpeg":
            with path.open("rb") as source:
                signature = source.read(3)
            if signature != b"\xff\xd8\xff":
                raise PRPClientError("unsupported_file_type")
            return
        if media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            try:
                with zipfile.ZipFile(path) as archive:
                    names = set(archive.namelist())
            except (OSError, zipfile.BadZipFile) as exc:
                raise PRPClientError("unsupported_file_type") from exc
            if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                raise PRPClientError("unsupported_file_type")
            return
        raise PRPClientError("unsupported_file_type")
