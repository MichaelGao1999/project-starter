#!/usr/bin/env python3
"""分析三个知识文件中的重复/冗余条目

用法:
    python scripts/analyze-duplicates.py                    # 文本报告模式（默认）
    python scripts/analyze-duplicates.py --json             # 输出结构化 JSON
    python scripts/analyze-duplicates.py --threshold 0.6    # 自定义相似度阈值
    python scripts/analyze-duplicates.py --json --threshold 0.6  # 组合使用
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from utils import similarity
from markdown_parser import parse_adr, parse_lessons, parse_troubleshooting


def main() -> None:
    parser = argparse.ArgumentParser(description="分析三个知识文件中的重复/冗余条目")
    parser.add_argument(
        "--json", action="store_true", help="输出结构化 JSON（供 AI 复查消费）"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.85, help="相似度阈值，默认 0.85"
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parent.parent

    # 收集候选对（--json 模式使用）
    candidates: dict[str, list[Any]] = {"adr": [], "ll": [], "ts": []}

    def read(name):
        return (base / name).read_text(encoding="utf-8")

    # ========== ADR 分析 ==========
    print("=" * 70)
    print("ADR.md 分析 - 按 ADR 编号聚类")
    print("=" * 70)
    adr_content = read("ADR.md")
    # ========== [OLD PARSER - ADR - kept for verification per migration doc §4] ==========
    # adr_pattern = r"^#{2,3}\s+(?:(?:repo_\d+/)?(ADR-\d+))[:：]\s*(.+?)(?:\s*\[来源:([^\]]+)\])?\s*\n"
    # adr_entries = []
    # for m in re.finditer(adr_pattern, adr_content, re.MULTILINE):
    #     num = m.group(1).strip()
    #     title = m.group(2).strip()
    #     source = m.group(3).strip() if m.group(3) else ""
    #     line_start = adr_content[:m.start()].count("\n") + 1
    #     adr_entries.append({"num": num, "title": title, "source": source, "line": line_start})
    # ========== [END OLD PARSER] ==========
    adr_entries: list[dict[str, Any]] = []
    for e in parse_adr(adr_content):
        adr_entries.append(
            {
                "num": e["adr_id"],
                "title": e["title"],
                "source": " | ".join(e["sources"]) if e["sources"] else "",
                "line": e["line_start"],
            }
        )

    # 按 ADR 编号聚类
    adr_by_num: dict[str, list[dict[str, Any]]] = {}
    for e in adr_entries:
        adr_by_num.setdefault(e["num"], []).append(e)

    print(f"总条目数: {len(adr_entries)}")
    print(f"不同 ADR 编号数: {len(adr_by_num)}")
    print()

    dup_adrs = {k: v for k, v in adr_by_num.items() if len(v) > 1}
    if dup_adrs:
        print("发现重复 ADR 编号:")
        for k, v in dup_adrs.items():
            print(f"  {k} ({len(v)} 次):")
            for e in v:
                print(f"    L{e['line']:4d} | {e['title'][:60]} | 来源: {e['source']}")
    else:
        print("无重复 ADR 编号")

    # 标题相似度检测
    print(f"\n标题相似度检测 (sim > {args.threshold}):")
    for i in range(len(adr_entries)):
        for j in range(i + 1, len(adr_entries)):
            a, b = adr_entries[i], adr_entries[j]
            sim = similarity(a["title"], b["title"])
            if sim > args.threshold:
                print(f"  L{a['line']:4d} vs L{b['line']:4d} (sim={sim:.2f})")
                print(f"    {a['num']}: {a['title'][:60]}")
                print(f"    {b['num']}: {b['title'][:60]}")
                candidates["adr"].append(
                    {
                        "type": "similar",
                        "sim": round(sim, 4),
                        "a": {
                            "line": a["line"],
                            "id": a["num"],
                            "title": a["title"],
                            "sources": a["source"],
                        },
                        "b": {
                            "line": b["line"],
                            "id": b["num"],
                            "title": b["title"],
                            "sources": b["source"],
                        },
                    }
                )

    # ========== lessons-learned 分析 ==========
    print("\n" + "=" * 70)
    print("lessons-learned.md 分析")
    print("=" * 70)
    ll_content = read("lessons-learned.md")
    # ========== [OLD PARSER - Lessons - kept for verification per migration doc §4] ==========
    # ll_entries = []
    # for line_no, line in enumerate(ll_content.split("\n"), 1):
    #     line = line.rstrip()
    #     m = re.match(r"^\|\s*(\d+)\s*\|\s*(TAG:\S+(?:\s+TAG:\S+)*)\s*\|\s*(INFO|WARNING|CRITICAL|TIP)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|$", line)
    #     if m:
    #         desc = m.group(4).strip()
    #         clean_desc = re.sub(r"\s*\[来源:[^\]]+\]", "", desc).strip()
    #         clean_desc = re.sub(r"\s*\[母库[^\]]*\]", "", clean_desc).strip()
    #         sources = re.findall(r"\[来源:([^\]]+)\]", desc)
    #         mother_sources = re.findall(r"\[母库[^\]]*\]", desc)
    #         all_sources = sources + [m for m in mother_sources]
    #         ll_entries.append({
    #             "line": line_no,
    #             "tags": m.group(2).strip(),
    #             "severity": m.group(3).strip(),
    #             "desc": desc,
    #             "clean_desc": clean_desc[:200],
    #             "sources": " | ".join(all_sources)[:100],
    #             "module": m.group(5).strip(),
    #         })
    # ========== [END OLD PARSER] ==========
    ll_entries = []
    for e in parse_lessons(ll_content):
        # Skip list-type entries (not matched by old 5-column regex)
        if e.get("type") == "list":
            continue
        # Skip entries without a num (header or non-standard table format)
        if not e.get("num"):
            continue
        # Skip entries without TAG: prefix in tags (not matched by old 5-column regex)
        if not e["tags"].startswith("TAG:"):
            continue
        sources_str = " | ".join(e["sources"]) if e["sources"] else ""
        ll_entries.append(
            {
                "line": e["line_start"],
                "tags": e["tags"],
                "severity": e["severity"],
                "desc": e["description"],
                "clean_desc": re.sub(r"\s*\[母库[^\]]*\]", "", e["description_clean"])[
                    :200
                ],
                "sources": sources_str[:100],
                "module": e["module"],
            }
        )

    print(f"总条目数: {len(ll_entries)}")

    # 按内容相似度去重
    print(f"\n内容相似度检测 (sim > {args.threshold}):")
    seen: dict[str, dict[str, Any]] = {}
    dups_ll = []
    for e in ll_entries:
        key = e["clean_desc"].lower().strip()
        if key in seen:
            dups_ll.append((seen[key], e))
        else:
            seen[key] = e

    # 模糊匹配
    fuzzy_dups_ll = []
    for i in range(len(ll_entries)):
        for j in range(i + 1, len(ll_entries)):
            a, b = ll_entries[i], ll_entries[j]
            sim = similarity(a["clean_desc"][:120], b["clean_desc"][:120])
            if sim > args.threshold:
                fuzzy_dups_ll.append((a, b, sim))

    if dups_ll or fuzzy_dups_ll:
        print("精确重复:")
        for a, b in dups_ll[:20]:
            print(f"  L{a['line']:4d} vs L{b['line']:4d}")
            print(f"    {a['clean_desc'][:80]}")
            candidates["ll"].append(
                {
                    "type": "exact_dup",
                    "sim": 1.0,
                    "a": {
                        "line": a["line"],
                        "id": f"LL-{a['line']}",
                        "title": a["clean_desc"][:200],
                        "sources": a["sources"],
                    },
                    "b": {
                        "line": b["line"],
                        "id": f"LL-{b['line']}",
                        "title": b["clean_desc"][:200],
                        "sources": b["sources"],
                    },
                }
            )
        if len(dups_ll) > 20:
            print(f"  ... 还有 {len(dups_ll) - 20} 条")
        print("\n模糊相似:")
        for a, b, sim in fuzzy_dups_ll[:20]:
            print(f"  L{a['line']:4d} vs L{b['line']:4d} (sim={sim:.2f})")
            print(f"    A: {a['clean_desc'][:80]}")
            print(f"    B: {b['clean_desc'][:80]}")
            candidates["ll"].append(
                {
                    "type": "similar",
                    "sim": round(sim, 4),
                    "a": {
                        "line": a["line"],
                        "id": f"LL-{a['line']}",
                        "title": a["clean_desc"][:200],
                        "sources": a["sources"],
                    },
                    "b": {
                        "line": b["line"],
                        "id": f"LL-{b['line']}",
                        "title": b["clean_desc"][:200],
                        "sources": b["sources"],
                    },
                }
            )
        if len(fuzzy_dups_ll) > 20:
            print(f"  ... 还有 {len(fuzzy_dups_ll) - 20} 条")
    else:
        print("无明显重复")

    # ========== troubleshooting 分析 ==========
    print("\n" + "=" * 70)
    print("troubleshooting.md 分析")
    print("=" * 70)
    ts_content = read("troubleshooting.md")
    # ========== [OLD PARSER - Troubleshooting - kept for verification per migration doc §4] ==========
    # ts_entries = []
    # current_entry = None
    # current_category = ""
    # for line_no, line in enumerate(ts_content.split("\n"), 1):
    #     line = line.rstrip()
    #     if line.startswith("## ") and not line.startswith("### "):
    #         current_category = line[3:].strip()
    #         continue
    #     if line.startswith("### "):
    #         if current_entry:
    #             ts_entries.append(current_entry)
    #         title_line = line[4:].strip()
    #         clean_title = re.sub(r"\s*\[来源:[^\]]+\]", "", title_line).strip()
    #         sources = re.findall(r"\[来源:([^\]]+)\]", title_line)
    #         current_entry = {
    #             "line": line_no,
    #             "category": current_category,
    #             "title": clean_title,
    #             "title_raw": title_line,
    #             "sources": " | ".join(sources)[:100],
    #         }
    #
    # if current_entry:
    #     ts_entries.append(current_entry)
    # ========== [END OLD PARSER] ==========
    ts_entries = []
    for e in parse_troubleshooting(ts_content):
        sources_str = " | ".join(e["sources"]) if e["sources"] else ""
        ts_entries.append(
            {
                "line": e["line_start"],
                "category": e["category"],
                "title": e["keyword"],
                "title_raw": e["keyword_raw"],
                "sources": sources_str[:100],
            }
        )

    print(f"总条目数: {len(ts_entries)}")

    # 按标题相似度检测
    print(f"\n标题相似度检测 (sim > {args.threshold}):")
    ts_dups = []
    for i in range(len(ts_entries)):
        for j in range(i + 1, len(ts_entries)):
            a, b = ts_entries[i], ts_entries[j]
            sim = similarity(a["title"][:80], b["title"][:80])
            if sim > args.threshold:
                ts_dups.append((a, b, sim))

    if ts_dups:
        for a, b, sim in ts_dups[:30]:
            print(
                f"  L{a['line']:4d} vs L{b['line']:4d} (sim={sim:.2f}) | 分类: {a['category']} / {b['category']}"
            )
            print(f"    A: {a['title'][:80]}")
            print(f"    B: {b['title'][:80]}")
            print(f"    来源 A: {a['sources']} | 来源 B: {b['sources']}")
            print()
            candidates["ts"].append(
                {
                    "type": "similar",
                    "sim": round(sim, 4),
                    "a": {
                        "line": a["line"],
                        "id": f"TS-{a['line']}",
                        "title": a["title"],
                        "sources": a["sources"],
                        "category": a["category"],
                    },
                    "b": {
                        "line": b["line"],
                        "id": f"TS-{b['line']}",
                        "title": b["title"],
                        "sources": b["sources"],
                        "category": b["category"],
                    },
                }
            )
        if len(ts_dups) > 30:
            print(f"  ... 还有 {len(ts_dups) - 30} 条")
    else:
        print("无明显重复标题")

    # 精确标题重复
    title_seen: dict[str, dict[str, Any]] = {}
    exact_ts_dups = []
    for e in ts_entries:
        key = e["title"].lower().strip()[:80]
        if key in title_seen:
            exact_ts_dups.append((title_seen[key], e))
        else:
            title_seen[key] = e

    if exact_ts_dups:
        print("\n精确标题重复:")
        for a, b in exact_ts_dups[:20]:
            print(f"  L{a['line']:4d} vs L{b['line']:4d}")
            print(f"    {a['title'][:80]}")
            print(f"    来源 A: {a['sources']} | 来源 B: {b['sources']}")
            candidates["ts"].append(
                {
                    "type": "exact_dup",
                    "sim": 1.0,
                    "a": {
                        "line": a["line"],
                        "id": f"TS-{a['line']}",
                        "title": a["title"],
                        "sources": a["sources"],
                        "category": a["category"],
                    },
                    "b": {
                        "line": b["line"],
                        "id": f"TS-{b['line']}",
                        "title": b["title"],
                        "sources": b["sources"],
                        "category": b["category"],
                    },
                }
            )

    # ── JSON 输出（--json 模式）──
    if args.json:
        total = len(candidates["adr"]) + len(candidates["ll"]) + len(candidates["ts"])
        print("\n>>>JSON_START>>>")
        print(
            json.dumps(
                {
                    "source": str(base),
                    "threshold": args.threshold,
                    "total_candidates": total,
                    "adr_candidates": candidates["adr"],
                    "ll_candidates": candidates["ll"],
                    "ts_candidates": candidates["ts"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print("<<<JSON_END<<<")


if __name__ == "__main__":
    main()
