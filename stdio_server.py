"""stdio 传输：从标准输入逐行读 JSON-RPC，把响应逐行写到标准输出。

stdio 模式下护栏没有自己的终端窗口，确认卡片和确认码都没处显示，所以只能以只读模式运行。
"""

import json

from logger import log
from server import rpc_error, handle_rpc


def handle_line(line, state):
    """
    处理一行输入。

    :param line: 一行 JSON 文本
    :param state: 服务状态
    :return: 要写回的响应 dict；通知或空行返回 None
    """
    if not line.strip():
        return None
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        log(f"stdio 收到无法解析的消息: 内容={line[:200]}", "WARNING")
        return rpc_error(None, -32700, "JSON 解析失败")
    if not isinstance(msg, dict):
        return rpc_error(None, -32600, "不支持批量请求")
    return handle_rpc(msg, state)


def serve_stdio(state, stdin, stdout):
    """
    处理 stdio 上的 MCP 消息，直到输入结束。

    :param state: 服务状态
    :param stdin: 输入流
    :param stdout: 输出流
    :return: None
    """
    log("stdio 服务已启动，等待 AI 客户端消息")
    for line in stdin:
        reply = handle_line(line, state)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()
    log("stdio 输入已结束，护栏退出")
