#!/usr/bin/env python3
"""
markdown_parser.py — 统一 Markdown 经验文件解析器

集中存放项目经验文件（ADR.md / lessons-learned.md / troubleshooting.md）
的解析逻辑，替代原来分散在 9 个脚本中的各自实现。

用法：
    from markdown_parser import parse_adr, parse_lessons, parse_troubleshooting

    entries = parse_adr(text)
    lessons = parse_lessons(text)
    issues = parse_troubleshooting(text)
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from utils import clean_source_tag, extract_source_tags


# ─────────────────────────── 区段解析 ───────────────────────────

class Section:
    """Markdown 区段：由标题行及其下内容组成。"""
    __slots__ = ("level", "title", "title_clean", "sources", "body", "line_start")

    def __init__(self, level: int, title: str, body: str, line_start: int):
        self.level = level
        self.title = title
        self.title_clean = clean_source_tag(title)
        self.sources = extract_source_tags(title)
        self.body = body.strip()
        self.line_start = line_start


def parse_sections(text: str, min_level: int = 2, max_level: int = 3) -> List[Section]:
    """
    按标题级别切分 Markdown 文本为区段列表。

    min_level/max_level 控制匹配的标题级别（1=#，2=##，3=###，...）。
    区段 body 包含从标题行开始到下一个同级或更高级标题之前的所有内容。
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines(keepends=True)
    sections: List[Section] = []
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    current_start: Optional[int] = None
    current_level: Optional[int] = None
    current_title: Optional[str] = None

    for i, line in enumerate(lines):
        m = heading_pattern.match(line)
        if m:
            level = len(m.group(1))
            if min_level <= level <= max_level:
                # 保存上一个区段
                if current_start is not None and current_title is not None:
                    body = "".join(lines[current_start:i])
                    sections.append(Section(
                        level=current_level,
                        title=current_title,
                        body=body,
                        line_start=current_start + 1,
                    ))
                current_start = i
                current_level = level
                current_title = m.group(2).strip()
                continue

    # 最后一个区段
    if current_start is not None and current_title is not None:
        body = "".join(lines[current_start:])
        sections.append(Section(
            level=current_level,
            title=current_title,
            body=body,
            line_start=current_start + 1,
        ))

    return sections


# ─────────────────────────── 表格解析 ───────────────────────────

def _find_table_region(text: str) -> Optional[Tuple[int, int]]:
    """
    定位 Markdown 管道表区域。
    返回 (start_line, end_line) 或 None（无表格）。
    start_line 包含表头行，end_line 为表格结束行（不含空行）。
    """
    lines = text.splitlines()
    sep_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|---"):
            sep_idx = i
            break
    if sep_idx is None:
        return None

    # 找表头行（分隔行前最近的管道行）
    header_idx = sep_idx - 1
    while header_idx >= 0 and not lines[header_idx].strip().startswith("|"):
        header_idx -= 1
    if header_idx < 0:
        return None

    # 找表格结束（空行或非管道行）
    end_idx = sep_idx + 1
    while end_idx < len(lines):
        stripped = lines[end_idx].strip()
        if not stripped.startswith("|"):
            break
        end_idx += 1

    return (header_idx, end_idx)


def parse_table_rows(text: str) -> List[List[str]]:
    """
    解析管道表，返回每行单元格的字符串列表。
    不包含表头和分隔行。
    """
    region = _find_table_region(text)
    if region is None:
        return []
    header_idx, end_idx = region

    lines = text.splitlines()
    # 找到分隔行
    sep_idx = None
    for i in range(header_idx, end_idx):
        if lines[i].strip().startswith("|---"):
            sep_idx = i
            break
    if sep_idx is None:
        return []

    rows = []
    for i in range(sep_idx + 1, end_idx):
        cell_text = lines[i].strip()
        if not cell_text.startswith("|") or cell_text == "|---|":
            continue
        # 去首尾 |，按 | 分割
        cells = [c.strip() for c in cell_text.strip("|").split("|")]
        rows.append(cells)

    return rows


def parse_key_value_table(text: str) -> Dict[str, str]:
    """
    解析"键值对"格式的管道表（如 ADR 和 troubleshooting 中的嵌入式表）。

    格式：
        | 字段 | 内容 |
        |------|------|
        | **状态** | Active |
        | **日期** | 2026-01-01 |

    返回 {键: 值} 字典。忽略表头和分隔行。
    """
    rows = parse_table_rows(text)
    result = {}
    for row in rows:
        if len(row) >= 2:
            key = row[0].strip().strip("*").strip()
            value = row[1].strip().strip("*").strip()
            if key:
                result[key] = value
    return result


