"""麦当劳 MCP 的 Streamable HTTP 客户端，只用标准库。

会话用一个 dict 表示：
    {"url", "token", "session_id", "protocol_version", "next_id"}
"""

import json
import threading
import time
import urllib.error
import urllib.request

from config import (
    CLIENT_NAME,
    CLIENT_VERSION,
    MCP_PROTOCOL_VERSION,
    MCP_RETRY_TIMES,
    MCP_RETRY_WAIT,
    MCP_TIMEOUT,
)
from logger import log

_id_lock = threading.Lock()


def _build_headers(session):
    """组装请求头，带上鉴权、会话 ID 和协议版本。"""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {session['token']}",
    }
    if session.get("session_id"):
        headers["Mcp-Session-Id"] = session["session_id"]
    if session.get("protocol_version"):
        headers["MCP-Protocol-Version"] = session["protocol_version"]
    return headers


def parse_sse(text):
    """
    解析 SSE 文本，取出每个事件的 data 并按 JSON 解析。

    :param text: 响应体文本
    :return: list[dict]，每个元素是一条 JSON-RPC 消息
    """
    messages, data_lines = [], []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line == "" and data_lines:
            messages.append(json.loads("\n".join(data_lines)))
            data_lines = []
    return messages


def _post(session, payload):
    """
    发送一条 JSON-RPC 消息，处理限流重试。

    :param session: 会话 dict
    :param payload: JSON-RPC 消息
    :return: (状态码, 响应头, 响应体文本)
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    wait = MCP_RETRY_WAIT
    for attempt in range(MCP_RETRY_TIMES + 1):
        req = urllib.request.Request(session["url"], data=body, headers=_build_headers(session), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=MCP_TIMEOUT) as resp:
                return resp.status, resp.headers, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            if e.code == 429 and attempt < MCP_RETRY_TIMES:
                log(f"MCP 限流，等待重试: 方法={payload.get('method')}, 第{attempt + 1}次, 等待秒数={wait}", "WARNING")
                time.sleep(wait)
                wait *= 2
                continue
            if e.code == 401:
                raise RuntimeError(f"MCP Token 无效、过期或未提供: 状态码=401, 返回={detail}") from e
            raise RuntimeError(f"MCP 请求失败: 方法={payload.get('method')}, 状态码={e.code}, 返回={detail}") from e
    raise RuntimeError(f"MCP 限流重试次数用尽: 方法={payload.get('method')}")


def _request(session, method, params=None):
    """
    发送 JSON-RPC 请求并取回对应 id 的结果。

    :param session: 会话 dict
    :param method: 方法名，如 tools/list
    :param params: 参数 dict
    :return: JSON-RPC result 字段
    """
    with _id_lock:
        req_id = session["next_id"]
        session["next_id"] += 1
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    _, headers, text = _post(session, payload)
    if headers.get("Mcp-Session-Id"):
        session["session_id"] = headers["Mcp-Session-Id"]
    if "text/event-stream" in (headers.get("Content-Type") or ""):
        messages = parse_sse(text)
    else:
        messages = [json.loads(text)] if text.strip() else []
    for msg in messages:
        if msg.get("id") != req_id:
            continue
        if "error" in msg:
            raise RuntimeError(f"MCP 返回错误: 方法={method}, 错误={json.dumps(msg['error'], ensure_ascii=False)}")
        return msg.get("result")
    raise RuntimeError(f"MCP 响应中没有对应的结果: 方法={method}, id={req_id}, 消息数={len(messages)}")


def open_session(url, token):
    """
    建立 MCP 会话：initialize 后发送 notifications/initialized。

    :param url: MCP 服务地址
    :param token: MCP Token
    :return: 会话 dict
    """
    session = {"url": url, "token": token, "session_id": None, "protocol_version": None, "next_id": 1}
    result = _request(session, "initialize", {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
    })
    session["protocol_version"] = result.get("protocolVersion")
    server = result.get("serverInfo", {})
    _post(session, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    log(f"MCP 会话已建立: 服务={server.get('name')}, 版本={server.get('version')}, "
        f"协议={session['protocol_version']}, 会话ID={'有' if session['session_id'] else '无'}")
    return session


def close_session(session):
    """
    结束会话：有会话 ID 时发送 DELETE，失败只记日志。

    :param session: 会话 dict
    :return: None
    """
    if not session.get("session_id"):
        return
    req = urllib.request.Request(session["url"], headers=_build_headers(session), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=MCP_TIMEOUT):
            pass
        log("MCP 会话已关闭")
    except (urllib.error.URLError, OSError) as e:
        log(f"关闭 MCP 会话失败，忽略: 原因={e}", "WARNING")


def list_tools(session):
    """
    列出全部工具（自动翻页）。

    :param session: 会话 dict
    :return: list[dict]，每个元素含 name / description / inputSchema
    """
    tools, cursor = [], None
    while True:
        result = _request(session, "tools/list", {"cursor": cursor} if cursor else {})
        tools.extend(result.get("tools", []))
        cursor = result.get("nextCursor")
        if not cursor:
            break
    log(f"获取工具列表: 数量={len(tools)}")
    return tools


def call_tool_raw(session, name, arguments=None):
    """
    调用一个工具，原样返回 MCP 的 result（含 content / structuredContent / isError）。

    :param session: 会话 dict
    :param name: 工具名
    :param arguments: 工具参数 dict
    :return: result dict
    """
    start = time.time()
    result = _request(session, "tools/call", {"name": name, "arguments": arguments or {}})
    log(f"调用工具: 工具={name}, 耗时秒={time.time() - start:.2f}, 出错={bool(result.get('isError'))}")
    return result


def parse_tool_result(result):
    """
    从 tools/call 的 result 中取出业务数据。

    优先取 structuredContent；否则把 text 内容按 JSON 解析，解析不了就原样返回文本。

    :param result: call_tool_raw 的返回值
    :return: 业务数据（dict / list / str）
    """
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def call_tool(session, name, arguments=None):
    """
    调用一个工具，返回解析后的业务数据；工具报错时抛 RuntimeError。

    :param session: 会话 dict
    :param name: 工具名，如 query-meals
    :param arguments: 工具参数 dict
    :return: 业务数据（dict / list / str）
    """
    result = call_tool_raw(session, name, arguments)
    if result.get("isError"):
        raise RuntimeError(f"工具调用失败: 工具={name}, 参数={json.dumps(arguments, ensure_ascii=False)}, "
                           f"返回={json.dumps(result.get('content'), ensure_ascii=False)[:500]}")
    return parse_tool_result(result)
