#!/usr/bin/env python3
"""自修复脚本：检查并修复母库知识文件的结构/质量问题。

子命令：
  agents     检查 AGENTS.md 章节顺序 + 补缺
  knowledge  去重/乱码/来源标签/编号跳号
  index      索引新鲜度检查 + 重建
  all        以上依次执行

用法：
  python scripts/self-repair.py agents --dry-run
  python scripts/self-repair.py knowledge --dry-run
  python scripts/self-repair.py all
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from markdown_parser import parse_sections, parse_lessons, parse_adr
from utils import clean_source_tag, extract_source_tags, uprint

PROJECT_DIR = Path(__file__).resolve().parent.parent

# ── 文件路径 ──
AGENTS_MD = PROJECT_DIR / "AGENTS.md"
STARTER_AGENTS = PROJECT_DIR / "starter" / "AGENTS.md"
LESSONS_MD = PROJECT_DIR / "lessons-learned.md"
TROUBLESHOOTING_MD = PROJECT_DIR / "troubleshooting.md"
ADR_MD = PROJECT_DIR / "ADR.md"
EXPERIENCE_INDEX = PROJECT_DIR / "experience-index.md"
BACKUP_DIR = PROJECT_DIR / ".backup"

# ── 脚本路径 ──
SCRIPTS_DIR = PROJECT_DIR / "scripts"
BUILD_INDEX = SCRIPTS_DIR / "build-experience-index.py"


# ═══════════════════════════════════════════════════════════════
# 通用工具
# ═══════════════════════════════════════════════════════════════

def _backup(path: Path) -> Path:
    """备份文件到 .backup/{filename}.{YYYYMMDD}。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    suf = datetime.now().strftime("%Y%m%d%H%M%S")
    dest = BACKUP_DIR / f"{path.name}.{suf}"
    shutil.copy2(str(path), str(dest))
    return dest


def _confirm(prompt: str = "是否执行上述修复？(y/n) ") -> bool:
    """等待用户确认。"""
    try:
        return input(prompt).strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def _format_repairs(items: list, title: str) -> str:
    """格式化修复建议列表。"""
    if not items:
        return ""
    lines = [f"\n=== {title} ==="]
    for item in items:
        lines.append(f"  - {item}")
    return "\n".join(lines)


def _plain_heading(s: str) -> str:
    """提取纯章节编号+名称（去掉附加符号）。"""
    m = re.match(r"^(\d[\d.]*)\s+(.+)", s)
    if m:
        return f"{m.group(1)} {m.group(2).strip()}"
    return s.strip()


# ═══════════════════════════════════════════════════════════════
# self-repair agents
# ═══════════════════════════════════════════════════════════════

def _parse_sync_blocks_from_starter() -> list[dict]:
    """解析 starter/AGENTS.md 中的 @sync 标记区段。
    
    下游项目无 starter/ 目录，返回空列表跳过。
    """
    if not STARTER_AGENTS.exists():
        return []
    text = STARTER_AGENTS.read_text(encoding="utf-8")
    blocks = []
    pattern = re.compile(r'<!-- @sync:id=(\S+) -->\n(.+?)\n<!-- /@sync -->', re.DOTALL)
    for m in pattern.finditer(text):
        sync_id = m.group(1)
        content = m.group(2).strip()
        # 提取 ## 标题
        heading = ""
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("## "):
                heading = s[3:].strip()
                break
        blocks.append({"id": sync_id, "heading": heading, "content": content})
    return blocks


