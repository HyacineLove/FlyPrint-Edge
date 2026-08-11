import { api, getJson, postJson } from "../shared/api.js";
import { createMainCountdown } from "../shared/countdown.js";
import { saveSessionState } from "../shared/session-state.js";
import { confirmLogout, showNotice } from "../shared/logout.js";

const ITEM_KEYS = new Set(["id", "name", "media_type", "size", "sha256", "created_at", "expires_at", "last_downloaded_at"]);
const SUPPORTED_MEDIA_TYPES = new Set(["application/pdf", "image/png", "image/jpeg", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]);
const FILE_LIST_REQUEST_TIMEOUT_MS = 35_000;
const PORTAL_SESSION_INVALID_CODES = new Set(["account_logged_out", "identity_session_expired", "portal_session_invalid", "session_expired", "unauthorized", "auth_required", "token_expired", "token_invalid"]);

export function isPortalSessionInvalidError(error) {
  return Number(error?.status) === 401 || PORTAL_SESSION_INVALID_CODES.has(String(error?.code || "").trim().toLowerCase());
}

export function isFilesExitDisabled({ exiting = false } = {}) {
  return Boolean(exiting);
}

export function createTimedRequestSignal(parentSignal, timeoutMs) {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  parentSignal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    dispose: () => {
      clearTimeout(timer);
      parentSignal?.removeEventListener("abort", abort);
    },
  };
}

export function mapPRPFileError(error) {
  const code = String(error?.code || "").toLowerCase();
  const messages = {
    prp_unavailable: "文件服务暂时不可用，请稍后重试",
    prp_list_timeout: "文件列表加载超时，请检查网络后重试",
    prp_list_failed: "文件列表暂时无法获取，请稍后重试",
    prp_response_too_large: "文件列表响应异常，请稍后重试",
    prp_download_failed: "文件下载失败，请重新选择文件",
    file_not_found: "文件不存在或已过期，请刷新列表后重试",
    file_too_large: "文件超过文件服务允许的下载大小，无法选择",
    edge_file_size_exceeded: "文件超过当前终端允许的大小，无法选择",
    unsupported_file_type: "文件类型不支持，请选择其他文件",
    content_length_mismatch: "文件传输不完整，请重新选择文件",
    content_hash_mismatch: "文件校验失败，请重新选择文件",
    invalid_prp_response: "文件服务返回的数据无效，请稍后重试",
  };
  return messages[code] || String(error?.message || "文件操作失败，请稍后重试");
}

export function normalizePRPFilePage(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("文件列表无效");
  const { items, page, page_size: pageSize, total } = payload;
  if (!Array.isArray(items) || !Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 50 || !Number.isInteger(total) || total < 0) throw new Error("文件分页无效");
  const normalized = items.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item) || Object.keys(item).some((key) => !ITEM_KEYS.has(key)) || typeof item.id !== "string" || !item.id || typeof item.name !== "string" || !item.name || !SUPPORTED_MEDIA_TYPES.has(item.media_type) || !Number.isInteger(item.size) || item.size < 0 || typeof item.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(item.sha256) || Number.isNaN(Date.parse(item.created_at)) || Number.isNaN(Date.parse(item.expires_at)) || (item.last_downloaded_at !== null && Number.isNaN(Date.parse(item.last_downloaded_at)))) throw new Error("文件数据无效");
    return { ...item };
  });
  return { items: normalized, page, page_size: pageSize, total };
}

