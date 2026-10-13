"""演示模式用的模拟麦当劳 MCP：不连官方服务、不需要 Token，门店、餐品、价格全部是虚构数据。

只实现体验护栏需要的几个工具。写操作不会产生任何真实订单。
"""

import json

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
    "storeCode": {"type": "string", "description": "门店编码，从 query-nearby-stores 获取"},
    "orderType": {"type": "integer", "enum": [1, 2], "description": "1-到店，2-外送"},
    "beType": {"type": "integer", "enum": [1, 2, 5, 6], "description": "1-到店取餐"},
    "items": {
        "type": "array",
        "description": "餐品列表",
        "items": {"type": "object", "required": ["productCode", "quantity"], "properties": {
            "productCode": {"type": "string", "description": "餐品编码，即 query-meals 返回的 code，如 D01"},
            "quantity": {"type": "integer", "description": "数量"},
        }},
    },
}
_REQUIRED = ["storeCode", "orderType", "beType"]
_STORE_ARGS = {"type": "object", "properties": {k: _ORDER_PROPS[k] for k in _REQUIRED}, "required": _REQUIRED}

DEMO_TOOLS = [
    {"name": "now-time-info", "description": "获取当前时间（演示）", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "query-nearby-stores", "description": "查询附近门店（演示）",
     "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}}},
    {"name": "query-meals", "description": "查询门店餐品菜单（演示）", "inputSchema": _STORE_ARGS},
    {"name": "query-my-coupons", "description": "查询我的优惠券（演示）", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "calculate-price", "description": "订单试算价格（演示）",
     "inputSchema": {"type": "object", "properties": _ORDER_PROPS, "required": [*_REQUIRED, "items"]}},
    {"name": "create-order", "description": "创建订单（演示，不会产生真实订单）。下单前需征得用户同意",
     "inputSchema": {"type": "object", "properties": {**_ORDER_PROPS, "takeWayCode": {"type": "string"}},
                     "required": [*_REQUIRED, "items"]}},
    {"name": "auto-bind-coupons", "description": "一键领取全部可领优惠券（演示）",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "draw-lottery", "description": "积分抽奖（演示）", "inputSchema": {"type": "object", "properties": {}}},
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
        return _result({"tip": "演示模式，时间以本机为准"})
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
