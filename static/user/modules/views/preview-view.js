import { api, postJson } from "../shared/api.js";
import { applyPrinterCapabilityState, setOptionDisabledState } from "../shared/capabilities.js";
import { createMainCountdown } from "../shared/countdown.js";
import {
  on,
  q,
  setPreviewBg,
  setPreviewOrientation,
  setText,
} from "../shared/dom.js";
import {
  clearPendingPrintRequest,
  createDefaultCapabilityState,
  createDefaultOptions,
  currentSessionId,
  defaultPaperSize,
  ensureStateOptions,
  getCopyLimitState,
  normalizeCopies,
  normalizeOrientation,
  normalizeRuntimeSettings,
  normalizeScalePercent,
  maxScalePercent,
  minScalePercent,
  orientationFromPaperSize,
  saveSessionState,
} from "../shared/session-state.js";
import {
  mapPreviewErrorMessage,
  normalizeDuplexForApi,
} from "../shared/runtime.js";

export function renderPreviewView() {
  return `
<div class="scroll-container-0_1">
  <div id="0_1" class="Pixso-canvas-0_1">
    <div id="55_77" class="Pixso-frame-55_77 fill-bg-gradient">
      <div id="97_446" class="Pixso-rectangle-97_446"></div>
      <div id="97_447" class="Pixso-group-97_447 ui-main-countdown" data-countdown-phase="idle" aria-label="浼氳瘽鍓╀綑鏃堕棿">
        <div id="97_448" class="Pixso-vector-97_448 ui-countdown-ring"></div>
        <p id="97_449" class="Pixso-paragraph-97_449 ui-countdown-value">鈥?/p>
      </div>
      <p id="97_450" class="Pixso-paragraph-97_450">2025/01/01 10:00:00</p>
      <button id="97_454" class="Pixso-group-97_454 ui-action-trigger" type="button">
        <div id="97_455" class="Pixso-rectangle-97_455"></div>
        <p id="97_456" class="Pixso-paragraph-97_456"></p>
      </button>
      <div id="97_457" class="Pixso-rectangle-97_457"></div>
      <p id="97_459" class="Pixso-paragraph-97_459"></p>
      <button id="97_460" class="Pixso-group-97_460 ui-action-trigger" type="button">
        <div id="97_461" class="Pixso-rectangle-97_461 fill-primary-gradient"></div>
        <p id="97_462" class="Pixso-paragraph-97_462"></p>
      </button>
      <div id="115_60" class="Pixso-group-115_60 preview-options-panel" aria-label="打印设置">
        <section class="preview-option-card preview-option-card--copies">
          <p id="55_113" class="preview-option-label"></p>
          <div class="preview-copies-control">
            <button id="55_116" class="preview-choice-button preview-step-button" type="button" aria-label="减少份数"><span id="55_117">−</span></button>
            <span id="55_118" class="preview-copies-value" data-role="copies-value">1</span>
            <button id="55_114" class="preview-choice-button preview-step-button" type="button" aria-label="增加份数"><span id="55_119">+</span></button>
          </div>
        </section>
        <section class="preview-option-card">
          <p id="preview-orientation-label" class="preview-option-label">纸张方向</p>
          <div class="preview-option-choices">
            <button id="preview-orientation-portrait" class="preview-choice-button" type="button">竖向</button>
            <button id="preview-orientation-landscape" class="preview-choice-button" type="button">横向</button>
          </div>
        </section>
        <section class="preview-option-card">
          <p id="55_124" class="preview-option-label"></p>
          <div class="preview-option-choices">
            <button id="55_122" class="preview-choice-button" type="button"><span id="55_126"></span></button>
            <button id="55_123" class="preview-choice-button" type="button"><span id="55_125"></span></button>
          </div>
        </section>
        <section class="preview-option-card preview-option-card--scale">
          <p id="preview-scale-label" class="preview-option-label">缩放</p>
          <div class="preview-copies-control">
            <button id="preview-scale-decrease" class="preview-choice-button preview-step-button" type="button" aria-label="缩小">−</button>
            <span id="preview-scale-value" class="preview-copies-value">100%</span>
            <button id="preview-scale-increase" class="preview-choice-button preview-step-button" type="button" aria-label="放大">+</button>
          </div>
        </section>
        <section class="preview-option-card preview-option-card--color">
          <p id="133_37" class="preview-option-label"></p>
          <div class="preview-option-choices">
            <button id="133_36" class="preview-choice-button" type="button"><span id="133_38"></span></button>
            <button id="133_35" class="preview-choice-button" type="button"><span id="133_39"></span></button>
          </div>
        </section>
      </div>
      <p id="97_480" class="Pixso-paragraph-97_480">-0/0页-</p>
      <p id="97_481" class="Pixso-paragraph-97_481">文档加载中...</p>
      <p id="97_473" class="Pixso-paragraph-97_473"></p>
      <div id="97_474" class="Pixso-vector-97_474"></div>
      <div id="115_56" class="Pixso-rectangle-115_56"></div>
      <div id="115_57" class="Pixso-group-115_57">
        <div id="115_58" class="Pixso-rectangle-115_58"><div id="preview-document-layer" aria-hidden="true"></div></div>
        <div id="115_59" class="Pixso-rectangle-115_59"></div>
      </div>
      <button id="115_61" class="Pixso-button-115_61" type="button" aria-label="上一页">&#8249;</button>
      <button id="115_62" class="Pixso-button-115_62" type="button" aria-label="下一页">&#8250;</button>
    </div>
  </div>
</div>
`;
}

