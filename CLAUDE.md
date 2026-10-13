# mcd-guard 项目说明

麦麦护栏：跑在用户本机的麦当劳 MCP 安全层，夹在 AI 客户端和 `https://mcp.mcd.cn` 之间。写操作必须用户在 AI 碰不到的地方亲自确认，支持消费上限、只读模式、工具白名单、审计日志，Token 只存本机。

参赛项目：麦当劳程序员创意开发大赛。报名截止 2026-10-25 23:59，最晚 10/15 报名；排名只看 2026-10-26 00:00 的 GitHub Star。

## 环境

- conda 环境：`mcd-guard`（Python 3.12），解释器 `/home/claude/miniconda3/envs/mcd-guard/bin/python`
- 只用标准库，零第三方依赖；确需依赖时先和用户确认，并写进 `requirements.txt`
- 密钥放项目根目录 `.env`（参考 `.env.example`），代码通过 `utils.get_secret()` 读取，不写进任何会提交的文件

## 运行

- 单元测试：`python -m unittest discover -s tests`（不需要 Token，用假依赖和本地服务；临时文件放在项目下 `test_tmp_*`，跑完自动删除）
- 启动护栏：运行 `run_guard.py`，默认监听 `http://127.0.0.1:1024/mcp`，写操作在这个终端里确认

## 模块

| 文件 | 用途 |
|---|---|
| `config.py` | 共用固定配置：端口、只读工具名单、写操作中文名、默认策略 |
| `logger.py` | `log()`，控制台 + `logs/日期.log`，保留 14 天 |
| `utils.py` | `.env` 读取、密钥打码 |
| `mcp_client.py` | 上游 MCP Streamable HTTP 客户端（会话用 dict 表示） |
| `policy.py` | 读取 `policy.json`（不提交）并与默认策略合并、校验 |
| `audit.py` | 审计日志 `audit/日期.jsonl`（保留 90 天），统计当天/本周已确认消费 |
| `guard.py` | 核心判断：放行 / 拦截 / 本机确认；下单前用 calculate-price 核价并检查限额 |
| `console_confirm.py` | 在护栏终端显示确认卡片并读取用户输入 |
| `server.py` | 本地 MCP 服务（只返回 JSON），改写工具列表、校验 Origin |
| `run_guard.py` | 启动入口 |
| `probe_mcp.py` | 手动连通性检查，输出 `data/tools.json` |

只提交和参赛作品相关的文件。开发辅助文件（`probe_mcp.py`、`tools/`、`data/`）只留本地，已写进 `.gitignore`。

## 用户授权（2026-10-13）

- 可以用用户的 GitHub 账号新建本比赛的公开仓库 `mcd-guard`，并随时 push。仅限这一个仓库，其他仓库不行。
- 可以在 `M-China/mcd-developer-innovation-challenge` 提报名 Issue；提交前把标题和正文按官方格式核对一遍。
- 提交署名：本仓库 git 配置为 `MrMa <1840436478@qq.com>`（只设在本仓库）。
- 可以把护栏作为 MCP 服务加到本项目范围的 Claude Code 配置里，用于实测和录演示。
- GitHub CLI 装在 conda 环境里：`/home/claude/miniconda3/envs/mcd-guard/bin/gh`。

## 合规约束（来自麦当劳 MCP 服务规则）

- 服务只允许个人正常使用，禁止脚本、爬虫、批量、高频、自动化调用；不得公开发布 MCP 返回的底层数据。
- 开发和测试一律用本地模拟服务；不要用脚本批量调用真实 MCP。真实服务只做少量手动检查。
- 开发过程中绝不真实调用会改动账户的工具：`create-order`、`cancel-order`、`party-order-create`、`draw-lottery`、`mall-create-order`、`auto-bind-coupons`、`delivery-create-address`。
- 参赛仓库必须包含 README.md、CONTEST_DECLARATION.md（官方原文，不能改）、MCP_INTEGRATION.md、mcp-config.example.json（只用环境变量占位符）。
