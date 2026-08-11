import { api, getJson, postJson } from "../shared/api.js";
import { createMainCountdown } from "../shared/countdown.js";
import { createRequestGate } from "../shared/request-gate.js";
import { saveSessionState } from "../shared/session-state.js";
import { confirmLogout } from "../shared/logout.js";

const ITEM_KEYS = new Set([
  "id", "name", "media_type", "size", "sha256",
  "created_at", "expires_at", "last_downloaded_at",
]);
const SUPPORTED_MEDIA_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);
const FILE_LIST_REQUEST_TIMEOUT_MS = 35_000;
function fileTypeLabel(mediaType) {
  if (mediaType === "application/pdf") return "PDF";
  if (mediaType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document") return "DOCX";
  return "图片";
}

const PORTAL_SESSION_INVALID_CODES = new Set([
  "account_logged_out",
  "identity_session_expired",
  "portal_session_invalid",
  "session_expired",
  "unauthorized",
]);

export function isPortalSessionInvalidError(error) {
  const code = String(error?.code || "").trim().toLowerCase();
  return Number(error?.status) === 401 || PORTAL_SESSION_INVALID_CODES.has(code);
}

export function isFilesExitDisabled({ exiting = false } = {}) {
  return Boolean(exiting);
}

export function createTimedRequestSignal(parentSignal, timeoutMs) {
  const controller = new AbortController();
  let timedOut = false;
  const abortFromParent = () => controller.abort();
  if (parentSignal) {
    if (parentSignal.aborted) {
      abortFromParent();
    } else {
      parentSignal.addEventListener("abort", abortFromParent, { once: true });
    }
  }
  const timer = globalThis.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    dispose() {
      globalThis.clearTimeout(timer);
      parentSignal?.removeEventListener("abort", abortFromParent);
    },
  };
}

export function mapPRPFileError(error) {
  const code = String(error?.code || "").trim().toLowerCase();
  const message = String(error?.message || "").trim();
  const messages = {
    prp_unavailable: "文件服务暂时不可用，请稍后重试",
    prp_list_timeout: "文件列表加载超时，请检查网络后重试",
    prp_list_failed: "文件列表暂时无法获取，请稍后重试",
    prp_response_too_large: "文件列表响应异常，请稍后重试",
    prp_download_failed: "文件下载失败，请重新选择文件",
    file_not_found: "文件不存在或已过期，请刷新列表后重试",
    file_too_large: "文件超过文件服务允许的下载大小，无法选择",
    unsupported_file_type: "文件类型不支持，请选择其他文件",
    content_length_mismatch: "文件传输不完整，请重新选择文件",
    content_hash_mismatch: "文件校验失败，请重新选择文件",
    invalid_prp_response: "文件服务返回的数据无效，请稍后重试",
  };
  return messages[code] || message || "文件操作失败，请稍后重试";
}

export function normalizePRPFilePage(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("文件列表无效");
  const { items, page, page_size: pageSize, total } = payload;
  if (!Array.isArray(items) || !Number.isInteger(page) || page < 1 ||
      !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 50 ||
      !Number.isInteger(total) || total < 0) throw new Error("文件分页无效");
  const normalized = items.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item) ||
        Object.keys(item).some((key) => !ITEM_KEYS.has(key)) ||
        typeof item.id !== "string" || !item.id ||
        typeof item.name !== "string" || !item.name ||
        !SUPPORTED_MEDIA_TYPES.has(item.media_type) ||
        !Number.isInteger(item.size) || item.size < 0 ||
        typeof item.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(item.sha256) ||
        Number.isNaN(Date.parse(item.created_at)) || Number.isNaN(Date.parse(item.expires_at)) ||
        (item.last_downloaded_at !== null && Number.isNaN(Date.parse(item.last_downloaded_at)))) {
      throw new Error("文件数据无效");
    }
    return { ...item };
  });
  return { items: normalized, page, page_size: pageSize, total };
}

