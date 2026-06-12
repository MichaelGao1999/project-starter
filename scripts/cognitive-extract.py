#!/usr/bin/env python3
"""
认知提取脚本 — 将存档时的认知收获保存到本地的 cognitive-log.md。

用法:
    python scripts/cognitive-extract.py --title "..." --body "..."
    python scripts/cognitive-extract.py --file <candidates.json>

后端（通过 --backend 或 COGNITIVE_EXTRACT_BACKEND 环境变量选择）:
    markdown  追加到 cognitive-log.md（零外部依赖，默认）
    none      仅 stdout 打印，不写入

返回: exit code 0=成功, 2=输入错误
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path


DEFAULT_BACKEND = "markdown"
BACKENDS = ("markdown", "none")

ENTRY_RE = re.compile(
    r"(?:^|\n\n)---\n\n"
    r"## (.+?)\n\n"
    r"- \*\*分类\*\*:\s*(.+?)\n"
    r"- \*\*时间\*\*:\s*(.+?)\n"
    r"(?:- \*\*标签\*\*:\s*(.+?)\n)?"
    r"\n(.+?)"
    r"(?=\n\n---\n\n## |\Z)",
    re.MULTILINE | re.DOTALL,
)


def log(msg: str) -> None:
    print(json.dumps({"level": "info", "message": msg}))


def error(msg: str) -> None:
    print(json.dumps({"level": "error", "message": msg}), file=sys.stderr)


def result(ok: bool, detail: str = "") -> None:
    print(json.dumps({"ok": ok, "detail": detail}))


def read_input(args: argparse.Namespace) -> list[dict]:
    if args.file:
        path = Path(args.file)
        if not path.exists():
            error(f"输入文件不存在: {args.file}")
            sys.exit(2)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return [data]
    if args.title and args.body:
        entry = {"title": args.title, "body": args.body}
        if args.category:
            entry["category"] = args.category
        if args.tags:
            entry["tags"] = args.tags
        if args.date:
            entry["date"] = args.date
        return [entry]
    error("请提供 --title + --body 或 --file")
    sys.exit(2)


def parse_entries(text: str) -> list[dict]:
    """Parse existing entries from cognitive-log.md."""
    entries = []
    for m in ENTRY_RE.finditer(text):
        entries.append({
            "title": m.group(1).strip(),
            "category": m.group(2).strip(),
            "date": m.group(3).strip(),
            "tags": (m.group(4) or "").strip(),
            "body": m.group(5).strip(),
        })
    return entries


def build_index(entries: list[dict]) -> list[str]:
    lines = ["## 索引", ""]
    lines.append("| 时间 | 分类 | 标题 | 标签 |")
    lines.append("|------|------|------|------|")
    for e in entries:
        title = e["title"].replace("|", "\\|")
        tags = e["tags"].replace("|", "\\|")
        lines.append(f"| {e['date']} | {e['category']} | {title} | {tags} |")
    lines.append("")
    return lines


def build_entry_block(entry: dict) -> list[str]:
    lines = ["---", "", f"## {entry['title']}", ""]
    lines.append(f"- **分类**: {entry['category']}")
    lines.append(f"- **时间**: {entry['date']}")
    if entry["tags"]:
        lines.append(f"- **标签**: {entry['tags']}")
    lines.append("")
    lines.append(entry["body"])
    lines.append("")
    return lines


def send_markdown(entries: list[dict]) -> bool:
    path = Path("cognitive-log.md")
    today = date.today().isoformat()

    # Parse existing + new entries
    existing = parse_entries(path.read_text("utf-8")) if path.exists() else []
    new_entries = [
        {
            "title": e.get("title", ""),
            "category": e.get("category", "认知"),
            "date": e.get("date", "") or today,
            "tags": e.get("tags", ""),
            "body": e.get("body", ""),
        }
        for e in entries
    ]
    all_entries = new_entries + existing

    # Dedup by (title, date)
    seen = set()
    unique = []
    for e in all_entries:
        key = (e["title"], e["date"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    unique.sort(key=lambda e: e["date"], reverse=True)

    # Build file content
    header = [
        "# 认知收获日志",
        "",
        "> 存档时从工程实践中提取的个人认知，与项目知识分离。",
        "> 分类：架构原则 | 设计哲学 | 技术选型 | 工程方法 | 模型心智",
        "",
    ]
    parts = header + build_index(unique)
    for e in unique:
        parts += build_entry_block(e)
    parts.append("")

    path.write_text("\n".join(parts), encoding="utf-8")
    log(f"已更新 {path}（共 {len(unique)} 条）")
    return True


SENDERS = {
    "markdown": send_markdown,
    "none": lambda entries: (log(f"模拟模式: 将发送 {len(entries)} 条"), True),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="认知提取 — 将认知收获保存到 cognitive-log.md")
    parser.add_argument("--backend", choices=BACKENDS, default=DEFAULT_BACKEND,
                        help=f"后端（默认: {DEFAULT_BACKEND}）")
    parser.add_argument("--title", help="条目标题")
    parser.add_argument("--body", help="条目正文")
    parser.add_argument("--category", help="分类（默认: 认知）")
    parser.add_argument("--tags", help="标签，逗号分隔（如: 架构, 设计）")
    parser.add_argument("--date", help="日期，ISO 格式（默认: 今天）")
    parser.add_argument("--file", help="JSON 文件路径（包含条目列表或单条目）")
    args = parser.parse_args()

    entries = read_input(args)
    backend = args.backend

    log(f"后端: {backend}, 条目数: {len(entries)}")

    sender = SENDERS.get(backend)
    ok = sender(entries)

    if ok:
        result(True, f"已写入 {len(entries)} 条")
        return 0
    else:
        result(False, "写入失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
