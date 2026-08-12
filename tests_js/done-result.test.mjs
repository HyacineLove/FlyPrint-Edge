import assert from "node:assert/strict";
import test from "node:test";

import { isFaultLockedDoneResult } from "../static/user/modules/shared/done-result.js";

test("printer fault and unconfirmed results require a user-session exit", () => {
  assert.equal(isFaultLockedDoneResult({ type: "error", error_code: "printer_out_of_paper" }), true);
  assert.equal(isFaultLockedDoneResult({ type: "error", error_code: "result_unconfirmed" }), true);
  assert.equal(isFaultLockedDoneResult({ type: "error", error_code: "print_canceled" }), false);
  assert.equal(isFaultLockedDoneResult({ type: "success" }), false);
});
