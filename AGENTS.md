# FlyPrint Edge — Agent

按需加载（勿整仓通读）：

| 任务 | 文档 |
|------|------|
| **全局计划 / 当前任务（先读）** | `../docs/plans/2026-07-31-统一打印链路重构.md`（本阶段唯一主文档） |
| 架构 / 数据流图源 | `../docs/diagrams/`（.drawio + .png 成对） |
| IPP 架构、协议、打印链路与安全边界 | `docs/agent/architecture-and-protocols.md` |
| IPP 环境、部署、排障、构建与验收 | `docs/agent/development-and-verification.md` |
| PRP 文件协议 | `docs/agent/prp-file-protocol.md` |
| Site Portal 身份协议 | `docs/agent/site-portal-identity-protocol.md` |
| 测试组织规则（新建测试先读） | `tests/README.md` |
| 历史归档 | `../../FlyPrint-archive/README.md`（工作区外，默认不读，不参与完成判定） |

工作区外 `../../FlyPrint-archive/` **默认不读、不参与范围与完成判定**；仅在当前任务明确需要历史资料时再按需查阅。旧私有域口径见 `../../FlyPrint-archive/workspace/superseded-private-domain-2026-07-30/`。

## 硬规则

- 改前先确认数据流、状态流转与 IO 边界；按完整调用链定位后再改。
- 禁止未确认的兜底、替代打印链路或协议分支；生产打印仅使用 IPP。
- 可先写小 demo 验证；合入后不得保留重复协议实现。
- 保持模块职责清晰，避免继续堆 `main.py`、Cloud 适配层或单一模块。
- 保留工作区已有改动；提交前检查 `git status --short`，并同步更新受影响说明。
- **完成态**：`[x]` 仅表示已合入（及该项验收所要求的打包/预演）；「代码/单测通过」最多 `[~]`。细则见根目录 `../docs/plans/2026-07-31-统一打印链路重构.md` §7。
- **文档校验**：提交前运行 `python ../scripts/doccheck.py`（链接与文档地图路径校验），有断链/失效路径时先修复再提交。
- **交付收口**：本轮 Edge 有改动时，全部改完后 bump 版本并重新 build 安装包：`.\.venv-build-3.12.10\Scripts\python.exe release/build_installer.py --version <新版本>`，产物 `dist/flyprint-edge-setup-<版本>.exe`（不入库）。Cloud 侧改动用 `docker compose up --build -d`，不打 Edge 包。双仓同改时：Cloud 先 `compose up --build`，Edge 整轮收尾再打安装包。
