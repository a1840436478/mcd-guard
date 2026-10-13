"""写操作确认：护栏终端输入 y/n，或在本地网页面板输入确认码，二选一。

AI 只能通过 MCP 和护栏交互，看不到护栏终端，因此拿不到确认码，也没法替用户输入 y。
同一时间只处理一个确认请求。
"""

import queue
import secrets
import sys
import threading
import time

from logger import log

MAX_WRONG_CODES = 5  # 网页确认码连续输错次数上限，超过就按拒绝处理

_lines = queue.Queue()
_confirm_lock = threading.Lock()
_state = {"pending": None, "reader_started": False}


def _read_stdin():
    """后台线程：把终端里输入的每一行放进队列。"""
    for line in sys.stdin:
        _lines.put(line.strip().lower())


def start_reader():
    """
    启动读取护栏终端输入的后台线程（只启动一次）。

    :return: 标准输入是否为交互终端
    """
    if not _state["reader_started"]:
        threading.Thread(target=_read_stdin, daemon=True).start()
        _state["reader_started"] = True
    interactive = sys.stdin.isatty()
    if not interactive:
        log("标准输入不是交互终端，只能在网页面板用确认码确认", "WARNING")
    return interactive


def _show_code(code):
    """
    只在护栏终端显示确认码，不写进日志文件，避免能读文件的程序拿到它。

    :param code: 确认码
    :return: None
    """
    sys.stdout.write(f"网页面板确认码：{code}（只显示在这个窗口）\n")
    sys.stdout.flush()


def get_pending():
    """
    当前待确认请求的公开信息（不含确认码），供网页面板展示。

    :return: dict 或 None
    """
    pending = _state["pending"]
    if pending is None:
        return None
    left = max(0, int(pending["deadline"] - time.time()))
    return {"id": pending["id"], "card": pending["card"], "seconds_left": left}


def answer_from_web(request_id, code, approve):
    """
    网页面板提交的确认结果。

    :param request_id: 待确认请求的 id
    :param code: 用户输入的确认码
    :param approve: True 表示确认，False 表示拒绝
    :return: (是否被接受, 说明文字)
    """
    pending = _state["pending"]
    if pending is None or pending["id"] != request_id:
        return False, "这个请求已经处理完或已过期"
    if not approve:
        pending["queue"].put(("no", "网页"))
        return True, "已拒绝"
    if secrets.compare_digest(str(code or ""), pending["code"]):
        pending["queue"].put(("yes", "网页"))
        return True, "已确认"
    pending["wrong"] += 1
    log(f"网页确认码错误: 请求={request_id}, 已错次数={pending['wrong']}", "WARNING")
    if pending["wrong"] >= MAX_WRONG_CODES:
        pending["queue"].put(("no", "网页（确认码错误次数过多）"))
        return False, "确认码错误次数过多，已按拒绝处理"
    return False, f"确认码不对，还能再试 {MAX_WRONG_CODES - pending['wrong']} 次"


def _forward_terminal(answers, stop):
    """把终端输入转进当前请求的答案队列，直到请求结束。"""
    while not stop.is_set():
        try:
            line = _lines.get(timeout=0.2)
        except queue.Empty:
            continue
        answers.put(("yes" if line in ("y", "yes") else "no", "终端"))
        return


def _drain():
    """丢弃确认开始前残留的终端输入，避免旧的回车被当成确认。"""
    while True:
        try:
            _lines.get_nowait()
        except queue.Empty:
            return


def confirm(card, timeout_sec):
    """
    显示确认卡片，等待用户在终端或网页面板作答。

    :param card: 卡片文本
    :param timeout_sec: 等待秒数
    :return: "yes"、"no" 或 "timeout"
    """
    with _confirm_lock:
        _drain()
        answers, stop = queue.Queue(), threading.Event()
        code = f"{secrets.randbelow(10 ** 6):06d}"
        _state["pending"] = {"id": secrets.token_hex(4), "card": card, "code": code, "queue": answers,
                             "wrong": 0, "deadline": time.time() + timeout_sec}
        threading.Thread(target=_forward_terminal, args=(answers, stop), daemon=True).start()
        try:
            log(card)
            log(f"输入 y 回车确认执行，输入其他内容拒绝（{timeout_sec} 秒后自动拒绝）；也可以在网页面板用确认码确认")
            _show_code(code)
            try:
                decision, source = answers.get(timeout=timeout_sec)
            except queue.Empty:
                log("等待确认超时，按拒绝处理", "WARNING")
                return "timeout"
            log(f"用户确认结果: 来源={source}, 结论={decision}")
            return decision
        finally:
            stop.set()
            _state["pending"] = None
