# Edge 架构与协议

## 生产打印链路（唯一）

`PDF / DOCX / 图片 → 标准 PDF → IPP Print-Job → 设备 Job ID → IPP 终态`

所有生产打印先生成标准 PDF，再直接通过 IPP 提交给设备。预览与打印共享同一排版模型；打印参数仅生成任务专用 PDF。不得使用 Windows Spooler、WSD、RAW、WMI、SumatraPDF、系统默认应用或其他回退链路。

| 模块 | 职责 |
|------|------|
| `printing/domain.py` | 请求、参数、状态、错误和用户提示 |
| `printing/documents.py` | LibreOffice 转换、PDF/图片排版、标准 PDF 与缓存 |
| `printing/ipp_protocol.py` | IPP/2.0 编解码、传输与响应校验 |
| `printing/ipp_device.py` | 设备能力、参数校验和故障归一化 |
| `printing/discovery.py` | `_ipp._tcp.local.` 发现、完整 URI 与 UUID 去重 |
| `printing/service.py` | 每台设备串行、提交、监控、取消和清理 |

HTTP、管理端、用户端与 Cloud 代码均为适配层，不实现打印协议或终态判定。

## PDF、缓存与清理所有权

- `documents.py` 以 `content_hash + 文件类别 + 转换版本` 标识标准 PDF；PDF、Office 和图片均须先完成此归一化。
- 标准 PDF 使用 30 分钟滑动 TTL、活跃租约与 5 分钟清理周期；预览或打印再次使用同一内容时，不重新下载或转换。
- 打印专用 PDF 在任务终止后立即删除；原始下载文件只在标准 PDF 验证成功后删除。
- Office 转换使用 Edge 专属固定 LibreOffice Profile，并由进程内唯一互斥锁串行执行。全新 Profile 在 Edge 启动后异步预热内置小型 DOCX；预热成功标记绑定 LibreOffice 可执行文件指纹。不得启动常驻进程或引入其他转换路径。

## IPP 约束与设备并发

- 打印目标必须是包含主机、端口和资源路径的完整 `ipp://` URI；任务寻址只用 Cloud `printer_id`，显示名不作为目标。
- Print-Job 始终提交 `application/pdf`，带明确 `Content-Length` 与 `ipp-attribute-fidelity=true`；PDF 固定块读取发送，不复制整份文件到第二个内存缓冲区。
- 响应必须校验 HTTP、IPP 状态、`request-id`、长度与属性类型。份数、单双面、色彩和 PWG media 在提交前依据能力校验；不支持时明确失败。
- 同一 `printer-uuid` 在进程内互斥：正式、Cloud 与测试任务共用同一串行锁。设备警告或 report 仅记录；只有当前 Job 明确故障或设备 `*-error` 才归因并取消。
- 相同 `printer-uuid` 的新 URI 探测通过后才更新保存地址。`printer_schema_version=2` 首次迁移清除旧 Windows/WSD/USB 记录；Edge 本地稳定 `id` 与 `cloud_id` 分开保存，Cloud 回包不得覆盖本地 ID。

## 状态机与终端结果协议

```text
PREPARING → SUBMITTING → QUEUED → PRINTING → COMPLETED
                           │          │
                           └──────────┴→ FAILED / CANCELED / UNCONFIRMED
```

- `pending`、`pending-held` 映射为 `QUEUED`，`processing` 映射为 `PRINTING`，`aborted` 映射为 `FAILED`，`canceled` 映射为 `CANCELED`。
- 只有设备 IPP `job-state=completed` 才能映射为 `COMPLETED`。Job 已完成时完成态优先；其后出现的缺纸只阻止下一任务。
- 提交响应丢失、作业查询失败，或 Cancel-Job 结果无法确认时，必须保持 `UNCONFIRMED`；不得自动重打。15 分钟超时后请求 Cancel-Job，取消不明同样保留该锁。
- 权威投递状态为 `job_delivery_store.py` 的 `runtime/edge_job_delivery.sqlite3`（inbox + outbox），内存 map 仅作缓存。IPP 终态与稳定 UUID `event_id` 同事务写入；`completed`、`failed`、`canceled`、`unconfirmed` 在收到 `job_update_ack/accepted` 前持续排队。
- 重连或未 ACK 使用最大 60 秒的指数退避且不过期；`rejected` 停止重试，记录本地通信故障，绝不记为打印成功。Edge 重启恢复 `received`；打印中断上报 `unconfirmed` 与 `edge_restart_result_unknown`，绝不重打旧作业。
- 本地事件可保留 `job-impressions-completed` 页数进度；Cloud 状态消息不发送或持久化逐页进度。用户刷新从交互会话快照恢复阶段和页数；`UNCONFIRMED` 在管理员解除设备锁前不得返回二维码页。
- Site Portal 直打的明确终态会上报最终 `job-impressions-completed`，再按单面/双面和份数边界换算实体纸张及额度；`UNCONFIRMED` 不携带用量字段。终态报告仍先进入同一 SQLite outbox，Cloud ACK 前不得丢弃。

