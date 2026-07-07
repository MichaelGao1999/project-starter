#!/usr/bin/env python3
"""
starter 安全安装向导。

用法：
    python install.py

功能：
- 检查关键文件是否齐全
- 提示修复方法（如有冲突）

运行时机：将 starter/ 复制到本项目后执行。
"""

import io
import sys
from pathlib import Path


# Windows 终端 UTF-8 支持
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception:
        pass


def ensure_files() -> bool:
    """检查并补全关键文件。"""
    required = {
        "config/github-sync.json": "母库同步配置",
        "status.md": "状态看板",
        "session-log.md": "会话记录",
        "docs/workflows/agent-coding-workflow.md": "五阶段 workflow",
        "docs/workflows/anti-patterns-checklist.md": "反模式检查清单",
    }

    all_ok = True
    for path, desc in required.items():
        if Path(path).exists():
            print(f"✅ {desc}: {path}")
        else:
            print(f"❌ {desc} 缺失: {path}")
            all_ok = False

    return all_ok


def main() -> int:
    print("=" * 50)
    print("starter 安全安装向导")
    print("=" * 50)
    print()

    files_ok = ensure_files()
    print()

    if files_ok:
        print("=" * 50)
        print("✅ 安装检查通过")
        print("=" * 50)
        return 0
    else:
        print("=" * 50)
        print("⚠️  安装检查未通过，请按上方提示修复")
        print("=" * 50)
        return 1


if __name__ == "__main__":
    sys.exit(main())
