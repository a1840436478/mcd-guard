"""演示模式测试：模拟服务的报价、护栏在演示数据上的确认和限额，以及审计写到演示目录。"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DEFAULT_POLICY  # noqa: E402
from demo_upstream import DEMO_TOOLS, demo_call  # noqa: E402
from guard import handle_call  # noqa: E402
from mcp_client import parse_tool_result  # noqa: E402
from run_guard import build_state, calc_props_of  # noqa: E402
from tmp_root import temp_dir  # noqa: E402

ORDER = {"storeCode": "DEMO001", "orderType": 1, "beType": 1, "items": [{"productCode": "D01", "quantity": 2}]}


def demo_ctx(audit_dir, answer, policy=None):
    """用演示服务组装护栏依赖，确认环节换成固定回答。"""
    state = build_state(DEMO_TOOLS, {**DEFAULT_POLICY, **(policy or {})}, demo_call, audit_dir)
    cards = []
    state["ctx"]["confirm"] = lambda card, timeout: cards.append(card) or answer
    return state, cards


class DemoTest(unittest.TestCase):

    def test_quote(self):
        body = parse_tool_result(demo_call("calculate-price", ORDER))
        self.assertEqual(body["data"]["price"], 5000)
        self.assertTrue(demo_call("calculate-price", {"items": [{"productCode": "X", "quantity": 1}]})["isError"])

    def test_calc_props(self):
        self.assertIn("items", calc_props_of(DEMO_TOOLS))

    def test_confirmed_order_counts_in_demo_audit(self):
        audit_dir = temp_dir(self)
        state, cards = demo_ctx(audit_dir, "yes")
        result = handle_call("create-order", ORDER, state["ctx"])
        self.assertFalse(result.get("isError"))
        self.assertIn("¥50.00", cards[0])
        self.assertEqual(state["ctx"]["spent"](), (5000, 5000))
        self.assertEqual(state["recent"]()[-1]["decision"], "confirmed")
        self.assertTrue((audit_dir / f"{date.today()}.jsonl").exists())

    def test_over_limit_blocked(self):
        state, cards = demo_ctx(temp_dir(self), "yes")
        big = {**ORDER, "items": [{"productCode": "D06", "quantity": 5}]}
        result = handle_call("create-order", big, state["ctx"])
        self.assertTrue(result["isError"])
        self.assertEqual(cards, [])
        self.assertEqual(state["recent"]()[-1]["reason"], "limit")


if __name__ == "__main__":
    unittest.main()
