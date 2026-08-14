import pathlib
import re
import unittest
from functools import lru_cache


BASE_DIR = pathlib.Path("static/user")
REQUIRED_SPA_FILES = [
    "app.js",
    "modules/views/login-view.js",
    "modules/views/preview-view.js",
    "modules/views/printing-view.js",
    "modules/views/done-view.js",
    "modules/app/sse-client.js",
]
FULL_PAGE_NAVIGATION_PATTERNS = [
    r"window\.location\.href\s*=",
    r"window\.location\.replace\s*\(",
    r"window\.location\.assign\s*\(",
    r"location\.href\s*=",
    r"location\.replace\s*\(",
    r"location\.assign\s*\(",
]


@lru_cache(maxsize=None)
def read_source(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


class UserPreviewAssetTests(unittest.TestCase):
    def test_user_spa_removes_the_obsolete_identity_success_page(self):
        app_controller = read_source(BASE_DIR / "modules/app/app-controller.js")
        index_html = read_source(BASE_DIR / "Index.html")

        self.assertNotIn('"../views/identity-view.js"', app_controller)
        self.assertNotIn("identity: { render:", app_controller)
        self.assertNotIn("css/identity.css", index_html)
        self.assertFalse((BASE_DIR / "modules/views/identity-view.js").exists())
        self.assertFalse((BASE_DIR / "css/identity.css").exists())

    def _require_existing_files(self, relative_paths, message_prefix):
        missing = [str(BASE_DIR / relative_path) for relative_path in relative_paths if not (BASE_DIR / relative_path).exists()]
        self.assertEqual([], missing, f"{message_prefix}: {missing}")

    def test_user_spa_required_files_exist(self):
        self._require_existing_files(REQUIRED_SPA_FILES, "missing SPA files")

    def test_user_index_shell_contains_app_mount_and_module_entry(self):
        path = BASE_DIR / "index.html"
        self.assertTrue(path.exists(), f"missing SPA shell: {path}")
        self._require_existing_files(["app.js"], "missing SPA entry required by shell")

        html = read_source(path)
        self.assertIn('id="app"', html, "SPA shell should expose a single #app mount node")
        self.assertIn('type="module"', html, "SPA shell should load the frontend through a module script")
        self.assertRegex(
            html,
            r'src=["\']/static/user/app\.js["\']',
            "SPA shell should bootstrap /static/user/app.js so it also works when served from /",
        )
        self.assertIn('href="/static/user/css/login.css"', html, "SPA shell should use absolute CSS paths")
        for pattern in FULL_PAGE_NAVIGATION_PATTERNS:
            self.assertNotRegex(html, pattern, f"SPA shell should not trigger full-page navigation via pattern {pattern}")

    def test_user_shell_loads_common_css_before_page_styles(self):
        html = read_source(BASE_DIR / "Index.html")
        common = html.index('href="/static/user/css/common.css"')
        login = html.index('href="/static/user/css/login.css"')
        files = html.index('href="/static/user/css/files.css"')
        self.assertLess(common, login)
        self.assertLess(login, files)

    def test_common_css_owns_shared_primitives(self):
        common_css = read_source(BASE_DIR / "css/common.css")
        for selector in (
            ".ui-main-countdown",
            ".ui-countdown-ring",
            ".ui-countdown-value",
            ".ui-action-region",
            ".ui-action-button",
            ".is-loading",
            ".is-business-locked",
            ".fill-bg-gradient",
            ".fill-primary-gradient",
        ):
            self.assertIn(selector, common_css)

    def test_countdown_views_use_shared_markup_and_explicit_loading_lifecycle(self):
        views = {
            "login": read_source(BASE_DIR / "modules/views/login-view.js"),
            "preview": read_source(BASE_DIR / "modules/views/preview-view.js"),
            "done": read_source(BASE_DIR / "modules/views/done-view.js"),
            "files": read_source(BASE_DIR / "modules/app/prp-files.js"),
        }
        for name, source in views.items():
            with self.subTest(page=name):
                self.assertIn("ui-main-countdown", source)
                self.assertIn("ui-countdown-ring", source)
                self.assertIn("ui-countdown-value", source)
                if name == "files":
                    self.assertIn("mainCountdown.pause()", source)
                    self.assertIn("mainCountdown.resume()", source)
                else:
                    self.assertIn('stop("loading")', source)
        self.assertNotIn('id="77_42"', views["preview"])
        self.assertNotIn('id="77_44"', views["preview"])

    def test_files_page_uses_common_single_action_region_and_minimal_success_copy(self):
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")
        files_css = read_source(BASE_DIR / "css/files.css")
        self.assertIn("ui-action-region", files_view)
        self.assertIn("ui-action-button", files_view)
        self.assertIn("files-action-region--single", files_view)
        self.assertNotIn('id="filesTotal"', files_view)
        self.assertNotIn('>鍙墦鍗版枃浠?', files_view)
        self.assertIn(".files-action-region--single", files_css)
        self.assertIn("width: 418px", files_css)
        self.assertIn("height: 110px", files_css)

    def test_countdown_and_action_css_are_centered_and_animated(self):
        common_css = read_source(BASE_DIR / "css/common.css")
        files_css = read_source(BASE_DIR / "css/files.css")
        self.assertRegex(common_css, r"\.ui-countdown-value\s*\{[^}]*width:\s*3ch")
        self.assertRegex(common_css, r"\.ui-countdown-value\s*\{[^}]*text-align:\s*center")
        self.assertIn("animation:", common_css)
        self.assertIn("animation:", files_css)
        self.assertRegex(common_css, r"\.ui-action-region\.is-single\s*\{[^}]*justify-content:\s*center")

    def test_visible_countdown_ring_keeps_rotating_in_every_phase(self):
        common_css = read_source(BASE_DIR / "css/common.css")
        self.assertRegex(
            common_css,
            r"\.ui-countdown-ring\s*\{[^}]*animation:\s*ui-countdown-spin",
        )
        self.assertNotRegex(
            common_css,
            r"\.ui-main-countdown\[data-countdown-phase=\"idle\"\] \.ui-countdown-ring\s*\{[^}]*animation:\s*none",
        )

    def test_login_refresh_button_has_explicit_terminal_position(self):
        login_css = read_source(BASE_DIR / "css/login.css")
        self.assertRegex(
            login_css,
            r"\.Pixso-group-3_28\.ui-action-trigger\s*\{[^}]*display:\s*block[^}]*position:\s*absolute[^}]*top:\s*724px",
        )

    def test_files_page_keeps_clock_refresh_and_pager_in_fixed_regions(self):
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")
        files_css = read_source(BASE_DIR / "css/files.css")
        runtime = read_source(BASE_DIR / "modules/shared/runtime.js")
        self.assertIn('id="filesClock"', files_view)
        self.assertIn('id="filesRefresh"', files_view)
        self.assertIn('"filesClock"', runtime)
        self.assertRegex(files_css, r"\.files-pager\s*\{[^}]*position:\s*absolute[^}]*top:\s*1550px")
        self.assertRegex(files_css, r"\.files-header[^}]*position:\s*relative")
        self.assertIn("files-header .files-refresh", files_css)

    def test_done_refresh_detection_is_hidden_outside_fault_or_unconfirmed_states(self):
        common_css = read_source(BASE_DIR / "css/common.css")
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")
        self.assertIn("[hidden]", common_css)
        self.assertIn('refreshButton.hidden = true', done_view)
        self.assertIn('refreshButton.hidden = false', done_view)

    def test_stale_countdown_css_is_removed_from_printing_and_preview(self):
        preview_css = read_source(BASE_DIR / "css/preview.css")
        printing_css = read_source(BASE_DIR / "css/printing.css")
        self.assertNotIn(".Pixso-group-77_42", preview_css)
        self.assertNotIn(".Pixso-vector-77_43", preview_css)
        self.assertNotIn(".Pixso-paragraph-77_44", preview_css)
        self.assertNotIn(".Pixso-group-115_18", printing_css)
        self.assertNotIn(".Pixso-vector-115_19", printing_css)
        self.assertNotIn(".Pixso-paragraph-115_20", printing_css)

    def test_user_app_entry_exists_and_is_not_empty(self):
        path = BASE_DIR / "app.js"
        self.assertTrue(path.exists(), f"missing SPA entry: {path}")

        script = read_source(path)
        self.assertTrue(script.strip(), "SPA entry app.js should not be empty")

    def test_user_spa_entry_and_views_avoid_full_page_navigation(self):
        navigation_files = ["app.js", *REQUIRED_SPA_FILES[1:5]]
        self._require_existing_files(navigation_files, "missing SPA files for navigation contract")

        for relative_path in navigation_files:
            path = BASE_DIR / relative_path
            script = read_source(path)
            for pattern in FULL_PAGE_NAVIGATION_PATTERNS:
                with self.subTest(path=str(path), pattern=pattern):
                    self.assertNotRegex(script, pattern, f"{path} should not trigger full-page navigation via pattern {pattern}")

    def test_sse_client_module_uses_eventsource_api(self):
        path = BASE_DIR / "modules/app/sse-client.js"
        self.assertTrue(path.exists(), f"missing SSE client: {path}")

        script = read_source(path)
        self.assertIn("EventSource", script, "sse-client.js should use the EventSource API")

    def test_printer_fault_handling_stays_on_result_page(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")
        done_result = read_source(BASE_DIR / "modules/shared/done-result.js")
        login_view = read_source(BASE_DIR / "modules/views/login-view.js")
        runtime = read_source(BASE_DIR / "modules/shared/runtime.js")
        api = read_source(BASE_DIR / "modules/shared/api.js")

        self.assertIn("printerAvailability", api)
        self.assertIn('qr: "/api/qr_code"', api)
        self.assertIn("printer_fault", runtime)
        self.assertNotIn("media-needed-error", runtime)
        self.assertIn("isPrinterFaultResult", done_view)
        self.assertIn("printer_out_of_paper", done_result)
        self.assertIn("printer_out_of_toner", done_result)
        self.assertIn("donePrinterRefresh", done_view)
        self.assertIn("checkPrinterAvailability", done_view)
        self.assertNotIn("printerAvailability", login_view)
        self.assertNotIn("setPrinterFaultLocked", login_view)
        self.assertNotIn("availabilityPollTimer", login_view)

    def test_homepage_qr_failures_retry_with_countdown_and_only_disable_during_fetch(self):
        login_view = read_source(BASE_DIR / "modules/views/login-view.js")
        runtime = read_source(BASE_DIR / "modules/shared/runtime.js")
        api = read_source(BASE_DIR / "modules/shared/api.js")

        self.assertIn("createMainCountdown", login_view)
        self.assertNotIn("loginQrRetryCountdownSeconds", login_view)
        self.assertNotIn("loginQrRetryCountdownSeconds", runtime)
        self.assertNotIn("loginCountdownTimer", login_view)
        self.assertNotIn("printerAvailability", login_view)
        self.assertNotIn("checkPrinterAvailability", login_view)
        self.assertNotIn("cloudAccessLocked", login_view)
        self.assertNotIn("terminalActivationRequired", login_view)
        self.assertIn('setQrCenterStatus("获取二维码中")', login_view)
        self.assertRegex(login_view, r"if\s*\(loginQrRefreshing\)\s*return false;")
        self.assertRegex(
            login_view,
            r"function\s+updateManualRefreshState\(\)\s*\{\s*setManualRefreshDisabled\(\s*loginQrRefreshing,?\s*\);",
        )
        refresh_body = login_view.split("async function refreshQrCode", 1)[1]
        self.assertNotIn("loginCountdownValue", refresh_body)
        self.assertIn("mainCountdown.stop()", login_view)
        self.assertIn("startCountdown(60", login_view)
        self.assertIn("startCountdown(10", login_view)
        self.assertNotIn("loginQrRetrySuffix", login_view)
        self.assertNotIn("loginQrRetrySuffix", runtime)
        self.assertIn('error.code = json?.error_code || json?.code || ""', api)
        self.assertIn("cloud_response_timeout", runtime)

    def test_terminal_occupied_is_business_lock_without_auto_retry_countdown(self):
        login_view = read_source(BASE_DIR / "modules/views/login-view.js")
        occupied_body = login_view.split("function setTerminalOccupied", 1)[1].split(
            "function setManualRefreshDisabled", 1
        )[0]

        self.assertIn("mainCountdown.stop()", occupied_body)
        self.assertIn("setQrCenterStatus(message)", occupied_body)
        self.assertNotIn("setLoginErrorCountdown", occupied_body)
        self.assertNotIn("startCountdown", occupied_body)

    def test_homepage_renders_all_qr_messages_in_the_qr_area_without_toasts(self):
        login_view = read_source(BASE_DIR / "modules/views/login-view.js")
        index_html = read_source(BASE_DIR / "Index.html")

        self.assertNotIn("toast.js", login_view)
        self.assertNotIn("showUserToast", login_view)
        self.assertNotIn("hideUserToast", login_view)
        self.assertNotIn("userToast", index_html)
        self.assertFalse((BASE_DIR / "modules/shared/toast.js").exists())
        self.assertIn('setQrCenterStatus("获取二维码中")', login_view)
        self.assertRegex(
            login_view,
            r"function\s+setLoginErrorCountdown[\s\S]*?setQrCenterStatus\(message\)",
        )

    def test_print_error_mapping_covers_cloud_availability_errors(self):
        runtime = read_source(BASE_DIR / "modules/shared/runtime.js")

        for error_code in ("node_disabled", "node_not_found", "printer_disabled", "printer_not_found"):
            with self.subTest(error_code=error_code):
                self.assertIn(f"{error_code}:", runtime)

    def test_portal_authorization_errors_are_user_visible(self):
        runtime = read_source(BASE_DIR / "modules/shared/runtime.js")

        for error_code in (
            "print_quota_insufficient",
            "printer_unavailable",
            "printer_capability_unsupported",
            "terminal_session_invalid",
            "print_confirmation_conflict",
            "job_bind_failed",
        ):
            with self.subTest(error_code=error_code):
                self.assertIn(error_code, runtime)

    def test_done_action_buttons_match_preview_side_by_side_layout(self):
        done_css = read_source(BASE_DIR / "css/done.css")
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")
        preview_css = read_source(BASE_DIR / "css/preview.css")

        self.assertRegex(
            done_css,
            r"\.Pixso-group-115_43\s*\{[^}]*width:\s*418px[^}]*height:\s*110px[^}]*left:\s*107px[^}]*top:\s*1700px",
        )
        self.assertRegex(
            done_css,
            r"\.Pixso-group-115_40\s*\{[^}]*width:\s*418px[^}]*height:\s*110px[^}]*left:\s*556px[^}]*top:\s*1700px",
        )
        self.assertRegex(
            done_css,
            r"\.Pixso-group-115_43\.single-action\s*\{[^}]*left:\s*331px",
        )
        self.assertIn("single-action", done_view)
        self.assertIn('class="Pixso-group-115_43"', done_view)
        self.assertIn("done-secondary-action-surface", done_view)
        self.assertNotIn("done-continue-button", done_view)
        self.assertRegex(
            preview_css,
            r"\.Pixso-rectangle-97_455,\s*\.done-secondary-action-surface\s*\{",
        )
        self.assertRegex(
            done_css,
            r"\.done-printer-refresh\.fault-action\s*\{[^}]*left:\s*107px[^}]*top:\s*1700px",
        )
        self.assertRegex(
            done_css,
            r"\.Pixso-group-115_43\.fault-session-exited\s*\{[^}]*left:\s*556px[^}]*top:\s*1700px",
        )

    def test_logout_actions_use_explicit_label_and_confirmation(self):
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")
        logout = read_source(BASE_DIR / "modules/shared/logout.js")

        self.assertIn('id="filesExit"', files_view)
        self.assertIn(">退出登录</button>", files_view)
        self.assertIn("confirmLogout", files_view)
        self.assertIn("confirmLogout", done_view)
        self.assertIn("退出登录", done_view)
        self.assertIn("是否退出当前账号？", logout)

    def test_done_view_makes_continue_primary_and_logout_secondary(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")

        self.assertRegex(
            done_view,
            r'button id="115_43"[^>]*>[\s\S]*?退出登录[\s\S]*?</button>',
        )
        self.assertRegex(
            done_view,
            r'button id="115_40"[^>]*>[\s\S]*?继续打印[\s\S]*?</button>',
        )

    def test_printer_fault_done_view_uses_main_countdown_until_recovered(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")

        self.assertRegex(
            done_view,
            r"if\s*\(\s*isFaultLockedDoneResult\(result\)\s*\)\s*\{[\s\S]*?startCountdown\(10,\s*checkPrinterAvailability\)",
            "printer fault result should use the main countdown to recheck",
        )
        self.assertIn("打印机已恢复", done_view)

    def test_printer_recovered_copy_matches_home_return_button(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")

        self.assertIn('logoutLabel.textContent = "返回首页"', done_view)
        self.assertIn('setText(["77_21"], "打印机已恢复，可返回首页后继续使用")', done_view)
        self.assertNotIn("可退出登录后继续使用", done_view)

    def test_done_view_uses_only_the_main_header_countdown(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")
        done_css = read_source(BASE_DIR / "css/done.css")

        self.assertIn('id="115_18"', done_view)
        self.assertIn('class="Pixso-paragraph-115_20"', done_view)
        self.assertNotIn('id="115_37"', done_view)
        self.assertNotIn('id="115_38"', done_view)
        self.assertNotIn('id="115_39"', done_view)
        self.assertNotIn("setCountdownAccessoryVisible", done_view)
        self.assertNotIn("秒后重试", done_view)
        self.assertIn("createMainCountdown", done_view)
        self.assertIn("doneCountdown", done_view)
        self.assertNotIn(".Pixso-group-115_37", done_css)
        self.assertNotIn(".Pixso-paragraph-115_39", done_css)

    def test_printer_fault_uses_manual_refresh_and_main_countdown(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")

        self.assertIn('id="donePrinterRefresh"', done_view)
        self.assertIn("checkPrinterAvailability", done_view)
        self.assertIn("on(\"donePrinterRefresh\"", done_view)
        self.assertRegex(done_view, r"startCountdown\(10,\s*checkPrinterAvailability\)")
        self.assertRegex(done_view, r"setLogoutEnabled\(true\)[\s\S]*?setRefreshEnabled\(false\)")
        self.assertRegex(done_view, r"startCountdown\(10,\s*leave\)")

    def test_preview_loading_locks_controls_and_pauses_countdown_for_every_preview_request(self):
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")

        self.assertRegex(
            preview_view,
            r"previewLoading\s*=\s*true;[\s\S]*?setPreviewControlsLocked\(true\);[\s\S]*?pausePreviewCountdown\(\);",
        )
        self.assertIn("!previewControlsLocked", preview_view)
        self.assertRegex(
            preview_view,
            r"function\s+queuePreviewRefresh\(\)\s*\{[\s\S]*?previewLoading\s*\|\|\s*previewFailureMode",
        )
        self.assertRegex(
            preview_view,
            r"function\s+queuePreviewRefresh\(\)[\s\S]*?setPreviewControlsLocked\(true\);[\s\S]*?pausePreviewCountdown\(\);",
        )
        self.assertIn("await renderPreview(previewCurrentPage - 1, false)", preview_view)
        self.assertIn("await renderPreview(previewCurrentPage + 1, false)", preview_view)
        self.assertIn("resumePreviewCountdown(true)", preview_view)

    def test_done_actions_use_loading_lock_without_changing_business_failure_lock(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")

        self.assertIn("let doneLoading = false", done_view)
        self.assertIn("function beginLoading", done_view)
        self.assertIn("createMainCountdown", done_view)
        self.assertIn("setLogoutEnabled(false)", done_view)
        self.assertIn("mainCountdown.stop()", done_view)
        self.assertIn("continueButton.disabled = true", done_view)
        self.assertIn("isPrinterFaultResult", done_view)
        self.assertIn("isUnconfirmedResult", done_view)
        self.assertNotIn("setCountdownAccessoryVisible", done_view)

    def test_fault_lock_waits_for_local_session_cleanup_without_unlocking_the_fault_page(self):
        controller = read_source(BASE_DIR / "modules/app/app-controller.js")

        self.assertRegex(
            controller,
            r"if\s*\(isFaultLockedDoneResult\(result\)\)\s*\{[\s\S]*?await cleanupSessionResources\(\);\s*clearLocalUserSession\(\);[\s\S]*?state\.sessionPhase\s*=\s*\"fault_locked\"[\s\S]*?router\.go\(\"done\"\)",
        )
        self.assertNotIn("void cleanupSessionResources();", controller)

    def test_successful_prp_done_view_offers_continue_file_selection(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")
        done_result = read_source(BASE_DIR / "modules/shared/done-result.js")
        controller = read_source(BASE_DIR / "modules/app/app-controller.js")

        self.assertIn('id="115_40"', done_view)
        self.assertIn("continueToFiles", done_view)
        self.assertIn("canContinueToFilesAfterDone", done_view)
        self.assertIn("sourceOrigin !== \"prp\"", done_result)
        self.assertIn("async function continueToFiles", controller)
        self.assertIn("api.prpSelection", controller)
        self.assertIn('await router.go("files")', controller)

    def test_normal_prp_failure_reuses_done_actions_but_fault_home_return_needs_no_logout_confirmation(self):
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")

        self.assertRegex(
            done_view,
            r'if\s*\(result\.type\s*===\s*"error"\)\s*\{[\s\S]*?startCountdown\(10,\s*leave\)',
        )
        self.assertIn('logoutLabel.textContent = "返回首页"', done_view)
        self.assertIn('on("115_43", () => void returnToHome?.())', done_view)

    def test_app_controller_failed_snapshot_uses_snapshot_error_fields(self):
        controller = read_source(BASE_DIR / "modules/app/app-controller.js")

        self.assertNotIn("normalized.error_code", controller)
        self.assertNotIn("normalized.error_message", controller)
        self.assertIn("snapshot.error_code", controller)
        self.assertIn("snapshot.error_message", controller)

    def test_terminal_mask_ack_preserves_command_id_from_sse_envelope(self):
        controller = read_source(BASE_DIR / "modules/app/app-controller.js")

        self.assertIn("onMessage: (message) =>", controller)
        self.assertIn("handleSseMessage(type, data || {}, message)", controller)
        self.assertIn("function handleSseMessage(type, data, message = {})", controller)
        self.assertIn("command_id: message.command_id", controller)

    def test_print_error_mapping_sanitizes_driver_and_job_tracking_errors(self):
        runtime = read_source(BASE_DIR / "modules/shared/runtime.js")

        self.assertNotIn("PCL XL", runtime)
        self.assertNotIn("MemAllocError", runtime)
        self.assertNotIn("ReadImage", runtime)
        self.assertNotIn("无法获取本地打印任务ID", runtime)
        self.assertNotIn("print_spooler_error", runtime)
        self.assertIn("无法确认本次打印结果，请勿重复提交", runtime)

    def test_preview_uses_runtime_layout_defaults(self):
        session_state = read_source(BASE_DIR / "modules/shared/session-state.js")
        admin_settings = read_source("static/admin/modules/render-sections.js")
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")
        main = read_source("main.py")

        self.assertIn("default_scale_percent", session_state)
        self.assertIn("默认缩放", admin_settings)
        self.assertIn("cfg.default_scale_percent", admin_settings)
        self.assertIn("default_scale_percent", main)
        self.assertIn("runtimeSettings.default_scale_percent", preview_view)
        self.assertIn('id="preview-scale-decrease"', preview_view)
        self.assertNotIn("default_scale_mode", preview_view)
        self.assertNotIn("default_max_upscale", preview_view)

    def test_scale_change_requests_a_preview_render_with_print_layout_scale(self):
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")
        self.assertRegex(
            preview_view,
            r"const changeScale = \(delta\) => \{[\s\S]*?saveSessionState\(\);[\s\S]*?renderOptionsUI\(\);[\s\S]*?\n  \};",
        )
        change_scale = preview_view.split("const changeScale = (delta) =>", 1)[1].split("const pickColor", 1)[0]
        self.assertIn("queuePreviewRefresh", change_scale)
        self.assertNotIn("setPreviewScale(\"115_58\", scalePercent)", preview_view)
        self.assertNotIn("scale_percent: forPreview ? 100", preview_view)
        self.assertIn("scale_percent: normalizeScalePercent(session.options.scale_percent)", preview_view)

    def test_preview_stage_switches_geometry_with_document_orientation(self):
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")
        dom = read_source(BASE_DIR / "modules/shared/dom.js")
        preview_css = read_source(BASE_DIR / "css/preview.css")

        self.assertIn("setPreviewOrientation(orientation)", preview_view)
        self.assertIn("export function setPreviewOrientation", dom)
        self.assertIn(".Pixso-frame-55_77.is-landscape", preview_css)
        self.assertIn(".Pixso-frame-55_77.is-portrait", preview_css)
        self.assertIn("#preview-document-layer", preview_css)

    def test_scale_value_stays_on_one_line(self):
        preview_css = read_source(BASE_DIR / "css/preview.css")

        self.assertIn(".preview-option-card--scale .preview-copies-value", preview_css)
        scale_rule = preview_css.split(".preview-option-card--scale .preview-copies-value", 1)[1]
        self.assertIn("white-space: nowrap", scale_rule)
        self.assertIn("flex: 0 0 74px", scale_rule)

    def test_printing_indicator_is_full_width_and_uses_device_page_progress(self):
        view = read_source(BASE_DIR / "modules/views/printing-view.js")
        runtime = read_source(BASE_DIR / "modules/shared/runtime.js")
        controller = read_source(BASE_DIR / "modules/app/app-controller.js")
        css = read_source(BASE_DIR / "css/printing.css")

        self.assertIn("renderPrintingIndicator", view)
        self.assertIn("current_page", view)
        self.assertIn("total_pages", view)
        self.assertIn("正在打印，第", view)
        self.assertIn("页……", view)
        self.assertIn("completedPages + 1", view)
        self.assertIn("Math.min(completedPages + 1, totalPages)", view)
        self.assertIn("data.current_page !== null", view)
        self.assertNotIn("张……", view)
        self.assertNotIn("printing-indicator-label", view)
        self.assertIn('aria-live="polite"', view)
        self.assertIn('id="printing_status_message"', view)
        self.assertIn('q("printing_status_message")', view)
        self.assertRegex(css, r"\.printing-status-message\s*\{[^}]*top:\s*1148px")
        self.assertNotIn(".Pixso-paragraph-115_26", css)
        self.assertNotIn("renderPrintingProgress", runtime)
        self.assertNotIn("progress >= 100", controller)
        self.assertRegex(css, r"\.Pixso-rectangle-77_20\s*\{[^}]*width:\s*556px")


    def test_preview_flow_preserves_content_hash_from_cloud_to_preview_api(self):
        controller = read_source(BASE_DIR / "modules/app/app-controller.js")
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")

        self.assertIn("content_hash: data.content_hash", controller)
        self.assertIn("content_hash: normalized.content_hash", controller)
        self.assertIn("content_hash: session.file.content_hash", preview_view)

    def test_prp_preview_does_not_require_a_public_file_url(self):
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")

        self.assertIn('session.file?.source_origin === "prp"', preview_view)
        self.assertNotIn(
            "!session.file?.file_id || !session.file?.file_url || previewLoading",
            preview_view,
        )

    def test_prp_preview_uses_the_same_print_submission_gate_as_other_sources(self):
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")

        self.assertNotIn("打印将在下一切片开放", preview_view)
        self.assertNotRegex(
            preview_view,
            r"setInteractionDisabled\(q\(\"97_460\"\),\s*locked\s*\|\|\s*isPRPSource\)",
        )
        self.assertNotRegex(
            preview_view,
            r'on\("97_460",\s*\(\)\s*=>\s*\{\s*if\s*\(isPRPSource\)\s*return;',
        )
        self.assertIn("queuePrintRequest({", preview_view)

    def test_prp_preview_back_returns_to_files_without_restarting_cycle(self):
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")
        api = read_source(BASE_DIR / "modules/shared/api.js")

        self.assertIn('prpSelection: "/api/prp/selection"', api)
        self.assertRegex(
            preview_view,
            r'async\s+function\s+returnToFiles\s*\([^)]*\)\s*\{[\s\S]*?postJson\(api\.prpSelection[\s\S]*?router\.go\("files"\)',
        )
        self.assertRegex(
            preview_view,
            r'if\s*\(\s*isPRPSource\s*\)\s*\{\s*void\s+returnToFiles\(\)',
        )

    def test_prp_preview_failure_returns_to_files_and_file_list_exposes_its_error(self):
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")

        self.assertIn("enterPreviewFailureMode", preview_view)
        self.assertIn("startCountdown(10", preview_view)
        self.assertNotIn("秒后重试", preview_view)
        self.assertIn("文件列表获取失败：${reason}", files_view)
        self.assertNotIn('error.message || "文件读取失败，请稍后重试。"', files_view)

    def test_prp_files_view_has_terminal_navigation_and_countdown(self):
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")

        self.assertIn('id="filesCountdown"', files_view)
        self.assertIn('id="filesExit"', files_view)
        self.assertIn('aria-live="polite"', files_view)
        self.assertIn("createMainCountdown", files_view)
        self.assertIn("await restartCycle()", files_view)
        self.assertIn("mainCountdown.destroy()", files_view)
        self.assertIn("exit.disabled = isFilesExitDisabled({ exiting });", files_view)
        self.assertIn("let loading = false", files_view)
        self.assertIn("function syncCountdown", files_view)
        self.assertIn("mainCountdown.start(60", files_view)
        self.assertIn("mainCountdown.pause()", files_view)
        self.assertIn("mainCountdown.resume()", files_view)
        self.assertNotIn("pointerdown", files_view)

    def test_prp_files_view_guards_duplicate_and_stale_requests(self):
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")
        api = read_source(BASE_DIR / "modules/shared/api.js")

        self.assertIn("const controllers = new Map()", files_view)
        self.assertIn("controllers.get(providerID)?.abort()", files_view)
        self.assertIn("controllers.get(providerID) !== controller", files_view)
        self.assertIn("controllers.forEach((controller) => controller.abort())", files_view)
        self.assertIn("fetch(url, { cache: \"no-store\", ...options })", api)

    def test_file_navigation_failures_keep_the_session_countdown_without_auto_retry(self):
        api = read_source(BASE_DIR / "modules/shared/api.js")
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")
        controller = read_source(BASE_DIR / "modules/app/app-controller.js")

        self.assertIn("getJson(", files_view)
        self.assertIn("createMainCountdown", files_view)
        self.assertIn("mainCountdown.start(60", files_view)
        self.assertNotIn("startCountdown(10", files_view)
        self.assertNotIn("isTransientRequestError(error)", files_view)
        self.assertNotIn("filesRetryTimer", files_view)
        self.assertNotIn("filesRetryCountdown", files_view)
        self.assertNotIn("秒后重试", files_view)
        self.assertRegex(files_view, r"async function exitToQrCode[\s\S]*?mainCountdown\.stop\(\)")
        self.assertIn("let filesFailureMode = false", files_view)
        self.assertNotIn("filesAutoRetryUsed", files_view)
        self.assertIn("createMainCountdown", preview_view)
        self.assertIn("startCountdown(60", preview_view)
        self.assertIn("startCountdown(10", preview_view)
        self.assertNotIn("previewRetryTimer", preview_view)
        self.assertNotIn("previewRetryCountdown", preview_view)
        self.assertNotIn("returnRetryTimer", preview_view)
        self.assertNotIn("returnRetryCountdown", preview_view)
        self.assertNotIn("秒后重试", preview_view)
        self.assertNotIn("retryRequest", preview_view)
        self.assertIn("postJson(api.prpSelection", preview_view)
        self.assertNotIn("retryRequest", controller)
        self.assertIn("postJson(api.prpSelection", controller)
        self.assertNotIn("attempts:", api)

    def test_business_locks_remain_separate_from_loading_locks(self):
        login_view = read_source(BASE_DIR / "modules/views/login-view.js")
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")
        preview_view = read_source(BASE_DIR / "modules/views/preview-view.js")
        done_view = read_source(BASE_DIR / "modules/views/done-view.js")

        self.assertIn("loginQrRefreshing", login_view)
        self.assertIn("let loading = false", files_view)
        self.assertIn("previewFailureMode", preview_view)
        self.assertIn("let doneLoading = false", done_view)
        self.assertIn("isFaultLockedDoneResult(result)", done_view)

    def test_prp_files_page_size_fits_the_terminal_canvas(self):
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")

        self.assertIn("page_size=6", files_view)
        self.assertNotIn("page_size=20", files_view)

    def test_prp_files_css_uses_the_terminal_canvas_and_visual_language(self):
        files_view = read_source(BASE_DIR / "modules/app/prp-files.js")
        files_css = read_source(BASE_DIR / "css/files.css")

        self.assertIn("width: 1080px", files_css)
        self.assertIn("min-height: 1920px", files_css)
        self.assertIn('class="files-terminal-shell fill-bg-gradient"', files_view)
        self.assertNotIn(".files-terminal-card", files_css)
        self.assertNotIn("files-eyebrow", files_view)
        self.assertNotIn("files-helper", files_view)
        self.assertNotIn("files-security-note", files_view)
        self.assertIn(".files-countdown", files_css)
        self.assertRegex(files_css, r"\.files-countdown\s*\{[^}]*width:\s*51px[^}]*height:\s*51px")
        self.assertIn("preview__Ellipse_97_448.png", files_css)

    def test_removed_legacy_pages_do_not_reintroduce_duplicate_frontend_logic(self):
        self.assertFalse((BASE_DIR / "main.js").exists())
        self.assertEqual([], list((BASE_DIR / "modules/pages").glob("*.js")))


if __name__ == "__main__":
    unittest.main()