def run_agents(dry_run: bool, verbose: bool) -> int:
    """检查 AGENTS.md 章节顺序 + 补缺。"""
    if not AGENTS_MD.exists():
        uprint("错误: AGENTS.md 不存在")
        return 1

    text = AGENTS_MD.read_text(encoding="utf-8")
    sections = parse_sections(text, min_level=2, max_level=2)
    repairs = []
    orphan_suggestions = []

    # ── 检查 1: 编号顺序 ──
    prev_num = ""
    prev_line = 0
    for sec in sections:
        m = re.match(r"^(\d[\d.]*)", sec.title)
        if m:
            cur = m.group(1)
            if prev_num and cur:
                prev_parts = [int(x) for x in prev_num.split(".") if x]
                cur_parts = [int(x) for x in cur.split(".") if x]
                if cur_parts < prev_parts:
                    repairs.append(
                        f"行 {sec.line_start}: 编号 {cur} 出现在 {prev_num}（{prev_line}行）之后, "
                        f"顺序异常"
                    )
            prev_num = cur
            prev_line = sec.line_start

    # ── 检查 2: 空章节 ──
    for sec in sections:
        body = sec.body.replace(sec.title, "", 1).strip()
        if not body or body == "---":
            repairs.append(f"行 {sec.line_start}: 「{sec.title[:40]}」内容为空")

    # ── 检查 3: starter 有但母库缺的 @sync 章节 ──
    starter_blocks = _parse_sync_blocks_from_starter()
    existing_headings = set()
    for sec in sections:
        existing_headings.add(_plain_heading(sec.title).lower())
    for block in starter_blocks:
        if block["heading"] and block["heading"].lower() not in existing_headings:
            # 建议插入位置：找到前驱和后继
            insert_after = ""
            for i, sec in enumerate(sections):
                m = re.match(r"^(\d[\d.]*)", sec.title)
                if m and block["heading"]:
                    block_m = re.match(r"^(\d[\d.]*)", block["heading"])
                    if block_m and m.group(1) < block_m.group(1):
                        insert_after = f"{m.group(1)} {sec.title}"
            orphan_suggestions.append(
                f"[{block['id']}] {block['heading']}  → "
                f"建议插入在「{insert_after}」之后"
                if insert_after
                else f"[{block['id']}] {block['heading']}  → 建议插入「必读上下文」之后"
            )

    # ── 输出报告 ──
    uprint(f"\n===== agents: 检查完成 =====")
    if repairs:
        uprint(f"\n发现 {len(repairs)} 个问题:")
        for r in repairs:
            uprint(f"  {r}")
    else:
        uprint("\n章节顺序和内容完整性：正常")

    if orphan_suggestions:
        uprint(f"\n发现 {len(orphan_suggestions)} 个缺失的 @sync 章节（starter 中有但 AGENTS.md 没有）:")
        for s in orphan_suggestions:
            uprint(f"  {s}")

    total = len(repairs) + len(orphan_suggestions)
    if total == 0:
        uprint("\nAGENTS.md 结构正常，无需修复。")
        return 0

    if dry_run:
        uprint(f"\n--dry-run: 共 {total} 项需处理（预览完毕，未做任何修改）")
        return 0

    uprint(f"\n共 {total} 项需处理。")
    if not _confirm():
        uprint("已取消。")
        return 0

    # ── 执行修复：插入缺失的 @sync 章节 ──
    modified = False
    if orphan_suggestions:
        backup_path = _backup(AGENTS_MD)
        uprint(f"已备份: {backup_path.name}")

        text = AGENTS_MD.read_text(encoding="utf-8")
        sections = parse_sections(text, min_level=2, max_level=2)

        for block in starter_blocks:
            if not block["heading"]:
                continue
            if _plain_heading(block["heading"]).lower() in existing_headings:
                continue

            # 找到插入位置：在前驱章节的 --- 之后插入
            insert_pos = -1
            predecessor = ""
            block_num = ""
            bm = re.match(r"^(\d[\d.]*)", block["heading"])
            if bm:
                block_num = bm.group(1)

            # 从前向后找前驱
            closest_pre = ""
            closest_pre_end = -1
            for sec in sections:
                sm = re.match(r"^(\d[\d.]*)", sec.title)
                if sm and sm.group(1) < block_num:
                    # 找到此章节结束位置（下一个 --- 后）
                    sec_end = text.find("\n---\n", text.find(f"## {sec.title}"))
                    if sec_end > 0:
                        closest_pre = sec.title
                        closest_pre_end = sec_end + 5  # 跳过 ---\n

            if closest_pre_end > 0:
                insert_pos = closest_pre_end
                predecessor = closest_pre
            else:
                # 无前驱，插入第一个 ## 章节之后
                first_sec = text.find("\n## ")
                insert_pos = first_sec if first_sec > 0 else text.find("## ") + len("## ")
                predecessor = "文件开头"

            # 构建待插入块
            new_block = (
                f"\n\n"
                f"<!-- @sync:id={block['id']} -->\n"
                f"{block['content']}\n"
                f"<!-- /@sync -->"
            )
            text = text[:insert_pos] + new_block + text[insert_pos:]
            uprint(f"  已插入 @{block['id']}（在「{predecessor}」之后）")
            modified = True

        if modified:
            AGENTS_MD.write_text(text, encoding="utf-8")
            # 重读 sections 以保持一致性
            sections = parse_sections(text, min_level=2, max_level=2)
            existing_headings = {_plain_heading(s.title).lower() for s in sections}

    if not modified:
        uprint("无需插入，已有章节已完整。")
    else:
        uprint("\nagents: 修复完成。")

    return 0


