"""网页确认码与面板测试。"""

import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import confirm  # noqa: E402
from server import create_server, is_local_host  # noqa: E402
from test_guard import FakeEnv  # noqa: E402


def run_confirm(timeout=5):
    """在后台线程里发起一次确认，返回 (结果容器, 线程)。"""
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault("answer", confirm.confirm("卡片", timeout)))
    thread.start()
    for _ in range(100):
        if confirm.get_pending():
            break
        time.sleep(0.01)
    return box, thread


class ConfirmTest(unittest.TestCase):

    def test_web_right_code(self):
        box, thread = run_confirm()
        pending = confirm.get_pending()
        self.assertNotIn("code", pending)  # 公开信息里不能带确认码
        code = confirm._state["pending"]["code"]
        self.assertEqual(confirm.answer_from_web(pending["id"], code, True), (True, "已确认"))
        thread.join(2)
        self.assertEqual(box["answer"], "yes")
        self.assertIsNone(confirm.get_pending())

    def test_web_reject_without_code(self):
        box, thread = run_confirm()
        self.assertTrue(confirm.answer_from_web(confirm.get_pending()["id"], "", False)[0])
        thread.join(2)
        self.assertEqual(box["answer"], "no")

    def test_wrong_codes_lock_out(self):
        box, thread = run_confirm()
        request_id = confirm.get_pending()["id"]
        real = confirm._state["pending"]["code"]
        wrong = "000000" if real != "000000" else "111111"
        for _ in range(confirm.MAX_WRONG_CODES):
            ok, _ = confirm.answer_from_web(request_id, wrong, True)
            self.assertFalse(ok)
        thread.join(2)
        self.assertEqual(box["answer"], "no")

    def test_stale_id_and_timeout(self):
        self.assertFalse(confirm.answer_from_web("nope", "123456", True)[0])
        box, thread = run_confirm(timeout=0.3)
        thread.join(2)
        self.assertEqual(box["answer"], "timeout")


class PanelTest(unittest.TestCase):

    def setUp(self):
        env = FakeEnv()
        state = {"tools": [], "policy": env.policy, "ctx": env.ctx(),
                 "recent": lambda: [{"time": "2026-10-13 18:00:00", "tool": "query-meals", "decision": "allowed"}]}
        server = create_server("127.0.0.1", 0, state)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_address[1]}"

    def fetch(self, path, data=None, headers=None):
        req = urllib.request.Request(self.base + path, data=data, headers=headers or {}, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_page_and_state(self):
        status, html = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertIn("麦麦护栏", html)
        status, body = self.fetch("/api/state")
        data = json.loads(body)
        self.assertEqual((status, data["pending"], data["spent_daily"]), (200, None, 0))
        self.assertEqual(data["recent"][0]["tool"], "query-meals")
        rules = {r["tool"]: r["rule"] for r in data["rules"]}
        self.assertEqual(rules["create-order"], "confirm")
        self.assertEqual(len(rules), 7)

    def test_foreign_host_rejected(self):
        status, _ = self.fetch("/api/state", headers={"Host": "evil.example:1024"})
        self.assertEqual(status, 403)
        self.assertTrue(is_local_host("localhost:1024"))
        self.assertTrue(is_local_host("[::1]:1024"))
        self.assertFalse(is_local_host("127.0.0.1.evil.example"))
        self.assertFalse(is_local_host(None))

    def test_decide_requires_json(self):
        status, _ = self.fetch("/api/decide", data=b"id=1&code=1&approve=1",
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 415)
        status, body = self.fetch("/api/decide", data=json.dumps({"id": "x", "code": "1", "approve": True}).encode(),
                                  headers={"Content-Type": "application/json"})
        self.assertEqual((status, json.loads(body)["ok"]), (200, False))

    def test_decide_with_right_code_over_http(self):
        box, thread = run_confirm()
        pending = json.loads(self.fetch("/api/state")[1])["pending"]
        self.assertNotIn("code", pending)
        code = confirm._state["pending"]["code"]
        status, body = self.fetch("/api/decide", data=json.dumps({"id": pending["id"], "code": code, "approve": True}).encode(),
                                  headers={"Content-Type": "application/json"})
        thread.join(2)
        self.assertEqual((status, json.loads(body)["ok"], box["answer"]), (200, True, "yes"))


if __name__ == "__main__":
    unittest.main()
