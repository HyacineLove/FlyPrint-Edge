import logging
import unittest
from unittest.mock import Mock, patch

from interactive_session import InteractiveSessionManager
from portal_print_service import PortalPrintService
from printing.domain import ErrorCode, PrintEvent, PrintState


class InlineExecutor:
    def submit(self, function, *args, **kwargs):
        function(*args, **kwargs)
        return Mock()


class RecordingPrintService:
    def __init__(self, terminal_event=None):
        self.requests = []
        self.terminal_event = terminal_event
        self.events = []

    def execute(self, request, callback=None):
        self.requests.append(request)
        if self.events:
            for event in self.events:
                if callback:
                    callback(event)
            return self.events[-1]
        event = self.terminal_event or PrintEvent(
            PrintState.COMPLETED,
            "completed",
            request.job_id,
            current_page=6,
            total_pages=6,
            impressions_completed=6,
        )
        if callback:
            callback(event)
        return event


class RecordingReporter:
    def __init__(self):
        self.reports = []
        self.status_reports = []

    def queue_terminal_job_update(self, job_id, status, payload):
        self.reports.append((job_id, status, payload))
        return True

    def report_job_status(self, job_id, status, message, current_page=None, total_pages=None):
        self.status_reports.append(
            (job_id, status, message, current_page, total_pages)
        )
        return True


class RecordingPrinterStatusReporter:
    def __init__(self):
        self.calls = []

    def force_report_printer(self, **kwargs):
        self.calls.append(kwargs)
        return True


class DummyConfig:
    def get_printer_by_id(self, printer_id):
        return {
            "id": printer_id,
            "name": "HP",
            "printer_uuid": "urn:uuid:printer-1",
            "ipp_uri": "ipp://printer.local/ipp/print",
        }


