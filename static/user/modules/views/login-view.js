import { api, getJson } from "../shared/api.js";
import { createMainCountdown } from "../shared/countdown.js";
import { clearBg, on, q, setBg, setText } from "../shared/dom.js";
import {
  createDefaultCapabilityState,
  normalizeRuntimeSettings,
  saveSessionState,
  setOpsContacts,
} from "../shared/session-state.js";
import {
  mapQrErrorMessage,
  renderCommonText,
  setQrCenterVisible,
} from "../shared/runtime.js";

export function renderLoginView() {
  return `
<div class="scroll-container-0_1">
  <div id="0_1" class="Pixso-canvas-0_1">
    <div id="3_24" class="Pixso-frame-3_24">
      <div id="97_164" class="Pixso-rectangle-97_164"></div>
      <p id="97_158" class="Pixso-paragraph-97_158"></p>
      <div id="3_33" class="Pixso-rectangle-3_33"></div>
      <div id="97_166" class="Pixso-group-97_166">
        <div id="3_35" class="Pixso-rectangle-3_35"></div>
        <p id="3_45" class="Pixso-paragraph-3_45"></p>
        <button id="3_28" class="Pixso-group-3_28 ui-action-trigger" type="button">
          <div id="3_29" class="Pixso-rectangle-3_29 fill-primary-gradient"></div>
          <p id="3_30" class="Pixso-paragraph-3_30"></p>
        </button>
        <div id="97_159" class="Pixso-group-97_159">
          <div id="3_37" class="Pixso-rectangle-3_37"></div>
          <div id="3_39" class="Pixso-rectangle-3_39"></div>
          <div id="3_26" class="Pixso-rectangle-3_26"></div>
          <div id="qrCenterStatus" class="qr-center-status is-hidden" aria-live="polite"></div>
        </div>
        <p id="3_46" class="Pixso-paragraph-3_46"></p>
      </div>
      <div id="77_54" class="Pixso-group-77_54 ui-main-countdown" data-countdown-phase="idle" aria-label="会话剩余时间">
        <div id="77_55" class="Pixso-vector-77_55 ui-countdown-ring"></div>
        <p id="77_56" class="Pixso-paragraph-77_56 ui-countdown-value">—</p>
      </div>
      <div id="97_155" class="Pixso-rectangle-97_155"></div>
      <p id="97_161" class="Pixso-paragraph-97_161">2025/01/01 10:00:00</p>
      <p id="97_162" class="Pixso-paragraph-97_162"></p>
    </div>
  </div>
</div>
`;
}

export function bindLoginViewEvents({ appState }) {
  const { session } = appState;
  let loginQrRefreshing = false;
  let terminalOccupied = false;
  const mainCountdown = createMainCountdown({
    render: (value, phase) => {
      setText(["77_56"], String(value));
      const countdown = q("77_54");
      if (countdown) countdown.dataset.countdownPhase = phase;
    },
  });
  const startCountdown = (seconds, action) => mainCountdown.start(seconds, action);

  function setQrCenterStatus(message) {
    const el = q("qrCenterStatus");
    if (!el) return;
    const text = String(message || "").trim();
    if (!text) {
      el.textContent = "";
      el.classList.add("is-hidden");
      return;
    }
    el.textContent = text;
    el.classList.remove("is-hidden");
  }

  function setTerminalOccupied(occupied, { message = "终端使用中\n请稍候或点击刷新" } = {}) {
    terminalOccupied = Boolean(occupied);
    if (occupied) {
      mainCountdown.stop();
      clearBg("3_37");
      setQrCenterVisible(false);
      setQrCenterStatus(message);
      setText(["77_56"], "—");
      updateManualRefreshState();
    }
  }

  function setManualRefreshDisabled(disabled) {
    const btn = q("3_28");
    if (!btn) return;
    btn.disabled = disabled;
    btn.classList.toggle("manual-refresh-disabled", !!disabled);
    btn.style.cursor = disabled ? "not-allowed" : "pointer";
    btn.style.pointerEvents = disabled ? "none" : "auto";
    btn.setAttribute("aria-disabled", disabled ? "true" : "false");
  }

  function updateManualRefreshState() {
    setManualRefreshDisabled(loginQrRefreshing);
  }

  function setLoginErrorCountdown(message) {
    terminalOccupied = false;
    clearBg("3_37");
    setQrCenterVisible(false);
    setQrCenterStatus(message);
    startCountdown(10, refreshQrCode);
  }

  function setQrRefreshLoading() {
    setQrCenterVisible(false);
  }

  async function refreshQrCode() {
    if (loginQrRefreshing) return false;
    terminalOccupied = false;
    const qrWrap = q("3_37");
    clearBg("3_37");
    loginQrRefreshing = true;
    mainCountdown.stop("loading");
    updateManualRefreshState();
    setQrRefreshLoading();
    setQrCenterStatus("获取二维码中");

    if (qrWrap) qrWrap.style.opacity = "0.6";

    try {
      const qr = await getJson(api.qr);
      if (terminalOccupied) return false;
      if (qr?.standby || qr?.success === false) {
        session.session_id = null;
        setLoginErrorCountdown(mapQrErrorMessage(qr?.error_code, qr?.message));
        return false;
      }
      if (qr?.success && qr.qr_url) {
        session.session_id = qr.session_id || null;
        session.file = {};
        session.runtimeSettings = normalizeRuntimeSettings(qr.settings);
        setOpsContacts(session.runtimeSettings.ops_contacts);
        session.opsContacts = session.runtimeSettings.ops_contacts || [];
        session.defaultPrinterCapabilities =
          qr.default_printer_capabilities && typeof qr.default_printer_capabilities === "object"
            ? qr.default_printer_capabilities
            : null;
        session.capabilityState = createDefaultCapabilityState();
        saveSessionState();
        renderCommonText("login");
        setBg("3_37", qr.qr_url);
        setQrCenterVisible(true);
        setQrCenterStatus("");
        startCountdown(60, refreshQrCode);
        return true;
      }
      setLoginErrorCountdown("二维码响应异常");
      return false;
    } catch (error) {
      session.session_id = null;
      setLoginErrorCountdown(mapQrErrorMessage(error?.code, error?.message || "二维码获取失败"));
      return false;
    } finally {
      if (qrWrap) qrWrap.style.opacity = "1";
      loginQrRefreshing = false;
      updateManualRefreshState();
    }
  }

  setText(["77_56"], "0");
  clearBg("3_37");
  setQrCenterVisible(false);

  on("3_28", () => {
    if (loginQrRefreshing) return;
    void refreshQrCode();
  });

  void refreshQrCode();

  return {
    setLoginErrorCountdown,
    setTerminalOccupied,
    destroy() {
      mainCountdown.destroy();
    },
  };
}
