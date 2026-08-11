import time
import threading
import unittest
from unittest.mock import Mock, patch

from cloud_service import PrinterStatusReporter
from cloud_websocket_client import CloudWebSocketClient, PrintJobHandler
from printing.domain import PrintEvent, PrintState


class _FakeWebSocket:
    def __init__(self):
        self.cloud_messages = []
        self.local_messages = []
        self.terminal_reports = []

    def send_message_sync(self, message):
        self.cloud_messages.append(message)
        return True

    def dispatch_local_message(self, message_type, message):
        self.local_messages.append((message_type, message))

    def queue_terminal_job_update(self, job_id, status, data):
        self.terminal_reports.append((job_id, status, data))
        return True


class _FakeApiClient:
    node_id = "node-1"


class PrintJobStatusReportingTests(unittest.TestCase):
    def make_handler(self):
        return PrintJobHandler(None, _FakeApiClient(), _FakeWebSocket())

    def test_page_counts_are_local_only_while_cloud_receives_status(self):
        handler = self.make_handler()

        handler._report_job_status(
            "job-1",
            "printing",
            0,
            "打印机正在打印……",
            current_page=2,
            total_pages=5,
        )

        cloud_data = handler.websocket_client.cloud_messages[0]["data"]
        self.assertEqual("processing", cloud_data["status"])
        self.assertNotIn("current_page", cloud_data)
        self.assertNotIn("total_pages", cloud_data)

        _, local_message = handler.websocket_client.local_messages[0]
        local_data = local_message["data"]
        self.assertEqual(2, local_data["current_page"])
        self.assertEqual(5, local_data["total_pages"])

    def test_cloud_client_reports_portal_processing_status(self):
        client = CloudWebSocketClient("ws://example.invalid", Mock(), node_id="node-1")
        client.send_message_sync = Mock(return_value=True)
        try:
            self.assertTrue(
                client.report_job_status(
                    "job-portal",
                    "printing",
                    "printer is printing",
                    current_page=2,
                    total_pages=5,
                )
            )
            message = client.send_message_sync.call_args.args[0]
            self.assertEqual("job_update", message["type"])
            self.assertEqual("node-1", message["node_id"])
            self.assertEqual("processing", message["data"]["status"])
            self.assertEqual("printer is printing", message["data"]["message"])
            self.assertNotIn("current_page", message["data"])
            self.assertNotIn("total_pages", message["data"])
        finally:
            client.stop()

    def test_unconfirmed_error_code_is_normalized_for_cloud(self):
        handler = self.make_handler()

        handler._report_job_failure(
            "job-2",
            "无法确认打印结果",
            "ipp_submission_unconfirmed",
            status="unconfirmed",
        )

        _, status, cloud_data = handler.websocket_client.terminal_reports[0]
        self.assertEqual("unconfirmed", status)
        self.assertEqual("unconfirmed", cloud_data["status"])
        self.assertEqual("submission_unconfirmed", cloud_data["error_code"])

    def test_confirmed_failure_keeps_its_original_error_code(self):
        handler = self.make_handler()

        handler._report_job_failure(
            "job-3",
            "打印任务超时并已取消",
            "print_timeout",
            status="failed",
        )

        _, status, cloud_data = handler.websocket_client.terminal_reports[0]
        self.assertEqual("failed", status)
        self.assertEqual("failed", cloud_data["status"])
        self.assertEqual("print_timeout", cloud_data["error_code"])


class UploadTokenResponseCorrelationTests(unittest.TestCase):
    def make_handler(self):
        handler = PrintJobHandler.__new__(PrintJobHandler)
        handler.websocket_client = None
        handler.upload_token_request_id = "request-1"
        handler.upload_token_callback = Mock()
        handler.upload_token_error_callback = Mock()
        handler.last_upload_token = None
        return handler

    def test_matching_dispatch_error_completes_upload_token_request(self):
        handler = self.make_handler()

        handler.handle_error_message({
            "data": {
                "request_id": "request-1",
                "code": "printer_out_of_paper",
                "message": "Printer cannot accept a new task",
            }
        })

        handler.upload_token_error_callback.assert_called_once_with(
            "printer_out_of_paper",
            "Printer cannot accept a new task",
        )

    def test_unrelated_error_does_not_complete_upload_token_request(self):
        handler = self.make_handler()

        handler.handle_error_message({
            "data": {
                "request_id": "request-2",
                "code": "printer_out_of_paper",
                "message": "Printer cannot accept a new task",
            }
        })

        handler.upload_token_error_callback.assert_not_called()

    def test_upload_token_prefers_fragment_web_url_over_programmatic_endpoint(self):
        handler = self.make_handler()

        handler.handle_upload_token({
            "data": {
                "request_id": "request-1",
                "token": "opaque-token",
                "expires_at": "2026-08-11T12:00:00Z",
                "upload_url": "/api/v1/files",
                "web_url": "/upload#token=opaque-token&node_id=node-1&printer_id=printer-1",
            }
        })

        handler.upload_token_callback.assert_called_once_with(
            "opaque-token",
            "2026-08-11T12:00:00Z",
            "/upload#token=opaque-token&node_id=node-1&printer_id=printer-1",
        )


