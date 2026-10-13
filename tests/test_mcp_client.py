"""用本地模拟的 MCP 服务测试客户端：握手、鉴权、SSE、翻页、工具调用、错误处理。"""

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcd_guard.mcp_client import call_tool, close_session, list_tools, open_session, parse_sse  # noqa: E402

TOKEN = "test-token-123456"
SESSION_ID = "sess-abc"


class FakeMcpHandler(BaseHTTPRequestHandler):
    """模拟的 MCP 服务：initialize 用 SSE 返回，其余用 JSON 返回。"""

    received = []

    def log_message(self, *args):
        pass

    def _send(self, status, body=b"", content_type="application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_DELETE(self):
        FakeMcpHandler.received.append({"method": "DELETE", "session": self.headers.get("Mcp-Session-Id")})
        self._send(200)

    def do_POST(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, b'{"error":"unauthorized"}')
            return
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeMcpHandler.received.append({
            "method": msg.get("method"),
            "session": self.headers.get("Mcp-Session-Id"),
            "protocol": self.headers.get("MCP-Protocol-Version"),
        })
        method, req_id = msg.get("method"), msg.get("id")
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "fake", "version": "1"}}
            notice = {"jsonrpc": "2.0", "method": "notifications/message", "params": {}}
            reply = {"jsonrpc": "2.0", "id": req_id, "result": result}
            sse = f"event: message\ndata: {json.dumps(notice)}\n\nevent: message\ndata: {json.dumps(reply)}\n\n"
            self._send(200, sse.encode(), "text/event-stream", {"Mcp-Session-Id": SESSION_ID})
        elif method == "notifications/initialized":
            self._send(202)
        elif method == "tools/list":
            cursor = msg["params"].get("cursor")
            result = {"tools": [{"name": "b-tool"}], "nextCursor": "p2"} if not cursor else {"tools": [{"name": "a-tool"}]}
            self._send(200, json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}).encode())
        elif method == "tools/call":
            name = msg["params"]["name"]
            if name == "bad":
                result = {"isError": True, "content": [{"type": "text", "text": "参数错误"}]}
            elif name == "structured":
                result = {"content": [], "structuredContent": {"success": True}}
            else:
                result = {"content": [{"type": "text", "text": json.dumps({"code": 200, "data": "中文"}, ensure_ascii=False)}]}
            self._send(200, json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, ensure_ascii=False).encode())
        else:
            err = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "not found"}}
            self._send(200, json.dumps(err).encode())


class McpClientTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMcpHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeMcpHandler.received = []

    def test_session_flow(self):
        session = open_session(self.url, TOKEN)
        try:
            self.assertEqual(session["session_id"], SESSION_ID)
            self.assertEqual(session["protocol_version"], "2025-03-26")
            names = [t["name"] for t in list_tools(session)]
            self.assertEqual(names, ["b-tool", "a-tool"])
            self.assertEqual(call_tool(session, "x"), {"code": 200, "data": "中文"})
            self.assertEqual(call_tool(session, "structured"), {"success": True})
        finally:
            close_session(session)
        after_init = FakeMcpHandler.received[1:]
        self.assertTrue(all(r["session"] == SESSION_ID for r in after_init))
        self.assertTrue(all(r["protocol"] == "2025-03-26" for r in after_init if r["method"] != "DELETE"))
        self.assertEqual(FakeMcpHandler.received[-1]["method"], "DELETE")

    def test_bad_token(self):
        with self.assertRaisesRegex(RuntimeError, "401"):
            open_session(self.url, "wrong")

    def test_tool_error_and_rpc_error(self):
        session = open_session(self.url, TOKEN)
        try:
            with self.assertRaisesRegex(RuntimeError, "工具调用失败"):
                call_tool(session, "bad")
            from mcd_guard.mcp_client import _request
            with self.assertRaisesRegex(RuntimeError, "MCP 返回错误"):
                _request(session, "unknown/method")
        finally:
            close_session(session)

    def test_parse_sse_multiline(self):
        text = 'data: {"a":\ndata: 1}\n\ndata: {"b": 2}'
        self.assertEqual(parse_sse(text), [{"a": 1}, {"b": 2}])


if __name__ == "__main__":
    unittest.main()
