#!/usr/bin/env python3
"""
移除已外部化的 skill。
检测单文件或目录结构，分别处理。交互式处理归档备份。

用法:
    python remove.py <name>
"""

import shutil
import sys
from lib import (
    workflow_path, workflow_dir_path, archived_dir,
    remove_trigger_entry,
)


def prompt_archive(name: str) -> bool:
    """交互式处理归档。返回 True=已处理, False=保留"""
    ap = archived_dir(name)
    if not ap.exists():
        return True

    print(f"\n归档备份 {ap}/ 还在。")
    print(f"  y → 一并删除（不可恢复）")
    print(f"  n → 保留归档")

    try:
        answer = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer == "y":
        try:
            shutil.rmtree(str(ap))
            print(f"✓ 已删除归档: {ap}")
        except OSError as e:
            print(f"⚠️ 删除归档失败: {e}")
    elif answer == "n":
        print(f"  保留归档: {ap}")
    else:
        print(f"  输入 '{answer}' 未识别，保留归档。")
    return True


def main():
    if len(sys.argv) < 2:
        print("用法: python remove.py <name>", file=sys.stderr)
        sys.exit(1)

    name = sys.argv[1]

    # 检测单文件/目录
    wf_file = workflow_path(name)
    wf_dir = workflow_dir_path(name)

    if wf_file.exists() and wf_dir.exists():
        print(f"错误: {name} 同时有单文件和目录，无法安全移除", file=sys.stderr)
        sys.exit(1)
    if not wf_file.exists() and not wf_dir.exists():
        print(f"错误: 未找到 {name} 的 workflow 文件或目录", file=sys.stderr)
        sys.exit(1)

    # 删除 workflow
    if wf_file.exists():
        try:
            wf_file.unlink()
            print(f"✓ 删除 workflow 文件: {wf_file}")
        except OSError as e:
            print(f"⚠️ 删除 workflow 文件失败: {e}")
    elif wf_dir.exists():
        try:
            shutil.rmtree(str(wf_dir))
            print(f"✓ 删除 workflow 目录: {wf_dir}")
        except OSError as e:
            print(f"⚠️ 删除 workflow 目录失败: {e}")

    # AGENTS.md 条目
    found = remove_trigger_entry(name)
    if found:
        print(f"✓ 删除 AGENTS.md 触发条目")
    else:
        print(f"  AGENTS.md 中未找到 {name} 的触发条目")

    # 归档
    prompt_archive(name)

    print(f"\n完成。已移除 {name} 的外部化。")


if __name__ == "__main__":
    main()
