# Site Portal 身份会话协议

本协议描述 PDF 检查点中 Site Portal 身份到 Edge 的边界。

- Cloud WebSocket 只通知 Edge 一次性领取所需的公开上下文，不携带 PRP Token。
- Edge 使用当前终端会话向 Site Portal 领取身份；`PortalSessionManager` 在进程内保存 `prp_base_url`、`access_token` 和过期时间。
- `InteractiveSessionManager` 只保存 Site Portal、Cloud 用户、外部用户和显示名称，不保存 Token、Cookie 或本地文件路径。
- 刷新二维码、结束会话或进程退出会清理 Portal 会话和未消费的 PRP 本地源文件。
- 同一浏览器登录同时建立独立的 Site Portal 上传会话；Edge 领取不会删除浏览器会话。

PDF 检查点中，身份就绪后 Edge 用户端进入 PRP 文件列表，不再停留在纯身份信息页。
