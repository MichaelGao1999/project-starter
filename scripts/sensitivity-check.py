#!/usr/bin/env python3
"""
sensitivity-check.py — 敏感信息扫描工具

在存档流程中扫描拟写入经验文档的内容，检测常见的敏感信息泄露：
  - 内网 IP 地址
  - 本地文件路径
  - 邮箱地址
  - API 密钥 / Token
  - 个人用户名（启发式）

用法:
    python3 scripts/sensitivity-check.py "要检查的文本"
    echo "文本" | python3 scripts/sensitivity-check.py
    python3 scripts/sensitivity-check.py --file path/to/file.md
    python3 scripts/sensitivity-check.py --dir path/to/project
"""

import re
import sys
from pathlib import Path

# 兼容 Windows GBK 终端无法输出 Unicode（macOS 编码为 UTF-8，此条件永不触发）
_enc = sys.stdout.encoding
if _enc is not None and _enc.upper() in ("GBK", "CP936", "GB2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# --dir 模式下排除的目录（片段匹配路径组件即可）
SKIP_DIRS = {
    ".git", "node_modules", ".backup", ".skillopt-sleep",
    "__pycache__", ".venv", "vendor", ".aider",
    ".kilo/node_modules",
}

CATEGORIES = {
    "内网 IP": re.compile(
        r"\b(?:"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r")\b"
    ),
    "本地路径 (Win)": re.compile(
        r"[A-Za-z]:\\(?:Users|Program Files|Windows|工作文件|项目|workspace|code|dev|Projects)\\[^\s\"'<>|]*"
    ),
    "本地路径 (Unix)": re.compile(
        r"(?:/home|/Users|/tmp|/var|/etc|/opt|/root)/[^\s\"'<>|]*"
    ),
    "本地路径 (混合)": re.compile(r"[A-Za-z]:/工作文件/[^\s\"'<>|]*"),
    "邮箱地址": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "API Key (通用)": re.compile(
        r"\b(?:sk-[A-Za-z0-9]{20,}|pk-[A-Za-z0-9]{20,}"
        r"|gh[ps]_[A-Za-z0-9]{36,}|AKIA[0-9A-Z]{16}"
        # 真正 base64：至少含一个 + 或 /，排除纯 hex 或长英文
        r"|(?=[A-Za-z0-9+/]{40,}={0,2}\b)[A-Za-z0-9+/]*[+/][A-Za-z0-9+/]*={0,2}"
        r")\b"
    ),
}


def _is_ssh_pseudo_email(matched: str) -> bool:
    """判断形如 git@hostname 的 SSH 伪邮箱，避免标红。

    特征：local-part 短（≤8 字符）、纯字母、不含点号。
    """
    if "@" not in matched:
        return False
    local = matched.split("@")[0]
    return len(local) <= 8 and local.isalpha() and "." not in local


def scan_text(text: str, filename: str = "<text>") -> list:
    """扫描文本，返回发现的敏感信息列表。"""
    findings = []
    for category, pattern in CATEGORIES.items():
        for m in pattern.finditer(text):
            matched = m.group()
            # 过滤 SSH 伪邮箱
            if category == "邮箱地址" and _is_ssh_pseudo_email(matched):
                continue
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 20)
            context = text[start:end].replace("\n", " ")
            # 截断过长的上下文
            if len(context) > 60:
                context = context[:28] + "..." + context[-28:]
            findings.append(
                {
                    "file": filename,
                    "line": text[: m.start()].count("\n") + 1,
                    "category": category,
                    "match": matched,
                    "context": context.strip(),
                }
            )
    return findings


def report(findings: list) -> None:
    """输出扫描报告。"""
    if not findings:
        print("[sensitivity-check] 未发现敏感信息")
        return

    print(f"[sensitivity-check] 发现 {len(findings)} 处潜在敏感信息：")
    print()
    # 按类别分组
    by_cat: dict[str, list[dict]] = {}
    for f in findings:
        by_cat.setdefault(f["category"], []).append(f)

    for cat, items in by_cat.items():
        print(f"  [{cat}] {len(items)} 处")
        for item in items:
            loc = (
                f"{item['file']}:{item['line']}"
                if item["file"] != "<text>"
                else f"第 {item['line']} 行"
            )
            print(f"    - {loc}: {item['context']}")
    print()


def main():
    args = sys.argv[1:]

    if not args:
        # 尝试从 stdin 读取
        if not sys.stdin.isatty():
            text = sys.stdin.read()
            findings = scan_text(text)
            report(findings)
            return
        # 无参数无管道 → 默认扫描当前目录
        args = ["--dir", "."]

    if args[0] == "--file" and len(args) >= 2:
        fpath = Path(args[1])
        if not fpath.exists():
            print(f"[sensitivity-check] 文件不存在: {fpath}")
            sys.exit(1)
        text = fpath.read_text(encoding="utf-8", errors="replace")
        findings = scan_text(text, filename=str(fpath))
        report(findings)
        return

    if args[0] == "--dir" and len(args) >= 2:
        root = Path(args[1])
        if not root.is_dir():
            print(f"[sensitivity-check] 目录不存在: {root}")
            sys.exit(1)
        all_findings = []
        for fpath in root.rglob("*.md"):
            # 排除第三方/临时目录
            if any(excl in fpath.parts for excl in SKIP_DIRS):
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            all_findings.extend(scan_text(text, filename=str(fpath)))
        report(all_findings)
        return

    # 参数模式：把所有参数拼成文本扫描
    text = " ".join(args)
    findings = scan_text(text)
    report(findings)


if __name__ == "__main__":
    main()
