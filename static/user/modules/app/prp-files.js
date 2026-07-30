import { api, getJson, postJson } from "../shared/api.js";
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
  return `<section class="files-view"><h1 id="filesGreeting">打印文件</h1>
    <p id="filesStatus" class="files-status">正在读取文件…</p>
    <div id="filesList" class="files-list"></div>
    <div class="files-pager"><button id="filesPrev">上一页</button><span id="filesPage"></span><button id="filesNext">下一页</button></div>
  </section>`;
}

export function bindPRPFilesViewEvents({ appState, router }) {
  let currentPage = 1;
  let pageCount = 1;
  const status = document.getElementById("filesStatus");
  const list = document.getElementById("filesList");
  const greeting = document.getElementById("filesGreeting");
  greeting.textContent = `${appState.session.identity?.display_name || "用户"}，请选择打印文件`;

  async function load(page) {
    status.textContent = "正在读取文件…";
    list.replaceChildren();
    try {
      const data = normalizePRPFilePage(await getJson(
        `${api.prpFiles}?session_id=${encodeURIComponent(appState.session.session_id)}&page=${page}&page_size=20`,
      ));
      currentPage = data.page;
      pageCount = Math.max(1, Math.ceil(data.total / data.page_size));
      document.getElementById("filesPage").textContent = `${currentPage} / ${pageCount}`;
      status.textContent = data.items.length ? "" : "暂无可用文件，请先在 Site Portal 上传 PDF。";
      for (const item of data.items) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "files-item";
        const name = document.createElement("strong");
        name.textContent = item.name;
        const detail = document.createElement("span");
        detail.textContent = `${Math.ceil(item.size / 1024)} KB`;
        row.append(name, detail);
        row.onclick = () => select(item, row);
        list.append(row);
      }
      document.getElementById("filesPrev").disabled = currentPage <= 1;
      document.getElementById("filesNext").disabled = currentPage >= pageCount;
    } catch (error) {
      status.textContent = error.message || "文件读取失败，请稍后重试。";
    }
  }

  async function select(item, button) {
    button.disabled = true;
    status.textContent = "正在下载并准备文件…";
    try {
      const result = await postJson(`${api.prpFiles}/${encodeURIComponent(item.id)}/select`, {
        session_id: appState.session.session_id,
      });
      const file = result.file;
      appState.session.file = {
        file_id: file.file_id, file_name: file.file_name, file_type: file.file_type,
        content_hash: file.content_hash, source_origin: "prp", file_url: null,
        page_count: 1, page_index: 0, print_options: {},
      };
      appState.sessionPhase = "preview_ready";
      saveSessionState();
      await router.go("preview");
    } catch (error) {
      status.textContent = error.message || "文件选择失败。";
      button.disabled = false;
    }
  }

  document.getElementById("filesPrev").onclick = () => load(currentPage - 1);
  document.getElementById("filesNext").onclick = () => load(currentPage + 1);
  void load(1);
  return { destroy() {} };
}
