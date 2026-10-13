"""护栏核心：判断每次工具调用是放行、拦截，还是交给用户在本机确认。

handle_call 的依赖都通过 ctx 传入，便于测试：
    ctx = {
        "policy": 策略 dict,
        "upstream": fn(name, arguments) -> 上游原始 result,
        "confirm": fn(card_text, timeout_sec) -> "yes" / "no" / "timeout",
        "spent": fn() -> (当天已花分, 本周已花分),
        "audit": fn(record) -> None,
        "calc_props": calculate-price 支持的参数名集合,
    }
"""

import json

from audit import redact
from config import READ_ONLY_TOOLS, WRITE_TOOL_NAMES
from logger import log
from mcp_client import parse_tool_result

BE_TYPE_NAMES = {1: "到店自取", 2: "麦乐送", 5: "得来速", 6: "企业团餐"}
GUARD_TAG = "【麦麦护栏】"


def is_write_tool(name):
    """
    判断工具是否为写操作；不在只读名单里的一律按写操作处理。

    :param name: 工具名
    :return: bool
    """
    return name not in READ_ONLY_TOOLS


def tool_label(name):
    """
    工具的中文名，未知工具返回原名。

    :param name: 工具名
    :return: str
    """
    return WRITE_TOOL_NAMES.get(name, name)


def text_result(text, is_error=True):
    """
    组装返回给 AI 的 MCP 文本结果。

    :param text: 文本内容
    :param is_error: 是否标记为出错
    :return: MCP result dict
    """
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def yuan(fen):
    """
    分转成“¥12.30”形式的字符串。

    :param fen: 金额，单位分
    :return: str
    """
    return f"¥{fen / 100:.2f}"


def quote_order(arguments, upstream, calc_props):
    """
    用官方 calculate-price 试算 create-order 的应付金额。

    :param arguments: create-order 的参数
    :param upstream: 上游调用函数
    :param calc_props: calculate-price 支持的参数名集合
    :return: (试算 data dict 或 None, 试算原始业务数据)
    """
    calc_args = {k: v for k, v in arguments.items() if k in calc_props}
    result = upstream("calculate-price", calc_args)
    body = parse_tool_result(result)
    data = body.get("data") if isinstance(body, dict) else None
    if result.get("isError") or not isinstance(data, dict) or not isinstance(data.get("price"), int):
        log(f"订单试算失败: 返回={json.dumps(body, ensure_ascii=False)[:300]}", "WARNING")
        return None, body
    log(f"订单试算: 应付分={data['price']}")
    return data, body


def check_limits(price_fen, policy, spent):
    """
    检查订单金额是否超过单笔、当天、本周上限。

    :param price_fen: 本单应付，单位分
    :param policy: 策略 dict
    :param spent: (当天已花分, 本周已花分)
    :return: 超限原因字符串；未超限返回 None
    """
    daily, weekly = spent
    checks = (
        (price_fen, policy["max_order_yuan"], "单笔上限"),
        (daily + price_fen, policy["max_daily_yuan"], "当天累计上限"),
        (weekly + price_fen, policy["max_weekly_yuan"], "本周累计上限"),
    )
    for amount, limit_yuan, label in checks:
        if amount > round(limit_yuan * 100):
            return f"本单应付 {yuan(price_fen)}，计入后为 {yuan(amount)}，超过{label} {yuan(round(limit_yuan * 100))}"
    return None


def describe_items(arguments, quote):
    """
    列出订单里的餐品；试算结果里有餐品名就用名字，否则用编码。

    :param arguments: create-order 参数
    :param quote: 试算 data
    :return: list[str]
    """
    lines = []
    for item in (quote or {}).get("productList") or []:
        name = item.get("productName") or item.get("name") or item.get("productCode") or "未知餐品"
        lines.append(f"{name} x{item.get('quantity', '?')}")
    if lines:
        return lines
    for item in arguments.get("items") or []:
        lines.append(f"{item.get('productCode', '未知编码')} x{item.get('quantity', '?')}")
    return lines