class PrinterStatusSnapshotReportingTests(unittest.TestCase):
    def test_terminal_event_refreshes_printer_before_local_completion(self):
        status_reporter = Mock()
        status_reporter.force_report_printer.return_value = True
        printer_manager = Mock()
        printer_manager.config.get_printer_by_id.return_value = {"id": "p1", "name": "HP"}
        handler = PrintJobHandler(
            printer_manager,
            _FakeApiClient(),
            _FakeWebSocket(),
            status_reporter=status_reporter,
        )
        order = []
        completed = threading.Event()
        handler._report_job_success = Mock(side_effect=lambda *_args: (order.append("job"), completed.set()))
        fake_service = Mock()
        fake_service.execute.side_effect = lambda _request, callback: callback(
            PrintEvent(PrintState.COMPLETED, "done", "job-1")
        )

        def record_status(**_kwargs):
            order.append("status")
            return True

        status_reporter.force_report_printer.side_effect = record_status
        with patch("print_runtime.build_print_service", return_value=fake_service), patch(
            "print_runtime.build_print_request", return_value=object()
        ):
            handler._start_ipp_print_service(
                job_id="job-1",
                printer_id="p1",
                file_path=None,
                job_name="file.pdf",
                print_options={},
                content_hash="a" * 64,
                file_mgr=None,
            )

        self.assertTrue(completed.wait(1.0))
        self.assertEqual(["status", "job"], order)

    def test_terminal_printer_refresh_waits_for_cloud_status_update(self):
        status_reporter = Mock()
        handler = PrintJobHandler(
            None,
            _FakeApiClient(),
            _FakeWebSocket(),
            status_reporter=status_reporter,
        )

        handler._refresh_printer_status_after_terminal("cloud-printer", "HP")

        status_reporter.force_report_printer.assert_called_once_with(
            printer_id="cloud-printer",
            printer_name="HP",
            wait=True,
            timeout=8.0,
        )

    def test_build_status_payload_preserves_vertical_runtime_state(self):
        printer_manager = Mock()
        printer_manager.get_printer_status_detail.return_value = {
            "printer_status": "printer_out_of_paper",
            "source_observed_at": "2026-07-19T01:02:03+00:00",
        }
        reporter = PrinterStatusReporter(None, printer_manager, "node-1", None)

        payload = reporter._build_status_payload(
            {"id": "local-printer", "cloud_id": "cloud-printer", "name": "HP"}
        )

        self.assertEqual("cloud-printer", payload["printer_id"])
        self.assertEqual("printer_out_of_paper", payload["printer_status"])
        self.assertEqual(
            "2026-07-19T01:02:03+00:00", payload["source_observed_at"]
        )
        self.assertEqual(
            {"printer_id", "printer_status", "source_observed_at"},
            set(payload),
        )

    def test_requested_refresh_is_coalesced_and_runs_on_reporter_thread(self):
        config = Mock()
        config.get_managed_printers.return_value = [
            {"id": "local", "cloud_id": "cloud", "name": "HP"}
        ]
        manager = Mock()
        manager.config = config
        manager.get_printer_status_detail.return_value = {
            "printer_status": "idle",
        }
        api = Mock()
        api.batch_update_printer_status.return_value = {"success": True}
        reporter = PrinterStatusReporter(None, manager, "node", api)
        reporter.check_interval = 3600
        reporter.start()
        try:
            deadline = time.time() + 1
            while (
                api.batch_update_printer_status.call_count < 1
                and time.time() < deadline
            ):
                time.sleep(0.01)
            baseline = api.batch_update_printer_status.call_count
            reporter.force_report_printer(printer_id="cloud")
            reporter.force_report_printer(printer_id="cloud")
            deadline = time.time() + 1
            while (
                api.batch_update_printer_status.call_count < baseline + 1
                and time.time() < deadline
            ):
                time.sleep(0.01)
            self.assertEqual(
                baseline + 1, api.batch_update_printer_status.call_count
            )
        finally:
            reporter.stop()
        self.assertFalse(reporter.running)
        self.assertIsNone(reporter.thread)

    def test_critical_refresh_can_wait_for_cloud_status_update(self):
        config = Mock()
        config.get_managed_printers.return_value = [
            {"id": "local", "cloud_id": "cloud", "name": "HP"}
        ]
        manager = Mock()
        manager.config = config
        manager.get_printer_status_detail.return_value = {"printer_status": "idle"}
        api = Mock()
        api.batch_update_printer_status.return_value = {"success": True}
        reporter = PrinterStatusReporter(None, manager, "node", api)
        reporter.check_interval = 3600
        reporter.start()
        try:
            self.assertTrue(
                reporter.force_report_printer(
                    printer_id="cloud",
                    wait=True,
                    timeout=1.0,
                )
            )
        finally:
            reporter.stop()


if __name__ == "__main__":
    unittest.main()
