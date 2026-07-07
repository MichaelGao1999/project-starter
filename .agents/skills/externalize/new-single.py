#!/usr/bin/env python3
"""
新建单模式外挂 skill（AI 采访收敛后调用）。

用法:
    python new-single.py --name <name> --trigger "词|变体" --actions "1. 步骤1;;2. 步骤2" [--desc "说明"] [--judgment "条件→动作;;条件2→动作2"] [--no-confirm]
"""

import argparse
import sys
from lib import workflow_path, write_file, add_trigger_entry


WORKFLOW_TEMPLATE = """# {name}

> 按需加载工作流。触发词：{trigger}

{actions}
{judgment_section}
{confirm_section}
"""

CONFIRM = """
## 确认

执行上述动作前，先向用户说明将要做什么，等待确认：
- `y` → 执行
- `n` → 取消
"""


def actions_to_md(raw: str) -> str:
    lines = raw.split(";;")
    return "\n".join(l.strip() for l in lines if l.strip())


def judgment_to_md(raw: str) -> str:
    """将 '条件→动作;;条件2→动作2' 转为判断逻辑章节"""
    lines = raw.split(";;")
    items = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        items.append(f"- {line}")
    if not items:
        return ""
    return "\n## 判断逻辑\n\n" + "\n".join(items) + "\n"


def main():
    parser = argparse.ArgumentParser(description="新建单模式外挂 skill")
    parser.add_argument("--name", required=True)
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--actions", required=True, help="动作列表，;; 分隔")
    parser.add_argument("--desc", help="简要说明")
    parser.add_argument("--judgment", help="判断逻辑 '条件→动作;;条件2→动作2'")
    parser.add_argument("--no-confirm", action="store_true")
    args = parser.parse_args()

    actions_text = actions_to_md(args.actions)
    if args.desc:
        actions_text = f"> {args.desc}\n\n{actions_text}"

    judgment_text = judgment_to_md(args.judgment) if args.judgment else ""

    confirm = "" if args.no_confirm else CONFIRM
    content = WORKFLOW_TEMPLATE.format(
        name=args.name, trigger=args.trigger,
        actions=actions_text, judgment_section=judgment_text,
        confirm_section=confirm,
    )

    wf_path = workflow_path(args.name)
    write_file(wf_path, content)
    print(f"✓ 创建 workflow: {wf_path}")

    doc_path = f"docs/workflows/{args.name}.md"
    added = add_trigger_entry(args.trigger, doc_path)
    if added:
        print(f"✓ 添加 AGENTS.md 触发条目")
    else:
        print(f"  AGENTS.md 触发条目已存在，跳过")

    print(f"\n完成。触发词 `{args.trigger}` → `{doc_path}`")


if __name__ == "__main__":
    main()
