#!/usr/bin/env python3
"""error-detector.py — 命令输出错误检测

在 Agent Coding 会话中使用，检测命令输出中的错误模式，提醒记录到 troubleshooting.md。

用法:
    1. 管道模式: some_command 2>&1 | python scripts/error-detector.py
    2. 参数模式: python scripts/error-detector.py "错误输出文本"
    3. 环境变量模式: ERROR_OUTPUT="错误输出文本" python scripts/error-detector.py

输出: 如检测到错误模式，输出 <error-detected> XML 标签到 stdout
"""

import os
import sys

ERROR_PATTERNS = [
    "error:",
    "Error:",
    "ERROR:",
    "failed",
    "FAILED",
    "command not found",
    "No such file",
    "Permission denied",
    "fatal:",
    "Exception",
    "Traceback",
    "npm ERR!",
    "ModuleNotFoundError",
    "SyntaxError",
    "TypeError",
    "exit code",
    "non-zero",
    "Segmentation fault",
    "core dumped",
    "Cannot find module",
    "ENOENT",
    "EACCES",
    "ETIMEDOUT",
    "0xc0000139",
    "0xc0000005",
    "Unexpected token",
]


def main() -> int:
    # 获取输入：参数 > 环境变量 > stdin
    if len(sys.argv) > 1:
        text = sys.argv[1]
    elif os.environ.get("ERROR_OUTPUT"):
        text = os.environ["ERROR_OUTPUT"]
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        text = ""

    if not text.strip():
        return 0

    # 大小写敏感匹配（与原 .sh 行为一致）
    for pattern in ERROR_PATTERNS:
        if pattern in text:
            print("""<error-detected>
检测到命令输出中包含错误模式。建议：
- 如为非预期的错误，记录到 troubleshooting.md（按模板：现象/原因/解决）
- 如为已知问题，确认 troubleshooting.md 中已有对应条目
- 存档时运行 `python scripts/build-experience-index.py` 重建索引
</error-detected>""")
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