def parse_table(text: str) -> List[Dict[str, str]]:
    """
    解析管道表，按表头字段名返回字典列表。
    自动识别表头行。
    """
    region = _find_table_region(text)
    if region is None:
        return []
    header_idx, end_idx = region

    lines = text.splitlines()
    # 表头行
    header_line = lines[header_idx].strip()
    headers = [h.strip() for h in header_line.strip("|").split("|")]

    rows = parse_table_rows(text)
    result = []
    for row in rows:
        row_dict = {}
        for i, h in enumerate(headers):
            if i < len(row):
                row_dict[h] = row[i]
            else:
                row_dict[h] = ""
        result.append(row_dict)

    return result


# ─────────────────────────── ADR 解析 ───────────────────────────

def parse_adr(text: str) -> List[dict]:
    """
    解析 ADR.md，返回条目列表。

    每条格式：
        ### repo_XXXX/ADR-NNN：标题 [来源:xxx]

        | 字段 | 内容 |
        |------|------|
        | **状态** | ... |
        ...
        可选的 --- 分隔符

    同时兼容旧格式（## ADR-NNN：标题 无来源标签）。
    """
    sections = parse_sections(text, min_level=2, max_level=3)
    entries = []

    for sec in sections:
        # 跳过 ## 项目: xxx 分类标签
        if sec.title_clean.startswith("项目:") or not sec.title_clean:
            continue

        m = re.match(
            r"(?:(?:repo_\d+/)?)?"
            r"(ADR-\d+)[：:]\s*(.+)",
            sec.title_clean
        )
        if not m:
            continue

        adr_id = m.group(1)
        adr_title = m.group(2).strip()

        # 从 body 中解析键值对表
        fields = parse_key_value_table(sec.body)

        # body 去掉首行（标题行本身），避免 merge 函数叠重复标题
        body_lines = sec.body.splitlines(keepends=True)
        body_content = "".join(body_lines[1:]).strip() if len(body_lines) > 1 else ""

        entries.append({
            "adr_id": adr_id,
            "title": adr_title,
            "title_raw": sec.title,
            "sources": sec.sources,
            "fields": fields,
            "body": body_content,
            "line_start": sec.line_start,
        })

    return entries


# ─────────────────────────── lessons-learned 解析 ───────────────────────────

def parse_lessons(text: str) -> List[dict]:
    """
    解析 lessons-learned.md，返回经验条目列表。

    兼容三种表格格式（5/6/7 列）+ 列表格式条目。

    5 列：| # | 标签 | 严重度 | 描述 | 来源模块 |
    6 列：| # | 标签 | 严重度 | 描述 | 来源 | 模块 |
    7 列：| # | 标签 | 严重度 | 描述 | 来源 | 模块 | 额外 |
    列表：- 描述 [来源:xxx]
    """
    entries: List[dict] = []

    # ── 解析表格条目 ──
    table_rows = parse_table_rows(text)
    for row in table_rows:
        col_count = len(row)

        # merge_lessons 的 3 列格式: | | desc [来源:xxx] | source |
        if col_count == 3 and row[0] == "":
            desc = row[1].strip()
            source = row[2].strip() if len(row) >= 3 else ""
            module = ""
            tags_str = ""
            severity = "INFO"
            num = ""
            entries.append({
                "type": "table",
                "num": num,
                "tags": tags_str,
                "severity": severity,
                "description": desc,
                "description_clean": clean_source_tag(desc),
                "source": source,
                "module": module,
                "sources": extract_source_tags(desc) + extract_source_tags(source),
            })
            continue

        if col_count < 4:
            continue

        # 自动识别列结构
        num = row[0] if col_count >= 1 else ""
        tags_str = row[1] if col_count >= 2 else ""
        severity = row[2] if col_count >= 3 else "INFO"
        desc = row[3] if col_count >= 4 else ""
        source = ""
        module = ""

        if col_count >= 5:
            source = row[4]
        if col_count >= 6:
            module = row[5]
        # 第 7 列忽略

        desc = desc.strip()
        if not desc:
            continue

        entries.append({
            "type": "table",
            "num": num,
            "tags": tags_str.strip(),
            "severity": severity.strip(),
            "description": desc,
            "description_clean": clean_source_tag(desc),
            "source": source.strip(),
            "module": module.strip(),
            "sources": extract_source_tags(desc) + extract_source_tags(source),
        })

    # ── 解析列表条目（以 - 或 * 开头的行） ──
    for line in text.splitlines():
        m = re.match(r"^[-*]\s+(.+)$", line.strip())
        if m:
            desc = m.group(1).strip()
            if not desc:
                continue
            entries.append({
                "type": "list",
                "num": "",
                "tags": "",
                "severity": "INFO",
                "description": desc,
                "description_clean": clean_source_tag(desc),
                "source": "",
                "module": "",
                "sources": extract_source_tags(desc),
            })

    return entries


