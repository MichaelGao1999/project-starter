#!/usr/bin/env python3
"""
新建打包外挂 skill（AI 采访收敛后调用）。

用法:
    python new-pack.py --name <name> --trigger "词|变体" \\
        --sub-modes "1:review:审查代码:动作内容;;2:core:心智模型" [--no-confirm]
"""

import argparse
import sys
from typing import List, Tuple
from lib import workflow_dir_path, write_file, add_trigger_entry


INDEX_TEMPLATE = """# {name}

> 按需加载工作流。触发词：{trigger}

## 模式选择

| # | 模式 | 说明 |
|---|------|------|
{modes_table}

AI 根据上下文自动选择模式，或用户直接指定。模式文件见对应编号文档：
{mode_links}
{confirm_section}
"""

SUB_TEMPLATE = """# {name}/{mode}

> {description}

## 标准动作

{actions}

## 确认

执行上述动作前，先向用户说明将要做什么，等待确认：
- `y` → 执行
- `n` → 取消

## 参见

- [索引](_index.md)
"""

CORE_TEMPLATE = """# {name}/core

> **始终开启的心智模型。** 每轮响应自动激活。无需显式调用。停用时说 `stop {name}` 或 `normal mode`。

## 标准动作

{actions}
"""

CONFIRM = """
## 确认

执行上述动作前，先向用户说明将要做什么，等待确认：
- `y` → 执行
- `n` → 取消
"""


def parse_modes(raw: str) -> List[Tuple[str, str, str, str]]:
    """解析 '1:review:说明:动作;;2:core:心智模型'"""
    modes = []
    for part in raw.split(";;"):
        part = part.strip()
        if not part:
            continue
        segs = part.split(":", 3)
        num = segs[0].strip() if len(segs) >= 1 else ""
        name = segs[1].strip() if len(segs) >= 2 else ""
        desc = segs[2].strip() if len(segs) >= 3 else ""
        action = segs[3].strip() if len(segs) >= 4 else ""
        if num and name:
            modes.append((num, name, desc, action))
    return modes


def main():
    parser = argparse.ArgumentParser(description="新建打包外挂 skill")
    parser.add_argument("--name", required=True)
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--sub-modes", required=True,
                        help="'1:review:说明:动作;;2:core:心智模型'")
    parser.add_argument("--no-confirm", action="store_true")
    args = parser.parse_args()

    modes = parse_modes(args.sub_modes)
    if not modes:
        print("错误: 未解析到有效的子模式", file=sys.stderr)
        sys.exit(1)

    wf_dir = workflow_dir_path(args.name)
    wf_dir.mkdir(parents=True, exist_ok=True)

    # _index.md
    mode_rows = []
    mode_links = []
    for num, mode_name, desc, _ in modes:
        mode_rows.append(f"| {num} | **{mode_name}** | {desc} |")
        mode_links.append(f"- [{num}. {mode_name}]({int(num):02d}-{mode_name}.md)")

    confirm = "" if args.no_confirm else CONFIRM
    index_content = INDEX_TEMPLATE.format(
        name=args.name, trigger=args.trigger,
        modes_table="\n".join(mode_rows),
        mode_links="\n".join(mode_links),
        confirm_section=confirm,
    )
    write_file(wf_dir / "_index.md", index_content)
    print(f"✓ 创建 _index.md")

    # 子模式文件
    for num, mode_name, desc, actions in modes:
        is_core = mode_name.lower() == "core"
        atext = actions if actions else f"详见 {args.name} 文档。"

        if is_core:
            content = CORE_TEMPLATE.format(name=args.name, mode=mode_name, actions=atext)
        else:
            content = SUB_TEMPLATE.format(
                name=args.name, mode=mode_name,
                description=desc or f"{args.name} 的 {mode_name} 模式",
                actions=atext,
            )

        filename = f"{int(num):02d}-{mode_name}.md"
        write_file(wf_dir / filename, content)
        print(f"✓ 创建 {filename}")

    doc_path = f"docs/workflows/{args.name}/_index.md"
    added = add_trigger_entry(args.trigger, doc_path)
    if added:
        print(f"✓ 添加 AGENTS.md 触发条目")
    else:
        print(f"  AGENTS.md 触发条目已存在，跳过")

    print(f"\n完成。触发词 `{args.trigger}` → `{doc_path}`，{len(modes)} 个子模式")


if __name__ == "__main__":
    main()
