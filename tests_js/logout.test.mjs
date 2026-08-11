import assert from "node:assert/strict";
import test from "node:test";

import { LOGOUT_CONFIRMATION_TEXT, confirmLogout } from "../static/user/modules/shared/logout.js";

test("logout uses an explicit application confirmation dialog", async () => {
  const dialogs = [];

  assert.equal(await confirmLogout((options) => {
    dialogs.push(options);
    return false;
  }), false);
  assert.deepEqual(dialogs, [{ title: "退出登录", message: LOGOUT_CONFIRMATION_TEXT, confirmText: "确认退出" }]);
  assert.equal(await confirmLogout(() => true), true);
});
