# mcd-guard 项目说明

麦麦护栏：跑在用户本机的麦当劳 MCP 安全层，夹在 AI 客户端和 `https://mcp.mcd.cn` 之间。写操作必须用户在 AI 碰不到的地方亲自确认，支持消费上限、只读模式、工具白名单、审计日志，Token 只存本机。

参赛项目：麦当劳程序员创意开发大赛。报名截止 2026-10-25 23:59，最晚 10/15 报名；排名只看 2026-10-26 00:00 的 GitHub Star。

## 环境

- conda 环境：`mcd-guard`（Python 3.12），解释器 `/home/claude/miniconda3/envs/mcd-guard/bin/python`
- 只用标准库，零第三方依赖；确需依赖时先和用户确认，并写进 `requirements.txt`
- 密钥放项目根目录 `.env`（参考 `.env.example`），代码通过 `utils.get_secret()` 读取，不写进任何会提交的文件

## 运行

- 单元测试：`python -m unittest discover -s tests`（不需要 Token，用本地模拟的 MCP 服务）

## 模块

| 文件 | 用途 |
|---|---|
| `config.py` | 共用固定配置 |
| `logger.py` | `log()`，控制台 + `logs/日期.log`，保留 14 天 |
| `utils.py` | `.env` 读取、密钥打码 |
| `mcp_client.py` | 上游 MCP Streamable HTTP 客户端（会话用 dict 表示） |
| `probe_mcp.py` | 手动连通性检查，输出 `data/tools.json` |

## 合规约束（来自麦当劳 MCP 服务规则）

- 服务只允许个人正常使用，禁止脚本、爬虫、批量、高频、自动化调用；不得公开发布 MCP 返回的底层数据。
- 开发和测试一律用本地模拟服务；不要用脚本批量调用真实 MCP。真实服务只做少量手动检查。
- 开发过程中绝不真实调用会改动账户的工具：`create-order`、`cancel-order`、`party-order-create`、`draw-lottery`、`mall-create-order`、`auto-bind-coupons`、`delivery-create-address`。
- 参赛仓库必须包含 README.md、CONTEST_DECLARATION.md（官方原文，不能改）、MCP_INTEGRATION.md、mcp-config.example.json（只用环境变量占位符）。
