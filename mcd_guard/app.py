"""护栏运行时的组装：上游调用、服务状态、HTTP 服务启动。run_guard.py / run_demo.py / run_stdio.py 共用。"""

import threading
from datetime import date

from mcd_guard.audit import read_audit, spent_fen, write_audit
from mcd_guard.confirm import confirm, start_reader
from mcd_guard.guard import auto_allowed_writes
from mcd_guard.logger import log
from mcd_guard.mcp_client import call_tool_raw
from mcd_guard.server import create_server


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


def readonly_state(tools, policy, upstream, audit_dir):
    """
    组装只读模式的服务状态，确认环节一律按拒绝处理（只读模式下本来也走不到确认）。

    :param tools: 上游工具列表
    :param policy: 用户策略 dict
    :param upstream: 上游调用函数
    :param audit_dir: 审计日志目录
    :return: state dict
    """
    if policy["mode"] != "readonly":
        log(f"stdio 模式无法确认写操作，策略模式由 {policy['mode']} 改为 readonly", "WARNING")
    state = build_state(tools, {**policy, "mode": "readonly"}, upstream, audit_dir)
    state["ctx"]["confirm"] = lambda card, timeout: "no"
    return state
