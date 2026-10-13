"""启动麦麦护栏：连接官方 MCP，在本机开一个 MCP 服务给 AI 客户端用。"""

from mcd_guard.app import build_state, build_upstream, serve
from mcd_guard.audit import cleanup_old_audit
from mcd_guard.config import AUDIT_DIR, DEMO_AUDIT_DIR, GUARD_HOST, GUARD_PORT, MCP_TOKEN_ENV, MCP_URL, POLICY_FILE
from mcd_guard.demo_upstream import DEMO_TOOLS, demo_call
from mcd_guard.logger import log
from mcd_guard.mcp_client import close_session, list_tools, open_session
from mcd_guard.policy import load_policy
from mcd_guard.utils import get_secret, mask


def main(host, port, policy_path, upstream_url, demo):
    """
    启动护栏，直到 Ctrl+C。

    :param host: 本地监听地址
    :param port: 本地端口
    :param policy_path: 策略文件路径
    :param upstream_url: 官方 MCP 地址
    :param demo: True 时用虚构数据的模拟服务，不连官方、不需要 Token
    :return: None
    """
    policy = load_policy(policy_path)
    if demo:
        cleanup_old_audit(DEMO_AUDIT_DIR)
        log(f"演示模式: 不连麦当劳官方 MCP，门店和餐品都是虚构数据，审计日志写到 {DEMO_AUDIT_DIR}", "WARNING")
        serve(host, port, build_state(DEMO_TOOLS, policy, demo_call, DEMO_AUDIT_DIR))
        return
    token = get_secret(MCP_TOKEN_ENV)
    cleanup_old_audit(AUDIT_DIR)
    log(f"连接官方 MCP: 地址={upstream_url}, Token={mask(token)}")
    session = open_session(upstream_url, token)
    try:
        tools = list_tools(session)
        serve(host, port, build_state(tools, policy, build_upstream(session), AUDIT_DIR))
    finally:
        close_session(session)


if __name__ == "__main__":
    HOST = GUARD_HOST  # 本地监听地址，默认只监听本机
    PORT = GUARD_PORT  # 本地端口
    POLICY_PATH = POLICY_FILE  # 策略文件，不存在时用默认策略
    UPSTREAM_URL = MCP_URL  # 官方 MCP 地址
    DEMO = False  # 演示模式开关；想先体验可以直接运行 run_demo.py
    main(HOST, PORT, POLICY_PATH, UPSTREAM_URL, DEMO)