class PortalPrintServiceTests(unittest.TestCase):
    def setUp(self):
        self.sessions = InteractiveSessionManager()
        session = self.sessions.start_session()
        self.session_id = session["session_id"]
        self.sessions.bind_portal_identity({
            "terminal_session_id": self.session_id,
            "site_portal_code": "official",
            "cloud_user_id": "cloud-user-1",
            "external_user_id": "portal-user-1",
            "display_name": "User",
        })
        self.sessions.bind_prp_file(self.session_id, {
            "source_origin": "prp",
            "file_id": "file-1",
            "file_name": "document.pdf",
            "file_type": "application/pdf",
            "content_hash": "a" * 64,
            "size": 10,
        })
        self.sessions.set_preview_page_count(self.session_id, "file-1", 3)
        self.authorizer = Mock()
        self.print_service = RecordingPrintService()
        self.reporter = RecordingReporter()
        self.printer_status_reporter = RecordingPrinterStatusReporter()
        self.local_events = []
        self.service = PortalPrintService(
            authorizer=self.authorizer,
            print_service=self.print_service,
            config_repo=DummyConfig(),
            session_manager=self.sessions,
            terminal_reporter=self.reporter,
            status_reporter=self.reporter,
            printer_status_reporter=self.printer_status_reporter,
            local_event_publisher=self.local_events.append,
            executor=InlineExecutor(),
            logger=logging.getLogger("test"),
        )
        self.printer = {"id": "printer-1", "cloud_id": "cloud-printer-1", "name": "HP"}
        self.options = {
            "copies": 2,
            "duplex": "longedge",
            "color_mode": "color",
            "paper_size": "A4",
        }

    def test_denial_never_executes_ipp_and_keeps_result_state(self):
        self.authorizer.authorize.return_value = {
            "allowed": False,
            "error_code": "print_quota_insufficient",
            "message": "quota insufficient",
        }
        result = self.service.submit(
            self.sessions.get_active_session(), self.printer, self.options
        )
        self.assertFalse(result["success"])
        self.assertEqual([], self.print_service.requests)
        snapshot = self.sessions.build_snapshot()
        self.assertEqual("failed", snapshot["state"])
        self.assertEqual("print_quota_insufficient", snapshot["error_code"])

    def test_allowed_request_binds_job_executes_once_and_reports_usage(self):
        self.authorizer.authorize.return_value = {
            "allowed": True,
            "job_id": "job-1",
            "reserved_quota": 8,
            "quota_balance": 42,
        }
        result = self.service.submit(
            self.sessions.get_active_session(), self.printer, self.options
        )
        self.assertTrue(result["success"])
        self.assertEqual(1, len(self.print_service.requests))
        self.assertEqual("job-1", self.sessions.build_snapshot()["job_id"])
        self.assertEqual(1, len(self.reporter.reports))
        report = self.reporter.reports[0][2]
        self.assertEqual(6, report["impressions_completed"])
        self.assertEqual(4, report["sheets_completed"])
        self.assertEqual(8, report["quota_consumed"])
        self.assertEqual("completed", self.local_events[-1]["status"])
        self.assertEqual(6, self.local_events[-1]["current_page"])
        self.assertEqual(6, self.local_events[-1]["total_pages"])
        self.assertEqual(
            [("cloud-printer-1", "HP")],
            [
                (call["printer_id"], call["printer_name"])
                for call in self.printer_status_reporter.calls
            ],
        )

    def test_terminal_refresh_happens_before_next_portal_authorization(self):
        authorizations = [
            {"allowed": True, "job_id": "job-1", "reserved_quota": 8, "quota_balance": 42},
            {"allowed": True, "job_id": "job-2", "reserved_quota": 2, "quota_balance": 40},
        ]

        def authorize(_payload):
            if len(self.authorizer.authorize.call_args_list) == 2:
                self.assertGreaterEqual(
                    len(self.printer_status_reporter.calls),
                    1,
                    "the previous terminal must refresh printer status before a new authorization",
                )
            return authorizations.pop(0)

        self.authorizer.authorize.side_effect = authorize

        first = self.service.submit(self.sessions.get_active_session(), self.printer, self.options)
        self.assertTrue(first["success"])
        self.sessions.clear_prp_selection(self.session_id)
        self.sessions.bind_prp_file(self.session_id, {
            "source_origin": "prp",
            "file_id": "file-2",
            "file_name": "second.pdf",
            "file_type": "application/pdf",
            "content_hash": "b" * 64,
            "size": 10,
        })
        self.sessions.set_preview_page_count(self.session_id, "file-2", 1)

        second_options = {**self.options, "copies": 1}
        self.print_service.events = [
            PrintEvent(
                PrintState.COMPLETED,
                "completed",
                "job-2",
                current_page=1,
                total_pages=1,
                impressions_completed=1,
            )
        ]
        second = self.service.submit(self.sessions.get_active_session(), self.printer, second_options)

        self.assertTrue(second["success"])
        self.assertEqual(2, self.authorizer.authorize.call_count)
        self.assertGreaterEqual(len(self.printer_status_reporter.calls), 1)

    def test_reprinting_same_file_creates_a_new_cloud_job_and_charge(self):
        self.authorizer.authorize.side_effect = [
            {"allowed": True, "job_id": "job-1", "reserved_quota": 8, "quota_balance": 42},
            {"allowed": True, "job_id": "job-2", "reserved_quota": 8, "quota_balance": 34},
        ]

        first = self.service.submit(self.sessions.get_active_session(), self.printer, self.options)
        self.assertTrue(first["success"])
        self.sessions.clear_prp_selection(self.session_id)
        self.sessions.bind_prp_file(self.session_id, {
            "source_origin": "prp",
            "file_id": "file-1",
            "file_name": "document.pdf",
            "file_type": "application/pdf",
            "content_hash": "a" * 64,
            "size": 10,
        })
        self.sessions.set_preview_page_count(self.session_id, "file-1", 3)
        self.print_service.events = [
            PrintEvent(
                PrintState.COMPLETED,
                "completed",
                "job-2",
                current_page=6,
                total_pages=6,
                impressions_completed=6,
            )
        ]

        second = self.service.submit(self.sessions.get_active_session(), self.printer, self.options)

        self.assertTrue(second["success"])
        self.assertEqual(2, self.authorizer.authorize.call_count)
        confirmation_ids = [call.args[0]["confirmation_id"] for call in self.authorizer.authorize.call_args_list]
        self.assertNotEqual(confirmation_ids[0], confirmation_ids[1])
        self.assertEqual(["job-1", "job-2"], [report[0] for report in self.reporter.reports])

    def test_allowed_portal_job_reports_nonterminal_states_to_cloud(self):
        self.authorizer.authorize.return_value = {
            "allowed": True,
            "job_id": "job-1",
            "reserved_quota": 8,
            "quota_balance": 42,
        }
        self.print_service.events = [
            PrintEvent(
                PrintState.QUEUED,
                "queued",
                "job-1",
                current_page=0,
                total_pages=6,
            ),
            PrintEvent(
                PrintState.PRINTING,
                "printing",
                "job-1",
                current_page=2,
                total_pages=6,
            ),
            PrintEvent(
                PrintState.COMPLETED,
                "completed",
                "job-1",
                current_page=6,
                total_pages=6,
                impressions_completed=6,
            ),
        ]

        result = self.service.submit(
            self.sessions.get_active_session(), self.printer, self.options
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            [
                ("job-1", "queued", "queued", 0, 6),
                ("job-1", "printing", "printing", 2, 6),
            ],
            self.reporter.status_reports,
        )
        self.assertEqual(1, len(self.reporter.reports))
        self.assertEqual("completed", self.reporter.reports[0][1])

    def test_authorized_job_bind_failure_reports_terminal_failure(self):
        self.authorizer.authorize.return_value = {
            "allowed": True, "job_id": "job-bind-failed",
            "reserved_quota": 8, "quota_balance": 42,
        }
        with patch.object(self.sessions, "attach_authorized_job", return_value=False):
            result = self.service.submit(self.sessions.get_active_session(), self.printer, self.options)
        self.assertFalse(result["success"])
        self.assertEqual("job_bind_failed", result["error_code"])
        self.assertEqual("failed", self.reporter.reports[0][1])

    def test_print_request_uses_canonical_cache_only(self):
        self.authorizer.authorize.return_value = {
            "allowed": True,
            "job_id": "job-1",
            "reserved_quota": 8,
            "quota_balance": 42,
        }
        self.service.submit(
            self.sessions.get_active_session(), self.printer, self.options
        )
        request = self.print_service.requests[0]
        self.assertEqual("a" * 64, request.content_hash)
        with self.assertRaises(Exception):
            request.source_supplier()

    def test_second_submit_does_not_authorize_or_print_again(self):
        self.authorizer.authorize.return_value = {
            "allowed": True,
            "job_id": "job-1",
            "reserved_quota": 8,
            "quota_balance": 42,
        }
        snapshot = self.sessions.get_active_session()
        self.assertTrue(self.service.submit(snapshot, self.printer, self.options)["success"])
        second = self.service.submit(snapshot, self.printer, self.options)
        self.assertFalse(second["success"])
        self.assertEqual(1, self.authorizer.authorize.call_count)
        self.assertEqual(1, len(self.print_service.requests))

    def test_pre_submit_failure_reports_zero_usage(self):
        self.print_service.terminal_event = PrintEvent(
            PrintState.FAILED,
            "submission failed",
            "job-1",
            impressions_completed=0,
            error_code=ErrorCode.IPP_SUBMISSION_FAILED,
        )
        self.authorizer.authorize.return_value = {
            "allowed": True,
            "job_id": "job-1",
            "reserved_quota": 8,
            "quota_balance": 42,
        }
        self.service.submit(
            self.sessions.get_active_session(), self.printer, self.options
        )
        report = self.reporter.reports[0][2]
        self.assertEqual(0, report["impressions_completed"])
        self.assertEqual(0, report["sheets_completed"])
        self.assertEqual(0, report["quota_consumed"])

    def test_unconfirmed_result_omits_usage(self):
        self.print_service.terminal_event = PrintEvent(
            PrintState.UNCONFIRMED,
            "result unknown",
            "job-1",
            impressions_completed=2,
            error_code=ErrorCode.IPP_JOB_QUERY_FAILED,
        )
        self.authorizer.authorize.return_value = {
            "allowed": True,
            "job_id": "job-1",
            "reserved_quota": 8,
            "quota_balance": 42,
        }
        self.service.submit(
            self.sessions.get_active_session(), self.printer, self.options
        )
        report = self.reporter.reports[0][2]
        self.assertNotIn("impressions_completed", report)
        self.assertNotIn("sheets_completed", report)
        self.assertNotIn("quota_consumed", report)

    def test_local_request_build_failure_after_authorization_reports_zero_usage(self):
        self.authorizer.authorize.return_value = {
            "allowed": True,
            "job_id": "job-1",
            "reserved_quota": 8,
            "quota_balance": 42,
        }
        self.service.config_repo = Mock()
        self.service.config_repo.get_printer_by_id.return_value = None

        result = self.service.submit(
            self.sessions.get_active_session(), self.printer, self.options
        )

        self.assertFalse(result["success"])
        self.assertEqual("job-1", result["job_id"])
        self.assertEqual("failed", self.reporter.reports[0][1])
        self.assertEqual(0, self.reporter.reports[0][2]["quota_consumed"])


if __name__ == "__main__":
    unittest.main()
