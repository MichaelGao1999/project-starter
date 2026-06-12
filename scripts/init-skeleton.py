#!/usr/bin/env python3
"""
骨架一键初始化脚本
从 GitHub 拉取 starter/ 全部文件到目标项目目录。

用法:
    python init-skeleton.py [--force] [--target TARGET_DIR]
"""

import argparse
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Optional, Tuple

RAW_BASE = "https://raw.githubusercontent.com/MichaelGao1999/project-starter/main"

# 从 starter/ 拉取的全部文件（路径相对于 starter/ 目录）
STARTER_FILES = [
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "anti-patterns-checklist.md",
    "config/github-sync.json",
    "ADR.md",
    "install.py",
    "lessons-learned.md",
    "scripts/sync-knowledge.py",
    "session-log.md",
    "status.md",
    "troubleshooting.md",
    "agent-coding-workflow.md",
]

CODE_INDICATORS = [
    "src", "lib", "app", "dist", "build",
    ".git", "package.json", "Cargo.toml", "pyproject.toml",
    "go.mod", "pom.xml", "CMakeLists.txt", "Makefile",
]

ENTRY_POINT_OPTIONS = {
    "1": ("AGENTS.md", "opencode"),
    "2": ("CLAUDE.md", "Claude Code"),
    "3": ("REASONIX.md", "Reasonix (DeepSeek)"),
}


def log(msg: str) -> None:
    print(f"[init-skeleton] {msg}")


def error(msg: str) -> None:
    print(f"[init-skeleton] ERROR: {msg}", file=sys.stderr)


def detect_conflicts(target_dir: Path) -> List[str]:
    conflicts = []
    for fname in STARTER_FILES:
        if (target_dir / fname).exists():
            conflicts.append(fname)
    return conflicts


def detect_existing_code(target_dir: Path) -> bool:
    for indicator in CODE_INDICATORS:
        if (target_dir / indicator).exists():
            return True
    for ext in [".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs", ".cpp", ".c", ".h"]:
        if list(target_dir.glob(f"*{ext}")):
            return True
    return False


def ensure_parent_dir(dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)


def prompt_entry_point() -> str:
    print()
    print("  No AGENTS.md found. Create it, or export to a different filename?")
    for key, (fname, desc) in ENTRY_POINT_OPTIONS.items():
        print(f"    {key}) {fname}  \u2014 {desc}")
    print(f"    4) Custom")
    choice = input("  Enter choice [1]: ").strip() or "1"
    if choice == "4":
        custom = input("  Enter filename (e.g., CURSOR.md): ").strip()
        return custom if custom else "AGENTS.md"
    return ENTRY_POINT_OPTIONS.get(choice, ("AGENTS.md",))[0]


def fetch_text(url: str) -> Optional[str]:
    try:
        resp = urllib.request.urlopen(url)
        return resp.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def download_file(url: str, dst: Path, force: bool = False) -> str:
    if dst.exists() and not force:
        return "skipped"
    try:
        ensure_parent_dir(dst)
        urllib.request.urlretrieve(url, dst)
        return "created"
    except urllib.error.HTTPError as e:
        error(f"下载失败 {url}: HTTP {e.code}")
        return "error"
    except urllib.error.URLError as e:
        error(f"下载失败 {url}: {e.reason}")
        return "error"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 GitHub 拉取 project-starter 骨架基础设施"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖目标目录已有的同名文件",
    )
    parser.add_argument(
        "--target",
        default=".",
        help="目标项目目录（默认当前目录）",
    )
    args = parser.parse_args()

    target_dir = Path(args.target).resolve()
    if not target_dir.is_dir():
        error(f"目标目录不存在: {target_dir}")
        return 1

    log(f"从 GitHub 拉取骨架...")
    log(f"目标路径: {target_dir}")

    # 检测冲突
    conflicts = detect_conflicts(target_dir)
    if conflicts and not args.force:
        log(f"检测到以下文件已存在，将跳过（使用 --force 覆盖）: {', '.join(conflicts)}")

    # 确定入口文件名
    entry_filename = "AGENTS.md"
    if not (target_dir / "AGENTS.md").exists():
        entry_filename = prompt_entry_point()
    else:
        log("检测到 AGENTS.md 已存在")

    results: List[Tuple[str, str]] = []

    # 确定文件列表
    files_to_fetch = list(STARTER_FILES)
    if entry_filename != "AGENTS.md":
        files_to_fetch = [f for f in STARTER_FILES if f != "AGENTS.md"]

    # 从 starter/ 拉取
    for fname in files_to_fetch:
        url = f"{RAW_BASE}/starter/{fname}"
        dst = target_dir / fname
        result = download_file(url, dst, args.force)
        results.append((fname, result))

    # 如用户选了非 AGENTS.md 的入口文件，拉取 AGENTS.md 内容合并
    if entry_filename != "AGENTS.md":
        agents_url = f"{RAW_BASE}/starter/AGENTS.md"
        agents_content = fetch_text(agents_url)
        if agents_content:
            dst = target_dir / entry_filename
            ensure_parent_dir(dst)
            if dst.exists():
                old_content = dst.read_text()
                merged = (agents_content.rstrip("\n") +
                          "\n\n---\n*以上为 agent-coding-skeleton 工作流规则，以下为项目原始内容*\n---\n\n" +
                          old_content)
            else:
                merged = agents_content
            dst.write_text(merged)
            results.append((entry_filename, "created"))
        else:
            error(f"获取 AGENTS.md 内容失败，无法创建 {entry_filename}")
            results.append((entry_filename, "error"))


    # 输出报告
    print("\n" + "=" * 50)
    print("初始化报告")
    print("=" * 50)

    created = [f for f, r in results if r == "created"]
    skipped = [f for f, r in results if r == "skipped"]
    errors = [f for f, r in results if r == "error"]

    if created:
        print(f"\n[+] 已创建 ({len(created)}):")
        for f in created:
            print(f"    {f}")

    if skipped:
        print(f"\n[-] 已跳过 ({len(skipped)})（使用 --force 可覆盖）:")
        for f in skipped:
            print(f"    {f}")

    if errors:
        print(f"\n[!] 失败 ({len(errors)}):")
        for f in errors:
            print(f"    {f}")

    if detect_existing_code(target_dir):
        print("\n[i] 提示: 检测到目标目录已有代码文件。")
        print("    建议从 agent-coding-workflow.md 阶段五开始，让 AI 逆向补全文档。")

    print(f"\n[>] 下一步:")
    print(f"    1. 编辑 {entry_filename}，按项目填空（项目名、技术栈等）")
    print("    2. 读取 agent-coding-workflow.md，判断项目当前阶段")
    print("    3. 按 SOP 五阶段推进")
    if not (target_dir / "AGENTS.md").resolve().parent.parent.name == "agent-coding-skeleton":
        print(f"    4. 记得将本新项目加入母库的 config/downstream-projects.json，以便后续分发覆盖")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
