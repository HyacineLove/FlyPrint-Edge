# FlyPrint Edge

FlyPrint Edge 是部署在校园一体机上的打印客户端（Windows）。它向 Cloud 申请并展示扫码二维码；用户经 Site Portal 登录后，Edge 领取访问凭证、读取 PRP 文件列表、本地预览确认，最后通过 IPP 直接向现场打印机出纸。打印文件只在本校 PRP、Edge 与打印机之间流转，不进入 Cloud。

## 与其他组件的关系

| 组件 | 位置 | 关系 |
|------|------|------|
| FlyPrint Cloud | 同级目录 `../fly-print-cloud/`（独立 Git 仓库） | 云端控制面：认证、终端会话、用户映射、额度、任务审计；Edge 通过 REST + WebSocket 与其通信 |
| 历史归档 | 工作区外 `../FlyPrint-archive/` | 默认不读，不参与当前范围与完成判定 |

## 目录

| 目录/文件 | 说明 |
|-----------|------|
| `main.py` | FastAPI 入口：kiosk 用户页 + 本地管理页 |
| `printing/` | 核心打印栈（IPP 协议/设备/服务、文档转换）——生产打印唯一路径 |
| `cloud_*.py` | 与 Cloud 通信的适配层（WebSocket、REST、心跳、服务协调） |
| `job_delivery_store.py` | SQLite 持久化投递状态（inbox/outbox，权威状态） |
| `interactive_session.py` | 交互会话（预览/打印确认/快照恢复） |
| `portal_*.py` / `prp_*.py` / `site_portal_client.py` | Site Portal 身份领取与 PRP 文件客户端 |
| `tests/` | 分层测试：`unit/` `contract/` `e2e/`（规则见 `tests/README.md`） |
| `release/` | 安装包构建脚本（`build_installer.py`） |

## 文档导航

Agent 路由（任务 → 文档的精确映射）、硬规则与交付收口见 **`AGENTS.md`**；全局计划与跨仓库文档见工作区根 **`README.md`**。本仓库技术协议见 `docs/agent/`（`site-portal-identity-protocol.md` 的完整权威在 cloud 侧）。

## 开发与测试

```powershell
.\.venv-build-3.12.10\Scripts\python.exe -m pytest            # 默认门禁：unit + contract
.\.venv-build-3.12.10\Scripts\python.exe -m pytest tests/e2e  # 真实环境脚本（手动）
```

Edge 的详细技术约束（唯一打印链路、状态机、凭证边界、交付收口）见 `AGENTS.md` 与 `docs/agent/`。
