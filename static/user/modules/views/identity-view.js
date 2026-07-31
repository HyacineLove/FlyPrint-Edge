import { on, setText } from "../shared/dom.js";

export function renderIdentityView() {
  return `
<main class="identity-ready-shell" aria-labelledby="identity-ready-title">
  <section class="identity-ready-card">
    <div class="identity-ready-mark" aria-hidden="true">✓</div>
    <p class="identity-ready-eyebrow">Site Portal 登录成功</p>
    <h1 id="identity-ready-title">欢迎，<span id="identity-display-name"></span></h1>
    <p class="identity-ready-message">身份已经安全送达本终端。</p>
    <dl class="identity-ready-details">
      <div>
        <dt>当前入口</dt>
        <dd id="identity-site-portal"></dd>
      </div>
    </dl>
    <p class="identity-ready-next">文件选择能力将在下一切片接入，本阶段不展示文件列表。</p>
    <button id="identity-restart" type="button">结束并刷新二维码</button>
  </section>
</main>
`;
}

export function bindIdentityViewEvents({ appState, restartCycle }) {
  const identity = appState.session.identity || {};
  setText(["identity-display-name"], identity.display_name || "用户");
  setText(["identity-site-portal"], identity.site_portal_code || "Site Portal");
  on("identity-restart", () => {
    void restartCycle();
  });
}
