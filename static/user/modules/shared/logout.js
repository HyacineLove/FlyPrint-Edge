export const LOGOUT_CONFIRMATION_TEXT = "是否退出当前账号？";

export function confirmLogout(confirmDialog = globalThis.confirm) {
  return confirmDialog(LOGOUT_CONFIRMATION_TEXT);
}
