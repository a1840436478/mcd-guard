"""逐个工具规则测试：allow 直接放行、block 拦截、confirm 需确认，以及与限额、只读模式、工具列表的配合。"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcd_guard.audit import spent_fen, write_audit  # noqa: E402
from mcd_guard.config import DEFAULT_POLICY  # noqa: E402
from mcd_guard.guard import auto_allowed_writes, handle_call, tool_rule  # noqa: E402
from mcd_guard.policy import validate_policy  # noqa: E402
from mcd_guard.server import transform_tools  # noqa: E402
from test_guard import ORDER, FakeEnv  # noqa: E402
from tmp_root import temp_dir  # noqa: E402

TOOLS = [{"name": n, "description": "原说明"} for n in ("query-meals", "create-order", "auto-bind-coupons", "draw-lottery")]


class ToolRulesTest(unittest.TestCase):

    def test_allow_write_skips_confirm(self):
        env = FakeEnv(answer="no", policy={"tool_rules": {"auto-bind-coupons": "allow"}})
        result = handle_call("auto-bind-coupons", {}, env.ctx())
        self.assertFalse(result.get("isError"))
        self.assertEqual(env.cards, [])
        self.assertEqual(len(env.called("auto-bind-coupons")), 1)
        self.assertEqual((env.audits[-1]["decision"], env.audits[-1]["reason"]), ("allowed", "tool_rules"))

    def test_allowed_order_still_limited(self):
        env = FakeEnv(price=15000, policy={"tool_rules": {"create-order": "allow"}})
        result = handle_call("create-order", ORDER, env.ctx())
        self.assertTrue(result["isError"])
        self.assertEqual(env.called("create-order"), [])
        self.assertEqual(env.audits[-1]["reason"], "limit")

    def test_allowed_order_within_limit(self):
        env = FakeEnv(price=2000, policy={"tool_rules": {"create-order": "allow"}})
        handle_call("create-order", ORDER, env.ctx())
        self.assertEqual(env.cards, [])
        self.assertEqual(len(env.called("create-order")), 1)
        self.assertEqual(env.audits[-1]["price_fen"], 2000)

    def test_block_rule(self):
        env = FakeEnv(policy={"tool_rules": {"query-meals": "block"}})
        result = handle_call("query-meals", {}, env.ctx())
        self.assertTrue(result["isError"])
        self.assertEqual(env.calls, [])

    def test_confirm_read_tool(self):
        env = FakeEnv(answer="no", policy={"tool_rules": {"query-meals": "confirm"}})
        handle_call("query-meals", {}, env.ctx())
        self.assertEqual(len(env.cards), 1)
        self.assertEqual(env.calls, [])

    def test_readonly_beats_allow(self):
        env = FakeEnv(policy={"mode": "readonly", "tool_rules": {"auto-bind-coupons": "allow"}})
        result = handle_call("auto-bind-coupons", {}, env.ctx())
        self.assertTrue(result["isError"])
        self.assertEqual(env.calls, [])

    def test_blocked_tools_beats_rules(self):
        policy = {**DEFAULT_POLICY, "blocked_tools": ["draw-lottery"], "tool_rules": {"draw-lottery": "allow"}}
        self.assertEqual(tool_rule("draw-lottery", policy), "block")
        self.assertEqual(auto_allowed_writes(policy), ["draw-lottery"])

    def test_transform_tools(self):
        policy = {**DEFAULT_POLICY, "tool_rules": {"auto-bind-coupons": "allow", "draw-lottery": "block"}}
        tools = {t["name"]: t for t in transform_tools(TOOLS, policy)}
        self.assertNotIn("draw-lottery", tools)
        self.assertIn("确认后才会执行", tools["create-order"]["description"])
        self.assertIn("消费上限", tools["auto-bind-coupons"]["description"])
        self.assertTrue(tools["auto-bind-coupons"]["annotations"]["destructiveHint"])
        self.assertEqual(tools["query-meals"]["description"], "原说明")

    def test_validate(self):
        for rules in ([], {"create-order": "yes"}, {"party-order-create": "allow"}):
            with self.assertRaises(RuntimeError):
                validate_policy({**DEFAULT_POLICY, "tool_rules": rules})
        validate_policy({**DEFAULT_POLICY, "tool_rules": {"create-order": "allow", "draw-lottery": "block"}})

    def test_spent_counts_allowed_orders(self):
        audit_dir, now = temp_dir(self), datetime(2026, 10, 14, 12, 0)
        write_audit({"tool": "create-order", "decision": "allowed", "price_fen": 3000, "upstream_ok": True}, audit_dir, now)
        write_audit({"tool": "create-order", "decision": "rejected", "price_fen": 9000}, audit_dir, now)
        self.assertEqual(spent_fen(audit_dir, now), (3000, 3000))


if __name__ == "__main__":
    unittest.main()
