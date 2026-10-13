"""护栏策略：读取 policy.json 并与默认策略合并、校验。"""

import json

from config import DEFAULT_POLICY
from logger import log


def validate_policy(policy):
    """
    校验策略字段，不合法时抛 RuntimeError。

    :param policy: 合并后的策略 dict
    :return: None
    """
    if policy["mode"] not in ("confirm", "readonly"):
        raise RuntimeError(f"策略 mode 只能是 confirm 或 readonly: mode={policy['mode']}")
    for key in ("max_order_yuan", "max_daily_yuan", "max_weekly_yuan", "confirm_timeout_sec"):
        value = policy[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise RuntimeError(f"策略字段必须是正数: {key}={value}")
    if not isinstance(policy["blocked_tools"], list):
        raise RuntimeError(f"策略 blocked_tools 必须是列表: blocked_tools={policy['blocked_tools']}")


def load_policy(path):
    """
    读取策略文件；文件不存在时使用默认策略。

    :param path: policy.json 路径
    :return: 策略 dict
    """
    policy = dict(DEFAULT_POLICY)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            custom = json.load(f)
        unknown = set(custom) - set(DEFAULT_POLICY)
        if unknown:
            raise RuntimeError(f"策略文件包含未知字段: 路径={path}, 字段={sorted(unknown)}")
        policy.update(custom)
        log(f"读取策略文件: 路径={path}")
    else:
        log(f"未找到策略文件，使用默认策略: 路径={path}")
    validate_policy(policy)
    log(f"当前策略: {json.dumps(policy, ensure_ascii=False)}")
    return policy