# ─────────────────────────── troubleshooting 解析 ───────────────────────────

def parse_troubleshooting(text: str) -> List[dict]:
    """
    解析 troubleshooting.md，返回问题条目列表。

    结构：
        ## 分类（大分类）
        ### 关键词/标题 [来源:xxx]

        | | 内容 |
        |---|---|
        | **状态** | ... |
        | **现象** | ... |
        | **原因** | ... |
        | **解决** | ... |
    """
    # 先按 ## 分类提取分类名
    categories = {}
    sections = parse_sections(text, min_level=2, max_level=2)
    for sec in sections:
        categories[sec.line_start] = sec.title_clean

    # 提取 ### 条目
    entries: List[dict] = []
    items = parse_sections(text, min_level=3, max_level=3)

    # 为每个 ### 条目找到它所属的 ## 分类
    def _find_category(line_start: int) -> str:
        cat_line = 0
        cat_name = ""
        for cl, cn in sorted(categories.items(), reverse=True):
            if cl < line_start:
                cat_line = cl
                cat_name = cn
                break
        return cat_name

    for item in items:
        # 从 body 中解析嵌入式键值对表
        fields = parse_key_value_table(item.body)

        category = _find_category(item.line_start)

        # body 去掉首行（标题行本身），避免 merge 函数叠重复标题
        body_lines = item.body.splitlines(keepends=True)
        body_content = "".join(body_lines[1:]).strip() if len(body_lines) > 1 else ""

        entries.append({
            "keyword": item.title_clean,
            "keyword_raw": item.title,
            "category": category,
            "sources": item.sources,
            "fields": fields,
            "status": fields.get("状态", ""),
            "symptom": fields.get("现象", ""),
            "cause": fields.get("原因", ""),
            "solution": fields.get("解决", ""),
            "body": body_content,
            "line_start": item.line_start,
        })

    return entries


# ─────────────────────────── 主入口 / 独立使用 ───────────────────────────

def main():
    """命令行入口，用于快速验证解析结果。"""
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Markdown 经验文件解析器")
    parser.add_argument("file", help="要解析的 .md 文件路径")
    parser.add_argument("--type", "-t", choices=["adr", "lessons", "troubleshooting"],
                        help="文件类型（自动检测）")
    parser.add_argument("--count", "-c", action="store_true",
                        help="只输出条目数量")
    parser.add_argument("--list", "-l", action="store_true",
                        help="列出所有条目标题/关键词")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"文件不存在: {path}")
        return 1

    text = path.read_text(encoding="utf-8", errors="replace")

    # 自动检测类型
    ftype = args.type
    if not ftype:
        name = path.name.lower()
        if "adr" in name:
            ftype = "adr"
        elif "lesson" in name:
            ftype = "lessons"
        elif "trouble" in name:
            ftype = "troubleshooting"
        else:
            print("无法自动检测文件类型，请使用 --type 指定")
            return 1

    if ftype == "adr":
        entries = parse_adr(text)
        title_key = "title"
    elif ftype == "lessons":
        entries = parse_lessons(text)
        title_key = "description"
    else:
        entries = parse_troubleshooting(text)
        title_key = "keyword"

    if args.count:
        print(f"{len(entries)} 条")
        return 0

    print(f"共 {len(entries)} 条{' ' * 4}(--count 只显示数量, --list 列出所有)")
    if args.list:
        print()
        for i, e in enumerate(entries, 1):
            title = e.get(title_key, "")
            if ftype == "adr":
                print(f"  {e['adr_id']:>8}  {title[:70]}")
            else:
                print(f"  {i:>4}. {title[:70]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