# ═══════════════════════════════════════════════════════════════
# self-repair knowledge
# ═══════════════════════════════════════════════════════════════

def _check_garbled(text: str, label: str, verbose: bool) -> list[str]:
    """检查乱码 Unicode。"""
    issues = []
    for i, line in enumerate(text.splitlines(), 1):
        if "\ufffd" in line:
            issues.append(f"{label} 行 {i}: 含 U+FFFD 替换字符")
        if "\x00" in line:
            issues.append(f"{label} 行 {i}: 含空字节 \\x00")
        if "\u200b" in line:
            issues.append(f"{label} 行 {i}: 含零宽空格 U+200B")
    return issues


def _dedup_source_tags(entries: list[dict], label: str, verbose: bool) -> list[str]:
    """检查同一条目中来源标签重复。"""
    fixes = []
    for e in entries:
        sources = e.get("sources", [])
        if len(sources) > 1:
            unique = list(dict.fromkeys(sources))  # 去重保序
            if len(unique) < len(sources):
                fixes.append(
                    f"{label} 行 {e.get('line_start', '?')}: "
                    f"{len(sources)} 个来源标签 → 去重到 {len(unique)} 个"
                )
    return fixes


def _check_numbering_gaps(entries: list[dict], label: str, key: str = "num") -> list[str]:
    """检查编号是否连续。"""
    gaps = []
    nums = []
    for e in entries:
        n = e.get(key, "")
        if n and n.isdigit():
            nums.append((int(n), e.get("line_start", 0)))
    nums.sort()
    for i in range(1, len(nums)):
        if nums[i][0] - nums[i-1][0] > 1:
            for missing in range(nums[i-1][0] + 1, nums[i][0]):
                gaps.append(
                    f"{label}: 条目 #{nums[i-1][0]}（行{nums[i-1][1]}）→ "
                    f"#{nums[i][0]}（行{nums[i][1]}）之间缺少 #{missing}"
                )
    return gaps


def _fix_file_garbled(path: Path, label: str, verbose: bool) -> bool:
    """修复文件中的乱码字符。"""
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace("\ufffd", "?")
    text = text.replace("\x00", "")
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def run_knowledge(dry_run: bool, verbose: bool) -> int:
    """检查并修复知识文件（lessons/troubleshooting/ADR）。"""
    if not LESSONS_MD.exists() or not TROUBLESHOOTING_MD.exists():
        uprint("错误: lessons-learned.md 或 troubleshooting.md 不存在")
        return 1

    issues: list[str] = []
    auto_fixes: list[str] = []

    # ── 检查 1: 乱码 ──
    for path, label in [(LESSONS_MD, "lessons"), (TROUBLESHOOTING_MD, "troubleshooting"),
                        (ADR_MD, "ADR")]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        garbled = _check_garbled(text, label, verbose)
        issues.extend(garbled)

    # ── 检查 2: 来源标签去重 ──
    for path, label in [(LESSONS_MD, "lessons"), (TROUBLESHOOTING_MD, "troubleshooting")]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if label == "lessons":
            entries = parse_lessons(text)
        else:
            from markdown_parser import parse_troubleshooting
            entries = parse_troubleshooting(text)
        tagged = _dedup_source_tags(entries, label, verbose)
        issues.extend(tagged)

    # ── 检查 3: 编号跳号 ──
    if LESSONS_MD.exists():
        lessons = parse_lessons(LESSONS_MD.read_text(encoding="utf-8"))
        gaps = _check_numbering_gaps(lessons, "lessons-learned", "num")
        issues.extend(gaps)



    # ── 输出报告 ──
    uprint(f"\n===== knowledge: 检查完成 =====")
    if issues:
        uprint(f"\n发现 {len(issues)} 项:")
        for item in issues:
            uprint(f"  {item}")
    else:
        uprint("\n所有知识文件正常。")

    if dry_run:
        uprint(f"\n--dry-run: 共 {len(issues)} 项（预览完毕，未做任何修改）")
        return 0 if not issues else 1

    # ── 可修复项：乱码修复 ──
    fixed = []
    for path, label in [(LESSONS_MD, "lessons"), (TROUBLESHOOTING_MD, "troubleshooting"),
                        (ADR_MD, "ADR")]:
        if path and path.exists():
            garbled_found = _check_garbled(path.read_text(encoding="utf-8"), label, verbose)
            if garbled_found:
                fixed.append(f"{label}: {len(garbled_found)} 处乱码可修复")

    can_repair = bool(fixed)
    if can_repair:
        uprint(f"\n可修复项: {len(fixed)}")
        for f in fixed:
            uprint(f"  - {f}")

    if not issues and not can_repair:
        uprint("\n所有知识文件正常，无需修复。")
        return 0

    if not can_repair:
        uprint("\n无自动可修复项（其余问题仅报告，需人工处理）。")
        return 0

    if not _confirm():
        uprint("已取消。")
        return 0

    # 执行修复
    _backup(LESSONS_MD)
    _backup(TROUBLESHOOTING_MD)
    if ADR_MD.exists():
        _backup(ADR_MD)
    uprint("已备份知识文件")

    changed = 0
    for path, label in [(LESSONS_MD, "lessons"), (TROUBLESHOOTING_MD, "troubleshooting"),
                        (ADR_MD, "ADR")]:
        if path and path.exists() and _fix_file_garbled(path, label, verbose):
            changed += 1
            uprint(f"  {label}: 乱码已修复")

    uprint(f"\nknowledge: 修复完成（{changed} 个文件有修改）")
    return 0


