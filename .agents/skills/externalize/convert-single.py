#!/usr/bin/env python3
"""
转化单模式 skill 为外部化 workflow。
从 SKILL.md 解析动作步骤，自动提取触发词（可用 --trigger 覆盖）。

用法:
    python convert-single.py <name>
    python convert-single.py <name> --trigger "词|变体" [--no-confirm]
"""

import argparse
import sys
from lib import (
    read_skill_text, parse_frontmatter, extract_trigger_words,
    extract_body, extract_action_section,
    workflow_path, write_file, archive_skill, add_trigger_entry,
)


WORKFLOW_TEMPLATE = """# {name}

> 按需加载工作流。触发词：{trigger}

{actions}
{confirm_section}
"""

CONFIRM = """
## 确认

执行上述动作前，先向用户说明将要做什么，等待确认：
- `y` → 执行
- `n` → 取消
"""


def main():
    parser = argparse.ArgumentParser(description="转化单模式 skill 为外部化 workflow")
    parser.add_argument("name", help="skill 名称")
    parser.add_argument("--trigger", help="触发词（支持 | 分隔变体）。不传则从 SKILL.md 描述自动提取")
    parser.add_argument("--no-confirm", action="store_true", help="跳过确认章节")
    args = parser.parse_args()

    name = args.name

    try:
        text = read_skill_text(name)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    # 自动提取触发词
    if args.trigger:
        trigger_str = args.trigger
    else:
        meta = parse_frontmatter(text)
        desc = meta.get("description", "") or meta.get("description_zh", "")
        words = extract_trigger_words(desc)
        if words:
            trigger_str = "|".join(words)
        else:
            trigger_str = name
            print(f"  未从描述提取到触发词，使用 skill 名: {name}")

    print(f"  触发词: {trigger_str}")

    body = extract_body(text)
    actions = extract_action_section(body)

    confirm = "" if args.no_confirm else CONFIRM
    content = WORKFLOW_TEMPLATE.format(
        name=name, trigger=trigger_str,
        actions=actions, confirm_section=confirm,
    )

    wf_path = workflow_path(name)
    write_file(wf_path, content)
    print(f"✓ 创建 workflow: {wf_path}")

    doc_path = f"docs/workflows/{name}.md"
    added = add_trigger_entry(trigger_str, doc_path)
    if added:
        print(f"✓ 添加 AGENTS.md 触发条目")
    else:
        print(f"  AGENTS.md 触发条目已存在，跳过")

    try:
        archive_skill(name)
        print(f"✓ 归档原 skill")
    except FileNotFoundError as e:
        print(f"  {e}，跳过归档")

    print(f"\n完成。触发词 `{trigger_str}` → `{doc_path}`")


if __name__ == "__main__":
    main()
