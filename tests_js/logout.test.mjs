import assert from "node:assert/strict";
import test from "node:test";

import { LOGOUT_CONFIRMATION_TEXT, confirmLogout } from "../static/user/modules/shared/logout.js";

test("logout requires an explicit confirmation", () => {
  const prompts = [];

  assert.equal(confirmLogout((message) => {
    prompts.push(message);
    return false;
  }), false);
  assert.deepEqual(prompts, [LOGOUT_CONFIRMATION_TEXT]);
  assert.equal(confirmLogout(() => true), true);
});
