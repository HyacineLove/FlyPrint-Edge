export const LOGOUT_CONFIRMATION_TEXT = "是否退出当前账号？";

let activeDialog = null;

function showDialog({ title, message, confirmText, cancelText = "取消" }) {
  if (activeDialog) return activeDialog;
  activeDialog = new Promise((resolve) => {
    const backdrop = document.createElement("div");
    const dialog = document.createElement("section");
    const heading = document.createElement("h2");
    const body = document.createElement("p");
    const actions = document.createElement("div");
    const cancel = document.createElement("button");
    const confirm = document.createElement("button");
    const finish = (result) => {
      document.removeEventListener("keydown", onKeydown);
      backdrop.remove();
      activeDialog = null;
      resolve(result);
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") finish(false);
    };

    backdrop.className = "edge-dialog-backdrop";
    dialog.className = "edge-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    heading.textContent = title;
    body.textContent = message;
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
    dialog.append(heading, body, actions);
    backdrop.append(dialog);
    backdrop.onclick = (event) => { if (event.target === backdrop) finish(false); };
    document.addEventListener("keydown", onKeydown);
    document.body.append(backdrop);
    confirm.focus();
  });
  return activeDialog;
}

export function confirmLogout(dialogRenderer = showDialog) {
  return dialogRenderer({ title: "退出登录", message: LOGOUT_CONFIRMATION_TEXT, confirmText: "确认退出" });
}

export function showNotice(title, message) {
  return showDialog({ title, message, confirmText: "我知道了", cancelText: "关闭" });
}
