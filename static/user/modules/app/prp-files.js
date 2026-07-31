import { api, getJson, postJson } from "../shared/api.js";
import { createRequestGate } from "../shared/request-gate.js";
import { saveSessionState } from "../shared/session-state.js";

const ITEM_KEYS = new Set([
  "id", "name", "media_type", "size", "sha256",
  "created_at", "expires_at", "last_downloaded_at",
]);

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
        item.media_type !== "application/pdf" ||
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
<div class="files-terminal-shell">
  <main id="filesView" class="files-terminal-card" aria-labelledby="filesGreeting">
    <header class="files-header">
      <div>
        <p class="files-eyebrow">Site Portal 登录成功</p>
        <h1 id="filesGreeting">请选择打印文件</h1>
        <p class="files-helper">文件将由当前 PRP 安全传输至本终端预览</p>
      </div>
      <div class="files-countdown" aria-label="会话剩余时间">
        <strong id="filesCountdown">60</strong>
        <span>秒后退出</span>
      </div>
    </header>

    <section id="filesPanel" class="files-panel" aria-busy="true">
      <div class="files-panel-heading">
        <div>
          <h2>PDF 文件</h2>
          <p id="filesStatus" class="files-status" aria-live="polite">正在读取文件…</p>
        </div>
        <div class="files-panel-actions">
          <span id="filesTotal" class="files-total">0 个文件</span>
          <button id="filesRefresh" class="files-refresh" type="button">刷新</button>
        </div>
      </div>
      <div id="filesList" class="files-list" role="list"></div>
      <div class="files-pager" aria-label="文件列表分页">
        <button id="filesPrev" type="button">上一页</button>
        <span id="filesPage">1 / 1</span>
        <button id="filesNext" type="button">下一页</button>
      </div>
    </section>

    <button id="filesExit" class="files-exit" type="button">返回二维码</button>
    <p class="files-security-note">退出或倒计时结束后，本次登录与文件访问凭证将失效</p>
  </main>
</div>`;
}

export function createPRPFilesRefreshHandler(getCurrentPage, load) {
  return () => void load(getCurrentPage());
}

export function bindPRPFilesViewEvents({ appState, router, restartCycle }) {
  let currentPage = 1;
  let pageCount = 1;
  let countdownValue = 60;
  let countdownTimer = null;
  let exiting = false;
  const sessionId = appState.session.session_id;
  const requestGate = createRequestGate();
  const view = document.getElementById("filesView");
  const panel = document.getElementById("filesPanel");
  const status = document.getElementById("filesStatus");
  const list = document.getElementById("filesList");
  const greeting = document.getElementById("filesGreeting");
  const previous = document.getElementById("filesPrev");
  const next = document.getElementById("filesNext");
  const refresh = document.getElementById("filesRefresh");
  const countdown = document.getElementById("filesCountdown");
  greeting.textContent = `${appState.session.identity?.display_name || "用户"}，请选择打印文件`;

  function resetCountdown() {
    countdownValue = 60;
    countdown.textContent = String(countdownValue);
  }

  function stopCountdown() {
    if (!countdownTimer) return;
    window.clearInterval(countdownTimer);
    countdownTimer = null;
  }

  function setBusy(busy) {
    panel.setAttribute("aria-busy", busy ? "true" : "false");
    previous.disabled = busy || currentPage <= 1;
    next.disabled = busy || currentPage >= pageCount;
    refresh.disabled = busy;
    list.querySelectorAll(".files-item").forEach((item) => {
      item.disabled = busy;
    });
  }

  function sessionIsCurrent(request) {
    return requestGate.isCurrent(request) && appState.session.session_id === sessionId;
  }

  async function exitToQrCode() {
    if (exiting) return;
    exiting = true;
    stopCountdown();
    requestGate.cancel();
    setBusy(true);
    await restartCycle();
  }

  async function load(page) {
    const request = requestGate.start();
    if (!request) return;
    resetCountdown();
    setBusy(true);
    status.textContent = "正在读取文件…";
    list.replaceChildren();
    try {
      const data = normalizePRPFilePage(await getJson(
        `${api.prpFiles}?session_id=${encodeURIComponent(sessionId)}&page=${page}&page_size=6`,
        { signal: request.signal },
      ));
      if (!sessionIsCurrent(request)) return;
      currentPage = data.page;
      pageCount = Math.max(1, Math.ceil(data.total / data.page_size));
      document.getElementById("filesPage").textContent = `${currentPage} / ${pageCount}`;
      document.getElementById("filesTotal").textContent = `${data.total} 个文件`;
      status.textContent = data.items.length ? "" : "暂无可用文件，请先在 Site Portal 上传 PDF。";
      for (const item of data.items) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "files-item";
        row.setAttribute("role", "listitem");
        const badge = document.createElement("span");
        badge.className = "files-item-badge";
        badge.textContent = "PDF";
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
      if (sessionIsCurrent(request) && error?.name !== "AbortError") {
        status.textContent = error.message || "文件读取失败，请稍后重试。";
      }
    } finally {
      if (requestGate.finish(request)) setBusy(false);
    }
  }

  async function select(item, button) {
    const request = requestGate.start();
    if (!request) return;
    resetCountdown();
    setBusy(true);
    status.textContent = "正在下载并准备文件…";
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
      requestGate.finish(request);
      await router.go("preview");
    } catch (error) {
      if (sessionIsCurrent(request) && error?.name !== "AbortError") {
        status.textContent = error.message || "文件选择失败。";
      }
    } finally {
      if (requestGate.finish(request)) setBusy(false);
    }
  }

  const onViewInteraction = () => resetCountdown();
  view.addEventListener("pointerdown", onViewInteraction);
  previous.onclick = () => void load(currentPage - 1);
  next.onclick = () => void load(currentPage + 1);
  refresh.onclick = createPRPFilesRefreshHandler(() => currentPage, load);
  document.getElementById("filesExit").onclick = () => void exitToQrCode();
  countdownTimer = window.setInterval(() => {
    countdownValue = Math.max(0, countdownValue - 1);
    countdown.textContent = String(countdownValue);
    if (countdownValue === 0) void exitToQrCode();
  }, 1000);
  void load(1);
  return {
    destroy() {
      stopCountdown();
      requestGate.cancel();
      view.removeEventListener("pointerdown", onViewInteraction);
    },
  };
}
