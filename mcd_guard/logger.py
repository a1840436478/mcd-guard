"""统一日志：同时输出到控制台和 logs/ 下按日期命名的文件。"""

import logging
import sys
import time
from datetime import date

from mcd_guard.config import LOG_DIR, LOG_KEEP_DAYS

_state = {"date": None, "logger": None, "stream": sys.stdout}


def _cleanup_old_logs():
    """删除超过保留天数的旧日志文件。"""
    expire = time.time() - LOG_KEEP_DAYS * 86400
    for path in LOG_DIR.glob("*.log"):
        if path.stat().st_mtime < expire:
            path.unlink()


def _get_logger():
    """返回当天的 logger；跨天时切换到新的日志文件。"""
    today = date.today().isoformat()
    if _state["date"] == today:
        return _state["logger"]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_old_logs()
    logger = logging.getLogger("mcd-guard")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    for handler in (
        logging.StreamHandler(_state["stream"]),
        logging.FileHandler(LOG_DIR / f"{today}.log", encoding="utf-8"),
    ):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    _state["date"], _state["logger"] = today, logger
    return logger


def use_stderr():
    """
    控制台日志改写到标准错误。stdio 模式下标准输出只能传 MCP 消息。

    :return: None
    """
    _state["stream"], _state["date"] = sys.stderr, None


def log(msg, level="INFO"):
    """
    输出一条日志。

    :param msg: 日志内容，格式如 "动作: key=value, key=value"
    :param level: 日志级别，DEBUG / INFO / WARNING / ERROR
    :return: None
    """
    _get_logger().log(getattr(logging, level.upper()), msg)
