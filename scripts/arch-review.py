#!/usr/bin/env python3
"""
arch-review.py — 全项目架构审查脚本

对指定目录下的 Python 模块进行六维度架构分析：
  (1) 扫描目录树         — 按文件类型分组统计
  (2) 读取核心模块       — 提取每个模块的 imports + 职责摘要
  (3) 生成依赖图         — 分 stdlib / 第三方 / 项目内 三类
  (4) 找循环依赖         — DFS 回溯检测有向环
  (5) 找重复实现         — SequenceMatcher 逐对比对
  (6) 找过度耦合         — 按 import 数量排名

用法:
    python scripts/arch-review.py                    # 审查 scripts/
    python scripts/arch-review.py --dir .            # 审查整个项目
    python scripts/arch-review.py --dir scripts --dir starter/scripts  # 多目录
    python scripts/arch-review.py --summary          # 只看结论摘要
    python scripts/arch-review.py --threshold 0.8    # 相似度阈值（默认 0.7）
"""

import argparse
import ast
import re
import sys
from utils import similarity
from pathlib import Path
from typing import Any, Dict, List, Set, cast


# ─────────────────────────── 工具函数 ───────────────────────────


def _is_ignored(path: Path, root: Path) -> bool:
    """检查路径是否应被跳过（硬编码忽略模式，对齐项目 .gitignore）。"""
    rel = path.relative_to(root).as_posix()
    ignore_patterns = {
        ".git/",
        "__pycache__/",
        ".backup/",
        ".mimocode/",
        ".trae/",
        ".aider",
        "node_modules/",
        ".DS_Store",
        "memory.db",
        "memory.db-shm",
        "memory.db-wal",
    }
    for p in ignore_patterns:
        if p in rel or rel.endswith(p):
            return True
    return False


def _collect_py_files(dirs: List[Path], root: Path) -> List[Path]:
    """收集所有 .py 文件，跳过被忽略的路径。"""
    files = []
    seen = set()
    for d in dirs:
        if not d.is_dir():
            print(f"  ⚠️  目录不存在，跳过: {d}")
            continue
        for fpath in sorted(d.rglob("*.py")):
            if _is_ignored(fpath, root):
                continue
            if fpath not in seen:
                seen.add(fpath)
                files.append(fpath)
    return files


# ─────────────────────────── (1) 目录树扫描 ───────────────────────────


def scan_directory_tree(dirs: List[Path], root: Path) -> dict:
    """按文件类型分组扫描目录树。"""
    groups: Dict[str, List[Path]] = {
        "Python 脚本 (.py)": [],
        "Markdown 文档 (.md)": [],
        "Shell 脚本 (.sh / .bat)": [],
        "JSON 配置 (.json)": [],
        "其他": [],
    }
    EXT_MAP = {
        ".py": "Python 脚本 (.py)",
        ".md": "Markdown 文档 (.md)",
        ".sh": "Shell 脚本 (.sh / .bat)",
        ".bat": "Shell 脚本 (.sh / .bat)",
        ".json": "JSON 配置 (.json)",
    }

    scanned_dirs: Set[str] = set()
    for d in dirs:
        if not d.is_dir():
            continue
        for fpath in sorted(d.rglob("*")):
            if _is_ignored(fpath, root):
                continue
            if fpath.is_dir():
                scanned_dirs.add(str(fpath.relative_to(root)))
                continue
            ext = fpath.suffix.lower()
            group = EXT_MAP.get(ext, "其他")
            groups[group].append(fpath.relative_to(root))

    return {"groups": groups, "dirs": sorted(scanned_dirs)}


# ─────────────────────────── (2) 模块导入解析 ───────────────────────────

# Python 标准库集合（手工维护，覆盖项目中用到的所有模块）
STDLIB_MODULES = {
    "argparse",
    "ast",
    "asyncio",
    "base64",
    "collections",
    "csv",
    "datetime",
    "difflib",
    "enum",
    "functools",
    "glob",
    "hashlib",
    "html",
    "http",
    "importlib",
    "inspect",
    "io",
    "itertools",
    "json",
    "logging",
    "math",
    "multiprocessing",
    "operator",
    "os",
    "pathlib",
    "pickle",
    "platform",
    "pprint",
    "random",
    "re",
    "shutil",
    "signal",
    "socket",
    "sqlite3",
    "statistics",
    "string",
    "struct",
    "subprocess",
    "sys",
    "tempfile",
    "textwrap",
    "threading",
    "time",
    "traceback",
    "typing",
    "urllib",
    "uuid",
    "webbrowser",
    "xml",
    "zipfile",
}