## 二维码、会话与安全边界

- `cloud.base_url` 支持受信证书的 HTTP/HTTPS；WebSocket 由 `url_scheme.py` 映射为 WS/WSS，REST 与文件下载跟随同一 base URL。若二维码配置含 `localhost` 或 `127.0.0.1`，仅改写为本机局域网 IP；禁止 `https://localhost` 后改写，也不得另设第二套二维码接口。
- 用户扫码进门签发 `terminal_ticket` 后，Cloud 下行 `terminal_occupied`（含 `msg_id`，Edge ACK）。登录页遮挡二维码，刷新仍可用；占用态暂停 60 秒后自动换码。不轮询 HTTP。断线时 Cloud 记为 pending，Edge 重连上报 `terminal_session_state` 后补发。
- 刷新二维码或新会话上报会作废 Cloud 未完成 ticket；手机旧票进入或上传必须返回明确错误。`preview_file` 必须携带 `terminal_session_id` 与 `terminal_ticket_hash`，第三方另带 `integration_request_id`，且须与当前会话一致才绑定；无 ticket hash 时可由 `terminal_occupied` 或首次有效预览绑定。
- 每台 Edge 由 Cloud 配置一个默认 Site Portal；用户扫码后由 Cloud 自动跳转。浏览器左划返回时仍可回到公网 H5 重新选择其他已配置入口。
- Site Portal 登录成功后，Cloud 只下发 `portal_session_ready`（领取地址、一次性领取码、终端会话和 Cloud 用户）。Edge 必须先匹配当前 `terminal_session_id` 与票据哈希，再向 Site Portal 原子领取身份和 PRP 访问凭证；凭证仅保存在 `PortalSessionManager` 进程内存中，不进入交互会话快照、SSE 或日志。领取失败明确报错，不自动重试或切换链路。
- 预览页「返回」直接回登录扫码页；打印中禁止中断回扫码。HMAC 第三方任务确认后仍经 `submit_print_params` 回传完整上下文。Site Portal/PRP 文件确认后由 Edge 携同终端会话、Site Portal、打印参数和稳定 `confirmation_id` 向 Cloud 原子授权，得到唯一 Cloud `job_id` 后才允许本地 IPP 提交。
- Cloud 下发 `preview_file` 后，Edge 本地下载、转换标准 PDF 并向用户页返回结果。预览失败仅在本地展示稳定错误，不新增 `preview_result` 或其他未经确认的 Cloud 回调。
- PRP 文件在预览阶段已生成标准 PDF；打印阶段必须按 `content_hash` 命中该缓存，缓存缺失即明确失败，不重新向 PRP 下载，也不把文件体送入 Cloud。
- 一体机为工控 PC 加直连打印机，kiosk 锁定用户页；本地管理默认仅回环监听，物理门锁不替代 Cloud 的终端身份密码学校验。非回环、代理暴露或远程维护须先确认并补充鉴权。`tests/ipp_completed_simulator.py` 仅用于测试，不进入生产路径。
## PRP PDF 检查点

当前 Site Portal 身份和 PRP 文件边界见 `site-portal-identity-protocol.md` 与 `prp-file-protocol.md`。PRP 文件字节只在 PRP、Edge 本地临时/标准文件和后续打印机之间流转；Cloud 与 Site Portal 后端不接收文件体。
