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
