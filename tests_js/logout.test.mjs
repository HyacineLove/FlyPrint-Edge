import assert from "node:assert/strict";
import test from "node:test";

import {
  LOGOUT_CONFIRMATION_TEXT,
  LOGOUT_COMPLETED_TEXT,
  confirmLogout,
  dismissActiveDialog,
  showLogoutCompleted,
} from "../static/user/modules/shared/logout.js";

test("logout uses an explicit application confirmation dialog", async () => {
  const dialogs = [];

  assert.equal(await confirmLogout((options) => {
    dialogs.push(options);
    return false;
  }), false);
  assert.deepEqual(dialogs, [{ title: "退出登录", message: LOGOUT_CONFIRMATION_TEXT, confirmText: "确认退出" }]);
  assert.equal(await confirmLogout(() => true), true);
});

test("logout completion is a short non-interactive application notice", () => {
  const dialogs = [];
  showLogoutCompleted((options) => dialogs.push(options));
  assert.deepEqual(dialogs, [{
    title: "\u9000\u51fa\u767b\u5f55",
    message: LOGOUT_COMPLETED_TEXT,
    dismissAfterMs: 3000,
  }]);
  assert.equal(dismissActiveDialog(), false);
});