export function bindPreviewViewEvents({ appState, router, queuePrintRequest, restartCycle }) {
  const session = appState.session;
  const isPRPSource = session.file?.source_origin === "prp";
  if (!session.file?.file_id || (!isPRPSource && !session.file?.file_url)) {
    void restartCycle();
    return { destroy() {} };
  }

  session.runtimeSettings = normalizeRuntimeSettings(session.runtimeSettings);
  const runtimeSettings = session.runtimeSettings;
  const initial = session.file?.print_options || {};
  const initialPaperSize = initial.paper_size || runtimeSettings.default_paper_size || defaultPaperSize;
  session.options = {
    ...createDefaultOptions(),
    copies: initial.copies ?? 1,
    paper_size: defaultPaperSize,
    orientation: normalizeOrientation(initial.orientation || orientationFromPaperSize(initialPaperSize)),
    color_mode: initial.color_mode === "grayscale" ? "mono" : (initial.color_mode || "color"),
    duplex: initial.duplex_mode === "duplex" ? "longedge" : "simplex",
    scale_percent: normalizeScalePercent(
      initial.scale_percent ?? runtimeSettings.default_scale_percent ?? 100
    ),
  };
  session.capabilityState = createDefaultCapabilityState();
  clearPendingPrintRequest();
  ensureStateOptions();
  applyPrinterCapabilityState(session.defaultPrinterCapabilities);
  saveSessionState();

  let previewFirstLoadDone = false;
  let previewLoading = false;
  let previewRefreshTimer = null;
  let previewCurrentPage = 0;
  let previewPageCount = 0;
  let previewFailureMode = false;
  let printSubmitting = false;
  let prpReturnInFlight = false;
  let previewControlsLocked = true;
  const mainCountdown = createMainCountdown({ render: setPreviewCountdownDisplay });
  const startCountdown = (seconds, action) => mainCountdown.start(seconds, action);

  function setPreviewCountdownDisplay(value, phase) {
    setText(["97_449"], String(value));
    const countdown = q("97_447");
    if (countdown) countdown.dataset.countdownPhase = phase;
  }

  function pausePreviewCountdown() {
    mainCountdown.stop("loading");
  }

  function resumePreviewCountdown(fullReset = false) {
    startCountdown(60, () => restartCycle());
  }

  function setPreviewLoadingPlaceholder(visible) {
    const placeholder = q("115_59");
    if (!placeholder) return;
    placeholder.classList.toggle("is-hidden", !visible);
  }

  function updatePreviewPageButtons() {
    const prevBtn = q("115_61");
    const nextBtn = q("115_62");
    if (!prevBtn || !nextBtn) return;
    const enabled =
      previewFirstLoadDone &&
      !previewControlsLocked &&
      !previewLoading &&
      !previewRefreshTimer &&
      !prpReturnInFlight &&
      !printSubmitting &&
      !previewFailureMode &&
      previewPageCount > 1;
    prevBtn.disabled = !enabled || previewCurrentPage <= 0;
    nextBtn.disabled = !enabled || previewCurrentPage >= previewPageCount - 1;
    updatePrintButtonState();
  }

  function setInteractionDisabled(element, disabled) {
    if (!element) return;
    element.classList.toggle("is-disabled", disabled);
    element.classList.toggle("is-loading", disabled && previewLoading);
    element.classList.toggle("is-business-locked", disabled && previewFailureMode);
    element.style.pointerEvents = disabled ? "none" : "auto";
    if ("disabled" in element) element.disabled = disabled;
    element.setAttribute("aria-disabled", disabled ? "true" : "false");
  }

  function updatePrintButtonState() {
    const locked =
      previewControlsLocked ||
      !previewFirstLoadDone ||
      previewLoading ||
      previewFailureMode ||
      printSubmitting ||
      Boolean(previewRefreshTimer);
    setInteractionDisabled(q("97_460"), locked);
  }

  function setPreviewControlsLocked(locked, allowBackWhenLocked = false) {
    previewControlsLocked = locked;
    const optionsGroup = q("115_60");
    const backBtn = q("97_454");

    setInteractionDisabled(optionsGroup, locked);
    setInteractionDisabled(backBtn, locked && !allowBackWhenLocked);
    updatePrintButtonState();
    updatePreviewPageButtons();
  }

  function enterPreviewFailureMode(errorMessage, retryAction) {
    previewFailureMode = true;
    pausePreviewCountdown();
    setText(["97_481"], "\u9884\u89c8\u52a0\u8f7d\u5931\u8d25");
    setText(["97_480"], `-${errorMessage || "\u8bf7\u7a0d\u540e\u91cd\u8bd5"}-`);
    setPreviewLoadingPlaceholder(true);
    setPreviewControlsLocked(true, true);
    startCountdown(10, retryAction);
  }

  function renderOptionsUI() {
    const setChoiceVisual = (id, { active = false, disabled = false } = {}) => {
      const element = q(id);
      if (!element) return;
      element.classList.toggle("is-selected", active);
      element.classList.toggle("is-option-disabled", disabled);
      element.disabled = disabled;
      element.setAttribute("aria-pressed", active ? "true" : "false");
      setOptionDisabledState([id], disabled);
    };

    const { min, max } = getCopyLimitState();
    const copies = normalizeCopies(session.options?.copies);
    session.options.copies = copies;
    setText(["55_118"], String(copies));
    setChoiceVisual("55_116", { disabled: copies <= min });
    setChoiceVisual("55_114", { disabled: copies >= max });

    const duplex = session.options?.duplex || "simplex";
    const duplexLongEdge = duplex !== "simplex";
    const duplexSupported = Boolean(session.capabilityState?.duplexSupported);
    setChoiceVisual("55_123", { active: duplexLongEdge, disabled: !duplexSupported });
    setChoiceVisual("55_122", { active: !duplexLongEdge });

    const orientation = normalizeOrientation(session.options?.orientation);
    session.options.orientation = orientation;
    setPreviewOrientation(orientation);
    setChoiceVisual("preview-orientation-portrait", { active: orientation === "portrait" });
    setChoiceVisual("preview-orientation-landscape", { active: orientation === "landscape" });

    const scalePercent = normalizeScalePercent(session.options?.scale_percent);
    session.options.scale_percent = scalePercent;
    setText(["preview-scale-value"], `${scalePercent}%`);
    setChoiceVisual("preview-scale-decrease", { disabled: scalePercent <= minScalePercent });
    setChoiceVisual("preview-scale-increase", { disabled: scalePercent >= maxScalePercent });

    const color = session.options?.color_mode || "color";
    const colorSupported = Boolean(session.capabilityState?.colorSupported);
    setChoiceVisual("133_36", { active: color === "mono" });
    setChoiceVisual("133_35", { active: color === "color", disabled: !colorSupported });

    updatePreviewPageButtons();
  }

  function buildRequestOptions({ forPreview = false } = {}) {
    return {
      copies: Number(session.options.copies || 1),
      duplex: session.options.duplex || "simplex",
      color_mode: session.options.color_mode || "color",
      orientation: normalizeOrientation(session.options.orientation),
      paper_size: defaultPaperSize,
      scale_percent: normalizeScalePercent(session.options.scale_percent),
    };
  }

  async function renderPreview(pageIndex = 0, blockUi = false, { retryAfterFailure = false } = {}) {
    if (
      !session.file?.file_id ||
      (!isPRPSource && !session.file?.file_url) ||
      previewLoading ||
      (previewFailureMode && !retryAfterFailure)
    ) return false;
    previewLoading = true;
    setPreviewLoadingPlaceholder(true);
    setPreviewControlsLocked(true);
    pausePreviewCountdown();
    updatePreviewPageButtons();

    try {
      const previewBox = q("115_58");
      const previewWidth = previewBox?.clientWidth || 620;
      const previewHeight = previewBox?.clientHeight || 870;
      const response = await postJson("/api/preview", {
        session_id: currentSessionId() || undefined,
        file_id: session.file.file_id,
        file_url: session.file.file_url,
        file_name: session.file.file_name,
        file_type: session.file.file_type,
        content_hash: session.file.content_hash,
        options: {
          ...buildRequestOptions({ forPreview: true }),
          page_index: pageIndex,
          preview_width_px: previewWidth,
          preview_height_px: previewHeight,
        },
      });

      session.file.page_count = Number(response.page_count || 1);
      session.file.page_index = Number(response.page_index || 0);
      saveSessionState();

      previewCurrentPage = session.file.page_index;
      previewPageCount = session.file.page_count;
      setText(["97_481"], session.file.file_name || "文档");
      setText(["97_480"], `-${previewCurrentPage + 1}/${previewPageCount}页-`);
      setPreviewBg("115_58", response.preview_url);
      setPreviewLoadingPlaceholder(false);

      previewFailureMode = false;
      if (!previewFirstLoadDone) {
        previewFirstLoadDone = true;
        setPreviewControlsLocked(false);
      } else {
        setPreviewControlsLocked(false);
      }
      resumePreviewCountdown(true);

      updatePreviewPageButtons();
      return true;
    } catch (error) {
      const message = mapPreviewErrorMessage(error?.code, error?.message || "预览加载失败");
      enterPreviewFailureMode(message, () => {
        previewFailureMode = false;
        void renderPreview(pageIndex, false, { retryAfterFailure: true });
      });
      setPreviewLoadingPlaceholder(true);
      return false;
    } finally {
      previewLoading = false;
      updatePreviewPageButtons();
    }
  }

  function queuePreviewRefresh() {
    if (!previewFirstLoadDone || previewLoading || previewFailureMode || prpReturnInFlight || printSubmitting) return;
    if (previewRefreshTimer) {
      window.clearTimeout(previewRefreshTimer);
      previewRefreshTimer = null;
    }
    setPreviewControlsLocked(true);
    pausePreviewCountdown();
    previewRefreshTimer = window.setTimeout(async () => {
      previewRefreshTimer = null;
      await renderPreview(previewCurrentPage, false);
    }, 120);
    updatePrintButtonState();
  }

  async function returnToFiles() {
    if (!isPRPSource || prpReturnInFlight) return false;
    prpReturnInFlight = true;
    pausePreviewCountdown();
    setPreviewControlsLocked(true);
    try {
      await postJson(api.prpSelection, {
        session_id: currentSessionId() || undefined,
      });
      session.file = {};
      appState.sessionPhase = "identity_ready";
      saveSessionState();
      await router.go("files");
      return true;
    } catch (error) {
      setText(["97_480"], `-${error?.message || "返回文件列表失败，请重试"}-`);
      setPreviewControlsLocked(previewFailureMode, previewFailureMode);
      startCountdown(10, () => returnToFiles());
      return false;
    } finally {
      prpReturnInFlight = false;
      updatePrintButtonState();
      updatePreviewPageButtons();
    }
  }

  setPreviewCountdownDisplay(60);
  setText(["97_481"], "文档加载中...");
  setText(["97_480"], "-0/0页-");
  setPreviewLoadingPlaceholder(true);

  on("97_454", () => {
    if (!previewFailureMode && !previewFirstLoadDone) return;
    if (isPRPSource) {
      void returnToFiles();
      return;
    }
    void restartCycle();
  });

  const changeCopies = (delta) => {
    if (!previewFirstLoadDone || previewLoading || previewRefreshTimer || prpReturnInFlight || printSubmitting || previewFailureMode) return;
    session.options.copies = normalizeCopies(Number(session.options.copies || 1) + delta);
    saveSessionState();
    renderOptionsUI();
    resumePreviewCountdown(true);
  };

  const pickDuplex = (value) => {
    if (!previewFirstLoadDone || previewLoading || previewRefreshTimer || prpReturnInFlight || printSubmitting || previewFailureMode) return;
    if (!session.capabilityState?.duplexSupported && value !== "simplex") return;
    session.options.duplex = value;
    saveSessionState();
    renderOptionsUI();
    resumePreviewCountdown(true);
  };

  const pickOrientation = (value) => {
    if (!previewFirstLoadDone || previewLoading || previewRefreshTimer || prpReturnInFlight || printSubmitting || previewFailureMode) return;
    session.options.orientation = normalizeOrientation(value);
    saveSessionState();
    renderOptionsUI();
    queuePreviewRefresh();
  };

  const changeScale = (delta) => {
    if (!previewFirstLoadDone || previewLoading || previewRefreshTimer || prpReturnInFlight || printSubmitting || previewFailureMode) return;
    session.options.scale_percent = normalizeScalePercent(
      Number(session.options.scale_percent || 100) + delta
    );
    saveSessionState();
    renderOptionsUI();
    queuePreviewRefresh();
  };

  const pickColor = (value) => {
    if (!previewFirstLoadDone || previewLoading || previewRefreshTimer || prpReturnInFlight || printSubmitting || previewFailureMode) return;
    if (!session.capabilityState?.colorSupported && value === "color") return;
    session.options.color_mode = value;
    saveSessionState();
    renderOptionsUI();
    queuePreviewRefresh();
  };

  on("55_116", () => changeCopies(-1));
  on("55_114", () => changeCopies(1));
  on("55_123", () => pickDuplex("longedge"));
  on("55_122", () => pickDuplex("simplex"));
  on("preview-orientation-portrait", () => pickOrientation("portrait"));
  on("preview-orientation-landscape", () => pickOrientation("landscape"));
  on("preview-scale-decrease", () => changeScale(-10));
  on("preview-scale-increase", () => changeScale(10));
  on("133_35", () => pickColor("color"));
  on("133_36", () => pickColor("mono"));

  on("115_61", async () => {
    if (!previewFirstLoadDone || previewControlsLocked || previewLoading || previewRefreshTimer || prpReturnInFlight || printSubmitting || previewFailureMode || previewCurrentPage <= 0) return;
    const ok = await renderPreview(previewCurrentPage - 1, false);
    if (ok) resumePreviewCountdown(true);
  });
  on("115_62", async () => {
    if (!previewFirstLoadDone || previewControlsLocked || previewLoading || previewRefreshTimer || prpReturnInFlight || printSubmitting || previewFailureMode || previewCurrentPage >= previewPageCount - 1) return;
    const ok = await renderPreview(previewCurrentPage + 1, false);
    if (ok) resumePreviewCountdown(true);
  });
  on("97_460", () => {
    if (
      !previewFirstLoadDone ||
      previewLoading ||
      previewFailureMode ||
      previewRefreshTimer ||
      !session.file?.file_id ||
      printSubmitting
    ) return;
    printSubmitting = true;
    setPreviewControlsLocked(true);
    queuePrintRequest({
      session_id: currentSessionId() || undefined,
      file_id: session.file.file_id,
      task_token: session.file.task_token || undefined,
      options: {
        ...buildRequestOptions(),
        copies: Number(session.options.copies || 1),
        duplex: normalizeDuplexForApi(session.options.duplex),
        color_mode: session.options.color_mode || "color",
        scale_percent: normalizeScalePercent(session.options.scale_percent),
      },
    });
  });

  renderOptionsUI();
  setPreviewControlsLocked(true);
  void renderPreview(0, true);

  return {
    handlePreviewError(message) {
      enterPreviewFailureMode(message, () => {
        previewFailureMode = false;
        void renderPreview(previewCurrentPage, false, { retryAfterFailure: true });
      });
    },
    destroy() {
      mainCountdown.destroy();
      if (previewRefreshTimer) window.clearTimeout(previewRefreshTimer);
    },
  };
}
