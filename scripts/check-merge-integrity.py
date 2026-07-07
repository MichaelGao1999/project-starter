#!/usr/bin/env python3
"""合并完整性校验：合并后检查远端侧文件是否意外丢失。

用法：
  python scripts/check-merge-integrity.py [--theirs <commit>] [--ours <commit>]

  默认行为：读取当前 HEAD，若为合并提交则自动取第一父为 --ours、第二父为 --theirs。

  退出码：
    0 — 全部通过
    1 — 存在意外丢失的文件（需人工审核）
    2 — 参数错误
"""

import argparse
import os
import re
import subprocess
import sys

# ── 已知在当前平台无法创建的字符（仅针对文件名/目录名，不含路径分隔符）──
_ILLEGAL_CHARS = {
    "win32": set('<>:"\\|?*'),
    "darwin": set(":"),
    "linux": set(),
}.get(sys.platform, set('<>:"\\|?*'))

# Windows 保留文件名（不区分扩展名，不区分大小写）
_ILLEGAL_PATTERNS = {
    "win32": {"CON", "PRN", "AUX", "NUL",
              *(f"COM{i}" for i in range(1, 10)),
              *(f"LPT{i}" for i in range(1, 10))},
    "darwin": set(),
    "linux": set(),
}.get(sys.platform, set())


def run_git(*args: str) -> str:
    """Run a git command, return stdout or raise."""
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


def is_path_legal(path: str) -> bool:
    """Return True if all path components can be created on this platform."""
    for part in path.split("/"):
        # 检查非法字符（仅针对组件名，不检查路径分隔符 /）
        if any(c in _ILLEGAL_CHARS for c in part):
            return False
        # 检查 Windows 保留名（仅检查纯文件名，不含点号部分）
        base = part.rsplit(".", 1)[0].upper() if "." in part else part.upper()
        if base in _ILLEGAL_PATTERNS:
            return False
    return True


def _decode_octal_escapes(s: str) -> str:
    """Decode git octal escape sequences (\\nnn) to Unicode.

    git diff --name-only uses octal escapes for non-ASCII characters
    when core.quotepath=true.  e.g. \\344\\277\\256 -> 修.
    """
    if not s or '\\' not in s:
        if s.startswith('"') and s.endswith('"'):
            return s[1:-1]
        return s
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]

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


def get_merge_parents() -> tuple[str, str]:
    """Return (ours, theirs) commit hashes for current HEAD.

    - Merge commit (2 parents): parents[0]=ours, parents[1]=theirs
    - Fast-forward (1 parent): HEAD@{1}=ours (pre-pull), HEAD=theirs (post-pull)
    """
    # 尝试获取 reflog 上一个位置（对 merge 和 fast-forward 均有效）
    try:
        ours_prev = run_git("rev-parse", "--verify", "HEAD@{1}")
    except (SystemExit, subprocess.TimeoutExpired):
        ours_prev = None

    parents = run_git("log", "-1", "--format=%P").split()

    if len(parents) == 2:
        return parents[0], parents[1]  # merge commit

    if len(parents) == 1 and ours_prev:
        # Fast-forward: HEAD 线性前进，HEAD@{1}=pre-pull, HEAD=post-pull
        # parents[0] 等于旧 HEAD（fast-forward 中旧 HEAD 成为新 HEAD 的父）
        current_head = run_git("rev-parse", "HEAD")
        if ours_prev != current_head:
            print("Fast-forward 检测到，使用 HEAD@{1} 作为 pull 前位置")
            return ours_prev, current_head

    print("ERROR: HEAD 不是合并提交，也无法检测 fast-forward。")
    print("  HEAD@{1} 不存在或与当前 HEAD 相同（可能无远端变化）。")
    print("  使用 --ours 和 --theirs 手动指定。")
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="合并完整性校验")
    parser.add_argument("--theirs", help="被合并的远端提交（默认：HEAD 的第二父）")
    parser.add_argument("--ours", help="合并前的本地提交（默认：HEAD 的第一父）")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示所有检查项")
    args = parser.parse_args()

    ours = args.ours
    theirs = args.theirs

    if ours and theirs:
        pass
    elif ours or theirs:
        print("ERROR: --ours 和 --theirs 必须同时提供或同时省略。")
        sys.exit(2)
    else:
        ours, theirs = get_merge_parents()

    # 1. 获取 merge base
    base = run_git("merge-base", ours, theirs)
    print(f"ours:   {ours[:7]}")
    print(f"theirs: {theirs[:7]}")
    print(f"base:   {base[:7]}")
    print()

    # 2. 列出 theirs 相对于 base 新增/修改的文件（排除删除，删除是预期行为）
    changed = run_git("diff", "--name-only", "--diff-filter=AMRC", base, theirs).splitlines()

    # 3. 检查每个文件是否存在于当前工作树
    missing = []
    illegal = []
    ok_count = 0

    for path in changed:
        if not path.strip():
            continue
        # Decode octal escapes before checking legality and existence.
        # On Windows git diff quotes non-ASCII as \nnn, and the literal
        # \ would falsely trigger the illegal-char check.
        decoded = _decode_octal_escapes(path)
        if not is_path_legal(decoded):
            illegal.append(decoded)
            if args.verbose:
                print(f"  SKIP (OS illegal): {decoded}")
            continue
        if os.path.exists(decoded):
            ok_count += 1
            if args.verbose:
                print(f"  OK: {decoded}")
        else:
            missing.append(decoded)
            print(f"  MISSING: {decoded}")

    print()
    print(f"总计: {len(changed)} 个文件")
    print(f"  通过: {ok_count}")
    print(f"  OS 不兼容（预期跳过）: {len(illegal)}")
    print(f"  意外丢失: {len(missing)}")

    if illegal:
        print()
        print("OS 不兼容文件（可安全忽略）:")
        for p in illegal:
            print(f"  {p}")

    if missing:
        print()
        print("以下文件意外丢失，需恢复：")
        for p in missing:
            print(f"  {p}")
        print()
        print("恢复命令示例：")
        print(f"  git checkout {theirs[:7]} -- {' '.join(missing[:5])}")
        if len(missing) > 5:
            print(f"  ... 等 {len(missing)} 个文件")
        sys.exit(1)
    else:
        print("合并完整性检查通过。")
        sys.exit(0)


if __name__ == "__main__":
    sys.exit(main())
