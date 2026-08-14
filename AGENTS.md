# FlyPrint Edge — Agent

Python Windows 一体机客户端（FastAPI + IPP）。独立 git 仓库。

## 本仓规则

- 测试：`.venv-build-3.12.10\Scripts\python.exe -m pytest`（默认 unit+contract）；`pytest tests/e2e` 手动。
- 生产打印仅 IPP；禁止 Windows Spooler/WSD/RAW 等回退链路。
- 协议：跨仓索引见根 `../docs/protocol.md`；改协议同步 Cloud WebSocket test + 本仓 consumer test。打印主链文件只打 Site Portal（`claim_base_url`），不得直连 PRP，不得持有 SSO token。
- 交付收口：Edge 改动完成后再 bump 版本打安装包（`release/build_installer.py`）；Cloud 改动用 `docker compose up --build -d`。
- 完成态判定见根 `../AGENTS.md`。
