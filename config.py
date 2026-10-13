"""项目共用的固定配置。"""

from pathlib import Path

# 目录
PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"  # 本地密钥文件，不提交
DATA_DIR = PROJECT_DIR / "data"  # 可提交的公开数据（工具 schema、录制的菜单快照等）
LOG_DIR = PROJECT_DIR / "logs"  # 按日期命名的日志
LOG_KEEP_DAYS = 14  # 日志保留天数，超过的自动删除

# 麦当劳 MCP
MCP_URL = "https://mcp.mcd.cn"
MCP_TOKEN_ENV = "MCD_MCP_TOKEN"  # Token 所在的环境变量名（或 .env 中的键名）
MCP_PROTOCOL_VERSION = "2025-06-18"  # 官方支持的最高协议版本
MCP_TIMEOUT = 30  # 单次请求超时，秒
MCP_RETRY_TIMES = 3  # 遇到 429 限流时的最多重试次数
MCP_RETRY_WAIT = 5  # 429 重试前等待的秒数（逐次翻倍）

# 客户端标识
CLIENT_NAME = "mcd-guard"
CLIENT_VERSION = "0.1.0"

# 护栏本地服务
GUARD_HOST = "127.0.0.1"  # 只监听本机，不对局域网开放
GUARD_PORT = 1024  # 本地端口，致敬 1024 程序员节
POLICY_FILE = PROJECT_DIR / "policy.json"  # 用户自己的策略文件（不提交），不存在时用默认策略
AUDIT_DIR = PROJECT_DIR / "audit"  # 审计日志，每天一个 jsonl 文件
AUDIT_KEEP_DAYS = 90  # 审计日志保留天数，超过的自动删除
DEMO_AUDIT_DIR = PROJECT_DIR / "audit-demo"  # 演示模式的审计日志，和真实账户的分开，同样保留 90 天

# 只读工具：直接放行。不在这个名单里的工具（包括官方以后新增的）一律按写操作处理
READ_ONLY_TOOLS = frozenset({
    "available-coupons", "calculate-price", "campaign-calendar", "delivery-query-addresses",
    "delivery-query-stores", "list-nutrition-foods", "mall-order-detail", "mall-order-list",
    "mall-points-products", "mall-product-detail", "now-time-info", "order-list",
    "query-lottery-info", "query-meal-assistance", "query-meal-detail", "query-meals",
    "query-my-account", "query-my-coupons", "query-my-prizes", "query-nearby-stores",
    "query-order", "query-party-city", "query-party-store", "query-party-store-date",
    "query-party-store-session", "query-promotions", "query-store-coupons", "query-survey-coupon",
})

# 写操作的中文名，用于确认卡片和审计日志
WRITE_TOOL_NAMES = {
    "create-order": "创建订单",
    "cancel-order": "取消订单",
    "party-order-create": "预约派对/活动",
    "mall-create-order": "积分兑换",
    "draw-lottery": "积分抽奖",
    "auto-bind-coupons": "一键领券",
    "delivery-create-address": "新增配送地址",
}

TOOL_RULES = ("allow", "confirm", "block")  # tool_rules 可选的规则
NO_AUTO_ALLOW_TOOLS = frozenset({"party-order-create"})  # 可能花钱但没法试算金额的工具，不允许设为 allow

# 默认策略，policy.json 中的同名字段会覆盖这里
DEFAULT_POLICY = {
    "mode": "confirm",  # confirm：写操作需本机确认；readonly：隐藏并拦截全部写操作
    "max_order_yuan": 100,  # 单笔订单应付上限（元），超过直接拦截
    "max_daily_yuan": 200,  # 当天已确认订单累计上限（元）
    "max_weekly_yuan": 600,  # 本周（周一起）已确认订单累计上限（元）
    "blocked_tools": [],  # 永远拦截的工具名，如 ["draw-lottery"]
    "tool_rules": {},  # 逐个工具设置：allow 直接放行 / confirm 需确认 / block 拦截；没写的写操作按 confirm
    "confirm_timeout_sec": 120,  # 等待用户确认的秒数，超时视为拒绝
}
