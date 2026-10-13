"""通用工具函数。"""

import os

from mcd_guard.config import ENV_FILE
from mcd_guard.logger import log


def read_env_file(path=ENV_FILE):
    """
    读取 .env 文件中的 KEY=VALUE 配置。

    :param path: .env 文件路径
    :return: dict，文件不存在时返回空 dict
    """
    if not path.exists():
        log(f"未找到 .env 文件: 路径={path}", "WARNING")
        return {}
    values = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def get_secret(name):
    """
    读取密钥：优先环境变量，其次 .env 文件。

    :param name: 变量名，如 MCD_MCP_TOKEN
    :return: 密钥字符串
    """
    value = os.environ.get(name) or read_env_file().get(name)
    if not value:
        raise RuntimeError(f"缺少密钥: 变量名={name}，请设置环境变量或写入项目根目录的 .env")
    return value


def mask(secret):
    """
    打码显示密钥，只保留首尾各 4 位。

    :param secret: 密钥字符串
    :return: 打码后的字符串
    """
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}***{secret[-4:]}"
