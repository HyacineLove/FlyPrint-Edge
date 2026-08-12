import { on, setText } from "../shared/dom.js";
import { api, getJson } from "../shared/api.js";
import { createMainCountdown } from "../shared/countdown.js";
import { confirmLogout } from "../shared/logout.js";
import {
  canContinueToFilesAfterDone,
  faultAvailabilityMessage,
  isFaultLockedDoneResult,
  isPrinterFaultDoneResult,
  isUnconfirmedDoneResult,
} from "../shared/done-result.js";

export function renderDoneView() {
  return `
<div class="scroll-container-0_1">
  <div id="0_1" class="Pixso-canvas-0_1">
    <div id="55_158" class="Pixso-frame-55_158 fill-bg-gradient">
      <div id="115_17" class="Pixso-rectangle-115_17"></div>
      <div id="115_18" class="Pixso-group-115_18" aria-label="剩余时间">
        <div id="115_19" class="Pixso-vector-115_19 ui-countdown-ring"></div>
        <p id="doneCountdown" class="Pixso-paragraph-115_20">—</p>
      </div>
      <p id="115_21" class="Pixso-paragraph-115_21">2025/01/01 10:00:00</p>
      <div id="77_17" class="Pixso-rectangle-77_17"></div>
      <p id="77_18" class="Pixso-paragraph-77_18"></p>
      <p id="77_21" class="Pixso-paragraph-77_21"></p>
      <button id="donePrinterRefresh" class="done-printer-refresh" type="button" hidden>刷新检测</button>
      <button id="115_43" class="Pixso-group-115_43" type="button">
        <div class="done-secondary-action-surface"></div>
        <p class="Pixso-paragraph-115_45">退出登录</p>
      </button>
      <button id="115_40" class="Pixso-group-115_40 ui-action-button ui-action-button--primary" type="button" hidden>
        <div id="115_41" class="Pixso-rectangle-115_41 fill-primary-gradient"></div>
        <p id="115_42" class="Pixso-paragraph-115_42">继续打印</p>
      </button>
      <p id="115_26" class="Pixso-paragraph-115_26"></p>
    </div>
  </div>
</div>
`;
}

