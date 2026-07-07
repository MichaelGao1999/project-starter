#!/usr/bin/env python3
"""
转化打包 skill 为外部化目录结构。
解析 SKILL.md，按子模式拆分为 _index.md + 独立子文件。

用法:
    python convert-pack.py <name> --sub-modes "1:模式1:说明;;2:模式2:说明" [--no-confirm]
    python convert-pack.py <name> --auto-detect
"""

import argparse
import re
import sys
from typing import List, Tuple

from lib import (
    read_skill_text, parse_frontmatter, extract_trigger_words,
    workflow_dir_path, write_file, archive_skill, add_trigger_entry,
    get_sections,
)


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


def parse_sub_modes(raw: str) -> List[Tuple[str, str, str]]:
    """解析 '1:review:审查代码;;2:audit:全仓库扫描' 格式"""
    modes = []
    for part in raw.split(";;"):
        part = part.strip()
        if not part:
            continue
        segments = part.split(":", 2)
        num = segments[0].strip() if len(segments) >= 1 else ""
        name = segments[1].strip() if len(segments) >= 2 else ""
        desc = segments[2].strip() if len(segments) >= 3 else ""
        if num and name:
            modes.append((num, name, desc))
    return modes


def auto_detect_modes(text: str) -> List[Tuple[str, str, str]]:
    """从 SKILL.md 自动检测子模式（基于 H2 章节）"""
    skip_keywords = ["触发", "trigger", "使用方式", "方法论",
                     "注意事项", "边界", "boundaries", "输出格式", "format"]
    modes = []
    for i, section in enumerate(get_sections(text), 1):
        if any(kw in section.lower() for kw in skip_keywords):
            continue
        modes.append((str(i), section.strip(), ""))
    return modes


def main():
    parser = argparse.ArgumentParser(description="转化打包 skill 为目录结构")
    parser.add_argument("name", help="skill 名称")
    parser.add_argument("--trigger", help="触发词（支持 | 分隔变体）。不传则从 SKILL.md 描述自动提取")
    parser.add_argument("--sub-modes", help="子模式列表 '1:review:说明;;2:audit:说明'")
    parser.add_argument("--auto-detect", action="store_true", help="从 SKILL.md 自动检测")
    parser.add_argument("--no-confirm", action="store_true", help="跳过确认章节")
    args = parser.parse_args()

    name = args.name

    # 读取 skill
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

    # 确定子模式
    if args.sub_modes:
        modes = parse_sub_modes(args.sub_modes)
    elif args.auto_detect:
        modes = auto_detect_modes(text)
    else:
        print("错误: 需要 --sub-modes 或 --auto-detect", file=sys.stderr)
        sys.exit(1)

    if not modes:
        print("错误: 未检测到子模式", file=sys.stderr)
        sys.exit(1)

    # 创建目录
    wf_dir = workflow_dir_path(name)
    wf_dir.mkdir(parents=True, exist_ok=True)

    # _index.md
    mode_rows = []
    mode_links = []
    for num, mode_name, desc in modes:
        mode_rows.append(f"| {num} | **{mode_name}** | {desc} |")
        mode_links.append(f"- [{num}. {mode_name}]({int(num):02d}-{mode_name}.md)")

    confirm = "" if args.no_confirm else CONFIRM
    index_content = INDEX_TEMPLATE.format(
        name=name, trigger=trigger_str,
        modes_table="\n".join(mode_rows),
        mode_links="\n".join(mode_links),
        confirm_section=confirm,
    )
    write_file(wf_dir / "_index.md", index_content)
    print(f"✓ 创建 _index.md")

    # 子模式文件
    for num, mode_name, desc in modes:
        is_core = mode_name.lower() == "core"
        actions = "详见原始 SKILL.md。"
        if args.auto_detect:
            pattern = re.compile(
                rf"^##\s+{re.escape(mode_name)}\s*$(.+?)(?=^##\s|\Z)",
                re.MULTILINE | re.DOTALL
            )
            m = pattern.search(text)
            if m:
                actions = f"```\n{m.group(1).strip()}\n```"

        if is_core:
            content = CORE_TEMPLATE.format(name=name, mode=mode_name, actions=actions)
        else:
            content = SUB_TEMPLATE.format(
                name=name, mode=mode_name,
                description=desc or f"{name} 的 {mode_name} 模式",
                actions=actions,
            )

        filename = f"{int(num):02d}-{mode_name}.md"
        write_file(wf_dir / filename, content)
        print(f"✓ 创建 {filename}")

    # AGENTS.md 条目
    doc_path = f"docs/workflows/{name}/_index.md"
    added = add_trigger_entry(trigger_str, doc_path)
    if added:
        print(f"✓ 添加 AGENTS.md 触发条目")
    else:
        print(f"  AGENTS.md 触发条目已存在，跳过")

    # 归档
    try:
        archive_skill(name)
        print(f"✓ 归档原 skill")
    except FileNotFoundError as e:
        print(f"  {e}，跳过归档")

    print(f"\n完成。触发词 `{trigger_str}` → `{doc_path}`，{len(modes)} 个子模式")


if __name__ == "__main__":
    main()
