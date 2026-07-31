"""Site Portal 文件经 Cloud 授权后由 Edge 直接提交到 IPP 打印机。"""

from concurrent.futures import ThreadPoolExecutor
import uuid

from print_quota import quota_usage
from print_runtime import build_print_request
from printing.domain import (
    ErrorCode,
    PrintError,
    PrintEvent,
    PrintOptions,
    PrintState,
    TERMINAL_STATES,
    USER_MESSAGES,
)


_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="portal-print")
_CONFIRMATION_NAMESPACE = uuid.UUID("52e4c294-8804-4fd2-9109-d10bcf274407")


class PortalPrintService:
    def __init__(
        self,
        *,
        authorizer,
        print_service,
        config_repo,
        session_manager,
        terminal_reporter,
        local_event_publisher=None,
        executor=None,
        logger,
    ):
        self.authorizer = authorizer
        self.print_service = print_service
        self.config_repo = config_repo
        self.session_manager = session_manager
        self.terminal_reporter = terminal_reporter
        self.local_event_publisher = local_event_publisher
        self.executor = executor or _EXECUTOR
        self.logger = logger

    def submit(self, session_snapshot: dict, printer: dict, options: dict) -> dict:
        session_id = str(session_snapshot.get("session_id") or "")
        file_id = str(session_snapshot.get("file_id") or "")
        if (
            session_snapshot.get("source_origin") != "prp"
            or not session_snapshot.get("site_portal_code")
            or not session_snapshot.get("content_hash")
            or not session_snapshot.get("page_count")
        ):
            return {"success": False, "error_code": "portal_print_context_invalid"}
        if not self.session_manager.mark_print_submitted(session_id, file_id, options):
            return {"success": False, "error_code": "print_already_submitted"}

        normalized = PrintOptions.from_mapping(options)
        confirmation_id = str(
            uuid.uuid5(_CONFIRMATION_NAMESPACE, f"{session_id}:{file_id}")
        )
        authorization = self.authorizer.authorize({
            "confirmation_id": confirmation_id,
            "terminal_session_id": session_id,
            "site_portal_code": session_snapshot["site_portal_code"],
            "local_file_id": file_id,
            "file_display_name": session_snapshot.get("file_name") or file_id,
            "page_count": int(session_snapshot["page_count"]),
            "copies": normalized.copies,
            "paper_size": normalized.paper_size,
            "color_mode": normalized.color_mode,
            "duplex_mode": normalized.duplex,
            "printer_id": str(printer.get("cloud_id") or ""),
        })
        if authorization.get("allowed") is not True:
            self.session_manager.reject_print_submission(
                session_id,
                file_id,
                str(authorization.get("error_code") or "print_authorization_denied"),
                str(authorization.get("message") or "打印授权未通过"),
            )
            return {"success": False, **authorization}

        job_id = str(authorization.get("job_id") or "")
        if not self.session_manager.attach_authorized_job(session_id, file_id, job_id):
            raise RuntimeError("authorized job could not bind to the active session")

        def cache_miss():
            raise PrintError(
                ErrorCode.SOURCE_NOT_FOUND,
                "canonical preview cache is missing",
            )

        try:
            request = build_print_request(
                self.config_repo,
                job_id=job_id,
                printer_id=str(printer.get("id") or ""),
                file_path=None,
                source_name=session_snapshot.get("file_name") or file_id,
                print_options=options,
                content_hash=session_snapshot["content_hash"],
                source_kind=session_snapshot.get("file_type") or "",
                source_supplier=cache_miss,
            )
            self.executor.submit(
                self._execute,
                request,
                int(session_snapshot["page_count"]),
                normalized,
            )
        except Exception:
            self.logger.exception(
                "unable to start authorized portal print job_id=%s", job_id
            )
            event = PrintEvent(
                PrintState.FAILED,
                USER_MESSAGES[ErrorCode.CONFIG_INCOMPLETE],
                job_id,
                impressions_completed=0,
                error_code=ErrorCode.CONFIG_INCOMPLETE,
            )
            self.session_manager.accept_job_status_event({
                "job_id": job_id,
                "status": event.state.value,
                "message": event.message,
                "error_code": event.error_code.value,
            })
            self._report_terminal(
                event,
                int(session_snapshot["page_count"]),
                normalized,
            )
            return {
                "success": False,
                "job_id": job_id,
                "error_code": event.error_code.value,
                "message": event.message,
            }
        return {
            "success": True,
            "job_id": job_id,
            "quota_balance": authorization.get("quota_balance"),
        }

    def _execute(self, request, page_count, options):
        terminal_seen = False

        def on_event(event: PrintEvent):
            nonlocal terminal_seen
            payload = {
                "job_id": event.job_id,
                "status": event.state.value,
                "message": event.message,
                "error_code": event.error_code.value if event.error_code else None,
                "current_page": event.current_page,
                "total_pages": event.total_pages,
            }
            accepted = self.session_manager.accept_job_status_event(payload)
            if accepted and self.local_event_publisher:
                self.local_event_publisher(accepted)
            if event.state in TERMINAL_STATES and not terminal_seen:
                terminal_seen = True
                self._report_terminal(event, page_count, options)

        event = self.print_service.execute(request, callback=on_event)
        if event.state in TERMINAL_STATES and not terminal_seen:
            on_event(event)

    def _report_terminal(self, event, page_count, options):
        payload = {
            "job_id": event.job_id,
            "status": event.state.value,
            "error_code": event.error_code.value if event.error_code else "",
            "error_message": event.message,
        }
        if event.state != PrintState.UNCONFIRMED:
            usage = quota_usage(
                page_count,
                options.copies,
                options.duplex,
                options.color_mode,
                impressions_completed=int(event.impressions_completed or 0),
            )
            payload.update({
                "impressions_completed": usage["impressions"],
                "sheets_completed": usage["sheets"],
                "quota_consumed": usage["points"],
            })
        if not self.terminal_reporter.queue_terminal_job_update(
            event.job_id, event.state.value, payload
        ):
            self.logger.error(
                "unable to persist portal terminal report job_id=%s", event.job_id
            )