export function bindDoneViewEvents({ appState, restartCycle, continueToFiles, returnToHome }) {
  const result = appState.session.doneResult || { type: "success", message: "" };
  const canContinueToFiles = canContinueToFilesAfterDone({
    result,
    sessionId: appState.session?.session_id,
    sourceOrigin: appState.session?.file?.source_origin,
  });
  const logoutButton = document.getElementById("115_43");
  const logoutLabel = logoutButton?.querySelector(".Pixso-paragraph-115_45");
  logoutButton?.classList.add("ui-action-button", "ui-action-button--secondary");
  if (logoutButton) logoutButton.classList.toggle("single-action", !canContinueToFiles);
  const continueButton = document.getElementById("115_40");
  if (continueButton) continueButton.hidden = !canContinueToFiles;
  const refreshButton = document.getElementById("donePrinterRefresh");
  refreshButton?.classList.add("ui-action-button", "ui-action-button--secondary");
  const countdownElement = document.getElementById("115_18");
  document.getElementById("115_19")?.classList.add("ui-countdown-ring");
  document.getElementById("doneCountdown")?.classList.add("ui-countdown-value");
  countdownElement?.classList.add("ui-main-countdown");
  let continueInFlight = false;
  let doneLoading = false;
  let availabilityCheckInFlight = false;
  const mainCountdown = createMainCountdown({
    render: (value, phase) => {
      setText(["doneCountdown"], String(value));
      if (countdownElement) countdownElement.dataset.countdownPhase = phase;
    },
  });
  const startCountdown = (seconds, action) => mainCountdown.start(seconds, action);
  function isPrinterFaultResult() {
    return isPrinterFaultDoneResult(result);
  }

  function isUnconfirmedResult() {
    return isUnconfirmedDoneResult(result);
  }

  function setLogoutEnabled(enabled) {
    const button = logoutButton;
    if (!button) return;
    button.style.pointerEvents = enabled ? "auto" : "none";
    button.style.opacity = enabled ? "1" : "0.45";
    button.style.cursor = enabled ? "pointer" : "not-allowed";
    button.disabled = !enabled;
    button.classList.toggle("is-business-locked", !enabled);
    button.setAttribute("aria-disabled", enabled ? "false" : "true");
  }

  function setRefreshEnabled(enabled) {
    if (!refreshButton) return;
    refreshButton.disabled = !enabled;
    refreshButton.style.pointerEvents = enabled ? "auto" : "none";
    refreshButton.style.opacity = enabled ? "1" : "0.45";
    refreshButton.classList.toggle("is-loading", !enabled && doneLoading);
    refreshButton.setAttribute("aria-disabled", enabled ? "false" : "true");
  }

  function beginLoading() {
    doneLoading = true;
    mainCountdown.stop("loading");
    setLogoutEnabled(false);
    setRefreshEnabled(false);
    if (continueButton) continueButton.disabled = true;
  }

  async function leave({ requireConfirmation = false } = {}) {
    if (continueInFlight || doneLoading) return;
    if (requireConfirmation && !(await confirmLogout())) return;
    beginLoading();
    mainCountdown.stop();
    void restartCycle();
  }

  async function checkPrinterAvailability() {
    if (availabilityCheckInFlight || doneLoading) return;
    availabilityCheckInFlight = true;
    beginLoading();
    try {
      const availability = await getJson(api.printerAvailability);
      if (!availability?.faulted) {
        setText(["77_21"], "打印机已恢复，可退出登录后继续使用");
        setLogoutEnabled(true);
        setRefreshEnabled(false);
        doneLoading = false;
        startCountdown(10, () => returnToHome?.());
        return;
      }
      setText(["77_21"], faultAvailabilityMessage(availability));
    } catch (error) {
      setText(["77_21"], error?.message || "打印机状态检测失败，请重试");
    } finally {
      availabilityCheckInFlight = false;
      if (doneLoading) {
        doneLoading = false;
        setLogoutEnabled(false);
        setRefreshEnabled(true);
        startCountdown(10, checkPrinterAvailability);
      }
    }
  }

  async function continueSelection() {
    if (!canContinueToFiles || !continueToFiles || continueInFlight || doneLoading) return;
    continueInFlight = true;
    beginLoading();
    try {
      await continueToFiles();
      mainCountdown.destroy();
    } catch (error) {
      continueInFlight = false;
      doneLoading = false;
      setLogoutEnabled(true);
      if (continueButton) continueButton.disabled = false;
      setText(["77_21"], error?.message || "暂时无法返回文件列表，请稍后重试");
      startCountdown(10, continueSelection);
    }
  }

  if (isFaultLockedDoneResult(result)) {
    const unconfirmed = isUnconfirmedResult();
    setText(["77_18"], unconfirmed ? "结果待确认" : "设备维护中");
    setText(["77_21"], result.message || (unconfirmed ? "请勿重复提交，请联系工作人员。" : "打印机故障，请联系管理员处理"));
    if (refreshButton) refreshButton.hidden = false;
    refreshButton?.classList.add("fault-action");
    logoutButton?.classList.add("fault-session-exited");
    if (logoutLabel) logoutLabel.textContent = "返回首页";
    setLogoutEnabled(false);
    setRefreshEnabled(true);
    startCountdown(10, checkPrinterAvailability);
    on("donePrinterRefresh", () => void checkPrinterAvailability());
    on("115_43", () => void returnToHome?.());
    return {
      destroy() {
        mainCountdown.destroy();
      },
    };
  }

  if (refreshButton) refreshButton.hidden = true;
  if (result.type === "error") {
    setText(["77_18"], "打印失败");
    setText(["77_21"], result.message || "云端服务异常，请稍后重试");
    setLogoutEnabled(true);
    startCountdown(10, leave);
  } else {
    setText(["77_18"], "打印完成");
    setText(["77_21"], "请尽快取走您的文件");
    setLogoutEnabled(true);
    startCountdown(10, leave);
  }

  on("115_43", () => void leave({ requireConfirmation: true }));
  on("115_40", () => void continueSelection());

  return {
    destroy() {
      mainCountdown.destroy();
    },
  };
}
