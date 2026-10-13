"""护栏的本地 MCP 服务（Streamable HTTP，只返回 JSON，不开 SSE 流）和网页面板。

AI 客户端连接本服务，护栏按策略处理后再转发给官方 MCP。
state = {"tools": 上游工具列表, "policy": 策略, "ctx": guard.handle_call 用的依赖, "recent": fn() -> 今天的审计记录}
网页面板：GET / 页面，GET /api/state 数据，POST /api/decide 用确认码确认。
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from config import CLIENT_VERSION
from confirm import answer_from_web
from guard import GUARD_TAG, handle_call, is_write_tool, text_result
from logger import log
from panel import PANEL_HTML, build_panel_state

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
INSTRUCTIONS = (
    "这是麦麦护栏，代理麦当劳中国官方 MCP。查询类工具直接可用；下单、取消订单、积分兑换、抽奖、领券、新增地址等写操作，"
    "需要用户在运行护栏的终端里亲自确认。写操作被拒绝、超时或超出消费上限时，不要重试、拆单或换工具绕过，直接告诉用户。"
)


def transform_tools(tools, policy):
    """
    按策略改写工具列表：隐藏被禁用的工具；只读模式隐藏写操作；给写操作加上护栏提示和注解。

    :param tools: 上游工具列表
    :param policy: 策略 dict
    :return: 改写后的新列表
    """
    result = []
    for tool in tools:
        name = tool["name"]
        write = is_write_tool(name)
        if name in policy["blocked_tools"] or (write and policy["mode"] == "readonly"):
            continue
        tool = dict(tool)
        annotations = dict(tool.get("annotations") or {})
        annotations["readOnlyHint"] = not write
        if write:
            annotations["destructiveHint"] = True
            tool["description"] = (f"{GUARD_TAG}此操作需要用户在麦麦护栏终端确认后才会执行；被拒绝、超时或超限时不要重试。\n"
                                   + tool.get("description", ""))
        tool["annotations"] = annotations
        result.append(tool)
    return result


def is_local_origin(origin):
    """
    校验 Origin 头，防止网页通过 DNS 重绑定访问本地服务。没有 Origin 头的请求（非浏览器）放行。

    :param origin: Origin 头的值
    :return: bool
    """
    if not origin:
        return True
    return urlparse(origin).hostname in LOCAL_HOSTS


def is_local_host(host):
    """
    校验 Host 头只能是本机地址，防止 DNS 重绑定后的网页读取面板数据。

    :param host: Host 头的值，如 127.0.0.1:1024
    :return: bool
    """
    return bool(host) and urlparse(f"//{host}").hostname in LOCAL_HOSTS


def _rpc_error(req_id, code, message):
    """组装 JSON-RPC 错误响应。"""
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_rpc(msg, state):
    """
    处理一条 JSON-RPC 消息。

    :param msg: 解析后的消息 dict
    :param state: 服务状态
    :return: 响应 dict；通知类消息返回 None
    """
    method, req_id = msg.get("method"), msg.get("id")
    if "id" not in msg:
        return None
    params = msg.get("params") or {}
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        client = params.get("clientInfo", {})
        log(f"AI 客户端已连接: 客户端={client.get('name')}, 版本={client.get('version')}, 协议={version}")
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "mcd-guard", "version": CLIENT_VERSION},
            "instructions": INSTRUCTIONS,
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": transform_tools(state["tools"], state["policy"])}
    elif method == "tools/call":
        try:
            result = handle_call(params.get("name"), params.get("arguments"), state["ctx"])
        except RuntimeError as e:
            log(f"处理工具调用出错: 工具={params.get('name')}, 原因={e}", "ERROR")
            result = text_result(f"{GUARD_TAG}调用官方 MCP 出错：{e}")
    else:
        return _rpc_error(req_id, -32601, f"不支持的方法: {method}")
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def make_handler(state):
    """
    生成绑定了服务状态的请求处理类。

    :param state: 服务状态
    :return: BaseHTTPRequestHandler 子类
    """

    class GuardHandler(BaseHTTPRequestHandler):

        def log_message(self, *args):
            pass

        def _send(self, status, payload=None):
            body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            if payload is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html):
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _check_local(self):
            """Host 和 Origin 都必须是本机，否则返回 403。"""
            if is_local_host(self.headers.get("Host")) and is_local_origin(self.headers.get("Origin")):
                return True
            log(f"拒绝非本机来源的请求: Host={self.headers.get('Host')}, Origin={self.headers.get('Origin')}", "WARNING")
            self._send(403, _rpc_error(None, -32000, "只接受本机请求"))
            return False

        def _read_json(self):
            """读取 JSON 请求体，失败返回 None 并已回复 400。"""
            try:
                return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            except (ValueError, json.JSONDecodeError):
                self._send(400, _rpc_error(None, -32700, "请求体不是合法的 JSON"))
                return None

        def do_GET(self):
            if not self._check_local():
                return
            path = urlparse(self.path).path
            if path in ("/", "/panel"):
                self._send_html(PANEL_HTML)
            elif path == "/api/state":
                self._send(200, build_panel_state(state))
            else:
                self._send(405, _rpc_error(None, -32000, "本服务不提供 SSE 流，请用 POST"))

        def do_DELETE(self):
            self._send(200)

        def do_POST(self):
            if not self._check_local():
                return
            path = urlparse(self.path).path
            if path == "/api/decide":
                self._handle_decide()
                return
            msg = self._read_json()
            if msg is None:
                return
            if not isinstance(msg, dict):
                self._send(400, _rpc_error(None, -32600, "不支持批量请求"))
                return
            response = handle_rpc(msg, state)
            if response is None:
                self._send(202)
            else:
                self._send(200, response)

        def _handle_decide(self):
            """网页面板提交确认结果；只接受 JSON，跨站表单无法伪造。"""
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                self._send(415, {"ok": False, "message": "只接受 JSON"})
                return
            body = self._read_json()
            if not isinstance(body, dict):
                return
            ok, message = answer_from_web(body.get("id"), body.get("code"), bool(body.get("approve")))
            self._send(200, {"ok": ok, "message": message})

    return GuardHandler


def create_server(host, port, state):
    """
    创建护栏本地服务（不启动）。

    :param host: 监听地址
    :param port: 端口，0 表示随机
    :param state: 服务状态
    :return: ThreadingHTTPServer
    """
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.daemon_threads = True
    return server
