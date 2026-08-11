import { api, getJson, postJson } from "../shared/api.js";
import { createMainCountdown } from "../shared/countdown.js";
import { saveSessionState } from "../shared/session-state.js";
import { confirmLogout } from "../shared/logout.js";

const ITEM_KEYS = new Set(["id", "name", "media_type", "size", "sha256", "created_at", "expires_at", "last_downloaded_at"]);
const SUPPORTED_MEDIA_TYPES = new Set(["application/pdf", "image/png", "image/jpeg", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]);
const FILE_LIST_REQUEST_TIMEOUT_MS = 35_000;
const PORTAL_SESSION_INVALID_CODES = new Set(["account_logged_out", "identity_session_expired", "portal_session_invalid", "session_expired", "unauthorized", "auth_required", "token_expired", "token_invalid"]);

export function isPortalSessionInvalidError(error) {
  return Number(error?.status) === 401 || PORTAL_SESSION_INVALID_CODES.has(String(error?.code || "").trim().toLowerCase());
}
export function isFilesExitDisabled({ exiting = false } = {}) { return Boolean(exiting); }
export function createTimedRequestSignal(parentSignal, timeoutMs) {
  const controller = new AbortController(); let timedOut = false;
  const abort = () => controller.abort();
  parentSignal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  return { signal: controller.signal, didTimeout: () => timedOut, dispose: () => { clearTimeout(timer); parentSignal?.removeEventListener("abort", abort); } };
}
export function mapPRPFileError(error) {
  const code = String(error?.code || "").toLowerCase();
  return ({ prp_unavailable: "文件服务暂时不可用，请稍后重试", prp_list_timeout: "文件列表加载超时，请检查网络后重试", prp_list_failed: "文件列表暂时无法获取，请稍后重试", prp_response_too_large: "文件列表响应异常，请稍后重试", prp_download_failed: "文件下载失败，请重新选择文件", file_not_found: "文件不存在或已过期，请刷新列表后重试", file_too_large: "文件超过文件服务允许的下载大小，无法选择", unsupported_file_type: "文件类型不支持，请选择其他文件", content_length_mismatch: "文件传输不完整，请重新选择文件", content_hash_mismatch: "文件校验失败，请重新选择文件", invalid_prp_response: "文件服务返回的数据无效，请稍后重试" })[code] || String(error?.message || "文件操作失败，请稍后重试");
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
export function renderPRPFilesView() {
  return `<div class="files-terminal-shell fill-bg-gradient"><main id="filesView" class="files-view"><header class="files-header"><div class="files-header-title-row"><h1 id="filesGreeting">请选择文件</h1><button id="filesRefresh" class="files-refresh ui-pager-button" type="button">刷新</button></div><div class="files-countdown ui-main-countdown" data-countdown-phase="idle"><span class="ui-countdown-ring"></span><strong id="filesCountdown" class="ui-countdown-value">--</strong></div><p id="filesClock" class="files-clock"></p></header><nav id="providerTabs" class="provider-tabs" aria-label="文件来源"></nav><section id="filesPanel" class="files-panel" aria-busy="true"><div class="files-panel-heading"><p id="filesStatus" class="files-status" aria-live="polite"></p></div><div id="filesList" class="files-list" role="list"></div><div class="files-pager"><button id="filesPrev" type="button">上一页</button><span id="filesPage">1 / 1</span><button id="filesNext" type="button">下一页</button></div></section><div class="ui-action-region files-action-region files-action-region--single is-single"><button id="filesExit" class="files-exit ui-action-button ui-action-button--primary" type="button">退出登录</button></div></main></div>`;
}
export function createPRPFilesRefreshHandler(getCurrentPage, load) { return () => void load(getCurrentPage()); }

export function bindPRPFilesViewEvents({ appState, router, restartCycle }) {
  const sessionId = appState.session.session_id;
  const tabs = document.getElementById("providerTabs"), panel = document.getElementById("filesPanel"), list = document.getElementById("filesList"), status = document.getElementById("filesStatus"), previous = document.getElementById("filesPrev"), next = document.getElementById("filesNext"), refresh = document.getElementById("filesRefresh"), exit = document.getElementById("filesExit"), countdown = document.getElementById("filesCountdown");
  const states = new Map(); const controllers = new Map(); let activeProvider = null; let exiting = false; let loading = false; let filesFailureMode = false;
  const mainCountdown = createMainCountdown({ render: (value, phase) => { countdown.textContent = String(value); document.querySelector(".files-countdown").dataset.countdownPhase = phase; } });
  const startCountdown = (seconds, action) => mainCountdown.start(seconds, action);
  function beginLoading() { loading = true; mainCountdown.stop("loading"); }
  document.getElementById("filesGreeting").textContent = `${appState.session.identity?.display_name || "用户"}，请选择文件`;
  const setStatus = (message, kind = "") => { status.textContent = message; status.dataset.statusKind = kind; };
  const current = () => states.get(activeProvider);
  const endpoint = (provider, page) => `${api.prpProviders}/${encodeURIComponent(provider)}/files?session_id=${encodeURIComponent(sessionId)}&page=${page}&page_size=6`;
  function renderTabs() { tabs.replaceChildren(...Array.from(states.values()).map((state) => { const button = document.createElement("button"); button.type = "button"; button.className = "provider-tab"; button.textContent = state.display_name; button.dataset.active = String(state.id === activeProvider); button.onclick = () => { activeProvider = state.id; renderTabs(); renderCurrent(); }; return button; })); }
  function renderCurrent() { const state = current(); if (!state) return; panel.setAttribute("aria-busy", state.loading ? "true" : "false"); list.replaceChildren(); if (state.error) setStatus(state.error, "error"); else if (state.loading) setStatus("正在加载文件列表，请稍候…", "loading"); else setStatus(state.items?.length ? "" : "暂无文件", state.items?.length ? "" : "empty"); const pages = Math.max(1, Math.ceil((state.total || 0) / (state.page_size || 6))); document.getElementById("filesPage").textContent = `${state.page || 1} / ${pages}`; previous.disabled = state.loading || Boolean(state.error) || (state.page || 1) <= 1; next.disabled = state.loading || Boolean(state.error) || (state.page || 1) >= pages; refresh.disabled = state.loading; if (!state.items) return; for (const item of state.items) { const row = document.createElement("button"); row.type = "button"; row.className = "files-item"; row.setAttribute("role", "listitem"); row.textContent = `${item.name}  ${Math.ceil(item.size / 1024)} KB`; row.onclick = () => void select(state.id, item); list.append(row); } }
  async function exitToQrCode() { if (exiting) return; exiting = true; mainCountdown.stop(); exit.disabled = isFilesExitDisabled({ exiting }); controllers.forEach((controller) => controller.abort()); await restartCycle(); }
  const endSession = exitToQrCode;
  async function load(providerID, page = 1) { const state = states.get(providerID); if (!state) return; controllers.get(providerID)?.abort(); const controller = new AbortController(); controllers.set(providerID, controller); const timed = createTimedRequestSignal(controller.signal, FILE_LIST_REQUEST_TIMEOUT_MS); state.loading = true; state.error = ""; beginLoading(); if (providerID === activeProvider) renderCurrent(); try { const data = normalizePRPFilePage(await getJson(endpoint(providerID, page), { signal: timed.signal })); if (controllers.get(providerID) !== controller) return; Object.assign(state, data, { loading: false, error: "" }); } catch (error) { if (controllers.get(providerID) !== controller || error?.name === "AbortError") return; state.loading = false; if (isPortalSessionInvalidError(error)) { await endSession(); return; } const reason = timed.didTimeout() ? mapPRPFileError({ code: "prp_list_timeout" }) : mapPRPFileError(error); state.error = `文件列表获取失败：${reason}`; if (providerID === activeProvider) startCountdown(10, () => load(providerID, page)); } finally { loading = false; timed.dispose(); if (providerID === activeProvider && !exiting) renderCurrent(); }
  }
  async function select(providerID, item) { const state = states.get(providerID); if (!state || state.loading) return; state.loading = true; renderCurrent(); try { const result = await postJson(`${api.prpProviders}/${encodeURIComponent(providerID)}/files/${encodeURIComponent(item.id)}/select`, { session_id: sessionId }); const file = result.file; appState.session.file = { file_id: file.file_id, provider_id: providerID, file_name: file.file_name, file_type: file.file_type, content_hash: file.content_hash, source_origin: "prp", file_url: null, page_count: 1, page_index: 0, print_options: {} }; appState.sessionPhase = "preview_ready"; saveSessionState(); await router.go("preview"); } catch (error) { state.error = isPortalSessionInvalidError(error) ? "登录已失效" : mapPRPFileError(error); if (isPortalSessionInvalidError(error)) await endSession(); } finally { state.loading = false; if (!exiting) renderCurrent(); } }
  previous.onclick = () => void load(activeProvider, Math.max(1, (current()?.page || 1) - 1)); next.onclick = () => void load(activeProvider, (current()?.page || 1) + 1); refresh.onclick = () => void load(activeProvider, current()?.page || 1); exit.onclick = async () => { if (confirmLogout()) await endSession(); };
  (async () => { try { const data = await getJson(`${api.prpProviders}?session_id=${encodeURIComponent(sessionId)}`); for (const provider of data.items || []) states.set(provider.provider_id, { id: provider.provider_id, display_name: provider.display_name, page: 1, page_size: 6, total: 0, items: null, loading: false, error: "" }); activeProvider = states.keys().next().value || null; renderTabs(); renderCurrent(); startCountdown(60, exitToQrCode); for (const providerID of states.keys()) void load(providerID, 1); } catch (_) { await exitToQrCode(); } })();
  return { destroy() { controllers.forEach((controller) => controller.abort()); mainCountdown.destroy(); } };
}
