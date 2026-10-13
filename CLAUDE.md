# mcbench 项目说明

麦当劳点餐大模型评测：用麦当劳中国 MCP 的真实菜单和官方核价出题，评测各家大模型的点餐能力，产出公开排行榜。参赛项目：麦当劳程序员创意开发大赛（报名截止 2026-10-25 23:59，排名只看 GitHub Star）。

## 环境

- conda 环境：`mcbench`（Python 3.12），解释器 `/home/claude/miniconda3/envs/mcbench/bin/python`
- 只用标准库，零第三方依赖；确需依赖时先和用户确认，并写进 `requirements.txt`
- 密钥放项目根目录 `.env`（参考 `.env.example`），代码通过 `utils.get_secret()` 读取，不写进任何会提交的文件

## 运行

- 单元测试：`python -m unittest discover -s tests`（不需要 Token）
- 探测 MCP 并保存工具 schema：运行 `probe_mcp.py`

## 模块

| 文件 | 用途 |
|---|---|
| `config.py` | 共用固定配置 |
| `logger.py` | `log()`，控制台 + `logs/日期.log`，保留 14 天 |
| `utils.py` | `.env` 读取、密钥打码 |
| `mcp_client.py` | MCP Streamable HTTP 客户端（会话用 dict 表示） |
| `probe_mcp.py` | 连通性探测，输出 `data/tools.json` |

## 安全约束

- 评测和开发过程中绝不真实调用 `create-order`、`mall-create-order`、`auto-bind-coupons` 等会改动账户的工具；评测里这类调用一律拦截并记录。
- 参赛仓库必须包含 README.md、CONTEST_DECLARATION.md（官方原文，不能改）、MCP_INTEGRATION.md、mcp-config.example.json（只用环境变量占位符）。