# 本项目内部模块前缀（用于区分"项目内"和"第三方"）
INTERNAL_PREFIXES = ("scripts.", ".memory", ".memory.cli", "memory.cli")

# 项目内部模块名称集合（被其他脚本 import 时识别为内部依赖）
# 每次扫描时动态构建
_project_module_names: set = set()


def _build_project_module_names(py_files: List[Path], root: Path) -> set:
    """从已收集的 .py 文件中提取模块名（不含扩展名），用于识别内部依赖。"""
    names = set()
    for f in py_files:
        rel = f.relative_to(root)
        # scripts/utils.py → utils (取 stem)
        names.add(rel.stem)
        # scripts/utils.py → scripts.utils
        names.add(rel.with_suffix("").as_posix().replace("/", "."))
    return names


def parse_imports(filepath: Path) -> dict:
    """用 AST 解析 Python 文件的导入语句，返回三类依赖。"""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        return {
            "stdlib": [],
            "third_party": [],
            "internal": [],
            "error": f"SyntaxError: {e}",
        }
    except Exception as e:
        return {"stdlib": [], "third_party": [], "internal": [], "error": str(e)}

    stdlib: List[str] = []
    third_party: List[str] = []
    internal: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in STDLIB_MODULES:
                    stdlib.append(alias.name)
                elif (
                    alias.name.startswith(INTERNAL_PREFIXES)
                    or top in _project_module_names
                ):
                    internal.append(alias.name)
                else:
                    third_party.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            top = node.module.split(".")[0]
            imported_names = [a.name for a in node.names]
            label = f"{node.module} (导入 {len(imported_names)} 个)"
            if top in STDLIB_MODULES:
                stdlib.append(label)
            elif (
                node.module.startswith(INTERNAL_PREFIXES)
                or top in _project_module_names
            ):
                internal.append(label)
            else:
                third_party.append(label)

    return {
        "stdlib": stdlib,
        "third_party": third_party,
        "internal": internal,
        "error": None,
    }


def read_modules(py_files: List[Path], root: Path) -> List[dict[str, Any]]:
    """读取所有模块，提取导入信息和文档摘要（职责）。"""
    modules: List[dict[str, Any]] = []
    for fpath in py_files:
        rel = str(fpath.relative_to(root))
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            modules.append({"path": rel, "error": "读取失败"})
            continue

        # 提取文档字符串首行 → 作为模块职责摘要
        doc_first = ""
        m = re.match(r'(?:#!.+\n)?\s*"""(.+?)"""', text, re.DOTALL)
        if m:
            doc_first = m.group(1).strip().split("\n")[0][:80]

        # 判断是否有 shebang
        shebang = "yes" if text.startswith("#!/usr/bin/env python3") else "no"

        imports = parse_imports(fpath)

        modules.append(
            {
                "path": rel,
                "shebang": shebang,
                "doc": doc_first,
                "imports": imports,
            }
        )
    return modules


# ─────────────────────────── (3) 依赖图生成 ───────────────────────────


def build_dependency_graph(modules: List[dict]) -> dict:
    """生成三类依赖的图结构。"""
    graph: Dict[str, dict] = {}
    for m in modules:
        if m.get("error"):
            continue
        graph[m["path"]] = {
            "stdlib": sorted(set(m["imports"]["stdlib"])),
            "third_party": sorted(set(m["imports"]["third_party"])),
            "internal": sorted(set(m["imports"]["internal"])),
            "total_imports": len(m["imports"]["stdlib"])
            + len(m["imports"]["third_party"])
            + len(m["imports"]["internal"]),
        }
    return graph


