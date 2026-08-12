import assert from "node:assert/strict";
import test from "node:test";

import {
  MANUAL_QR_REFRESH_CONFIRMATION_TEXT,
  confirmManualQrRefresh,
} from "../static/user/modules/shared/logout.js";
import { shouldConfirmManualQrRefresh } from "../static/user/modules/views/login-view.js";

test("manual QR refresh asks for confirmation only while a scanned login is pending", () => {
  assert.equal(shouldConfirmManualQrRefresh({ terminalOccupied: false, loginQrRefreshing: false }), false);
  assert.equal(shouldConfirmManualQrRefresh({ terminalOccupied: true, loginQrRefreshing: false }), true);
  assert.equal(shouldConfirmManualQrRefresh({ terminalOccupied: true, loginQrRefreshing: true }), false);
});

test("manual QR refresh uses the Edge confirmation dialog", async () => {
  const dialogs = [];
  assert.equal(await confirmManualQrRefresh((options) => {
    dialogs.push(options);
    return true;
  }), true);
  assert.deepEqual(dialogs, [{
    title: "刷新二维码",
    message: MANUAL_QR_REFRESH_CONFIRMATION_TEXT,
    confirmText: "确认刷新",
  }]);
});
