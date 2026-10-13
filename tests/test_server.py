"""端到端测试：用本项目的 MCP 客户端扮演 AI 客户端，连接护栏本地服务。"""

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DEFAULT_POLICY  # noqa: E402
from mcp_client import call_tool_raw, close_session, list_tools, open_session  # noqa: E402
from server import create_server, is_local_origin  # noqa: E402
from test_guard import FakeEnv  # noqa: E402

UPSTREAM_TOOLS = [
    {"name": "query-meals", "description": "餐品列表", "inputSchema": {}},
    {"name": "calculate-price", "description": "算价", "inputSchema": {}},
    {"name": "create-order", "description": "创建订单", "inputSchema": {}},
    {"name": "draw-lottery", "description": "抽奖", "inputSchema": {}},
]


class ServerTest(unittest.TestCase):

    def start(self, env):
        """启动护栏服务，返回地址。"""
        state = {"tools": UPSTREAM_TOOLS, "policy": env.policy, "ctx": env.ctx()}
        server = create_server("127.0.0.1", 0, state)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/mcp"

    def test_confirm_mode_flow(self):
        env = FakeEnv(answer="yes", price=2500)
        session = open_session(self.start(env), "unused-token")
        try:
            self.assertEqual(session["protocol_version"], "2025-06-18")
            tools = {t["name"]: t for t in list_tools(session)}
            self.assertEqual(set(tools), {t["name"] for t in UPSTREAM_TOOLS})
            self.assertTrue(tools["query-meals"]["annotations"]["readOnlyHint"])
            self.assertTrue(tools["create-order"]["annotations"]["destructiveHint"])
            self.assertTrue(tools["create-order"]["description"].startswith("【麦麦护栏】"))
            self.assertFalse(call_tool_raw(session, "query-meals", {"storeCode": "1"}).get("isError"))
            result = call_tool_raw(session, "create-order", {"storeCode": "1", "items": []})
            self.assertFalse(result.get("isError"))
            self.assertEqual(len(env.called("create-order")), 1)
        finally:
            close_session(session)

    def test_readonly_mode_hides_and_blocks(self):
        env = FakeEnv(policy={"mode": "readonly"})
        session = open_session(self.start(env), "x")
        try:
            names = {t["name"] for t in list_tools(session)}
            self.assertEqual(names, {"query-meals", "calculate-price"})
            result = call_tool_raw(session, "create-order", {"storeCode": "1"})
            self.assertTrue(result["isError"])
            self.assertEqual(env.called("create-order"), [])
        finally:
            close_session(session)

    def test_reject_foreign_origin(self):
        url = self.start(FakeEnv())
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 403)

    def test_bad_json_and_notification(self):
        url = self.start(FakeEnv())
        for body, expected in ((b"{not json", 400), (b"[]", 400),
                               (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode(), 202)):
            req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    status = resp.status
            except urllib.error.HTTPError as e:
                status = e.code
            self.assertEqual(status, expected, body)

    def test_local_origin(self):
        self.assertTrue(is_local_origin(None))
        self.assertTrue(is_local_origin("http://localhost:3000"))
        self.assertTrue(is_local_origin("http://127.0.0.1"))
        self.assertFalse(is_local_origin("http://127.0.0.1.evil.example"))
        self.assertFalse(is_local_origin("https://evil.example"))


if __name__ == "__main__":
    unittest.main()
