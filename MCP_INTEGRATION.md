# 麦当劳 MCP 接入说明

## 使用的 MCP Server

| 项目 | 内容 |
| --- | --- |
| 服务地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP，协议版本 `2025-06-18` |
| 鉴权 | `Authorization: Bearer ${MCD_MCP_TOKEN}`，Token 只由护栏从本机 `.env` 或环境变量读取 |
| 上游客户端 | [`mcp_client.py`](mcp_client.py)，只用 Python 标准库：`initialize` → `notifications/initialized` → `tools/list` / `tools/call`，兼容 JSON 与 SSE 响应 |

麦麦护栏同时是一个 MCP Server（给 AI 客户端连）和一个 MCP Client（连麦当劳官方）：

```text
AI 客户端（WorkBuddy / Claude Code …）
        │  http://127.0.0.1:1024/mcp（无 Token）
        ▼
麦麦护栏（本机）── 策略判断 ── 护栏终端：确认卡片，等你输入 y
        │  https://mcp.mcd.cn（Bearer Token）
        ▼
麦当劳中国官方 MCP
```

## 使用的 Tool

护栏转发官方全部 35 个工具（启动时从 `tools/list` 实时获取），按用途分三类处理：

| 类别 | 工具 | 护栏怎么处理 |
| --- | --- | --- |
| 只读查询（28 个） | `query-nearby-stores`、`query-meals`、`query-meal-detail`、`calculate-price`、`query-store-coupons`、`query-my-coupons`、`query-my-account`、`order-list`、`query-order`、`campaign-calendar`、`list-nutrition-foods`、`now-time-info` 等 | 直接放行，记审计日志 |
| 写操作（7 个） | `create-order`、`cancel-order`、`party-order-create`、`mall-create-order`、`draw-lottery`、`auto-bind-coupons`、`delivery-create-address` | 只读模式下隐藏并拦截；确认模式下在护栏终端弹出确认卡片，用户输入 `y` 才转发 |
| 护栏自用 | `calculate-price` | AI 调 `create-order` 时，护栏先用同样的门店和餐品参数调一次官方试算，取 `data.price`（单位分）作为应付金额，用于确认卡片和消费上限检查 |

只读名单见 [`config.py`](config.py) 的 `READ_ONLY_TOOLS`。**不在名单里的工具（包括官方以后新增的）一律按写操作处理。**

## 调用流程

一次 `tools/call` 在护栏里的处理顺序（[`guard.py`](guard.py) 的 `handle_call`）：

1. 工具在 `blocked_tools` 里：拦截。
2. 只读工具：转发给官方，原样返回结果。
3. 写操作 + 只读模式：拦截。
4. `create-order`：先调 `calculate-price` 试算。试算失败就拦截；应付金额超过单笔、当天或本周上限也拦截，不弹确认。
5. 在护栏终端显示确认卡片，等用户作答，默认 120 秒超时。用户可以在终端输入，也可以打开网页面板 `http://127.0.0.1:1024/`，输入只显示在护栏终端里的 6 位确认码：
   - 确认：转发给官方，原样返回结果。
   - 拒绝、确认码连续输错 5 次或超时：不转发，告诉 AI 用户已拒绝，不要重试。
6. 用户确认后转发出错：告诉 AI 结果未知，先用 `order-list` / `query-order` 查询，不要直接重试。

每一步都写进 `audit/日期.jsonl`。拒绝和拦截时返回给 AI 的都是 `isError: true` 的文本，并明确要求它不要重试、不要拆单绕过。

给 AI 的工具列表也会被改写：写操作的说明前加上“需要用户在麦麦护栏终端确认”，并补上 MCP 的 `readOnlyHint` / `destructiveHint` 注解，让 AI 一开始就知道哪些操作需要确认。

## 业务价值

麦当劳 MCP 服务规则写明：“持有该凭证即代表拥有您账号的操作权限……凡是通过该凭证发起的任何指令，均视为您本人行为。”护栏让用户能放心把 MCP 交给 AI：

- **查询照常**：菜单、门店、价格、优惠券、订单查询都不受影响。
- **下单有刹车**：AI 理解错、被群聊或网页里的文字带偏，都绕不过本机确认。
- **花钱有上限**：单笔、当天、本周三档上限，按官方试算金额判断。
- **事后可追溯**：AI 用账号做过什么，审计日志里一条不少。
- **Token 不外露**：AI 客户端配置里不再出现 Token。

## 验证记录（2026-10-13）

以下都是用真实 Token 连接官方服务完成的，全程没有向官方发出任何写操作。

| 验证项 | 结果 |
| --- | --- |
| `initialize` / `tools/list` | 成功，协议 `2025-06-18`，返回 35 个工具；服务端不返回会话 ID |
| `now-time-info` | 成功，返回北京时间 |
| 经护栏 `query-nearby-stores` | 成功，上海人民广场附近返回多家门店，选用麦当劳上海黄浦华旭国际大厦餐厅（`1450713`） |
| 经护栏 `query-meals` | 成功，返回分类菜单，麦辣鸡腿汉堡单品编码 `1440` |
| 下单前核价 | 护栏调 `calculate-price`，1 个麦辣鸡腿汉堡应付 2250 分；确认卡片显示餐品名和 ¥22.50 |
| 确认环节拒绝 | 输入 `n` 后返回“用户拒绝”，护栏日志中没有任何转发 `create-order` 的记录 |
| 真实 AI 客户端 | Claude Code 2.1.296 经护栏完成查店 → 菜单 → 试算 → 下单请求；被拒绝后没有重试，并询问用户下一步 |
| 超限拦截 | Claude Code 为 12 人下单，官方试算应付 ¥270.00，超过单笔上限 ¥100，护栏直接拦截，不弹确认 |
| 演示模式 | `run_demo.py` 不连官方服务；Claude Code 经护栏查虚构门店和菜单 → 试算 → 下单请求，护栏终端确认后才返回演示订单 |

单元测试（`python -m unittest discover -s tests`）覆盖：握手与 SSE 解析、放行与拦截、确认 / 拒绝 / 超时、单笔与累计上限、试算失败、转发出错、个人信息打码、只读模式下工具列表改写、Host / Origin 校验、网页面板确认码、演示模式。测试使用本地模拟服务，不调用真实 MCP。

## 模块

| 文件 | 用途 |
| --- | --- |
| `run_guard.py` | 启动入口 |
| `run_demo.py` / `demo_upstream.py` | 演示模式入口与虚构数据的模拟服务，不需要 Token |
| `server.py` | 本地 MCP 服务（Streamable HTTP，只返回 JSON）与网页面板，改写工具列表、校验 Host 和 Origin |
| `guard.py` | 核心判断：放行 / 拦截 / 本机确认，下单前核价并检查上限 |
| `confirm.py` | 写操作确认：护栏终端输入 y/n，或网页面板输入只显示在终端的确认码 |
| `panel.py` | 本地网页面板 |
| `policy.py` | 读取并校验 `policy.json` |
| `audit.py` | 审计日志与累计消费统计 |
| `mcp_client.py` | 连接官方 MCP 的客户端 |
| `config.py` / `logger.py` / `utils.py` | 配置、日志、通用工具 |
