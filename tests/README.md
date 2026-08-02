# Edge 测试组织与规则

测试按**分层目录**组织，目录即运行层级。默认门禁（CI/日常）只跑 `unit/` 与 `contract/`。

```
tests/
├── unit/        单元测试：单模块行为，mock 一切外部边界
├── contract/    云边协议契约：Cloud↔Edge 消息的解析/生成
├── e2e/         真实环境脚本：性能、端到端、IPP 模拟器（手动运行，不进门禁）
└── js/          前端 JS 测试
```

## 各层定义（新建测试时按此归类）

| 层 | 放进什么 | 排除什么 | 运行方式 |
|----|---------|---------|---------|
| `unit/` | 单模块/单文件行为测试；允许进程内依赖：`tempfile`、进程内 SQLite、本地回环 socket、mock 的 soffice/HTTP/设备 | 一切真实外部进程或服务 | `pytest`（默认） |
| `contract/` | 云边协议消息的**解析与生成**测试：`job_update`、`print_job`、`preview_file`、心跳、领取、`url_scheme` 映射等；消息样本放 `contract/messages/*.json` | 与协议无关的业务行为 | `pytest`（默认） |
| `e2e/` | 需要真实 Cloud / 真实 IPP 设备 / 真实 LibreOffice 的端到端与性能脚本、IPP 模拟器工具 | — | 手动：`pytest tests/e2e` 或直接运行脚本 |
| `integration/`（未来） | 需要真实外部组件（LibreOffice 二进制、IPP 设备、真实 Cloud/PG）的测试 | — | `pytest -m integration`，需 `@pytest.mark.integration` |

## 硬规则

1. **一个文件一个维度**：一个测试文件只测一个模块/一个协议消息类型的公共行为；不测私有实现、不 assert 内部函数调用顺序或字符串细节。发现需要测内部细节时，先考虑这是不是"实现细节测试"——是则删，不是则通过公共接口测。
2. **协议两端成对**：改 Cloud–Edge 协议时，Cloud 侧 provider 测试与本仓 consumer 测试**必须同时更新**，且优先复用 `contract/messages/*.json` 样本，不各自硬编码新字段。
3. **进程内优先**：默认用 mock / tempfile / 进程内资源；只有验证"与真实组件协同"这一目的本身时才写 `integration`/`e2e`。
4. **命名**：`test_<模块或协议>_<行为>.py`；类名 `<模块>Tests`；用例名 `test_<行为描述>`（Given-When-Then 式描述，不写实现细节）。
5. **e2e/ 不入默认收集**：`pytest.ini` 已配置 `testpaths = tests/unit tests/contract` 与 `norecursedirs = e2e`；新增真实环境脚本一律放 `e2e/`，不带 `test_` 前缀（脚本）或由 pytest.ini 排除。
6. 保持进程内测试**快速**（单文件应 < 1s 级）；慢的用例归入 integration 并打 marker。

## 常用命令

```powershell
.\.venv-build-3.12.10\Scripts\python.exe -m pytest            # 默认：unit + contract
.\.venv-build-3.12.10\Scripts\python.exe -m pytest tests/e2e  # 手动：真实环境脚本
.\.venv-build-3.12.10\Scripts\python.exe -m pytest tests/unit -k 关键字
```
