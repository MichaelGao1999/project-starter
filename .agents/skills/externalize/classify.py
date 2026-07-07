#!/usr/bin/env python3
"""
技能类型诊断。读取 SKILL.md，输出类型 + 建议方案。
供 AI 使用：基于输出与用户确认外部化策略。

用法:
    python classify.py <name>
"""

import sys
from lib import read_skill_text, diagnose_type, format_diagnosis, get_sections


def main():
    if len(sys.argv) < 2:
        print("用法: python classify.py <skill-name>", file=sys.stderr)
        sys.exit(1)

    name = sys.argv[1]
    try:
        text = read_skill_text(name)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    skill_type = diagnose_type(text)
    sections = get_sections(text)
    print(format_diagnosis(name, skill_type, sections))


if __name__ == "__main__":
    main()
