"""审计日志与策略文件测试。"""

import json
import os
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit import cleanup_old_audit, read_audit, spent_fen, write_audit  # noqa: E402
from config import AUDIT_KEEP_DAYS, DEFAULT_POLICY  # noqa: E402
from policy import load_policy  # noqa: E402
from tmp_root import temp_dir  # noqa: E402


def order(price, decision="confirmed", upstream_ok=True):
    """组装一条下单审计记录。"""
    return {"tool": "create-order", "decision": decision, "price_fen": price, "upstream_ok": upstream_ok}


class AuditTest(unittest.TestCase):

    def test_spent_daily_and_weekly(self):
        d = temp_dir(self)
        # 2026-10-14 是周三；本周从 10-12（周一）开始
        write_audit(order(1000), d, datetime(2026, 10, 11, 12))  # 上周日，不计入
        write_audit(order(2000), d, datetime(2026, 10, 12, 12))  # 周一，只计入本周
        write_audit(order(3000), d, datetime(2026, 10, 14, 9))  # 当天
        write_audit(order(500, upstream_ok=None), d, datetime(2026, 10, 14, 10))  # 结果未知，保守计入
        write_audit(order(9999, upstream_ok=False), d, datetime(2026, 10, 14, 11))  # 上游失败，不计入
        write_audit(order(8888, decision="rejected"), d, datetime(2026, 10, 14, 11))  # 拒绝，不计入
        write_audit({"tool": "query-meals", "decision": "allowed"}, d, datetime(2026, 10, 14, 11))
        self.assertEqual(spent_fen(d, datetime(2026, 10, 14, 20)), (3500, 5500))

    def test_read_audit_keeps_time(self):
        d = temp_dir(self)
        write_audit({"tool": "x", "decision": "allowed"}, d, datetime(2026, 10, 14, 8, 30))
        records = read_audit(datetime(2026, 10, 14).date(), d)
        self.assertEqual(records[0]["time"], "2026-10-14 08:30:00")
        self.assertEqual(read_audit(datetime(2026, 1, 1).date(), d), [])

    def test_cleanup_old_audit(self):
        d = temp_dir(self)
        old, new = d / "2026-01-01.jsonl", d / "2026-10-14.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        new.write_text("{}\n", encoding="utf-8")
        expired = time.time() - (AUDIT_KEEP_DAYS + 1) * 86400
        os.utime(old, (expired, expired))
        self.assertEqual(cleanup_old_audit(d), 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())


class PolicyTest(unittest.TestCase):

    def test_default_when_missing(self):
        self.assertEqual(load_policy(temp_dir(self) / "policy.json"), DEFAULT_POLICY)

    def test_override(self):
        path = temp_dir(self) / "policy.json"
        path.write_text(json.dumps({"mode": "readonly", "max_order_yuan": 30}), encoding="utf-8")
        policy = load_policy(path)
        self.assertEqual((policy["mode"], policy["max_order_yuan"]), ("readonly", 30))
        self.assertEqual(policy["max_daily_yuan"], DEFAULT_POLICY["max_daily_yuan"])

    def test_invalid(self):
        path = temp_dir(self) / "policy.json"
        for bad in ({"mode": "yolo"}, {"max_order_yuan": 0}, {"max_daily_yuan": True}, {"typo_field": 1},
                    {"blocked_tools": "draw-lottery"}):
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(RuntimeError, msg=str(bad)):
                load_policy(path)


if __name__ == "__main__":
    unittest.main()
