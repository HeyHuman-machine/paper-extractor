"""M0 环境验证脚本。

运行该文件可以确认项目使用的是 Python 3.11，而不是电脑上其他版本的
Python。这个脚本不包含任何论文抽取业务逻辑。
"""

import platform
import sys


def main() -> int:
    """打印环境信息，并在 Python 版本不正确时返回非零状态码。"""

    current_version = sys.version_info[:2]
    required_version = (3, 11)

    if current_version != required_version:
        print(
            "环境检查失败：项目要求 Python 3.11，"
            f"当前是 Python {platform.python_version()}。"
        )
        return 1

    print("PaperExtractor 环境准备完成")
    print(f"Python version: {platform.python_version()}")
    print(f"Platform: {platform.system()} {platform.release()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

