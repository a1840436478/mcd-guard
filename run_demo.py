"""演示模式入口：不需要麦当劳 Token，用虚构门店和餐品体验护栏的确认、限额和网页面板。"""

from config import GUARD_HOST, GUARD_PORT, POLICY_FILE, MCP_URL
from run_guard import main

if __name__ == "__main__":
    HOST = GUARD_HOST  # 本地监听地址，默认只监听本机
    PORT = GUARD_PORT  # 本地端口，和正式模式相同，AI 客户端配置不用改
    POLICY_PATH = POLICY_FILE  # 策略文件，不存在时用默认策略
    UPSTREAM_URL = MCP_URL  # 演示模式不会连接，仅占位
    DEMO = True  # 演示模式：不连官方 MCP，不需要 Token
    main(HOST, PORT, POLICY_PATH, UPSTREAM_URL, DEMO)
