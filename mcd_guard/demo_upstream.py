"""演示模式用的模拟麦当劳 MCP：不连官方服务、不需要 Token，门店、餐品、价格全部是虚构数据。

只实现体验护栏需要的几个工具。写操作不会产生任何真实订单。
"""

import json
from datetime import datetime

DEMO_STORE = {"storeCode": "DEMO001", "storeName": "演示餐厅（虚构）", "address": "演示路 1 号", "beType": 1}

# 虚构餐品：编码 -> (名称, 单价分)，价格只用于演示
DEMO_MEALS = {
    "D01": ("巨无霸（演示）", 2500),
    "D02": ("麦辣鸡腿汉堡（演示）", 2300),
    "D03": ("麦乐鸡 5 块（演示）", 1300),
    "D04": ("中薯条（演示）", 1200),
    "D05": ("中杯可乐（演示）", 1000),
    "D06": ("麦辣鸡腿汉堡套餐（演示）", 3800),
}

_ORDER_PROPS = {
    "storeCode": {"type": "string", "description": "门店编码，取自 query-nearby-stores 返回的 storeCode；演示里只有 DEMO001"},
    "orderType": {"type": "integer", "enum": [1, 2], "description": "订单类型：1 到店，2 外送。演示门店只支持 1"},
    "beType": {"type": "integer", "enum": [1, 2, 5, 6], "description": "业务类型，取自 query-nearby-stores 返回的 beType；演示门店为 1（到店取餐）"},
    "items": {
        "type": "array",
        "description": "要点的餐品，每项一个餐品编码和数量，至少一项",
        "items": {"type": "object", "required": ["productCode", "quantity"], "properties": {
            "productCode": {"type": "string", "description": "餐品编码，即 query-meals 返回的 code，如 D01"},
            "quantity": {"type": "integer", "minimum": 1, "description": "份数，正整数"},
        }},
    },
}
_REQUIRED = ["storeCode", "orderType", "beType"]
_STORE_ARGS = {"type": "object", "properties": {k: _ORDER_PROPS[k] for k in _REQUIRED}, "required": _REQUIRED}
_NO_ARGS = {"type": "object", "properties": {}}
_DEMO_NOTE = "演示数据，虚构，不连麦当劳官方服务。"

DEMO_TOOLS = [
    {"name": "now-time-info",
     "description": f"返回当前日期和时间（ISO 格式）。用于判断门店营业时间、优惠券是否在有效期内。只读，无参数。{_DEMO_NOTE}",
     "inputSchema": _NO_ARGS},
    {"name": "query-nearby-stores",
     "description": f"按关键词查附近门店，返回门店列表（storeCode、门店名、地址、beType）。点餐流程第一步：后续查菜单、试算、下单都要用这里的 storeCode 和 beType。只读。{_DEMO_NOTE}",
     "inputSchema": {"type": "object", "properties": {
         "keyword": {"type": "string", "description": "地点或门店关键词，如“人民广场”；可省略，省略时返回默认门店"}}}},
    {"name": "query-meals",
     "description": f"查询指定门店的菜单，返回餐品列表（code、名称、单价，单位元）。下单和试算时 items 里的 productCode 就是这里的 code。只读。{_DEMO_NOTE}",
     "inputSchema": _STORE_ARGS},
    {"name": "query-my-coupons",
     "description": f"列出当前账号已领取、可使用的优惠券名称。只读，不会领取新券；要领券用 auto-bind-coupons。无参数。{_DEMO_NOTE}",
     "inputSchema": _NO_ARGS},
    {"name": "calculate-price",
     "description": f"按门店和餐品试算订单应付金额，返回总价（单位分）和餐品明细。只算价、不下单，可放心调用；用户问“多少钱”时用它，不要用 create-order。只读。{_DEMO_NOTE}",
     "inputSchema": {"type": "object", "properties": _ORDER_PROPS, "required": [*_REQUIRED, "items"]}},
    {"name": "create-order",
     "description": f"创建订单（写操作）。只有在用户明确说要下单、并确认过门店、餐品和金额后才调用；建议先用 calculate-price 给用户报价。返回订单号。演示模式不会产生真实订单。{_DEMO_NOTE}",
     "inputSchema": {"type": "object", "properties": {**_ORDER_PROPS, "takeWayCode": {
         "type": "string", "description": "取餐方式编码，可省略"}}, "required": [*_REQUIRED, "items"]}},
    {"name": "auto-bind-coupons",
     "description": f"一键领取当前账号所有可领的优惠券（写操作，会改动账户）。用户明确要求领券时才调用。无参数，返回领取结果。{_DEMO_NOTE}",
     "inputSchema": _NO_ARGS},
    {"name": "draw-lottery",
     "description": f"消耗积分进行一次抽奖（写操作，会扣积分）。用户明确要求抽奖时才调用。无参数，返回抽奖结果。{_DEMO_NOTE}",
     "inputSchema": _NO_ARGS},
]


def _result(data):
    """包装成和官方类似的工具返回：success + data。"""
    body = {"success": True, "code": 200, "message": "演示数据", "data": data}
    return {"content": [{"type": "text", "text": json.dumps(body, ensure_ascii=False)}], "structuredContent": body}


def _error(message):
    """包装业务错误。"""
    body = {"success": False, "message": message}
    return {"content": [{"type": "text", "text": json.dumps(body, ensure_ascii=False)}], "isError": True}


def _quote(arguments):
    """按虚构单价算出应付金额；有未知餐品时返回 None。"""
    total, product_list = 0, []
    for item in arguments.get("items") or []:
        meal = DEMO_MEALS.get(str(item.get("productCode")))
        quantity = item.get("quantity", 1)
        if meal is None or not isinstance(quantity, int) or quantity < 1:
            return None
        total += meal[1] * quantity
        product_list.append({"productName": meal[0], "quantity": quantity})
    return {"price": total, "productList": product_list} if product_list else None


def demo_call(name, arguments):
    """
    模拟官方 MCP 的工具调用。

    :param name: 工具名
    :param arguments: 参数 dict
    :return: MCP tools/call 的 result dict
    """
    arguments = arguments or {}
    if name == "now-time-info":
        return _result({"now": datetime.now().isoformat(timespec="seconds")})
    if name == "query-nearby-stores":
        return _result({"stores": [DEMO_STORE]})
    if name == "query-meals":
        return _result({"meals": [{"code": c, "name": n, "price": f"{p / 100:.2f}"} for c, (n, p) in DEMO_MEALS.items()]})
    if name == "query-my-coupons":
        return _result({"coupons": [{"name": "薯条第二份半价（演示）"}]})
    if name in ("calculate-price", "create-order"):
        quote = _quote(arguments)
        if quote is None:
            return _error("餐品编码不存在或数量不对：items 每项要有 productCode（D01~D06）和 quantity")
        if name == "calculate-price":
            return _result(quote)
        return _result({**quote, "orderId": "DEMO-ORDER", "tip": "演示订单，没有发给麦当劳，也不需要支付"})
    if name == "auto-bind-coupons":
        return _result({"bound": 1, "tip": "演示领券，没有真实领取"})
    if name == "draw-lottery":
        return _result({"prize": "谢谢参与（演示）"})
    return _error(f"演示模式不支持这个工具: {name}")
