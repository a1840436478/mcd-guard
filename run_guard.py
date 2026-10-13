"""启动麦麦护栏：连接官方 MCP，在本机开一个 MCP 服务给 AI 客户端用。"""

import threading
from datetime import date

from audit import cleanup_old_audit, read_audit, spent_fen, write_audit
from config import AUDIT_DIR, DEMO_AUDIT_DIR, GUARD_HOST, GUARD_PORT, MCP_TOKEN_ENV, MCP_URL, POLICY_FILE
from confirm import confirm, start_reader
from demo_upstream import DEMO_TOOLS, demo_call
from guard import auto_allowed_writes
from logger import log
from mcp_client import call_tool_raw, close_session, list_tools, open_session
from policy import load_policy
from server import create_server
from utils import get_secret, mask


def build_upstream(session):
    """
    生成串行调用上游的函数（同一时间只发一个请求，符合个人正常使用的频率）。

    :param session: 上游会话 dict
    :return: fn(name, arguments) -> 上游原始 result
    """
    lock = threading.Lock()

    def upstream(name, arguments):
        with lock:
            return call_tool_raw(session, name, arguments)

    return upstream


def calc_props_of(tools):
    """
    取出 calculate-price 支持的参数名。

    :param tools: 上游工具列表
    :return: set[str]
    """
    for tool in tools:
        if tool["name"] == "calculate-price":
            return set(tool.get("inputSchema", {}).get("properties", {}))
    raise RuntimeError(f"上游工具列表里没有 calculate-price，无法核实订单金额: 工具数={len(tools)}")


def build_state(tools, policy, upstream, audit_dir):
    """
    组装本地服务需要的状态。

    :param tools: 上游工具列表
    :param policy: 策略 dict
    :param upstream: 上游调用函数 fn(name, arguments)
    :param audit_dir: 审计日志目录
    :return: state dict
    """
    return {
        "tools": tools,
        "policy": policy,
        "ctx": {
            "policy": policy,
            "upstream": upstream,
            "confirm": confirm,
            "spent": lambda: spent_fen(audit_dir),
            "audit": lambda record: write_audit(record, audit_dir),
            "calc_props": calc_props_of(tools),
        },
        "recent": lambda: read_audit(date.today(), audit_dir)[-50:],
    }


def serve(host, port, state):
    """
    启动本地服务，直到 Ctrl+C。

    :param host: 本地监听地址
    :param port: 本地端口
    :param state: build_state 的结果
    :return: None
    """
    policy = state["policy"]
    allowed = auto_allowed_writes(policy)
    if allowed and policy["mode"] == "confirm":
        log(f"注意：以下写操作按你的 tool_rules 不需要确认就会执行（下单仍受消费上限约束）: {', '.join(allowed)}", "WARNING")
    start_reader()
    server = create_server(host, port, state)
    try:
        log(f"麦麦护栏已启动: 地址=http://{host}:{port}/mcp, 模式={policy['mode']}, "
            f"单笔上限={policy['max_order_yuan']}元, 当天上限={policy['max_daily_yuan']}元")
        log("在 AI 客户端里把麦当劳 MCP 的地址换成上面的地址，不需要再填 Token。写操作会在这个窗口里请你确认。")
        log(f"网页面板: http://{host}:{port}/ （确认时需要输入只显示在这个窗口里的确认码）")
        server.serve_forever()
    except KeyboardInterrupt:
        log("收到 Ctrl+C，护栏退出")
    finally:
        server.server_close()


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
