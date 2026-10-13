"""连接麦当劳 MCP，保存全部工具的 schema，并调用一个只读工具做冒烟测试。"""

import json

from config import DATA_DIR, MCP_TOKEN_ENV, MCP_URL
from logger import log
from mcp_client import call_tool, close_session, list_tools, open_session
from utils import get_secret, mask


def save_tools(tools, path):
    """
    把工具 schema 按名称排序后保存为 JSON。

    :param tools: list_tools 的返回值
    :param path: 保存路径
    :return: None
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tools = sorted(tools, key=lambda t: t["name"])
    path.write_text(json.dumps(tools, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"保存工具 schema: 路径={path}, 数量={len(tools)}")


def main(url, tools_path, smoke_tool):
    """
    探测 MCP 服务。

    :param url: MCP 服务地址
    :param tools_path: 工具 schema 保存路径
    :param smoke_tool: 用于冒烟测试的只读工具名
    :return: None
    """
    token = get_secret(MCP_TOKEN_ENV)
    log(f"开始探测 MCP: 地址={url}, Token={mask(token)}")
    session = open_session(url, token)
    try:
        tools = list_tools(session)
        save_tools(tools, tools_path)
        log(f"工具名: {', '.join(t['name'] for t in sorted(tools, key=lambda t: t['name']))}")
        result = call_tool(session, smoke_tool)
        log(f"冒烟测试结果: 工具={smoke_tool}, 返回={json.dumps(result, ensure_ascii=False)[:300]}")
    finally:
        close_session(session)


if __name__ == "__main__":
    URL = MCP_URL  # MCP 服务地址
    TOOLS_PATH = DATA_DIR / "tools.json"  # 工具 schema 保存位置
    SMOKE_TOOL = "now-time-info"  # 冒烟测试用的只读工具，不涉及账户
    main(URL, TOOLS_PATH, SMOKE_TOOL)
