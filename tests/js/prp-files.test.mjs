import test from "node:test";
import assert from "node:assert/strict";

import {
  exceedsLocalFileSize,
  formatFileSize,
  isPortalSessionInvalidError,
  normalizePRPFilePage,
} from "../../static/user/modules/app/prp-files.js";

const item = {
  id: "file-1", name: "sample.pdf", media_type: "application/pdf", size: 12,
  sha256: "a".repeat(64), created_at: "2026-07-30T12:00:00Z",
  expires_at: "2026-08-06T12:00:00Z", last_downloaded_at: null,
};

test("normalizes a valid literal PRP page", () => {
  const page = normalizePRPFilePage({ items: [item], page: 1, page_size: 20, total: 1 });
  assert.equal(page.items[0].name, "sample.pdf");
});

test("rejects credentials, malformed hashes, pagination and missing ids", () => {
  for (const payload of [
    { items: [{ ...item, access_token: "secret" }], page: 1, page_size: 20, total: 1 },
    { items: [{ ...item, sha256: "bad" }], page: 1, page_size: 20, total: 1 },
    { items: [item], page: 0, page_size: 20, total: 1 },
    { items: [{ ...item, id: "" }], page: 1, page_size: 20, total: 1 },
  ]) {
    assert.throws(() => normalizePRPFilePage(payload));
  }
});

test("accepts empty sha256 and a display name without extension", () => {
  const { size, sha256, ...metadata } = item;
  const page = normalizePRPFilePage({
    items: [{ ...metadata, name: "个人简历", sha256: "" }],
    page: 1, page_size: 20, total: 1,
  });
  assert.equal(page.items[0].name, "个人简历");
});

test("accepts list items that omit or null size and sha256", () => {
  const { size, sha256, ...metadata } = item;
  for (const payloadItem of [metadata, { ...metadata, size: null, sha256: null }]) {
    const page = normalizePRPFilePage({ items: [payloadItem], page: 1, page_size: 20, total: 1 });
    assert.equal(page.items[0].id, "file-1");
  }
});

test("hides unknown list size and skips local size intercept", () => {
  assert.equal(formatFileSize(undefined), "");
  assert.equal(formatFileSize(null), "");
  assert.equal(exceedsLocalFileSize({ name: "a.pdf" }, 1024), false);
});

test("recognizes an expired portal session so the kiosk can explain the logout", () => {
  assert.equal(isPortalSessionInvalidError({ status: 401 }), true);
  assert.equal(isPortalSessionInvalidError({ code: "portal_session_invalid" }), true);
  assert.equal(isPortalSessionInvalidError({ code: "network_error", status: 502 }), false);
});
