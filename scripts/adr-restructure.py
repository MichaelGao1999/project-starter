#!/usr/bin/env python3
"""
ADR.md 全量重构脚本 — 六阶段全自动

用法:
    python scripts/adr-restructure.py          # 默认模式，备份旧文件后生成新文件
    python scripts/adr-restructure.py --dry    # 只输出统计，不改文件
    python scripts/adr-restructure.py --verify # 只做 VERIFY 阶段（验证已有文件）
"""

import argparse
import os
import re
import shutil
import sys
from typing import Any

# Windows GBK 兼容：print() 遇到非 BMP 字符时 fallback 到 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass
from markdown_parser import parse_sections
import json
from utils import similarity
from datetime import date
from pathlib import Path


# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────
ADR_PATH = "ADR.md"
BACKUP_DIR = ".backup"


def _load_repo_config():
    """从 config/repo-ids.json 加载仓库映射（替代旧版硬编码）。"""
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "repo-ids.json"
    with open(cfg_path, "r", encoding="utf-8") as f:
        repos = json.load(f).get("repos", {})
    # id → 名称（字符串键，与原 REPO_NAMES 格式一致）
    repo_names = {str(v): k for k, v in repos.items()}
    # 名称 → id + 母库别名（与原 SOURCE_TO_REPO 格式一致）
    source_to_repo = {k: str(v) for k, v in repos.items()}
    # 母库特殊处理：指向 AI Workbench 的 ID
    workbench_id = str(repos.get("AI Workbench", ""))
    if workbench_id:
        source_to_repo["母库"] = workbench_id
    return repo_names, source_to_repo


REPO_NAMES, SOURCE_TO_REPO = _load_repo_config()

SIMILARITY_THRESHOLD = 0.75


# ──────────────────────────────────────────────
# 阶段一：PARSE
# ──────────────────────────────────────────────
def parse_adr(text: str) -> list[dict]:
    """
    解析 ADR.md，返回结构化条目列表（使用 markdown_parser 统一解析器）。
    同时支持新旧两种格式。
    """
    sections = parse_sections(text, min_level=2, max_level=3)
    entries: list[dict] = []
    current_section = "（未归类）"

    for sec in sections:
        # 检测项目分组
        m_section = re.match(r"^项目:\s*(.+)", sec.title_clean)
        if m_section:
            current_section = m_section.group(1).strip()
            continue

        # 解析 ADR 标题
        m = re.match(r"((?:repo_\d+/)?)(ADR-\d+)[：:]\s*(.+)", sec.title_clean)
        if not m:
            continue

        prefix = m.group(1) or ""
        adr_id = m.group(2)
        title_raw = m.group(3).strip()

        # 来源标签（parse_sections 已提取 [来源:xxx]）
        sources = list(sec.sources)
        mother_sources = re.findall(r"\[母库[^\]]*\]", sec.title)

        # body 去掉首行（标题行）
        body_lines = sec.body.splitlines(keepends=True)
        body = "".join(body_lines[1:]).strip() if len(body_lines) > 1 else ""

        # 判断格式
        is_new = sec.level == 3

        # 判断草稿
        is_draft = "[决策标题]" in sec.title

        entries.append(
            {
                "adr_id": adr_id,
                "title": title_raw,
                "sources": sources,
                "mother_sources": mother_sources,
                "body": body,
                "section": current_section,
                "format": "new" if is_new else "old",
                "prefix": prefix,
                "draft": is_draft,
            }
        )

    return entries