def render_dependency_tree(graph: dict) -> str:
    """打印 ASCII 依赖树（按总依赖数倒序）。"""
    lines = []
    sorted_modules = sorted(
        graph.items(), key=lambda x: x[1]["total_imports"], reverse=True
    )

    for i, (path, deps) in enumerate(sorted_modules):
        prefix = "  └─ " if i == len(sorted_modules) - 1 else "  ├─ "
        dep_count = deps["total_imports"]
        lines.append(f"{prefix}{path}  ({dep_count} 个依赖)")

        if dep_count == 0:
            continue

        child_prefix = "     " if i == len(sorted_modules) - 1 else "  │  "

        # 项目内依赖
        if deps["internal"]:
            for d in deps["internal"]:
                lines.append(f"{child_prefix}├─ [内] {d}")
        # 第三方依赖
        if deps["third_party"]:
            for d in deps["third_party"]:
                lines.append(f"{child_prefix}├─ [三] {d}")
        # 标准库（只展示前 5 个，避免太长）
        if deps["stdlib"]:
            shown = 0
            for d in deps["stdlib"]:
                if shown < 5:
                    lines.append(f"{child_prefix}├─ [标] {d}")
                shown += 1
            if len(deps["stdlib"]) > 5:
                # 最后一条用 └─
                if not deps["internal"] and not deps["third_party"]:
                    lines[-1] = lines[-1].replace("├─", "└─")
                lines.append(
                    f"{child_prefix}└─ ... 另有 {len(deps['stdlib']) - 5} 个标准库模块"
                )
            else:
                # 标记最后一行
                pass  # 保持 ├─ 即可

    # 美化：将每个模块的最后一条 ├─ 改为 └─
    result = "\n".join(lines)
    # 对每个块最后一个条目做 └─ 替换（简化处理）
    return result


# ─────────────────────────── (4) 循环依赖检测 ───────────────────────────


def find_circular_deps(graph: dict) -> List[List[str]]:
    """DFS 回溯检测有向环。关注 internal（项目内）依赖。"""
    # 构建邻接表（只看 internal 引用）
    adj: Dict[str, List[str]] = {path: [] for path in graph}
    for path, deps in graph.items():
        for dep in deps["internal"]:
            # dep 是 "scripts.foo (导入 3 个)" 或 ".memory.cli.models" 格式
            mod_name = dep.split(" (")[0].strip()
            # 尝试在 graph 中匹配
            for p in graph:
                # 把 scripts.foo 转成 scripts/foo.py
                p_normalized = p.replace(".py", "").replace("/", ".")
                if mod_name.endswith(p_normalized) or p_normalized.endswith(mod_name):
                    adj[path].append(p)
                    break

    cycles = []
    visited: Set[str] = set()
    rec_stack: List[str] = []
    rec_set: Set[str] = set()

    def dfs(node: str):
        visited.add(node)
        rec_stack.append(node)
        rec_set.add(node)

        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_set:
                # 找到一个环
                idx = rec_stack.index(neighbor)
                cycle = rec_stack[idx:] + [neighbor]
                # 去重标准化
                cycle_min = min(cycle[:-1])
                min_idx = cycle.index(cycle_min)
                normalized = cycle[min_idx:-1] + cycle[:min_idx] + [cycle_min]
                cycles.append(normalized)

        rec_stack.pop()
        rec_set.discard(node)

    for node in adj:
        if node not in visited:
            dfs(node)

    # 去重（同一环的不同起始点）
    seen_cycles: Set[str] = set()
    unique_cycles = []
    for cycle in cycles:
        key = "→".join(cycle)
        if key not in seen_cycles:
            seen_cycles.add(key)
            unique_cycles.append(cycle)

    return unique_cycles


# ─────────────────────────── (5) 重复实现检测 ───────────────────────────