# ═══════════════════════════════════════════════════════════════
# self-repair index
# ═══════════════════════════════════════════════════════════════

def run_index(dry_run: bool, verbose: bool) -> int:
    """检查并重建经验索引。"""
    if not BUILD_INDEX.exists():
        uprint("错误: build-experience-index.py 未找到")
        return 1

    check_cmd = [sys.executable, str(BUILD_INDEX), "--check"]
    r = subprocess.run(check_cmd, capture_output=True, text=True, timeout=30, encoding="utf-8")

    if r.returncode == 0:
        uprint("\n===== index: 索引已是最新 =====")
        return 0

    uprint(f"\n===== index: 索引需要重建 =====")
    if verbose:
        uprint(r.stdout.strip() if r.stdout else r.stderr.strip())

    if dry_run:
        uprint("--dry-run: 索引需要重建（预览完毕，未做修改）")
        return 1

    if not _confirm("索引已过期，是否重建？(y/n) "):
        uprint("已取消。")
        return 0

    uprint("正在重建索引...")
    r2 = subprocess.run(
        [sys.executable, str(BUILD_INDEX)],
        capture_output=True, text=True, timeout=60, encoding="utf-8",
    )
    if r2.returncode == 0:
        uprint("index: 索引已重建")
        return 0
    else:
        uprint(f"index: 重建失败\n{r2.stderr.strip()}")
        return 1


# ═══════════════════════════════════════════════════════════════
# self-repair all
# ═══════════════════════════════════════════════════════════════

def run_all(dry_run: bool, verbose: bool) -> int:
    """依次执行 agents → knowledge → index。"""
    uprint("========================================")
    uprint("self-repair all: 开始全面检查")
    uprint("========================================")

    # 步 1: agents（只读检查）
    uprint("\n>>> 步 1/3: agents（章节检查）")
    exit_code = run_agents(dry_run, verbose)

    # 步 2: knowledge（可修复）
    uprint("\n>>> 步 2/3: knowledge（知识文件）")
    exit_code = run_knowledge(dry_run, verbose) or exit_code

    # 步 3: index（重建）
    uprint("\n>>> 步 3/3: index（索引重建）")
    exit_code = run_index(dry_run, verbose) or exit_code

    uprint("\n========================================")
    if exit_code == 0:
        uprint("self-repair all: 全部完成，无待处理项")
    else:
        uprint("self-repair all: 有项目需处理（详情见上）")
    uprint("========================================")
    return exit_code


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="自修复脚本：检查并修复母库知识文件的结构/质量问题",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
子命令:
  agents     检查 AGENTS.md 章节顺序 + 补缺
  knowledge  去重/乱码/来源标签/编号跳号
  index      索引新鲜度检查 + 重建
  all        以上依次执行

示例:
  python scripts/self-repair.py agents --dry-run
  python scripts/self-repair.py knowledge --dry-run
  python scripts/self-repair.py all
        """,
    )
    parser.add_argument(
        "command",
        choices=["agents", "knowledge", "index", "all"],
        help="子命令",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅报告不修改")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    args = parser.parse_args()

    if args.command == "agents":
        return run_agents(dry_run=args.dry_run, verbose=args.verbose)
    elif args.command == "knowledge":
        return run_knowledge(dry_run=args.dry_run, verbose=args.verbose)
    elif args.command == "index":
        return run_index(dry_run=args.dry_run, verbose=args.verbose)
    elif args.command == "all":
        return run_all(dry_run=args.dry_run, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
