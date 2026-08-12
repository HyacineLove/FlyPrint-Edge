import threading
import time
import uuid
import hashlib
from copy import deepcopy
from typing import Any, Dict, Optional


class InteractiveSessionManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._active_session: Optional[Dict[str, Any]] = None
        self._qr_generation = 0

    def start_session(
        self,
        upload_token: Optional[str] = None,
        terminal_ticket: Optional[str] = None,
        entry_type: str = "official",
    ) -> Dict[str, Any]:
        with self._lock:
            self._qr_generation += 1
            session_id = uuid.uuid4().hex
            self._active_session = {
                "session_id": session_id,
                "upload_token": upload_token,
                "terminal_ticket_hash": hashlib.sha256(terminal_ticket.encode("utf-8")).hexdigest() if terminal_ticket else None,
                "entry_type": entry_type,
                "qr_generation": self._qr_generation,
                "site_portal_code": None,
                "site_portal_display_name": None,
                "cloud_user_id": None,
                "external_user_id": None,
                "display_name": None,
                "state": "awaiting_preview",
                "file_id": None,
                "provider_id": None,
                "source_origin": None,
                "file_url": None,
                "file_name": None,
                "file_type": None,
                "content_hash": None,
                "page_count": None,
                "job_id": None,
                "print_options": None,
                "initial_print_options": None,
                "submitted": False,
                "error_code": None,
                "error_message": None,
                "printer_fault": None,
                "job_status": None,
                "job_message": None,
                "current_page": None,
                "total_pages": None,
                "updated_at": time.time(),
            }
            return deepcopy(self._active_session)

    def bind_entry_ticket(self, session_id: str, ticket: str) -> bool:
        """Bind Cloud-issued T1 to the current QR generation."""
        with self._lock:
            if not self._active_session or self._active_session["session_id"] != session_id or not ticket:
                return False
            self._active_session["terminal_ticket_hash"] = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
            self._active_session["updated_at"] = time.time()
            return True

    def get_active_session(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._active_session:
                return None
            return deepcopy(self._active_session)

    def update_upload_token(self, session_id: str, upload_token: Optional[str]) -> bool:
        with self._lock:
            if not self._active_session or self._active_session["session_id"] != session_id:
                return False
            self._active_session["upload_token"] = upload_token
            self._active_session["updated_at"] = time.time()
            return True

    def bind_prp_file(self, session_id: str, metadata: Dict[str, Any]) -> bool:
        required = {
            "source_origin", "file_id", "file_name", "file_type", "content_hash", "size"
        }
        if not isinstance(metadata, dict) or not required.issubset(metadata):
            return False
        if metadata.get("source_origin") != "prp":
            return False
        with self._lock:
            if not self._active_session or self._active_session["session_id"] != session_id:
                return False
            self._active_session["source_origin"] = "prp"
            self._active_session["provider_id"] = metadata.get("provider_id") or "default"
            self._active_session["file_id"] = metadata["file_id"]
            self._active_session["file_url"] = None
            self._active_session["file_name"] = metadata["file_name"]
            self._active_session["file_type"] = metadata["file_type"]
            self._active_session["content_hash"] = metadata["content_hash"]
            self._active_session["page_count"] = None
            self._active_session["size"] = metadata["size"]
            self._active_session["state"] = "preview_ready"
            self._active_session["submitted"] = False
            self._active_session["error_code"] = None
            self._active_session["error_message"] = None
            self._active_session["updated_at"] = time.time()
            return True

    def set_preview_page_count(self, session_id: str, file_id: str, page_count: int) -> bool:
        """记录 Edge 预览确认的单份页数，供打印授权和结算使用。"""
        if not isinstance(page_count, int) or page_count < 1:
            return False
        with self._lock:
            if (
                not self._active_session
                or self._active_session["session_id"] != session_id
                or self._active_session.get("file_id") != file_id
            ):
                return False
            self._active_session["page_count"] = page_count
            self._active_session["updated_at"] = time.time()
            return True

    def clear_prp_selection(self, session_id: str) -> Optional[str]:
        """清除当前 PRP 文件，但保留已登录的 Site Portal 用户会话。"""
        with self._lock:
            if (
                not self._active_session
                or self._active_session["session_id"] != session_id
                or self._active_session.get("source_origin") != "prp"
            ):
                return None
            file_id = self._active_session.get("file_id")
            if not file_id:
                return None
            for field in (
                "source_origin",
                "provider_id",
                "file_id",
                "file_url",
                "file_name",
                "file_type",
                "content_hash",
                "page_count",
                "size",
                "job_id",
                "print_options",
                "initial_print_options",
                "error_code",
                "error_message",
                "printer_fault",
                "job_status",
                "job_message",
                "current_page",
                "total_pages",
            ):
                self._active_session[field] = None
            self._active_session["submitted"] = False
            self._active_session["state"] = "identity_ready"
            self._active_session["updated_at"] = time.time()
            return file_id

    def bind_portal_identity(self, data: Dict[str, Any]) -> bool:
        """Bind only public identity fields; PRP credentials live in PortalSessionManager."""
        required = {
            "terminal_session_id",
            "site_portal_code",
            "cloud_user_id",
            "external_user_id",
            "display_name",
        }
        if not isinstance(data, dict) or not required.issubset(data):
            return False
        if any(key in data for key in ("access_token", "prp_credential", "cookie", "password")):
            return False
        with self._lock:
            if not self._active_session or self._active_session["session_id"] != data["terminal_session_id"]:
                return False
            for key in ("site_portal_code", "cloud_user_id", "external_user_id", "display_name"):
                value = str(data.get(key) or "").strip()
                if not value:
                    return False
                self._active_session[key] = value
            self._active_session["site_portal_display_name"] = str(data.get("site_portal_display_name") or "").strip()
            self._active_session["entry_type"] = "site_portal"
            self._active_session["state"] = "identity_ready"
            self._active_session["updated_at"] = time.time()
            return True

    def _matches_terminal_context(self, data: Dict[str, Any]) -> bool:
        """Preview/print events must prove they belong to the active kiosk session."""
        if not self._active_session:
            return False
        incoming_session_id = data.get("terminal_session_id")
        if incoming_session_id != self._active_session.get("session_id"):
            return False
        incoming_ticket_hash = data.get("terminal_ticket_hash")
        if not isinstance(incoming_ticket_hash, str) or len(incoming_ticket_hash) != 64:
            return False
        if any(char not in "0123456789abcdef" for char in incoming_ticket_hash):
            return False
        ticket_hash = self._active_session.get("terminal_ticket_hash")
        if ticket_hash and incoming_ticket_hash != ticket_hash:
            return False
        return True
    def apply_occupied(self, data: Dict[str, Any]) -> bool:
        """Bind ticket proof from Cloud terminal_occupied onto the active session.

        Returns True when the session was newly updated (caller should report state).
        Returns False when ignored or already bound to the same ticket (no report).
        """
        with self._lock:
            if not self._active_session:
                return False
            session_id = data.get("terminal_session_id")
            ticket_hash = data.get("terminal_ticket_hash")
            if session_id != self._active_session.get("session_id"):
                return False
            if not isinstance(ticket_hash, str) or len(ticket_hash) != 64:
                return False
            if any(char not in "0123456789abcdef" for char in ticket_hash):
                return False
            already_bound = (
                self._active_session.get("occupied")
                and self._active_session.get("terminal_ticket_hash") == ticket_hash
            )
            if already_bound:
                expires_at = data.get("expires_at")
                if expires_at is not None:
                    self._active_session["occupied_expires_at"] = expires_at
                return False
            self._active_session["terminal_ticket_hash"] = ticket_hash
            expires_at = data.get("expires_at")
            self._active_session["occupied_expires_at"] = expires_at
            self._active_session["occupied"] = True
            self._active_session["updated_at"] = time.time()
            return True

    def clear_occupied(self) -> None:
        with self._lock:
            if not self._active_session:
                return
            self._active_session["occupied"] = False
            self._active_session["occupied_expires_at"] = None
            self._active_session["updated_at"] = time.time()

    def accept_preview_event(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        file_id = data.get("file_id")
        file_url = data.get("file_url")
        if not file_id or not file_url:
            return None

        with self._lock:
            if not self._active_session:
                return None
            if not self._matches_terminal_context(data):
                return None

            current_file_id = self._active_session.get("file_id")
            if current_file_id and current_file_id != file_id:
                return None
            # Same file already bound: keep user-tuned options; suppress SSE remount.
            if current_file_id and current_file_id == file_id:
                return None

            self._active_session["file_id"] = file_id
            self._active_session["file_url"] = file_url
            self._active_session["file_name"] = data.get("file_name")
            self._active_session["file_type"] = data.get("file_type")
            self._active_session["content_hash"] = data.get("content_hash")
            self._active_session["page_count"] = None
            if data.get("terminal_ticket_hash") and not self._active_session.get("terminal_ticket_hash"):
                self._active_session["terminal_ticket_hash"] = data.get("terminal_ticket_hash")
            self._active_session["occupied"] = False
            self._active_session["initial_print_options"] = deepcopy(data.get("print_options") or {})
            self._active_session["state"] = "preview_ready"
            self._active_session["error_code"] = None
            self._active_session["error_message"] = None
            self._active_session["printer_fault"] = None
            self._active_session["job_status"] = None
            self._active_session["job_message"] = None
            self._active_session["current_page"] = None
            self._active_session["total_pages"] = None
            self._active_session["updated_at"] = time.time()

            enriched = deepcopy(data)
            enriched["session_id"] = self._active_session["session_id"]
            return enriched

    def mark_print_submitted(
        self,
        session_id: str,
        file_id: str,
        print_options: Optional[Dict[str, Any]] = None,
    ) -> bool:
        with self._lock:
            if not self._active_session:
                return False
            if self._active_session["session_id"] != session_id:
                return False
            if self._active_session.get("file_id") != file_id:
                return False
            if self._active_session.get("submitted"):
                return False

            self._active_session["submitted"] = True
            self._active_session["print_options"] = deepcopy(print_options) if print_options else None
            self._active_session["state"] = "print_submitted"
            self._active_session["job_status"] = "preparing"
            self._active_session["job_message"] = "正在准备打印文件……"
            self._active_session["current_page"] = None
            self._active_session["total_pages"] = None
            self._active_session["error_code"] = None
            self._active_session["error_message"] = None
            self._active_session["printer_fault"] = None
            self._active_session["updated_at"] = time.time()
            return True

    def attach_cloud_job(self, file_url: str, job_id: str) -> Optional[Dict[str, Any]]:
        if not file_url or not job_id:
            return None

        with self._lock:
            if not self._active_session:
                return None
            if self._active_session.get("file_url") != file_url:
                return None
            if not self._active_session.get("submitted"):
                return None

            self._active_session["job_id"] = job_id
            self._active_session["state"] = "printing"
            self._active_session["job_status"] = "preparing"
            self._active_session["job_message"] = "正在准备打印文件……"
            self._active_session["updated_at"] = time.time()

            return {
                "session_id": self._active_session["session_id"],
                "job_id": job_id,
                "print_options": deepcopy(self._active_session.get("print_options")),
            }

    def attach_authorized_job(
        self, session_id: str, file_id: str, job_id: str
    ) -> bool:
        """绑定由 Cloud 授权、随后由本机直接执行的任务。"""
        with self._lock:
            if (
                not self._active_session
                or self._active_session["session_id"] != session_id
                or self._active_session.get("file_id") != file_id
                or not self._active_session.get("submitted")
                or self._active_session.get("job_id")
                or not job_id
            ):
                return False
            self._active_session["job_id"] = job_id
            self._active_session["state"] = "printing"
            self._active_session["job_status"] = "preparing"
            self._active_session["updated_at"] = time.time()
            return True

    def reject_print_submission(
        self, session_id: str, file_id: str, error_code: str, message: str
    ) -> bool:
        with self._lock:
            if (
                not self._active_session
                or self._active_session["session_id"] != session_id
                or self._active_session.get("file_id") != file_id
            ):
                return False
            self._active_session["submitted"] = True
            self._active_session["state"] = "failed"
            self._active_session["job_status"] = "failed"
            self._active_session["error_code"] = error_code
            self._active_session["error_message"] = message
            self._active_session["job_message"] = message
            self._active_session["updated_at"] = time.time()
            return True

    def revert_print_submission(self, session_id: str, file_id: str) -> bool:
        with self._lock:
            if not self._active_session:
                return False
            if self._active_session["session_id"] != session_id:
                return False
            if self._active_session.get("file_id") != file_id:
                return False

            self._active_session["submitted"] = False
            self._active_session["job_id"] = None
            self._active_session["print_options"] = None
            self._active_session["state"] = "preview_ready"
            self._active_session["error_code"] = None
            self._active_session["error_message"] = None
            self._active_session["printer_fault"] = None
            self._active_session["job_status"] = None
            self._active_session["job_message"] = None
            self._active_session["current_page"] = None
            self._active_session["total_pages"] = None
            self._active_session["updated_at"] = time.time()
            return True

    def accept_job_status_event(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        job_id = data.get("job_id")
        if not job_id:
            return None

        with self._lock:
            if not self._active_session:
                return None
            # Job status is already bound by job_id; enforce terminal proof only
            # when Cloud includes it. Bare official updates pass.
            if any(
                (
                    data.get("terminal_session_id"),
                    data.get("terminal_ticket_hash"),
                )
            ) and not self._matches_terminal_context(data):
                return None
            if self._active_session.get("job_id") != job_id:
                return None

            status = str(data.get("status") or "").lower()
            if status in {"completed", "complete", "done", "success"}:
                self._active_session["state"] = "completed"
                self._active_session["error_code"] = None
                self._active_session["error_message"] = None
                self._active_session["printer_fault"] = None
            elif status in {"failed", "error", "canceled", "cancelled", "unconfirmed"}:
                self._active_session["state"] = "failed"
                default_error_code = {
                    "canceled": "print_canceled",
                    "cancelled": "print_canceled",
                    "unconfirmed": "result_unconfirmed",
                }.get(status)
                self._active_session["error_code"] = data.get("error_code") or default_error_code
                self._active_session["error_message"] = data.get("message") or data.get("error_message")
                self._active_session["printer_fault"] = deepcopy(data.get("printer_fault"))
            else:
                self._active_session["state"] = "printing"
            self._active_session["job_status"] = status or None
            self._active_session["job_message"] = data.get("message") or data.get("error_message")
            self._active_session["current_page"] = data.get("current_page")
            self._active_session["total_pages"] = data.get("total_pages")
            self._active_session["updated_at"] = time.time()

            enriched = deepcopy(data)
            enriched["session_id"] = self._active_session["session_id"]
            return enriched

    def matches(self, session_id: Optional[str], file_id: Optional[str] = None) -> bool:
        with self._lock:
            if not self._active_session or not session_id:
                return False
            if self._active_session["session_id"] != session_id:
                return False
            if file_id is not None and self._active_session.get("file_id") != file_id:
                return False
            return True

    def build_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            if not self._active_session:
                return {
                    "active": False,
                    "session_id": None,
                    "state": "idle",
                    "file_id": None,
                    "file_url": None,
                    "file_name": None,
                    "file_type": None,
                    "job_id": None,
                    "submitted": False,
                    "error_code": None,
                    "error_message": None,
                    "printer_fault": None,
                    "job_status": None,
                    "job_message": None,
                    "current_page": None,
                    "total_pages": None,
                }

            snapshot = {
                "active": True,
                "session_id": self._active_session["session_id"],
                "state": self._active_session.get("state") or "idle",
                "file_id": self._active_session.get("file_id"),
                "file_url": self._active_session.get("file_url"),
                "file_name": self._active_session.get("file_name"),
                "file_type": self._active_session.get("file_type"),
                "job_id": self._active_session.get("job_id"),
                "submitted": bool(self._active_session.get("submitted")),
                "error_code": self._active_session.get("error_code"),
                "error_message": self._active_session.get("error_message"),
                "printer_fault": deepcopy(self._active_session.get("printer_fault")),
                "job_status": self._active_session.get("job_status"),
                "job_message": self._active_session.get("job_message"),
                "current_page": self._active_session.get("current_page"),
                "total_pages": self._active_session.get("total_pages"),
            }
            if self._active_session.get("content_hash"):
                snapshot["content_hash"] = self._active_session.get("content_hash")
            if self._active_session.get("source_origin"):
                snapshot["source_origin"] = self._active_session.get("source_origin")
            if self._active_session.get("provider_id"):
                snapshot["provider_id"] = self._active_session.get("provider_id")
            if self._active_session.get("size") is not None:
                snapshot["size"] = self._active_session.get("size")
            if self._active_session.get("initial_print_options"):
                snapshot["initial_print_options"] = deepcopy(self._active_session["initial_print_options"])
            if self._active_session.get("site_portal_code"):
                snapshot["site_portal_code"] = self._active_session["site_portal_code"]
                snapshot["site_portal_display_name"] = self._active_session["site_portal_display_name"]
                snapshot["cloud_user_id"] = self._active_session["cloud_user_id"]
                snapshot["external_user_id"] = self._active_session["external_user_id"]
                snapshot["display_name"] = self._active_session["display_name"]
            return snapshot

    def clear_session(self, session_id: Optional[str] = None) -> bool:
        with self._lock:
            if not self._active_session:
                return False
            if session_id and self._active_session["session_id"] != session_id:
                return False
            self._active_session = None
            return True
