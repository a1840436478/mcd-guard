"""审计日志：记录 AI 通过护栏做的每一次调用，并据此统计已确认的消费。

每天一个 jsonl 文件，位于 audit/ 下，保留 AUDIT_KEEP_DAYS 天。
"""

import json
import time
from datetime import datetime, timedelta

from mcd_guard.config import AUDIT_DIR, AUDIT_KEEP_DAYS
from mcd_guard.logger import log

# 写进审计日志前要打码的字段（新增地址里的个人信息）
SENSITIVE_KEYS = {"phone", "contactName", "address", "addressDetail"}


def redact(arguments):
    """
    对参数中的个人信息打码。

    :param arguments: 工具参数 dict
    :return: 打码后的新 dict
    """
    return {k: ("***" if k in SENSITIVE_KEYS else v) for k, v in (arguments or {}).items()}


def cleanup_old_audit(audit_dir=AUDIT_DIR):
    """
    删除超过保留天数的审计文件。

    :param audit_dir: 审计目录
    :return: 删除的文件数
    """
    if not audit_dir.exists():
        return 0
    expire = time.time() - AUDIT_KEEP_DAYS * 86400
    removed = 0
    for path in audit_dir.glob("*.jsonl"):
        if path.stat().st_mtime < expire:
            path.unlink()
            removed += 1
    if removed:
        log(f"清理旧审计日志: 删除数={removed}, 保留天数={AUDIT_KEEP_DAYS}")
    return removed


def write_audit(record, audit_dir=AUDIT_DIR, now=None):
    """
    追加一条审计记录。

    :param record: 记录 dict，至少含 tool、decision
    :param audit_dir: 审计目录
    :param now: 当前时间（测试用），默认取系统时间
    :return: 实际写入的记录 dict（补上了 time）
    """
    now = now or datetime.now()
    audit_dir.mkdir(parents=True, exist_ok=True)
    record = {"time": now.strftime("%Y-%m-%d %H:%M:%S"), **record}
    with open(audit_dir / f"{now:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_audit(day, audit_dir=AUDIT_DIR):
    """
    读取某一天的全部审计记录。

    :param day: date 对象
    :param audit_dir: 审计目录
    :return: list[dict]，文件不存在时返回空列表
    """
    path = audit_dir / f"{day:%Y-%m-%d}.jsonl"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def spent_fen(audit_dir=AUDIT_DIR, now=None):
    """
    统计当天和本周（周一起）已确认或按规则放行、并成功创建的订单应付金额。

    已创建但未支付、以及转发出错结果未知的订单也计入，宁可多算不少算。

    :param audit_dir: 审计目录
    :param now: 当前时间（测试用）
    :return: (当天分, 本周分)
    """
    now = now or datetime.now()
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    daily = weekly = 0
    for offset in range((today - monday).days + 1):
        day = monday + timedelta(days=offset)
        for rec in read_audit(day, audit_dir):
            if rec.get("tool") == "create-order" and rec.get("decision") in ("confirmed", "allowed") and rec.get("upstream_ok") is not False:
                amount = rec.get("price_fen") or 0
                weekly += amount
                if day == today:
                    daily += amount
    return daily, weekly
