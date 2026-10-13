"""在护栏自己的终端里向用户确认写操作。

AI 只能通过 MCP 和护栏交互，看不到也碰不到这个终端，所以无法替用户点确认。
后台线程持续读取标准输入；同一时间只处理一个确认请求。
"""

import queue
import sys
import threading

from logger import log

_answers = queue.Queue()
_confirm_lock = threading.Lock()
_reader = {"started": False}


def _read_stdin():
    """后台线程：把用户输入的每一行放进队列。"""
    for line in sys.stdin:
        _answers.put(line.strip().lower())


def start_reader():
    """
    启动读取标准输入的后台线程（只启动一次）。

    :return: 标准输入是否为交互终端
    """
    if not _reader["started"]:
        threading.Thread(target=_read_stdin, daemon=True).start()
        _reader["started"] = True
    interactive = sys.stdin.isatty()
    if not interactive:
        log("标准输入不是交互终端，写操作将无法确认并全部按超时拒绝", "WARNING")
    return interactive


def _drain():
    """丢弃确认开始前残留的输入，避免旧的回车被当成确认。"""
    while True:
        try:
            _answers.get_nowait()
        except queue.Empty:
            return


def confirm(card, timeout_sec):
    """
    显示确认卡片并等待用户输入。

    :param card: 卡片文本
    :param timeout_sec: 等待秒数
    :return: "yes"（输入 y/yes）、"no"（其他输入）或 "timeout"
    """
    with _confirm_lock:
        _drain()
        log(card)
        log(f"输入 y 回车确认执行，输入其他内容拒绝（{timeout_sec} 秒后自动拒绝）")
        try:
            answer = _answers.get(timeout=timeout_sec)
        except queue.Empty:
            log("等待确认超时，按拒绝处理", "WARNING")
            return "timeout"
        decision = "yes" if answer in ("y", "yes") else "no"
        log(f"用户确认结果: 输入={answer!r}, 结论={decision}")
        return decision