function fileBadge(mediaType) {
  if (mediaType === "application/pdf") return "PDF";
  if (mediaType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document") return "DOC";
  return "图片";
}

export function formatFileSize(size) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.ceil(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(size >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
}

export function exceedsLocalFileSize(item, maxFileSizeBytes) {
  return Number.isInteger(item?.size) && Number.isInteger(maxFileSizeBytes) && maxFileSizeBytes > 0 && item.size > maxFileSizeBytes;
}

export function renderPRPFilesView() {
  return `<div class="files-terminal-shell fill-bg-gradient"><main id="filesView" class="files-view"><header class="files-header"><div class="files-header-title-row"><h1 id="filesGreeting">请选择文件</h1><button id="filesRefresh" class="files-refresh ui-pager-button" type="button">刷新</button></div><div class="files-countdown ui-main-countdown" data-countdown-phase="idle"><span class="ui-countdown-ring"></span><strong id="filesCountdown" class="ui-countdown-value">--</strong></div><p id="filesClock" class="files-clock"></p></header><section class="files-source-switch" aria-label="文件来源"><span class="files-source-label">文件来源</span><nav id="providerTabs" class="provider-tabs" aria-label="文件来源"></nav></section><section id="filesPanel" class="files-panel" aria-busy="true"><div class="files-panel-heading"><h2>文件列表</h2><p id="filesStatus" class="files-status" aria-live="polite"></p></div><div id="filesList" class="files-list" role="list"></div><div class="files-pager"><button id="filesPrev" type="button">上一页</button><span id="filesPage">1 / 1</span><button id="filesNext" type="button">下一页</button></div></section><div class="ui-action-region files-action-region files-action-region--single is-single"><button id="filesExit" class="files-exit ui-action-button ui-action-button--primary" type="button">退出登录</button></div></main></div>`;
}

export function createPRPFilesRefreshHandler(getCurrentPage, load) {
  return () => void load(getCurrentPage());
}

export function bindPRPFilesViewEvents({ appState, router, restartCycle }) {
  const sessionId = appState.session.session_id;
  const tabs = document.getElementById("providerTabs");
  const panel = document.getElementById("filesPanel");
  const list = document.getElementById("filesList");
  const status = document.getElementById("filesStatus");
  const previous = document.getElementById("filesPrev");
  const next = document.getElementById("filesNext");
  const refresh = document.getElementById("filesRefresh");
  const exit = document.getElementById("filesExit");
  const countdown = document.getElementById("filesCountdown");
  const maxFileSizeBytes = Math.max(0, Number.parseInt(appState.session.runtimeSettings?.max_file_size_bytes, 10) || 0);
  const states = new Map();
  const controllers = new Map();
  let activeProvider = null;
  let exiting = false;
  let loading = false;
  let filesFailureMode = false;
  const mainCountdown = createMainCountdown({
    render: (value, phase) => {
      countdown.textContent = String(value);
      document.querySelector(".files-countdown").dataset.countdownPhase = phase;
    },
  });

  document.getElementById("filesGreeting").textContent = `${appState.session.identity?.display_name || "用户"}，请选择文件`;
  const setStatus = (message, kind = "") => {
    status.textContent = message;
    status.dataset.statusKind = kind;
  };
  const current = () => states.get(activeProvider);
  const endpoint = (provider, page) => `${api.prpProviders}/${encodeURIComponent(provider)}/files?session_id=${encodeURIComponent(sessionId)}&page=${page}&page_size=6`;

  function syncCountdown() {
    const state = current();
    loading = Boolean(state?.loading || state?.selecting);
    if (exiting || !state) return;
    if (loading) mainCountdown.pause();
    else mainCountdown.resume();
  }

  function renderTabs() {
    tabs.replaceChildren(...Array.from(states.values()).map((state) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "provider-tab";
      button.textContent = state.display_name;
      button.dataset.active = String(state.id === activeProvider);
      button.onclick = () => {
        activeProvider = state.id;
        syncCountdown();
        renderTabs();
        renderCurrent();
      };
      return button;
    }));
  }

  function renderCurrent() {
    const state = current();
    if (!state) return;
    const busy = Boolean(state.loading || state.selecting);
    panel.setAttribute("aria-busy", String(busy));
    list.replaceChildren();
    if (state.error) setStatus(state.error, "error");
    else if (state.selecting) setStatus("正在下载并校验文件，请稍候…", "loading");
    else if (state.loading) setStatus("正在加载文件列表，请稍候…", "loading");
    else setStatus(state.items?.length ? "" : "暂无文件", state.items?.length ? "" : "empty");
    const pages = Math.max(1, Math.ceil((state.total || 0) / (state.page_size || 6)));
    document.getElementById("filesPage").textContent = `${state.page || 1} / ${pages}`;
    previous.disabled = busy || Boolean(state.error) || (state.page || 1) <= 1;
    next.disabled = busy || Boolean(state.error) || (state.page || 1) >= pages;
    refresh.disabled = busy;
    if (!state.items) return;
    for (const item of state.items) {
      const blocked = exceedsLocalFileSize(item, maxFileSizeBytes);
      const row = document.createElement("button");
      const badge = document.createElement("span");
      const summary = document.createElement("span");
      const name = document.createElement("strong");
      const detail = document.createElement("span");
      const arrow = document.createElement("span");
      row.type = "button";
      row.className = "files-item";
      row.classList.toggle("files-item--blocked", blocked);
      row.setAttribute("role", "listitem");
      row.setAttribute("aria-label", `选择文件 ${item.name}`);
      badge.className = "files-item-badge";
      badge.textContent = fileBadge(item.media_type);
      summary.className = "files-item-summary";
      name.textContent = item.name;
      detail.className = "files-item-detail";
      detail.textContent = blocked ? `${fileBadge(item.media_type)} · ${formatFileSize(item.size)} · 超出本机上限` : `${fileBadge(item.media_type)} · ${formatFileSize(item.size)}`;
      arrow.className = "files-item-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = "›";
      summary.append(name, detail);
      row.append(badge, summary, arrow);
      row.onclick = () => void select(state.id, item);
      list.append(row);
    }
  }

  async function exitToQrCode() {
    if (exiting) return;
    exiting = true;
    mainCountdown.stop();
    exit.disabled = isFilesExitDisabled({ exiting });
    controllers.forEach((controller) => controller.abort());
    await restartCycle();
  }

  async function load(providerID, page = 1) {
    const state = states.get(providerID);
    if (!state) return;
    controllers.get(providerID)?.abort();
    const controller = new AbortController();
    controllers.set(providerID, controller);
    const timed = createTimedRequestSignal(controller.signal, FILE_LIST_REQUEST_TIMEOUT_MS);
    state.loading = true;
    state.error = "";
    if (providerID === activeProvider) {
      syncCountdown();
      renderCurrent();
    }
    try {
      const data = normalizePRPFilePage(await getJson(endpoint(providerID, page), { signal: timed.signal }));
      if (controllers.get(providerID) !== controller) return;
      Object.assign(state, data, { loading: false, error: "" });
    } catch (error) {
      if (controllers.get(providerID) !== controller || error?.name === "AbortError") return;
      state.loading = false;
      if (isPortalSessionInvalidError(error)) {
        await exitToQrCode();
        return;
      }
      const reason = timed.didTimeout() ? mapPRPFileError({ code: "prp_list_timeout" }) : mapPRPFileError(error);
      state.error = `文件列表获取失败：${reason}`;
    } finally {
      timed.dispose();
      if (providerID === activeProvider && !exiting) {
        syncCountdown();
        renderCurrent();
      }
    }
  }

  async function select(providerID, item) {
    const state = states.get(providerID);
    if (!state || state.loading || state.selecting) return;
    if (exceedsLocalFileSize(item, maxFileSizeBytes)) {
      await showNotice("文件超过大小上限", `${item.name} 为 ${formatFileSize(item.size)}，超过当前终端允许的 ${formatFileSize(maxFileSizeBytes)} 上限。`);
      return;
    }
    state.selecting = true;
    syncCountdown();
    renderCurrent();
    try {
      const result = await postJson(`${api.prpProviders}/${encodeURIComponent(providerID)}/files/${encodeURIComponent(item.id)}/select`, { session_id: sessionId });
      const file = result.file;
      appState.session.file = {
        file_id: file.file_id,
        provider_id: providerID,
        file_name: file.file_name,
        file_type: file.file_type,
        content_hash: file.content_hash,
        source_origin: "prp",
        file_url: null,
        page_count: 1,
        page_index: 0,
        print_options: {},
      };
      appState.sessionPhase = "preview_ready";
      saveSessionState();
      await router.go("preview");
    } catch (error) {
      state.error = isPortalSessionInvalidError(error) ? "登录已失效" : mapPRPFileError(error);
      if (isPortalSessionInvalidError(error)) await exitToQrCode();
    } finally {
      state.selecting = false;
      if (!exiting) {
        syncCountdown();
        renderCurrent();
      }
    }
  }

  previous.onclick = () => void load(activeProvider, Math.max(1, (current()?.page || 1) - 1));
  next.onclick = () => void load(activeProvider, (current()?.page || 1) + 1);
  refresh.onclick = () => void load(activeProvider, current()?.page || 1);
  exit.onclick = async () => {
    if (await confirmLogout()) await exitToQrCode();
  };

  (async () => {
    try {
      const data = await getJson(`${api.prpProviders}?session_id=${encodeURIComponent(sessionId)}`);
      for (const provider of data.items || []) {
        states.set(provider.provider_id, {
          id: provider.provider_id,
          display_name: provider.display_name,
          page: 1,
          page_size: 6,
          total: 0,
          items: null,
          loading: false,
          selecting: false,
          error: "",
        });
      }
      activeProvider = states.keys().next().value || null;
      renderTabs();
      renderCurrent();
      mainCountdown.start(60, exitToQrCode);
      for (const providerID of states.keys()) void load(providerID, 1);
    } catch (_) {
      await exitToQrCode();
    }
  })();

  return {
    destroy() {
      controllers.forEach((controller) => controller.abort());
      mainCountdown.destroy();
    },
  };
}
