export const LOGOUT_CONFIRMATION_TEXT = "是否退出当前账号？";
export const LOGOUT_COMPLETED_TEXT = "已退出当前账号";
export const MANUAL_QR_REFRESH_CONFIRMATION_TEXT = "当前登录正在确认中，刷新将取消本次登录。是否继续？";

let activeDialog = null;

function showDialog({ title, message, confirmText, cancelText = "取消", dismissAfterMs = 0 }) {
  if (activeDialog) return activeDialog.promise;
  const entry = { promise: null, finish: null, finished: false };
  entry.promise = new Promise((resolve) => {
    const backdrop = document.createElement("div");
    const dialog = document.createElement("section");
    const heading = document.createElement("h2");
    const body = document.createElement("p");
    const actions = document.createElement("div");
    let timer = null;
    const finish = (result) => {
      if (entry.finished) return;
      entry.finished = true;
      if (timer) window.clearTimeout(timer);
      document.removeEventListener("keydown", onKeydown);
      backdrop.remove();
      if (activeDialog === entry) activeDialog = null;
      resolve(result);
    };
    entry.finish = finish;
    const onKeydown = (event) => {
      if (event.key === "Escape") finish(false);
    };

    backdrop.className = "edge-dialog-backdrop";
    dialog.className = "edge-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    heading.textContent = title;
    body.textContent = message;
    dialog.append(heading, body);
    if (confirmText) {
      const cancel = document.createElement("button");
      const confirm = document.createElement("button");
      actions.className = "edge-dialog-actions";
      cancel.className = "edge-dialog-button edge-dialog-button--secondary";
      cancel.type = "button";
      cancel.textContent = cancelText;
      cancel.onclick = () => finish(false);
      confirm.className = "edge-dialog-button edge-dialog-button--primary";
      confirm.type = "button";
      confirm.textContent = confirmText;
      confirm.onclick = () => finish(true);
      actions.append(cancel, confirm);
      dialog.append(actions);
    } else {
      dialog.classList.add("edge-dialog--notice");
    }
    backdrop.append(dialog);
    backdrop.onclick = (event) => { if (event.target === backdrop) finish(false); };
    document.addEventListener("keydown", onKeydown);
    document.body.append(backdrop);
    if (confirmText) dialog.querySelector(".edge-dialog-button--primary")?.focus();
    if (Number.isFinite(dismissAfterMs) && dismissAfterMs > 0) {
      timer = window.setTimeout(() => finish(false), dismissAfterMs);
    }
  });
  activeDialog = entry;
  return entry.promise;
}

export function dismissActiveDialog(result = false) {
  if (!activeDialog) return false;
  activeDialog.finish(result);
  return true;
}

export function confirmLogout(dialogRenderer = showDialog) {
  return dialogRenderer({ title: "退出登录", message: LOGOUT_CONFIRMATION_TEXT, confirmText: "确认退出" });
}

export function confirmManualQrRefresh(dialogRenderer = showDialog) {
  return dialogRenderer({
    title: "刷新二维码",
    message: MANUAL_QR_REFRESH_CONFIRMATION_TEXT,
    confirmText: "确认刷新",
  });
}

export function showNotice(title, message) {
  return showDialog({ title, message, confirmText: "我知道了", cancelText: "关闭" });
}

export function showLogoutCompleted(dialogRenderer = showDialog) {
  return dialogRenderer({ title: "退出登录", message: LOGOUT_COMPLETED_TEXT, dismissAfterMs: 3000 });
}
