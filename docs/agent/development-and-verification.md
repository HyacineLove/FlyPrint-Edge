# Edge 开发、部署与验证

## 环境要求

- 使用 Python 3.12.10 venv；协议和状态机必须具备离线单元测试。
- Windows 主机与打印机必须网络可达；网线直连时两端使用同一网段的静态 IPv4。
- 打印机须启用 IPP 或 AirPrint，并支持直接接收 PDF。Windows 不需要添加打印机、安装驱动或安装 SumatraPDF。
- DOCX 打印需要 LibreOffice；PDF 与图片不依赖 LibreOffice。Edge 维护独立 LibreOffice Profile，新 Profile 异步预热且不阻塞二维码、PDF 或图片功能，也不得修改用户日常 LibreOffice 配置。
- `runtime/` 已被 gitignore；本地 SQLite 投递库不入库。

## 首次配置打印机

1. 用网线连接主机和打印机，确认两端 IP 在同一网段。
2. 在打印机 Web 管理页启用 IPP/AirPrint。
3. 打开 Edge 管理端「打印机管理」，刷新 IPP 打印机。
4. 若未发现，输入完整 URI（例如 `ipp://192.0.2.10:631/ipp/print`，其中地址为文档示例）并检测。
5. 仅在兼容检测通过后添加打印机并设为默认。
6. 执行测试打印；只有设备返回 `completed` 才算通过。

## 地址变化与日常判断

- 自动发现再次见到相同 `printer-uuid` 且新 URI 探测通过时，Edge 才自动更新保存地址。手工换址必须先检测完整 URI 再重新添加；不得只按名称或 IP 认定同一设备。
- 缺纸、卡纸、机盖打开、离线或耗材耗尽会阻止新任务；碳粉偏低只提示，不阻止任务。
- 打印中发生明确故障时，Edge 取消设备 Job 并显示错误。「无法确认打印结果」表示设备可能已接收任务，不得立即重试；管理员确认没有遗留任务后，才可在管理端解除锁定。

## 排障顺序

1. 检查网线、电源与主机到打印机 IP 的连通性。
2. 确认 IPP/AirPrint 已启用，URI 资源路径来自设备 DNS-SD `rp` 或设备说明。
3. 在管理端重新检测 URI，查看不兼容原因。
4. 检查 `edge.log` 中的 IPP 操作、`request-id`、设备 `job-id` 与状态原因。
5. 故障恢复后确认设备不再报告 error，再恢复二维码和打印。

日志或诊断摘要不得包含 Cloud 密钥、令牌或用户文件内容。

## D12 Edge 本地限制

Edge 限制配置保存在本机 `config.json` 的 `settings` 中，由 Edge 本地校验，不下发到 Cloud，也不依赖 Cloud 才能生效：

- `copies_min` / `copies_max`：本地打印份数范围；
- `max_file_size_bytes`：下载源文件的本地体积上限，`0` 表示不启用；
- `max_document_pages`：转换后标准 PDF 的页数上限，默认 `5`，`0` 表示不启用；
- `max_list_items`：本地文件列表/第三方清单的预留上限，`0` 表示不启用。当前 Edge 没有文件列表接口，因此该字段仅保留配置框架，不虚构列表流程。

预览转换完成后，Edge 在本地检查页数；超限直接返回 `edge_limit_exceeded`，不向 Cloud 增加预览结果回传协议。Cloud 的上传大小、页数与文件类型限制由 Cloud 独立维护，不能替代或覆盖 Edge 本地限制。

## 升级、卸载与真机验收

- 从旧版本首次升级到配置版本 2 会清除旧 Windows/WSD/USB 打印机记录，之后必须重新添加 IPP 设备。
- 工具版本、设备能力或 URI 变化后，重新执行测试打印。
- 卸载前从托盘退出 Edge；安装程序会停止运行进程后再删除文件。
- 真机验收必须在网线直连 HP Color LaserJet Pro 3288dn 的目标机器完成，开发机发现结果不得替代。验收覆盖自动发现、手动添加、PDF/DOCX/图片、单双面、彩色/黑白、多份、缺纸、补纸、卡纸、离线、取消、恢复和 Cloud 状态回报。

## 构建、测试与安装包

```powershell
# 在 fly-print-edge 根目录，激活开发 venv 后运行
python -m pytest

# 安装包：先 PyInstaller，再 Inno Setup
# PyInstaller: .venv-build-3.12.10\Scripts\pyinstaller.exe
# ISCC: C:\Users\HQIT-LAPTOP\AppData\Local\Programs\Inno Setup 6\ISCC.exe
pyinstaller --noconfirm flyprint-edge.spec
& "C:\Users\HQIT-LAPTOP\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
# 输出：dist\flyprint-edge-setup-<版本>.exe；版本见 installer.iss 的 MyAppVersion
```

本轮 Edge 有改动时，全部完成后再 bump 版本并重新构建安装包，避免中途反复打包。Cloud 改动使用 `docker compose up --build -d`，不构建 Edge 安装包。
