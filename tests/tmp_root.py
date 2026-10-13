"""测试共用的临时根目录：一次运行的所有临时文件都放在这里，进程退出时整体删除。"""

import atexit
import tempfile
from pathlib import Path

_ROOT = tempfile.TemporaryDirectory(prefix="test_tmp_", dir=Path(__file__).resolve().parent.parent)
atexit.register(_ROOT.cleanup)
ROOT = Path(_ROOT.name)


def temp_dir(testcase):
    """
    在根目录下建一个临时目录，测试结束时自动删除。

    :param testcase: unittest.TestCase 实例
    :return: Path
    """
    tmp = tempfile.TemporaryDirectory(dir=ROOT)
    testcase.addCleanup(tmp.cleanup)
    return Path(tmp.name)