export function renderPRPFilesView() {
  return `
<div class="files-terminal-shell fill-bg-gradient">
  <main id="filesView" class="files-view" aria-labelledby="filesGreeting">
    <header class="files-header">
      <div class="files-header-title-row">
        <h1 id="filesGreeting">请选择文件</h1>
        <button id="filesRefresh" class="files-refresh ui-pager-button" type="button">刷新</button>
      </div>
      <div class="files-countdown ui-main-countdown" data-countdown-phase="idle" aria-label="会话剩余时间">
        <span class="ui-countdown-ring" aria-hidden="true"></span>
        <strong id="filesCountdown" class="ui-countdown-value">—</strong>
      </div>
      <p id="filesClock" class="files-clock">2025/01/01 10:00:00</p>
    </header>

    <section id="filesPanel" class="files-panel" aria-busy="true">
      <div class="files-panel-heading">
        <p id="filesStatus" class="files-status" aria-live="polite"></p>
      </div>
      <div id="filesList" class="files-list" role="list"></div>
      <div class="files-pager" aria-label="文件列表分页">
        <button id="filesPrev" type="button">上一页</button>
        <span id="filesPage">1 / 1</span>
        <button id="filesNext" type="button">下一页</button>
      </div>
    </section>

    <div class="ui-action-region files-action-region files-action-region--single is-single">
      <button id="filesExit" class="files-exit ui-action-button ui-action-button--primary" type="button">退出登录</button>
    </div>
  </main>
</div>`;
}

export function createPRPFilesRefreshHandler(getCurrentPage, load) {
  return () => void load(getCurrentPage());
}