def build_card(name, arguments, policy, quote=None, spent=None):
    """
    生成给用户看的确认卡片。

    :param name: 工具名
    :param arguments: 工具参数
    :param policy: 策略 dict
    :param quote: create-order 的试算 data
    :param spent: (当天已花分, 本周已花分)
    :return: 卡片文本
    """
    lines = ["", "=" * 46, f"  {GUARD_TAG}AI 请求执行写操作", "=" * 46, f"  操作：{tool_label(name)}（{name}）"]
    if name == "create-order" and quote is not None:
        be_type = BE_TYPE_NAMES.get(arguments.get("beType"), arguments.get("beType"))
        lines.append(f"  门店：{arguments.get('storeCode')}    方式：{be_type}")
        if arguments.get("reservationDate"):
            lines.append(f"  预约：{arguments['reservationDate']}")
        lines.append("  餐品：")
        lines += [f"    - {line}" for line in describe_items(arguments, quote)]
        lines.append(f"  应付：{yuan(quote['price'])}（下单前试算）")
        if spent is not None:
            lines.append(f"  今日已确认：{yuan(spent[0])} / 上限 {yuan(round(policy['max_daily_yuan'] * 100))}")
    else:
        lines.append(f"  参数：{json.dumps(arguments, ensure_ascii=False)}")
    lines.append("-" * 46)
    return "\n".join(lines)


def _upstream_ok(result):
    """上游结果是否表示成功：没有 isError，且业务 success 不为 False。"""
    if result.get("isError"):
        return False
    body = parse_tool_result(result)
    return not (isinstance(body, dict) and body.get("success") is False)


def handle_call(name, arguments, ctx):
    """
    处理一次工具调用。

    :param name: 工具名
    :param arguments: 工具参数
    :param ctx: 依赖集合，见模块说明
    :return: 返回给 AI 的 MCP result dict
    """
    policy, arguments = ctx["policy"], arguments or {}
    record = {"tool": name, "arguments": redact(arguments)}

    def finish(decision, result, **extra):
        ctx["audit"]({**record, "decision": decision, **extra})
        log(f"处理调用: 工具={name}, 结论={decision}")
        return result

    if name in policy["blocked_tools"]:
        return finish("blocked", text_result(
            f"{GUARD_TAG}已拦截：用户在护栏策略中禁用了「{tool_label(name)}」，没有执行任何操作。不要重试，请告诉用户。"),
            reason="blocked_tools")

    if not is_write_tool(name):
        result = ctx["upstream"](name, arguments)
        return finish("allowed", result, upstream_ok=_upstream_ok(result))

    if policy["mode"] == "readonly":
        return finish("blocked", text_result(
            f"{GUARD_TAG}已拦截：当前是只读模式，不允许「{tool_label(name)}」，没有执行任何操作。"
            "不要重试；如确需执行，请用户把护栏策略的 mode 改为 confirm。"), reason="readonly")

    quote, spent = None, None
    if name == "create-order":
        quote, body = quote_order(arguments, ctx["upstream"], ctx["calc_props"])
        if quote is None:
            return finish("blocked", text_result(
                f"{GUARD_TAG}已拦截：无法用官方试算核实这笔订单的金额，为安全起见没有下单。"
                f"请先检查参数并用 calculate-price 试算。试算返回：{json.dumps(body, ensure_ascii=False)[:300]}"),
                reason="quote_failed")
        record["price_fen"] = quote["price"]
        spent = ctx["spent"]()
        over = check_limits(quote["price"], policy, spent)
        if over:
            return finish("blocked", text_result(
                f"{GUARD_TAG}已拦截：{over}，没有下单。不要重试或拆单绕过，请告诉用户；如需调整上限，请用户修改护栏策略。"),
                reason="limit")

    timeout = policy["confirm_timeout_sec"]
    answer = ctx["confirm"](build_card(name, arguments, policy, quote, spent), timeout)
    if answer == "no":
        return finish("rejected", text_result(
            f"{GUARD_TAG}用户在护栏终端拒绝了「{tool_label(name)}」，没有执行任何操作。不要重试，请直接询问用户下一步怎么做。"))
    if answer != "yes":
        return finish("timeout", text_result(
            f"{GUARD_TAG}用户在 {timeout} 秒内没有确认「{tool_label(name)}」，已按拒绝处理，没有执行任何操作。"
            "请提醒用户到运行麦麦护栏的终端窗口确认后再试。"))

    try:
        result = ctx["upstream"](name, arguments)
    except RuntimeError as e:
        return finish("confirmed", text_result(
            f"{GUARD_TAG}用户已确认，但转发「{tool_label(name)}」时出错，操作结果未知：{e}。"
            "不要直接重试，先用 order-list / query-order 等查询工具确认是否已经生效，再告诉用户。"),
            upstream_ok=None, error=str(e))
    return finish("confirmed", result, upstream_ok=_upstream_ok(result))
