import test from "node:test";
import assert from "node:assert/strict";

import { isPortalSessionInvalidError, normalizePRPFilePage } from "../../static/user/modules/app/prp-files.js";

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

test("recognizes an expired portal session so the kiosk can explain the logout", () => {
  assert.equal(isPortalSessionInvalidError({ status: 401 }), true);
  assert.equal(isPortalSessionInvalidError({ code: "portal_session_invalid" }), true);
  assert.equal(isPortalSessionInvalidError({ code: "network_error", status: 502 }), false);
});
