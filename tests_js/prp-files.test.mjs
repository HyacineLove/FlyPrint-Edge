import assert from "node:assert/strict";
import test from "node:test";

import * as prpFiles from "../static/user/modules/app/prp-files.js";

test("PRP file list renders a refresh action", () => {
  const html = prpFiles.renderPRPFilesView();

  assert.match(html, /<button id="filesRefresh"[^>]*type="button"[^>]*>刷新<\/button>/);
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
