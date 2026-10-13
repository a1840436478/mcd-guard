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
CLIENT_NAME = "mcbench"
CLIENT_VERSION = "0.1.0"