def _read_code_body(filepath: Path) -> str:
    """读取代码正文，去掉 shebang、文档字符串，保留核心内容。"""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    # 去掉 shebang 行
    if text.startswith("#!/usr/bin/env python3"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    # 去掉文档字符串（只去掉第一个）
    text = re.sub(r'^\s*""".+?"""', "", text, count=1, flags=re.DOTALL)
    return text.strip()


def find_duplicates(
    py_files: List[Path], root: Path, threshold: float = 0.7
) -> List[dict]:
    """逐对比较 Python 文件的代码相似度。"""
    main_scripts = [f for f in py_files if f.name != "__init__.py"]

    bodies = {}
    for f in main_scripts:
        body = _read_code_body(f)
        if len(body) > 100:  # 过短的文件（<100 字符）不参与比较
            bodies[f.relative_to(root).as_posix()] = body

    results = []
    paths = list(bodies.keys())
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            a, b = paths[i], paths[j]
            # 取前 2000 字符做相似度比较（避免超大文件 OOM）
            sim = similarity(bodies[a][:2000], bodies[b][:2000])
            if sim >= threshold:
                results.append(
                    {
                        "file_a": a,
                        "file_b": b,
                        "similarity": round(sim, 3),
                    }
                )

    results.sort(key=cast(Any, lambda x: x["similarity"]), reverse=True)
    return results


# ─────────────────────────── (6) 过度耦合检测 ───────────────────────────


def find_over_coupling(graph: dict) -> List[dict]:
    """按 import 总数排序，返回耦合度排名。"""
    rankings = []
    for path, deps in graph.items():
        rankings.append(
            {
                "path": path,
                "total": deps["total_imports"],
                "internal": len(deps["internal"]),
                "third_party": len(deps["third_party"]),
                "stdlib": len(deps["stdlib"]),
            }
        )

    rankings.sort(key=cast(Any, lambda x: x["total"]), reverse=True)
    return rankings


# ─────────────────────────── 报告输出 ───────────────────────────


def print_section(title: str, width: int = 72):
    """打印带标题的分隔线。"""
    (width - len(title) - 4) // 2
    print()
    print(" " + "─" * (width - 2))
    print(f"  {title}")
    print(" " + "─" * (width - 2))
    print()


def run_report(
    modules: List[dict],
    graph: dict,
    tree: dict,
    duplicates: List[dict],
    rankings: List[dict],
    cycles: List[List[str]],
    args,
):
    """输出完整的六维审查报告。"""
    summary_mode = args.summary
    threshold = args.threshold

    # ═══════════════════════ (1) 目录树 ═══════════════════════
    if not summary_mode:
        print_section("(1) 目录树扫描  📂")
        for group_name, files in tree["groups"].items():
            print(f"  • {group_name}: {len(files)} 个")
        print(f"\n  扫描了 {len(tree['dirs'])} 个子目录")

    # ═══════════════════════ (2) 核心模块 ═══════════════════════
    if not summary_mode:
        print_section("(2) 核心模块清单  📋")
        print(f"  {'模块路径':<45} {'Shebang':<8} {'依赖':<5} {'职责摘要'}")
        print(f"  {'─' * 45:<45} {'─' * 8:<8} {'─' * 5:<5} {'─' * 40}")
        for m in modules:
            if m.get("error"):
                print(f"  {m['path']:<45} {'❌  ' + m['error']:<52}")
                continue
            deps = m["imports"]
            total = (
                len(deps["stdlib"]) + len(deps["third_party"]) + len(deps["internal"])
            )
            sheb = "✓" if m["shebang"] == "yes" else "✗"
            doc = m.get("doc", "")[:50] or "(无文档)"
            print(f"  {m['path']:<45} {sheb:<8} {total:<5} {doc}")

    # ═══════════════════════ (3) 依赖图 ═══════════════════════
    if not summary_mode:
        print_section("(3) 依赖图（按依赖数倒序）  🔗")
        print(render_dependency_tree(graph))

    # ═══════════════════════ (4) 循环依赖 ═══════════════════════
    print_section("(4) 循环依赖检测  🔄")
    if not cycles:
        print("  ✅ 未检测到循环依赖")
        print("     （本项目的脚本均为独立入口，无跨文件引用，属于正常预期）")
    else:
        print(f"  ⚠️  发现 {len(cycles)} 个循环依赖：")
        for i, cycle in enumerate(cycles, 1):
            print(f"  {i}. {' → '.join(cycle)}")

    # ═══════════════════════ (5) 重复实现 ═══════════════════════
    print_section(f"(5) 重复实现检测（阈值 ≥ {threshold:.0%}）  🔍")
    if not duplicates:
        print(f"  ✅ 未发现相似度 ≥ {threshold:.0%} 的脚本对")
    else:
        print(f"  ⚠️  发现 {len(duplicates)} 对相似脚本：")
        print()
        for d in duplicates[:15]:
            sim_pct = f"{d['similarity']:.1%}"
            print(f"  {sim_pct:>6}  {d['file_a']}")
            print(f"           ↔ {d['file_b']}")
        if len(duplicates) > 15:
            print(f"\n  ... 还有 {len(duplicates) - 15} 对（调高 --threshold 过滤）")

    # ═══════════════════════ (6) 过度耦合 ═══════════════════════
    print_section("(6) 过度耦合分析  🔗📊")
    if not rankings:
        print("  （无数据）")
    else:
        print(
            f"  {'排名':<4} {'模块':<42} {'总依赖':<6} {'内部':<6} {'第三方':<6} {'标准库':<6}"
        )
        print(
            f"  {'─' * 4:<4} {'─' * 42:<42} {'─' * 6:<6} {'─' * 6:<6} {'─' * 6:<6} {'─' * 6:<6}"
        )
        for i, r in enumerate(rankings, 1):
            marker = " ⚠️" if r["total"] >= 10 else ""
            print(
                f"  {i:<4} {r['path']:<42} {r['total']:<6} {r['internal']:<6} {r['third_party']:<6} {r['stdlib']:<6}{marker}"
            )

        total = len(rankings)
        avg_deps = sum(r["total"] for r in rankings) / total if total else 0
        max_deps = rankings[0]
        print()
        print(f"  📊 平均依赖数: {avg_deps:.1f} / 模块")
        print(f"  📊 最高依赖: {max_deps['path']}（{max_deps['total']} 个）")
        heavy = [r for r in rankings if r["total"] >= 10]
        if heavy:
            print(f"  ⚠️  高耦合模块（≥10 依赖）: {len(heavy)} 个")
            for r in heavy:
                print(f"      - {r['path']} ({r['total']} 个依赖)")

    # ═══════════════════════ 总体评价 ═══════════════════════
    print_section("总体评价  📝")
    issues = 0
    if duplicates:
        issues += 1
    heavy = [r for r in rankings if r["total"] >= 10]

    if issues == 0 and not heavy:
        print("  ✅ 项目结构健康，未发现明显架构问题。")
        print()
        print(f"  审查完成：{len(modules)} 个模块，{len(graph)} 个依赖节点")
    else:
        if duplicates:
            print(f"  ⚠️  发现 {len(duplicates)} 对重复代码候选")
            print("     建议：提取公共工具函数到独立模块，减少复制粘贴")
        if heavy:
            print(f"  ⚠️  发现 {len(heavy)} 个高耦合模块（单模块 ≥10 个依赖）")
            print("     建议：拆分或抽取共用的低级工具模块")
        print()
        print(f"  审查完成：共扫描 {len(modules)} 个模块，{len(graph)} 个依赖节点")


# ─────────────────────────── 主入口 ───────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="全项目架构审查 — 扫描目录树·核心模块·依赖图·循环依赖·重复实现·过度耦合"
    )
    parser.add_argument(
        "--dir",
        "-d",
        action="append",
        default=[],
        help="审查目录（可多次指定，默认 scripts/）",
    )
    parser.add_argument("--summary", "-s", action="store_true", help="只输出结论摘要")
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.7,
        help="重复检测相似度阈值（0~1，默认 0.7）",
    )
    args = parser.parse_args()

    # 确定项目根目录
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    # 确定审查目录
    if not args.dir:
        dirs = [script_dir]  # 默认只审查 scripts/
    else:
        dirs = []
        for d in args.dir:
            p = Path(d)
            if not p.is_absolute():
                p = project_root / d
            dirs.append(p)

    # ── (1)+(2) 扫描+读取 ──
    py_files = _collect_py_files(dirs, project_root)
    tree = scan_directory_tree(dirs, project_root)
    # 构建项目模块名集合，用于识别内部依赖
    global _project_module_names
    _project_module_names = _build_project_module_names(py_files, project_root)
    modules = read_modules(py_files, project_root)

    # ── (3) 依赖图 ──
    graph = build_dependency_graph(modules)

    # ── (4) 循环依赖 ──
    cycles = find_circular_deps(graph)

    # ── (5) 重复实现 ──
    duplicates = find_duplicates(py_files, project_root, args.threshold)

    # ── (6) 过度耦合 ──
    rankings = find_over_coupling(graph)

    # ── 输出报告 ──
    run_report(modules, graph, tree, duplicates, rankings, cycles, args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
