"""stdio 只读模式测试：逐行收发、写操作隐藏和拦截、错误消息。"""

import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcd_guard.config import DEFAULT_POLICY  # noqa: E402
from mcd_guard.demo_upstream import DEMO_TOOLS, demo_call  # noqa: E402
from mcd_guard.app import readonly_state  # noqa: E402
from mcd_guard.stdio_server import serve_stdio  # noqa: E402
from tmp_root import temp_dir  # noqa: E402


def rpc(req_id, method, params=None):
    """生成一行 JSON-RPC 请求。"""
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}) + "\n"


class StdioTest(unittest.TestCase):

    def run_lines(self, lines):
        """把多行输入交给 stdio 服务，返回解析后的响应列表。"""
        state = readonly_state(DEMO_TOOLS, dict(DEFAULT_POLICY), demo_call, temp_dir(self))
        out = io.StringIO()
        serve_stdio(state, io.StringIO("".join(lines)), out)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_readonly_flow(self):
        order = {"storeCode": "DEMO001", "orderType": 1, "beType": 1, "items": [{"productCode": "D01", "quantity": 1}]}
        replies = self.run_lines([
            rpc(1, "initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "t"}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n",
            rpc(2, "tools/list"),
            rpc(3, "tools/call", {"name": "query-meals", "arguments": {"storeCode": "DEMO001"}}),
            rpc(4, "tools/call", {"name": "create-order", "arguments": order}),
        ])
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4])
        names = {t["name"] for t in replies[1]["result"]["tools"]}
        self.assertIn("query-meals", names)
        self.assertNotIn("create-order", names)
        self.assertFalse(replies[2]["result"].get("isError"))
        self.assertTrue(replies[3]["result"]["isError"])
        self.assertIn("只读模式", replies[3]["result"]["content"][0]["text"])

    def test_bad_input(self):
        replies = self.run_lines(["not json\n", "\n", "[1, 2]\n"])
        self.assertEqual([r["error"]["code"] for r in replies], [-32700, -32600])


if __name__ == "__main__":
    unittest.main()