export function bindPRPFilesViewEvents({ appState, router, restartCycle }) {
  let currentPage = 1;
  let pageCount = 1;
  let loading = false;
  let filesFailureMode = false;
  let exiting = false;
  let loadingHintTimer = null;
  const sessionId = appState.session.session_id;
  const requestGate = createRequestGate();
  const panel = document.getElementById("filesPanel");
  const status = document.getElementById("filesStatus");
  const list = document.getElementById("filesList");
  const greeting = document.getElementById("filesGreeting");
  const previous = document.getElementById("filesPrev");
  const next = document.getElementById("filesNext");
  const refresh = document.getElementById("filesRefresh");
  const exit = document.getElementById("filesExit");
  const countdown = document.getElementById("filesCountdown");
  const countdownContainer = document.querySelector(".files-countdown");
  const mainCountdown = createMainCountdown({
    render: (value, phase) => {
      countdown.textContent = String(value);
      if (countdownContainer) countdownContainer.dataset.countdownPhase = phase;
    },
  });
  const startCountdown = (seconds, action) => mainCountdown.start(seconds, action);
  greeting.textContent = `${appState.session.identity?.display_name || "用户"}，请选择文件`;

  function beginLoading() {
    loading = true;
    mainCountdown.stop("loading");
    clearLoadingHintTimer();
    setStatus("正在加载文件列表，请稍候...", "loading");
    loadingHintTimer = window.setTimeout(() => {
      if (loading) setStatus("网络较慢，文件列表仍在加载，请稍候...", "loading");
    }, 3000);
    setBusy(true);
  }

  function endLoading({ releaseControls = true, retry = false, action = exitToQrCode } = {}) {
    loading = false;
    clearLoadingHintTimer();
    if (!releaseControls) return;
    setBusy(false);
    if (retry) {
      startCountdown(10, action);
    } else {
      startCountdown(60, action);
    }
  }

  function clearLoadingHintTimer() {
    if (loadingHintTimer) {
      window.clearTimeout(loadingHintTimer);
      loadingHintTimer = null;
    }
  }

  function setStatus(message, kind = "") {
    status.textContent = message;
    status.dataset.statusKind = kind;
  }

  function setBusy(busy) {
    panel.setAttribute("aria-busy", busy ? "true" : "false");
    panel.classList.toggle("is-loading", busy);
    previous.disabled = busy || filesFailureMode || currentPage <= 1;
    next.disabled = busy || filesFailureMode || currentPage >= pageCount;
    refresh.disabled = busy;
    exit.disabled = isFilesExitDisabled({ exiting });
    refresh.classList.toggle("is-loading", busy);
    exit.classList.toggle("is-loading", busy && exiting);
    list.querySelectorAll(".files-item").forEach((item) => {
      item.disabled = busy || filesFailureMode;
      item.classList.toggle("is-loading", busy);
      item.classList.toggle("is-business-locked", filesFailureMode && !busy);
    });
  }

  function sessionIsCurrent(request) {
    return requestGate.isCurrent(request) && appState.session.session_id === sessionId;
  }

  async function exitToQrCode({ requireConfirmation = false } = {}) {
    if (exiting) return;
    if (requireConfirmation && !confirmLogout()) return;
    exiting = true;
    mainCountdown.stop();
    requestGate.cancel();
    beginLoading();
    await restartCycle();
  }

  async function load(page) {
    const request = requestGate.start();
    if (!request) return;
    filesFailureMode = false;
    let loaded = false;
    let failureAction = () => load(page);
    const timedRequest = createTimedRequestSignal(
      request.signal,
      FILE_LIST_REQUEST_TIMEOUT_MS,
    );
    beginLoading();
    list.replaceChildren();
    try {
      const data = normalizePRPFilePage(await getJson(
        `${api.prpFiles}?session_id=${encodeURIComponent(sessionId)}&page=${page}&page_size=6`,
        { signal: timedRequest.signal },
      ));
      if (!sessionIsCurrent(request)) return;
      filesFailureMode = false;
      loaded = true;
      currentPage = data.page;
      pageCount = Math.max(1, Math.ceil(data.total / data.page_size));
      document.getElementById("filesPage").textContent = `${currentPage} / ${pageCount}`;
      setStatus(data.items.length ? "" : "暂无文件，请先上传", data.items.length ? "" : "empty");
      for (const item of data.items) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "files-item";
        row.setAttribute("role", "listitem");
        const badge = document.createElement("span");
        badge.className = "files-item-badge";
        badge.textContent = fileTypeLabel(item.media_type);
        const summary = document.createElement("span");
        summary.className = "files-item-summary";
        const name = document.createElement("strong");
        name.textContent = item.name;
        const detail = document.createElement("span");
        detail.className = "files-item-detail";
        detail.textContent = `${Math.ceil(item.size / 1024)} KB`;
        const arrow = document.createElement("span");
        arrow.className = "files-item-arrow";
        arrow.setAttribute("aria-hidden", "true");
        arrow.textContent = "›";
        summary.append(name, detail);
        row.append(badge, summary, arrow);
        row.onclick = () => select(item, row);
        list.append(row);
      }
    } catch (error) {
      const timedOut = timedRequest.didTimeout();
      if (sessionIsCurrent(request) && (error?.name !== "AbortError" || timedOut)) {
        filesFailureMode = true;
        const displayError = timedOut ? { code: "prp_list_timeout" } : error;
        error = { ...displayError, message: mapPRPFileError(displayError) };
        const reason = String(error?.message || "请稍后重试。").trim();
        if (isPortalSessionInvalidError(error)) {
          failureAction = exitToQrCode;
          setStatus("账号已退出，请重新扫码登录", "session-expired");
        } else {
          setStatus(`文件列表获取失败：${reason}`, "error");
        }
      }
    } finally {
      timedRequest.dispose();
      if (requestGate.finish(request)) {
        endLoading({
          retry: !loaded,
          action: loaded ? exitToQrCode : failureAction,
        });
      }
    }
  }

  async function select(item) {
    const request = requestGate.start();
    if (!request) return;
    filesFailureMode = false;
    let selected = false;
    let failureAction = () => select(item);
    beginLoading();
    try {
      const result = await postJson(`${api.prpFiles}/${encodeURIComponent(item.id)}/select`, {
        session_id: sessionId,
      }, { signal: request.signal });
      if (!sessionIsCurrent(request)) return;
      const file = result.file;
      appState.session.file = {
        file_id: file.file_id, file_name: file.file_name, file_type: file.file_type,
        content_hash: file.content_hash, source_origin: "prp", file_url: null,
        page_count: 1, page_index: 0, print_options: {},
      };
      appState.sessionPhase = "preview_ready";
      saveSessionState();
      selected = true;
      requestGate.finish(request);
      endLoading({ releaseControls: false });
      await router.go("preview");
    } catch (error) {
      if (sessionIsCurrent(request) && error?.name !== "AbortError") {
        filesFailureMode = true;
        error = { ...error, message: mapPRPFileError(error) };
        const reason = String(error?.message || "请稍后重试").trim();
        if (isPortalSessionInvalidError(error)) {
          failureAction = exitToQrCode;
          setStatus("账号已退出，请重新扫码登录", "session-expired");
        } else {
          setStatus(`选择文件失败：${reason}`, "error");
        }
      }
    } finally {
      if (requestGate.finish(request)) {
        endLoading({
          retry: !selected,
          action: selected ? exitToQrCode : failureAction,
        });
      }
    }
  }

  previous.onclick = () => void load(currentPage - 1);
  next.onclick = () => void load(currentPage + 1);
  refresh.onclick = createPRPFilesRefreshHandler(() => currentPage, load);
  exit.onclick = () => void exitToQrCode({ requireConfirmation: true });
  void load(1);
  return {
    destroy() {
      mainCountdown.destroy();
      clearLoadingHintTimer();
      requestGate.cancel();
    },
  };
}
