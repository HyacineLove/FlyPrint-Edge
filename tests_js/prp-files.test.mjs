import assert from "node:assert/strict";
import test from "node:test";

import * as prpFiles from "../static/user/modules/app/prp-files.js";

test("PRP file list renders a refresh action", () => {
  const html = prpFiles.renderPRPFilesView();

  assert.match(html, /id="providerTabs"/);
  assert.match(html, /<button id="filesRefresh"[^>]*type="button"[^>]*>刷新<\/button>/);
  assert.match(html, /<button id="filesExit"[^>]*type="button"[^>]*>退出登录<\/button>/);
});

test("refresh action reloads the currently displayed page", () => {
  assert.equal(typeof prpFiles.createPRPFilesRefreshHandler, "function");

  const loadedPages = [];
  const refresh = prpFiles.createPRPFilesRefreshHandler(
    () => 3,
    (page) => loadedPages.push(page),
  );

  refresh();

  assert.deepEqual(loadedPages, [3]);
});

test("PRP file page accepts PDF, image and DOCX metadata", () => {
  const item = (id, name, mediaType) => ({
    id,
    name,
    media_type: mediaType,
    size: 12,
    sha256: "0".repeat(64),
    created_at: "2026-07-31T00:00:00Z",
    expires_at: "2026-08-01T00:00:00Z",
    last_downloaded_at: null,
  });
  const result = prpFiles.normalizePRPFilePage({
    items: [
      item("pdf-1", "sample.pdf", "application/pdf"),
      item("png-1", "sample.png", "image/png"),
      item("docx-1", "sample.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ],
    page: 1,
    page_size: 6,
    total: 3,
  });

  assert.equal(result.items.length, 3);
});

test("recognizes an expired portal session for a user-visible logout message", () => {
  assert.equal(prpFiles.isPortalSessionInvalidError({ status: 401 }), true);
  assert.equal(prpFiles.isPortalSessionInvalidError({ code: "portal_session_invalid" }), true);
  assert.equal(prpFiles.isPortalSessionInvalidError({ status: 502 }), false);
});

test("exit remains available while a file-list request is loading", () => {
  assert.equal(prpFiles.isFilesExitDisabled({ loading: true, exiting: false }), false);
  assert.equal(prpFiles.isFilesExitDisabled({ loading: false, exiting: true }), true);
});

test("file-list timeout aborts the browser request and is distinguishable from user cancellation", async () => {
  const timed = prpFiles.createTimedRequestSignal(null, 5);

  await new Promise((resolve) => setTimeout(resolve, 20));

  assert.equal(timed.signal.aborted, true);
  assert.equal(timed.didTimeout(), true);
  timed.dispose();
});

test("maps stable PRP error codes to user actions instead of HTTP status text", () => {
  assert.equal(prpFiles.mapPRPFileError({ code: "prp_unavailable" }), "文件服务暂时不可用，请稍后重试");
  assert.equal(prpFiles.mapPRPFileError({ code: "prp_list_timeout" }), "文件列表加载超时，请检查网络后重试");
  assert.equal(prpFiles.mapPRPFileError({ code: "prp_response_too_large" }), "文件列表响应异常，请稍后重试");
  assert.equal(prpFiles.mapPRPFileError({ code: "file_too_large" }), "文件超过文件服务允许的下载大小，无法选择");
  assert.equal(prpFiles.mapPRPFileError({ code: "content_hash_mismatch" }), "文件校验失败，请重新选择文件");
});
