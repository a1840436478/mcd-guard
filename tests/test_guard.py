"""护栏核心逻辑测试：放行、拦截、确认、限额、超时、打码。"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcd_guard.config import DEFAULT_POLICY  # noqa: E402
from mcd_guard.guard import check_limits, handle_call, is_write_tool  # noqa: E402


def ok_result(data):
    """模拟上游的成功返回。"""
    return {"content": [{"type": "text", "text": json.dumps({"success": True, "code": 200, "data": data})}]}


class FakeEnv:
    """记录上游调用、确认请求和审计记录的假依赖。"""

    def __init__(self, answer="yes", price=3000, spent=(0, 0), policy=None, fail_tools=()):
        self.calls, self.cards, self.audits = [], [], []
        self.answer, self.price, self._spent, self.fail_tools = answer, price, spent, fail_tools
        self.policy = {**DEFAULT_POLICY, **(policy or {})}

    def upstream(self, name, arguments):
        self.calls.append((name, arguments))
        if name in self.fail_tools:
            raise RuntimeError("网络断了")
        if name == "calculate-price":
            if self.price is None:
                return {"content": [{"type": "text", "text": '{"success": false, "message": "餐品不存在"}'}]}
            return ok_result({"price": self.price, "productList": [{"productName": "巨无霸", "quantity": 1}]})
        return ok_result({"tool": name})

    def confirm(self, card, timeout):
        self.cards.append(card)
        return self.answer

    def ctx(self):
        return {
            "policy": self.policy, "upstream": self.upstream, "confirm": self.confirm,
            "spent": lambda: self._spent, "audit": self.audits.append,
            "calc_props": {"storeCode", "orderType", "beType", "items", "beCode", "reservationDate"},
        }

    def called(self, name):
        return [c for c in self.calls if c[0] == name]


ORDER = {"storeCode": "1990346", "orderType": 1, "beType": 1, "takeWayCode": "take-in-store",
         "items": [{"productCode": "9900005466", "quantity": 1}]}


class GuardTest(unittest.TestCase):

    def test_read_tool_passes_through(self):
        env = FakeEnv()
        result = handle_call("query-meals", {"storeCode": "1"}, env.ctx())
        self.assertFalse(result.get("isError"))
        self.assertEqual(env.called("query-meals"), [("query-meals", {"storeCode": "1"})])
        self.assertEqual(env.cards, [])
        self.assertEqual(env.audits[-1]["decision"], "allowed")

    def test_unknown_tool_treated_as_write(self):
        self.assertTrue(is_write_tool("some-new-tool"))
        env = FakeEnv(answer="no")
        handle_call("some-new-tool", {}, env.ctx())
        self.assertEqual(len(env.cards), 1)
        self.assertEqual(env.called("some-new-tool"), [])

    def test_readonly_blocks_write(self):
        env = FakeEnv(policy={"mode": "readonly"})
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertTrue(result["isError"])
        self.assertIn("只读模式", result["content"][0]["text"])
        self.assertEqual(env.calls, [])
        self.assertEqual(env.audits[-1]["reason"], "readonly")

    def test_blocked_tools(self):
        env = FakeEnv(policy={"blocked_tools": ["draw-lottery", "order-list"]})
        for name in ("draw-lottery", "order-list"):
            result = handle_call(name, {}, env.ctx())
            self.assertTrue(result["isError"])
        self.assertEqual(env.calls, [])

    def test_order_confirmed(self):
        env = FakeEnv(answer="yes", price=3880)
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertFalse(result.get("isError"))
        quote_args = env.called("calculate-price")[0][1]
        self.assertNotIn("takeWayCode", quote_args)  # 只把 calculate-price 支持的参数传去试算
        self.assertEqual(len(env.called("create-order")), 1)
        self.assertIn("¥38.80", env.cards[0])
        self.assertIn("巨无霸 x1", env.cards[0])
        record = env.audits[-1]
        self.assertEqual((record["decision"], record["price_fen"], record["upstream_ok"]), ("confirmed", 3880, True))

    def test_order_rejected(self):
        env = FakeEnv(answer="no")
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertTrue(result["isError"])
        self.assertIn("拒绝", result["content"][0]["text"])
        self.assertEqual(env.called("create-order"), [])
        self.assertEqual(env.audits[-1]["decision"], "rejected")

    def test_order_timeout(self):
        env = FakeEnv(answer="timeout")
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertIn("没有确认", result["content"][0]["text"])
        self.assertEqual(env.called("create-order"), [])
        self.assertEqual(env.audits[-1]["decision"], "timeout")

    def test_order_over_single_limit(self):
        env = FakeEnv(price=10001)  # 默认单笔上限 100 元
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertIn("单笔上限", result["content"][0]["text"])
        self.assertEqual(env.cards, [])
        self.assertEqual(env.called("create-order"), [])

    def test_order_over_daily_limit(self):
        env = FakeEnv(price=5000, spent=(16000, 16000))  # 当天已花 160，再花 50 超过 200
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertIn("当天累计上限", result["content"][0]["text"])
        self.assertEqual(env.called("create-order"), [])

    def test_quote_failed_blocks(self):
        env = FakeEnv(price=None)
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertIn("无法用官方试算核实", result["content"][0]["text"])
        self.assertEqual(env.cards, [])
        self.assertEqual(env.called("create-order"), [])

    def test_upstream_error_after_confirm(self):
        env = FakeEnv(answer="yes", fail_tools=("create-order",))
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertIn("结果未知", result["content"][0]["text"])
        self.assertIsNone(env.audits[-1]["upstream_ok"])

    def test_non_order_write_needs_confirm(self):
        env = FakeEnv(answer="yes")
        handle_call("auto-bind-coupons", {}, env.ctx())
        self.assertIn("一键领券", env.cards[0])
        self.assertEqual(len(env.called("auto-bind-coupons")), 1)
        self.assertEqual(env.called("calculate-price"), [])

    def test_address_redacted_in_audit(self):
        env = FakeEnv(answer="no")
        args = {"city": "南京市", "contactName": "李明", "phone": "18600000000", "address": "某小区", "addressDetail": "1-101"}
        handle_call("delivery-create-address", args, env.ctx())
        logged = env.audits[-1]["arguments"]
        self.assertEqual(logged["city"], "南京市")
        for key in ("contactName", "phone", "address", "addressDetail"):
            self.assertEqual(logged[key], "***")

    def test_check_limits_boundary(self):
        policy = {**DEFAULT_POLICY, "max_order_yuan": 50, "max_daily_yuan": 100, "max_weekly_yuan": 300}
        self.assertIsNone(check_limits(5000, policy, (5000, 5000)))  # 正好等于上限，放行
        self.assertIn("单笔上限", check_limits(5001, policy, (0, 0)))
        self.assertIn("本周累计上限", check_limits(1000, policy, (0, 29500)))


if __name__ == "__main__":
    unittest.main()
