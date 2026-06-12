#!/usr/bin/env python3
"""
跨项目知识聚合脚本
从 GitHub 用户/组织的所有仓库中拉取 ADR.md、lessons-learned.md、troubleshooting.md，
合并到本项目中，形成跨项目知识母库。

用法:
    python scripts/sync-knowledge.py [--config config/github-sync.json]

依赖:
    - gh CLI（需先 gh auth login）
    - requests（仅用于下载 raw 文件）
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, List, Optional, Union
from urllib.parse import quote

import requests


DEFAULT_CONFIG = "config/github-sync.json"
TARGET_FILES = ["ADR.md", "lessons-learned.md", "troubleshooting.md"]
RAW_GITHUB = "https://raw.githubusercontent.com"


def log(msg: str) -> None:
    print(f"[sync-knowledge] {msg}")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path: str, cfg: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def check_gh_auth() -> bool:
    """检查 gh CLI 是否已认证。"""
    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    return result.returncode == 0


def api_get(endpoint: str) -> Optional[Union[dict, list]]:
    """用 gh api 调用 GitHub API，自动复用 gh 登录态。"""
    try:
        result = subprocess.run(
            ["gh", "api", "--paginate", "--slurp", endpoint],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log(f"gh api 失败: {result.stderr.strip()}")
            return None
        return json.loads(result.stdout)
    except FileNotFoundError:
        log("错误: 未找到 gh CLI，请先安装: https://cli.github.com")
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        log(f"请求失败: {endpoint} -> {e}")
        return None


def fetch_raw(owner: str, repo: str, branch: str, filepath: str) -> Optional[str]:
    url = f"{RAW_GITHUB}/{owner}/{repo}/{branch}/{quote(filepath)}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        log(f"拉取失败: {url} -> {e}")
        return None


def list_repos(username: str) -> List[dict]:
    """列出用户所有仓库，gh api --paginate --slurp 自动处理翻页。"""
    endpoint = f"/users/{username}/repos"
    data = api_get(endpoint)
    if data is None:
        return []
    # --slurp 返回 [page1, page2, ...]，需展平
    if isinstance(data, list) and data and isinstance(data[0], list):
        flat = []
        for page in data:
            flat.extend(page)
        return flat
    return data


def filter_repos(repos: list[dict], include: list[str], exclude: list[str]) -> list[dict]:
    names = [r["name"] for r in repos]
    if include:
        names = [n for n in names if n in include]
    if exclude:
        names = [n for n in names if n not in exclude]
    return [r for r in repos if r["name"] in names]


def backup_file(path: Path) -> Optional[Path]:
    backup_dir = path.parent / ".backup"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}_{timestamp}{path.suffix}"
    if path.exists():
        shutil.copy2(path, backup_path)
        return backup_path
    return None


def parse_adr_entries(text: str) -> list[dict]:
    """从 ADR.md 中提取 ADR 条目。"""
    entries = []
    # 匹配 ## ADR-xxx: [标题] 开头的区块
    pattern = r"^## (ADR-\d+[:：]\s*.+?)\n(.*?)(?=\n## |\Z)"
    for m in re.finditer(pattern, text, re.MULTILINE | re.DOTALL):
        title = m.group(1).strip()
        body = m.group(2).strip()
        entries.append({"title": title, "body": body, "raw": m.group(0)})
    return entries


def parse_lesson_entries(text: str) -> list[dict]:
    """从 lessons-learned.md 中提取表格经验条目。"""
    entries = []
    # 匹配技术经验表格行 | 1 | [经验描述] | [来源模块] |
    for line in text.splitlines():
        m = re.match(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|$", line)
        if m and not line.strip().startswith("|---"):
            desc = m.group(1).strip()
            # 过滤模板内容和无意义条目
            if _is_valid_lesson(desc):
                entries.append({"description": desc, "source": m.group(2).strip()})
    # 也匹配列表形式的经验条目
    for line in text.splitlines():
        m = re.match(r"^[-*]\s+(.+)$", line)
        if m:
            desc = m.group(1).strip()
            if _is_valid_lesson(desc):
                entries.append({"description": desc, "source": ""})
    return entries


def _is_valid_lesson(desc: str) -> bool:
    """过滤掉模板占位符和明显不是经验的内容。"""
    if not desc or desc.startswith("[") and desc.endswith("]"):
        return False
    # 排除标准（模板内容）
    if desc.startswith("❌"):
        return False
    # 流程说明类
    if desc.startswith("**AI 助手**") or desc.startswith("**人类把控者**"):
        return False
    # 待验证假设 checkbox
    if re.match(r"^\[\s*[xX\s]\]\s*$", desc) or desc in ("[ ] xxx", "[ ] 无"):
        return False
    # 纯环境备忘（启动/优势/限制/完整功能验证等）
    if re.match(r"^\*\*(启动|优势|限制|完整功能验证)\*\*", desc):
        return False
    # 排除标准章节标题
    exclude_keywords = ["不记录的内容", "排除标准", "何时记录", "记录时机", "与 troubleshooting.md 的分界"]
    if any(kw in desc for kw in exclude_keywords):
        return False
    return True


def parse_trouble_entries(text: str) -> list[dict]:
    """从 troubleshooting.md 中提取问题条目。"""
    entries = []
    # 匹配 ### [错误关键词/标题] 开头的区块
    pattern = r"^### (.+?)\n(.*?)(?=\n### |\Z)"
    for m in re.finditer(pattern, text, re.MULTILINE | re.DOTALL):
        title = m.group(1).strip()
        body = m.group(2).strip()
        entries.append({"keyword": title, "body": body, "raw": m.group(0)})
    return entries


def read_local_file(path: Path) -> str:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度（0~1）。"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def merge_decisions(local_text: str, remote_entries: list[dict], repo_name: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    source_tag = f"[来源:{repo_name} @{today}]"
    blocks = []
    for e in remote_entries:
        new_block = f"## {e['title']} {source_tag}\n\n{e['body']}\n"
        title_clean = re.sub(r"\[来源:.+?\]", "", e["title"]).strip()

        # 精确去重
        if title_clean in local_text:
            log(f"  跳过已存在的决策: {title_clean}")
            continue

        # 相似度去重（检测语义重复）
        existing_titles = re.findall(r"^##\s+(.+?)$", local_text, re.MULTILINE)
        dup = False
        for existing in existing_titles:
            existing_clean = re.sub(r"\[来源:.+?\]", "", existing).strip()
            if _similarity(title_clean, existing_clean) > 0.75:
                log(f"  跳过相似决策: {title_clean}（与「{existing_clean}」相似度 {_similarity(title_clean, existing_clean):.0%}）")
                dup = True
                break
        if dup:
            continue

        blocks.append(new_block)
    if blocks:
        separator = "\n---\n\n" if local_text.strip() else ""
        return local_text.rstrip() + separator + "\n".join(blocks)
    return local_text


def merge_lessons(local_text: str, remote_entries: list[dict], repo_name: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    source_tag = f"[来源:{repo_name} @{today}]"
    added = 0
    skipped_similar = 0

    # 提取本地已有的经验描述
    existing_descs = re.findall(r"^\|\s*\|\s*(.+?)\s*(?:\[来源:.+?\])?\s*\|", local_text, re.MULTILINE)

    for e in remote_entries:
        desc = e["description"]
        if not desc or desc.startswith("[") and desc.endswith("]"):
            continue

        # 精确去重
        if desc in local_text:
            continue

        # 相似度去重
        dup = False
        for existing in existing_descs:
            existing_clean = re.sub(r"\[来源:.+?\]", "", existing).strip()
            if _similarity(desc, existing_clean) > 0.75:
                skipped_similar += 1
                dup = True
                break
        if dup:
            continue

        line_to_add = f"| | {desc} {source_tag} | {e.get('source', '')} |"
        table_end = local_text.rfind("|\n\n## ")
        if table_end == -1:
            table_end = len(local_text)
        local_text = local_text[:table_end] + line_to_add + "\n" + local_text[table_end:]
        added += 1

    if skipped_similar:
        log(f"  新增经验: {added} 条，跳过相似: {skipped_similar} 条")
    else:
        log(f"  新增经验: {added} 条")
    return local_text


def merge_troubleshooting(local_text: str, remote_entries: list[dict], repo_name: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    source_tag = f"[来源:{repo_name} @{today}]"
    blocks = []

    # 提取本地已有的关键词
    existing_keywords = re.findall(r"^###\s+(.+?)(?:\s+\[来源:.+?\])?$", local_text, re.MULTILINE)

    for e in remote_entries:
        keyword = e["keyword"]

        # 精确去重
        if keyword in local_text:
            log(f"  跳过已存在的问题: {keyword}")
            continue

        # 相似度去重
        dup = False
        for existing in existing_keywords:
            existing_clean = re.sub(r"\[来源:.+?\]", "", existing).strip()
            if _similarity(keyword, existing_clean) > 0.75:
                log(f"  跳过相似问题: {keyword}（与「{existing_clean}」相似度 {_similarity(keyword, existing_clean):.0%}）")
                dup = True
                break
        if dup:
            continue

        new_block = f"### {keyword} {source_tag}\n\n{e['body']}\n"
        blocks.append(new_block)
    if blocks:
        separator = "\n---\n\n" if local_text.strip() else ""
        return local_text.rstrip() + separator + "\n".join(blocks)
    return local_text


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def run_sync(config_path: str) -> int:
    if not check_gh_auth():
        log("错误: gh CLI 未认证，请先运行: gh auth login")
        return 1

    cfg = load_config(config_path)
    username = cfg.get("username", "").strip()
    include = cfg.get("includeRepos", [])
    exclude = cfg.get("excludeRepos", [])
    branch = cfg.get("branch", "main")
    backup = cfg.get("backupBeforeMerge", True)
    targets = cfg.get("targetFiles", TARGET_FILES)

    if not username:
        log("错误: config/github-sync.json 中 username 为空，请先填写 GitHub 用户名")
        return 1

    sync_from = cfg.get("syncFrom", "").strip()

    if sync_from:
        log(f"母库同步模式: 只从 {sync_from} 拉取更新")
        repo_info = api_get(f"/repos/{username}/{sync_from}")
        if not repo_info:
            log(f"错误: 无法获取仓库 {sync_from} 的信息")
            return 1
        repo_branch = repo_info.get("default_branch", branch)
        repos = [{"name": sync_from, "default_branch": repo_branch}]
        log(f"跳过其他仓库，只处理母库")
    else:
        log(f"开始聚合用户 {username} 的仓库知识...")
        repos = list_repos(username)
        repos = filter_repos(repos, include, exclude)
        log(f"发现 {len(repos)} 个目标仓库")

    stats = {"repos": 0, "files": 0, "entries": 0}

    for repo in repos:
        repo_name = repo["name"]
        repo_branch = repo.get("default_branch", branch)
        log(f"处理仓库: {repo_name} (分支: {repo_branch})")
        stats["repos"] += 1

        for fname in targets:
            raw = fetch_raw(username, repo_name, repo_branch, fname)
            if raw is None:
                continue
            stats["files"] += 1
            log(f"  拉取到 {fname} ({len(raw)} 字符)")

            local_path = Path(fname)
            if backup:
                backup_file(local_path)

            local_text = read_local_file(local_path)

            if fname == "ADR.md":
                entries = parse_adr_entries(raw)
                new_text = merge_decisions(local_text, entries, repo_name)
            elif fname == "lessons-learned.md":
                entries = parse_lesson_entries(raw)
                new_text = merge_lessons(local_text, entries, repo_name)
            elif fname == "troubleshooting.md":
                entries = parse_trouble_entries(raw)
                new_text = merge_troubleshooting(local_text, entries, repo_name)
            else:
                continue

            if new_text != local_text:
                write_file(local_path, new_text)
                stats["entries"] += len(entries)
                log(f"  已合并到 {fname}")
            else:
                log(f"  无新内容需要合并")

    log("=" * 40)
    log(f"聚合完成: {stats['repos']} 个仓库, {stats['files']} 个文件, 约 {stats['entries']} 个新条目")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="跨项目知识同步")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="配置文件路径")
    args = parser.parse_args()
    return run_sync(args.config)


if __name__ == "__main__":
    sys.exit(main())