# ──────────────────────────────────────────────
# 阶段二：DEDUP
# ──────────────────────────────────────────────
def dedup(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    相似度去重。
    新格式条目作为基准，旧格式条目与新格式条目标题比较。
    相似度 > THRESHOLD 则合并来源标签到新格式条目。
    """
    news = [e for e in entries if e["format"] == "new" and not e["draft"]]
    olds = [e for e in entries if e["format"] == "old" and not e["draft"]]
    drafts = [e for e in entries if e["draft"]]

    kept = list(news)  # 新格式全部保留
    deduped_count = 0
    merged_count = 0

    for old in olds:
        best_match = None
        best_score: float = 0.0

        for new_entry in kept:
            # 比较标题
            score = similarity(old["title"], new_entry["title"])
            if score > best_score:
                best_score = score
                best_match = new_entry

        if best_score >= SIMILARITY_THRESHOLD:
            # 合并来源标签
            assert best_match is not None
            merged_count += 1
            for s in old["sources"]:
                if s not in best_match["sources"]:
                    best_match["sources"].append(s)
            for s in old.get("mother_sources", []):
                label = "母库"
                if label not in best_match["sources"]:
                    best_match["sources"].append(label)
        else:
            # 无匹配 → 作为独立条目保留
            kept.append(old)
            deduped_count += 1

    # 草稿条目 → 记录但不保留
    draft_count = len(drafts)
    draft_titles = [d["title"] for d in drafts]

    # 统计
    stats = {
        "new_count": len(news),
        "old_count": len(olds),
        "draft_count": draft_count,
        "merged_count": merged_count,
        "kept_new_count": len(olds) - merged_count,
        "draft_titles": draft_titles,
    }

    return kept, stats  # type: ignore[return-value]


# ──────────────────────────────────────────────
# 阶段三：CLASSIFY
# ──────────────────────────────────────────────
def classify(entries: list[dict]) -> dict[str, list[dict]]:
    """
    按项目分组归类。
    优先使用来源标签映射到 repo_id，再归入对应项目分组。
    """
    groups: dict[str, list[dict]] = {}

    for entry in entries:
        project = "（未归类）"

        # 从来源标签推断项目
        all_sources = entry.get("sources", []) + entry.get("mother_sources", [])
        for s in all_sources:
            # 提取纯项目名（去掉 @date 部分）
            parts = s.split(" @")[0].strip()
            if parts in SOURCE_TO_REPO:
                project = REPO_NAMES[SOURCE_TO_REPO[parts]]
                break
            # 直接匹配 repo name
            if parts in REPO_NAMES.values():
                project = parts
                break

        if project not in groups:
            groups[project] = []
        groups[project].append(entry)

    return groups


# ──────────────────────────────────────────────
# 阶段四：ASSIGN
# ──────────────────────────────────────────────
def assign_numbers(groups: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """
    分配全局唯一编号。
    规则：
    - 同一编号多次出现 → 仅第一个保留，后续重新编号
    - 同编号 + 同标题 → 自动去重合并（已在 DEDUP 处理）
    - 新条目从最大编号 +1 开始
    """
    # 收集所有出现过的编号
    all_nums = set()
    for project, entries in groups.items():
        for entry in entries:
            m = re.match(r"ADR-(\d+)", entry["adr_id"])
            if m:
                all_nums.add(int(m.group(1)))

    if not all_nums:
        next_num = 1
    else:
        next_num = max(all_nums) + 1

    # 已使用的编号 → 条目特征（用于检测冲突）
    used_numbers: dict[int, list[dict]] = {}

    for project, entries in groups.items():
        for entry in entries:
            m = re.match(r"ADR-(\d+)", entry["adr_id"])
            if not m:
                entry["adr_id"] = f"ADR-{next_num:03d}"
                next_num += 1
                continue

            num = int(m.group(1))

            if num not in used_numbers:
                # 编号第一次出现 → 保留
                used_numbers[num] = [entry]
                entry["adr_id"] = f"ADR-{num:03d}"
            else:
                # 编号已存在 → 比较标题，相同则合并来源，不同则重新编号
                first = used_numbers[num][0]
                score = similarity(entry["title"], first["title"])
                if score >= SIMILARITY_THRESHOLD:
                    # 同内容 → 合并来源
                    for s in entry.get("sources", []):
                        if s not in first["sources"]:
                            first["sources"].append(s)
                    for s in entry.get("mother_sources", []):
                        label = "母库"
                        if label not in first["sources"]:
                            first["sources"].append(label)
                    used_numbers[num].append(entry)
                else:
                    # 不同内容 → 重新编号
                    entry["adr_id"] = f"ADR-{next_num:03d}"
                    next_num += 1

    # 重新统计各组条目数（合并后可能有空的）
    active_groups = {}
    for project, entries in groups.items():
        active = [e for e in entries if e]
        if active:
            active_groups[project] = active

    return active_groups, next_num - 1  # type: ignore[return-value]


# ──────────────────────────────────────────────
# 阶段五：GENERATE
# ──────────────────────────────────────────────
def generate(groups: dict[str, list[dict]], total: int) -> str:
    """
    生成重组后的 ADR.md。
    """
    lines = []
    lines.append("# AI Workbench — 跨项目决策母库")
    lines.append("")
    lines.append("> 本文件聚合自多个项目的关键设计决策。所有 ADR 均标注来源。")
    lines.append("> 母库自身决策标注 `[母库]`。")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 项目排序：母库排第一，其他按字母序
    sorted_projects = sorted(groups.keys())
    if "AI Workbench" in sorted_projects:
        sorted_projects.remove("AI Workbench")
    if "（未归类）" in sorted_projects:
        sorted_projects.remove("（未归类）")
    ordered = ["AI Workbench"] + sorted_projects
    if "（未归类）" in groups:
        ordered.append("（未归类）")

    written_count = 0

    for project in ordered:
        if project not in groups or not groups[project]:
            continue
        entries = groups[project]
        count = len(entries)
        lines.append(f"## 项目: {project}（共 {count} 条决策）")
        lines.append("")

        for entry in entries:
            # 确定 repo_id
            repo_id = ""
            for s in entry.get("sources", []):
                parts = s.split(" @")[0].strip()
                if parts in SOURCE_TO_REPO:
                    repo_id = SOURCE_TO_REPO[parts]
                    break
            # 也检查 mother_sources
            if not repo_id:
                for s in entry.get("mother_sources", []):
                    label = "母库"
                    if label in SOURCE_TO_REPO:
                        repo_id = SOURCE_TO_REPO[label]
                        break

            # 构建来源标签
            all_sources = list(entry.get("sources", []))
            for s in entry.get("mother_sources", []):
                label = "母库"
                if label not in all_sources:
                    all_sources.append(label)

            source_str = ""
            if all_sources:
                # 去重 + 按来源名排序
                unique_sources = sorted(set(all_sources))
                tags = " ".join(f"[来源:{s}]" for s in unique_sources)
                source_str = f" {tags}"

            # 写入标题行
            title = entry["title"]
            # 去掉旧格式里可能残留的来源标签
            title = re.sub(r"\s*\[[^\]]*\]\s*$", "", title).strip()
            # 去掉 [决策标题] 标记
            title = title.replace("[决策标题]", "").strip()
            if not title:
                title = "（待补充标题）"

            if repo_id:
                header = f"### repo_{repo_id}/{entry['adr_id']}：{title}{source_str}"
            else:
                header = f"### {entry['adr_id']}：{title}{source_str}"

            lines.append(header)

            # 写入 body
            body = entry.get("body", "").strip()
            # 旧格式的 body 可能包含前导/后导空行
            if body:
                # 确保 body 以 --- 结束
                if not body.endswith("---"):
                    body += "\n\n---"
                lines.append("")
                lines.append(body)
            else:
                lines.append("")
                lines.append("---")

            lines.append("")
            written_count += 1

    # 尾部说明
    lines.append("---")
    lines.append("")
    lines.append("*新增决策时，请在对应项目分组下按格式追加，编号使用下一个可用数字。*")
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 阶段六：VERIFY
# ──────────────────────────────────────────────
def verify(text: str) -> list[str]:
    """
    自检：编号唯一性 / 格式完整性 / 来源标签完整性。
    返回问题列表，空列表 = 通过。
    """
    issues = []
    lines = text.split("\n")

    # 1. 检查所有标题行是否都是 ### repo_ 格式
    adr_headers = [line for line in lines if re.match(r"^#{2,3}\s+", line)]
    for header in adr_headers:
        if re.match(r"^##\s+项目:", header):
            continue  # 项目分组标题正常
        if re.match(r"^##\s+ADR-", header):
            issues.append(f"旧格式残留：{header[:60]}")
        if not re.match(r"^###\s+repo_\d+/ADR-\d+", header):
            if re.match(r"^###\s+", header):
                issues.append(f"非标准格式：{header[:60]}")

    # 2. 编号唯一性
    nums = []
    for header in adr_headers:
        m = re.search(r"ADR-(\d+)", header)
        if m:
            nums.append(int(m.group(1)))
    from collections import Counter

    dupes = {n: c for n, c in Counter(nums).items() if c > 1}
    if dupes:
        for n, c in dupes.items():
            issues.append(f"编号冲突：ADR-{n:03d} 出现 {c} 次")

    # 2b. 编号连续性
    sorted_nums = sorted(set(nums))
    for i in range(1, len(sorted_nums)):
        if sorted_nums[i] - sorted_nums[i - 1] > 1:
            for missing in range(sorted_nums[i - 1] + 1, sorted_nums[i]):
                issues.append(f"编号跳号：缺少 ADR-{missing:03d}（在 {sorted_nums[i - 1]:03d} 与 {sorted_nums[i]:03d} 之间）")

    # 3. 来源标签检查
    entry_headers = [
        line for line in lines if re.match(r"^###\s+repo_\d+/ADR-\d+", line)
    ]
    for header in entry_headers:
        if "[来源:" not in header:
            issues.append(f"缺少来源标签：{header[:60]}")

    return issues


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ADR.md 全量重构")
    parser.add_argument("--dry", action="store_true", help="只输出统计，不改文件")
    parser.add_argument("--verify", action="store_true", help="只做 VERIFY 阶段")
    args = parser.parse_args()

    if not os.path.exists(ADR_PATH):
        print(f"❌ 未找到 {ADR_PATH}")
        sys.exit(1)

    with open(ADR_PATH, "r", encoding="utf-8") as f:
        original_text = f.read()

    if args.verify:
        issues = verify(original_text)
        if issues:
            print("⚠️  发现问题：")
            for issue in issues:
                print(f"  • {issue}")
        else:
            print("✅ 验证通过，无问题")
        return

    # ── 阶段一：PARSE ──
    print("📖 阶段一 PARSE：解析 ADR.md...")
    entries = parse_adr(original_text)
    new_count = sum(1 for e in entries if e["format"] == "new" and not e["draft"])
    old_count = sum(1 for e in entries if e["format"] == "old" and not e["draft"])
    draft_count = sum(1 for e in entries if e["draft"])
    print(f"   新格式: {new_count} 条")
    print(f"   旧格式: {old_count} 条")
    print(f"   草稿:   {draft_count} 条")
    print(f"   合计:   {len(entries)} 条")

    # ── 阶段二：DEDUP ──
    print("\n🔍 阶段二 DEDUP：去重检测...")
    deduped, stats = dedup(entries)
    print(f"   新格式保留:         {stats['new_count']}")
    print(f"   旧格式去重合并:     {stats['merged_count']}")
    print(f"   旧格式独立保留:     {stats['kept_new_count']}")
    print(f"   草稿剔除:           {stats['draft_count']}")
    if stats["draft_titles"]:
        print(f"   剔除草稿:           {stats['draft_titles']}")
    print(f"   去重后总数:         {len(deduped)}")

    # ── 阶段三：CLASSIFY ──
    print("\n📂 阶段三 CLASSIFY：按项目分组...")
    groups = classify(deduped)
    for project, entries in sorted(groups.items()):
        print(f"   {project}: {len(entries)} 条")

    # ── 阶段四：ASSIGN ──
    print("\n🔢 阶段四 ASSIGN：分配全局唯一编号...")
    groups, max_num = assign_numbers(groups)
    print(f"   最大编号: ADR-{max_num:03d}")

    # ── 阶段五：GENERATE ──
    print("\n✍️  阶段五 GENERATE：生成新 ADR.md...")
    total_entries = sum(len(v) for v in groups.values())
    new_text = generate(groups, total_entries)
    print(f"   共 {total_entries} 条 → 写入 {len(new_text)} 字符")

    if args.dry:
        print("\n🔹 DRY RUN 模式，未写入文件")
        issues = verify(new_text)
        if issues:
            print("\n⚠️  验证发现问题：")
            for issue in issues:
                print(f"  • {issue}")
        else:
            print("\n✅ 验证通过")
        return

    # ── 备份 ──
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    backup_path = os.path.join(BACKUP_DIR, f"ADR.md.{today}")
    shutil.copy2(ADR_PATH, backup_path)
    print(f"\n💾 备份已保存: {backup_path}")

    # ── 写入新文件 ──
    with open(ADR_PATH, "w", encoding="utf-8") as f:
        f.write(new_text)
    print("✅ 新 ADR.md 已写入")

    # ── 阶段六：VERIFY ──
    print("\n✅ 阶段六 VERIFY：自检...")
    issues = verify(new_text)
    if issues:
        print("⚠️  发现问题（需手动修复）：")
        for issue in issues:
            print(f"  • {issue}")
    else:
        print("   全部通过 ✅")

    # ── 最终统计 ──
    print(f"\n{'=' * 50}")
    print("重构完成")
    print(f"  条目数: {total_entries}")
    print(f"  备份:   {backup_path}")
    print(f"  输出:   {ADR_PATH}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    sys.exit(main())
