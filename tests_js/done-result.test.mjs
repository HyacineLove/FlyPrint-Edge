import assert from "node:assert/strict";
import test from "node:test";

import {
  canContinueToFilesAfterDone,
  faultAvailabilityMessage,
  isFaultLockedDoneResult,
} from "../static/user/modules/shared/done-result.js";

test("printer fault and unconfirmed results require a user-session exit", () => {
  assert.equal(isFaultLockedDoneResult({ type: "error", error_code: "printer_out_of_paper" }), true);
  assert.equal(isFaultLockedDoneResult({ type: "error", error_code: "result_unconfirmed" }), true);
  assert.equal(isFaultLockedDoneResult({ type: "error", error_code: "print_canceled" }), false);
  assert.equal(isFaultLockedDoneResult({ type: "success" }), false);
});

test("a normal PRP print failure can return to its file list, but a lock cannot", () => {
  const context = { sessionId: "session-1", sourceOrigin: "prp" };

  assert.equal(canContinueToFilesAfterDone({ ...context, result: { type: "success" } }), true);
  assert.equal(canContinueToFilesAfterDone({ ...context, result: { type: "error", error_code: "print_quota_insufficient" } }), true);
  assert.equal(canContinueToFilesAfterDone({ ...context, result: { type: "error", error_code: "printer_fault" } }), false);
  assert.equal(canContinueToFilesAfterDone({ ...context, result: { type: "error", error_code: "print_quota_insufficient" }, sourceOrigin: "cloud" }), false);
});

test("a refreshed printer fault preserves the specific availability message", () => {
  assert.equal(
    faultAvailabilityMessage({ faulted: true, message: "打印机缺纸，请联系管理员补纸" }),
    "打印机缺纸，请联系管理员补纸",
  );
  assert.equal(faultAvailabilityMessage({ faulted: true }), "打印机仍需处理，请检查后重试");
});
