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


def shutdown_portal_executor() -> None:
    """进程退出时优雅关闭 portal 打印执行器（取消未启动的排队任务）。"""
    _EXECUTOR.shutdown(wait=False, cancel_futures=True)


class PortalPrintService:
    def __init__(
        self,
        *,
        authorizer,
        print_service,
        config_repo,
        session_manager,
        terminal_reporter,
        status_reporter,
        printer_status_reporter=None,
        local_event_publisher=None,
        executor=None,
        logger,
    ):
        self.authorizer = authorizer
        self.print_service = print_service
        self.config_repo = config_repo
        self.session_manager = session_manager
        self.terminal_reporter = terminal_reporter
        self.status_reporter = status_reporter
        self.printer_status_reporter = printer_status_reporter
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
        # A confirmation identifies one print attempt, not one source file.
        # The session deliberately survives a successful print so the user can
        # print the same PRP file again; deriving this value from session/file
        # would make Cloud return the previous idempotent job and skip a new
        # quota reservation.
        confirmation_id = str(uuid.uuid4())
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
            # Cloud 已分配 job_id 并预留额度：不能静默悬空。上报 failed 并复位会话，
            # 避免 Cloud 侧任务永久挂起、额度永久扣留。
            self.terminal_reporter.queue_terminal_job_update(
                job_id,
                "failed",
                {
                    "job_id": job_id,
                    "status": "failed",
                    "error_code": "job_bind_failed",
                    "error_message": "授权任务未能绑定当前会话",
                },
            )
            self.session_manager.reject_print_submission(
                session_id, file_id, "job_bind_failed", "授权任务未能绑定当前会话"
            )
            return {"success": False, "error_code": "job_bind_failed", "message": "授权任务未能绑定当前会话"}

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
                printer,
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

    def _execute(self, request, page_count, options, printer):
        terminal_seen = False

        def on_event(event: PrintEvent):
            nonlocal terminal_seen
            terminal = event.state in TERMINAL_STATES
            first_terminal = terminal and not terminal_seen
            if first_terminal:
                # Cloud refuses a new authorization while its printer lease is
                # still non-idle. Refresh the physical state before publishing
                # the terminal UI event or consuming the terminal result.
                terminal_seen = True
                self._refresh_printer_status(printer, event.job_id)
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
            if event.state not in TERMINAL_STATES:
                if not self.status_reporter.report_job_status(
                    event.job_id,
                    event.state.value,
                    event.message,
                    current_page=event.current_page,
                    total_pages=event.total_pages,
                ):
                    self.logger.warning(
                        "unable to report portal print status to Cloud job_id=%s status=%s",
                        event.job_id,
                        event.state.value,
                    )
            if first_terminal:
                self._report_terminal(event, page_count, options)

        event = self.print_service.execute(request, callback=on_event)
        if event.state in TERMINAL_STATES and not terminal_seen:
            on_event(event)

    def _refresh_printer_status(self, printer, job_id):
        reporter = self.printer_status_reporter
        if not reporter or not hasattr(reporter, "force_report_printer"):
            return
        try:
            printer_id = str(printer.get("cloud_id") or printer.get("id") or "")
            printer_name = str(printer.get("name") or "")
            refreshed = reporter.force_report_printer(
                printer_id=printer_id,
                printer_name=printer_name,
                wait=True,
                timeout=8.0,
            )
            if not refreshed:
                self.logger.warning(
                    "post-terminal printer status refresh did not complete: job_id=%s printer_id=%s",
                    job_id,
                    printer_id,
                )
        except Exception:
            self.logger.warning(
                "post-terminal printer status refresh failed: job_id=%s",
                job_id,
                exc_info=True,
            )

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
