# Edge 开发、构建与验证

## 原则

- 协议/状态机须有离线单元测试。
- 真机验收：网线直连目标机上的 HP Color LaserJet Pro 3288dn；开发机发现结果不能替代。
- Python 3.12.10 venv。
- **交付收口：** 本轮 Edge 有改动时，全部改完后再 bump 并打安装包（勿中途反复打包）。Cloud 改动用 compose update，不打 Edge 包。

## 常用命令

```powershell
# 测试（在 fly-print-edge 根目录，激活开发 venv 后）
python -m pytest

# 安装包：先 PyInstaller，再 Inno Setup
# PyInstaller: .venv-build-3.12.10\Scripts\pyinstaller.exe
# ISCC: C:\Users\HQIT-LAPTOP\AppData\Local\Programs\Inno Setup 6\ISCC.exe
pyinstaller --noconfirm flyprint-edge.spec
& "C:\Users\HQIT-LAPTOP\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
# 输出: dist\flyprint-edge-setup-<版本>.exe ；版本见 installer.iss → MyAppVersion
```

- `runtime/` 已 gitignore（本地 SQLite 投递库不入库）。

## D12 Edge 本地限制

Edge 的限制配置保存在本机 `config.json` 的 `settings`，不下发到 Cloud，也不依赖 Cloud 才能校验：

- `copies_min` / `copies_max`：本地打印份数范围；
- `max_file_size_bytes`：下载源文件的本地体积上限，`0` 表示不启用；
- `max_document_pages`：转换后的标准 PDF 页数上限，默认 `5`，`0` 表示不启用；
- `max_list_items`：本地文件列表/三方清单预留上限，`0` 表示不启用。当前 Edge 没有文件列表接口，因此只提供配置框架，不虚构列表流程。

预览转换完成后，Edge 在本地检查页数；超限直接返回 `edge_limit_exceeded`，不向 Cloud 增加预览结果回传协议。Cloud 的上传大小、页数和文件类型限制仍由 Cloud 独立维护。

## Cloud 传输地址

- `cloud.base_url` 支持 **http** 与 **https**（受信证书；勿用 `https://localhost` 再改写局域网 IP）。
- WebSocket 由 `url_scheme.http_url_to_websocket_url` 映射为 **ws** / **wss**；REST 与文件下载跟随同一 `base_url`。
