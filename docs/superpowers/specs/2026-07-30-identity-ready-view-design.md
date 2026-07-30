# Edge 身份就绪页修复设计

## 问题

Edge 后端已将 Site Portal 登录结果绑定为 `identity_ready`，但用户前端只处理 `terminal_occupied`、预览和打印事件。实时 `portal_session_ready` 被忽略，刷新恢复也未识别 `identity_ready`，因此页面一直显示“终端使用中”。

## 目标

- 实时收到 `portal_session_ready` 后切换到身份就绪页。
- 页面刷新后根据 `/api/session/current` 的 `identity_ready` 快照恢复同一页面。
- 只展示 Site Portal、用户显示名和登录成功状态，不展示或保存 PRP 访问凭证。
- `portal_session_error` 明确提示重新扫码。
- 身份就绪页只说明文件能力将在下一切片接入，不提前实现文件列表。

## 结构

- 新增纯状态模块，将实时消息或快照归一化为公共身份字段并写入前端会话状态。
- 新增薄身份就绪 View，显示用户身份、阶段说明和“结束并刷新二维码”按钮。
- `app-controller.js` 负责 SSE 分支、快照恢复和路由，不在 View 中实现协议逻辑。
- 清理会话时同步删除公共身份。

## 测试

- Node 单元测试直接执行纯状态模块，验证实时消息进入 `identity_ready`、只保留公共字段，以及错误/空数据不建立身份。
- Edge 全量 Python 测试保证现有二维码、预览和打印链路不回归。
- 浏览器人工验证实时登录后切页，刷新仍恢复身份就绪页，结束会话后生成新二维码。
