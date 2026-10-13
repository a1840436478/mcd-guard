"""stdio 只读模式入口：给只支持 stdio 的 MCP 客户端用。

stdio 模式下护栏没有自己的终端窗口，写操作没法让用户确认，所以固定为只读模式：
写操作从工具列表里隐藏，AI 硬调也会被拦截。需要下单请用 run_guard.py（HTTP 模式）。
"""

import sys

from mcd_guard.app import build_upstream, readonly_state
from mcd_guard.audit import cleanup_old_audit
from mcd_guard.config import AUDIT_DIR, DEMO_AUDIT_DIR, MCP_TOKEN_ENV, MCP_URL, POLICY_FILE
from mcd_guard.demo_upstream import DEMO_TOOLS, demo_call
from mcd_guard.logger import log, use_stderr
from mcd_guard.mcp_client import close_session, list_tools, open_session
from mcd_guard.policy import load_policy
from mcd_guard.stdio_server import serve_stdio
from mcd_guard.utils import get_secret, mask


def main(policy_path, upstream_url, demo):
    """
    以 stdio 只读模式运行护栏，直到输入结束。

    :param policy_path: 策略文件路径
    :param upstream_url: 官方 MCP 地址
    :param demo: True 时用虚构数据的模拟服务，不连官方、不需要 Token
    :return: None
    """
    use_stderr()
    policy = load_policy(policy_path)
    if demo:
        cleanup_old_audit(DEMO_AUDIT_DIR)
        log("演示模式: 不连麦当劳官方 MCP，门店和餐品都是虚构数据", "WARNING")
        serve_stdio(readonly_state(DEMO_TOOLS, policy, demo_call, DEMO_AUDIT_DIR), sys.stdin, sys.stdout)
        return
    token = get_secret(MCP_TOKEN_ENV)
    cleanup_old_audit(AUDIT_DIR)
    log(f"连接官方 MCP: 地址={upstream_url}, Token={mask(token)}")
    session = open_session(upstream_url, token)
    try:
        tools = list_tools(session)
        serve_stdio(readonly_state(tools, policy, build_upstream(session), AUDIT_DIR), sys.stdin, sys.stdout)
    finally:
        close_session(session)


if __name__ == "__main__":
    POLICY_PATH = POLICY_FILE  # 策略文件，不存在时用默认策略；mode 固定为 readonly
    UPSTREAM_URL = MCP_URL  # 官方 MCP 地址
    DEMO = False  # True 时用虚构数据，不需要 Token
    main(POLICY_PATH, UPSTREAM_URL, DEMO)
