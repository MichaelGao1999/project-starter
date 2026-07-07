#!/usr/bin/env python3
"""合并前文件名预检：扫描远端文件是否含当前 OS 非法字符。

用法：
  python scripts/pre-merge-check.py <remote-branch>

  在 git pull / git merge 之前运行，检测被合并分支中是否存在
  当前文件系统无法创建的文件。命中后给出安全替代方案（merge-tree）。

  退出码：
    0 — 通过（无兼容性问题）
    1 — 发现不兼容文件（已给出 merge-tree 替代命令）
    2 — 参数错误
"""

import argparse
import os
import re
import subprocess
import sys

# ── 当前平台的非法字符和保留名 ──
_ILLEGAL_CHARS = {
    "win32": set('<>:"\\|?*'),
    "darwin": set(":"),
    "linux": set(),
}.get(sys.platform, set('<>:"\\|?*'))

_ILLEGAL_PATTERNS = {
    "win32": {"CON", "PRN", "AUX", "NUL",
              *(f"COM{i}" for i in range(1, 10)),
              *(f"LPT{i}" for i in range(1, 10))},
    "darwin": set(),
    "linux": set(),
}.get(sys.platform, {"CON", "PRN", "AUX", "NUL"})


def run_git(*args: str) -> str:
    r = subprocess.run(
        ["git"] + list(args),
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    if r.returncode != 0:
        sys.stderr.write(f"git {' '.join(args)} failed: {r.stderr.strip()}\n")
        sys.exit(2)
    return r.stdout.strip()


def is_component_legal(name: str) -> bool:
    """Check if a single path component (file or dir name) is legal."""
    if any(c in _ILLEGAL_CHARS for c in name):
        return False
    base = name.rsplit(".", 1)[0].upper() if "." in name else name.upper()
    if base in _ILLEGAL_PATTERNS:
        return False
    return True


def find_illegal_paths(branch: str) -> list[str]:
    """Return paths in branch that can't be created on this platform."""
    ours = run_git("rev-parse", "HEAD")
    their_tree = run_git("rev-parse", f"{branch}^{{tree}}")

    # 列出分支中所有文件（相对于我们的 HEAD）
    changed = run_git(
        "diff", "--name-only", "--diff-filter=AMRC",
        ours, branch
    ).splitlines()

    illegal = []
    for path in changed:
        if not path.strip():
            continue
        # Strip git quoting and decode octal escapes.
        # On Windows, git diff outputs non-ASCII paths as \nnn
        # (core.quotepath=true), and the literal \ would be mistaken
        # for an OS-illegal character.
        decoded = _decode_octal_escapes(path)
        for part in decoded.split("/"):
            if not is_component_legal(part):
                illegal.append(decoded)
                break
    return illegal


def _decode_octal_escapes(s: str) -> str:
    """Decode git octal escape sequences (\\nnn) to Unicode.

    git diff --name-only uses octal escapes for non-ASCII characters
    when core.quotepath=true (the default on Windows).
    e.g. \\344\\277\\256 -> 修.
    """
    if not s or '\\' not in s:
        # Strip git quoting ("path") if present
        if s.startswith('"') and s.endswith('"'):
            return s[1:-1]
        return s

    # Strip git quoting before decoding octal escapes
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]

    # Collect all octal-escaped bytes, then decode as UTF-8 unit
    parts = []
    last_end = 0
    for m in re.finditer(r"\\(\d{3})", s):
        parts.append(s[last_end:m.start()])
        parts.append(chr(int(m.group(1), 8)))
        last_end = m.end()
    parts.append(s[last_end:])

    result = []
    byte_buf = bytearray()
    for part in parts:
        for ch in part:
            code = ord(ch)
            if code > 127:
                byte_buf.append(code)
            else:
                if byte_buf:
                    result.append(byte_buf.decode("utf-8", errors="replace"))
                    byte_buf.clear()
                result.append(ch)
    if byte_buf:
        result.append(byte_buf.decode("utf-8", errors="replace"))
    return "".join(result)


def main():
    parser = argparse.ArgumentParser(
        description="合并前文件名预检 — 检测远端文件是否含当前 OS 非法字符"
    )
    parser.add_argument("branch", help="被合并的远端分支（如 origin/main）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出结果（供脚本消费）")
    args = parser.parse_args()

    ours = run_git("rev-parse", "HEAD")

    if not args.json:
        print(f"当前 HEAD:  {ours[:7]}")
        print(f"目标分支:  {args.branch}")
        print(f"当前平台:  {sys.platform}")
        if _ILLEGAL_CHARS:
            chars = " ".join(repr(c) for c in sorted(_ILLEGAL_CHARS))
            print(f"非法字符:  {chars}")
        print()

    illegal = find_illegal_paths(args.branch)

    if args.json:
        import json
        result = {
            "status": "blocked" if illegal else "ok",
            "illegal_count": len(illegal),
            "illegal_paths": illegal,
            "platform": sys.platform,
            "merge_tree_command": generate_merge_tree_command(args.branch),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1 if illegal else 0)

    if illegal:
        print(f"发现 {len(illegal)} 个无法在当前文件系统创建的文件:")
        for p in illegal:
            print(f"  {p}")
        print()
        print("禁止使用 git merge / git pull，改用对象空间合并:")
        print()
        print(generate_merge_tree_command(args.branch))
        print()
        print("合并后运行完整性检查:")
        print(f"  python scripts/check-merge-integrity.py")
        sys.exit(1)
    else:
        print("通过 — 未发现文件系统兼容性问题。可以正常 git merge。")
        sys.exit(0)


def generate_merge_tree_command(branch: str) -> str:
    """Generate the safe merge-tree command."""
    theirs = run_git("rev-parse", branch).strip()[:7]
    ours = run_git("rev-parse", "HEAD").strip()[:7]
    return (
        f"# Step 1: 对象空间合并\n"
        f"git merge-tree --write-tree -X theirs HEAD {branch}\n"
        f"\n"
        f"# Step 2: 过滤非法文件名，创建最终树\n"
        f"FILTERED_TREE=$(git ls-tree -r <MERGE_TREE_HASH> | grep -v '<ILLEGAL_PATTERN>' | git mktree)\n"
        f"\n"
        f"# Step 3: 创建合并提交\n"
        f"git commit-tree $FILTERED_TREE -p HEAD -p {branch} -m \"merge {branch}: (safe, OS-incompatible files excluded)\"\n"
        f"\n"
        f"# Step 4: 检出\n"
        f"git reset --hard <COMMIT_HASH>\n"
        f"\n"
        f"# Step 5: 完整性检查\n"
        f"python scripts/check-merge-integrity.py\n"
        f"\n"
        f"参考: scripts/check-merge-integrity.py, AGENTS.md RULE-15"
    )


if __name__ == "__main__":
    sys.exit(main())
