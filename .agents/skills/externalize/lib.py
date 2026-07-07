#!/usr/bin/env python3
"""
externalize 共享工具库。
多脚本模式共享：路径解析、文件IO、SKILL.md解析、AGENTS.md操作、归档、诊断。
"""

import re
import shutil
from pathlib import Path
from typing import Optional, List

# ── 路径常量 ──

SKILLS_DIR_NAME = ".agents/skills"
WORKFLOWS_DIR_NAME = "docs/workflows"
AGENTS_FILENAME = "AGENTS.md"


def _find_root() -> Path:
    start = Path.cwd()
    for parent in [start] + list(start.parents):
        if (parent / AGENTS_FILENAME).exists():
            return parent
    raise FileNotFoundError(f"找不到仓库根目录（未发现 {AGENTS_FILENAME}）")


ROOT: Path = _find_root()


def skill_dir(name: str) -> Path:
    return ROOT / SKILLS_DIR_NAME / name


def archived_dir(name: str) -> Path:
    return ROOT / SKILLS_DIR_NAME / "_archived" / name


def workflow_path(name: str) -> Path:
    return ROOT / WORKFLOWS_DIR_NAME / f"{name}.md"


def workflow_dir_path(name: str) -> Path:
    return ROOT / WORKFLOWS_DIR_NAME / name


# ── 文件 I/O（RULE-14 编码）──

def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── SKILL.md 解析（从旧 externalize.py 移植）──

def parse_frontmatter(text: str) -> dict:
    """Parse YAML-like frontmatter between --- markers."""
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return {}
    fm: dict = {}
    for line in match.group(1).split('\n'):
        line = line.strip()
        if ':' in line:
            key, _, value = line.partition(':')
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def extract_trigger_words(description: str) -> list[str]:
    """从 description 提取触发词：中文引号或英文引号内的内容"""
    words = re.findall(r'["""]\s*(.+?)\s*["»"]', description)
    words += re.findall(r'"(.+?)"', description)
    seen: set = set()
    result: list = []
    for w in words:
        w = w.strip()
        if w and w not in seen:
            seen.add(w)
            result.append(w)
    return result


def extract_body(text: str) -> str:
    """提取 frontmatter 之后的正文"""
    match = re.search(r'^---\s*\n.*?\n---\s*\n(.*)', text, re.DOTALL)
    if not match:
        return text
    return match.group(1).strip()


def extract_action_section(body: str) -> str:
    """从正文提取编号动作步骤，包装为 ## 标准动作"""
    lines = body.split('\n')
    numbered_steps = [l.strip() for l in lines if re.match(r'^\d+[.、)]\s', l.strip())]
    if numbered_steps:
        return "## 标准动作\n\n" + '\n'.join(numbered_steps) + '\n'

    h1_end = re.search(r'^#\s+.*?\n', body)
    remaining = body[h1_end.end():].strip() if h1_end else body.strip()
    remaining = re.sub(r'^#{2,4}\s+.*?\n', '', remaining, flags=re.MULTILINE).strip()
    if remaining:
        return f"## 标准动作\n\n{remaining}\n"
    return "## 标准动作\n\n1. 参考原始 skill\n"


def get_sections(text: str) -> List[str]:
    """提取 SKILL.md 中的 H2 章节标题"""
    return re.findall(r"^##\s+(.+)$", text, re.MULTILINE)


def read_skill_text(name: str) -> str:
    """读取 skill 完整文本（优先当前，回退归档）"""
    for base in (skill_dir(name), archived_dir(name)):
        path = base / "SKILL.md"
        if path.exists():
            return read_file(path)
    raise FileNotFoundError(f"找不到 skill {name} 的 SKILL.md")


def read_skill_meta(name: str) -> dict:
    """读取 skill 的 frontmatter"""
    return parse_frontmatter(read_skill_text(name))


# ── 技能类型诊断 ──

SKILL_TYPES = {
    "mental_model": "心智模型",
    "single_tool": "单模式工具型",
    "packaged": "打包技能",
}


def diagnose_type(text: str) -> str:
    """根据 SKILL.md 全文判断技能类型"""
    meta = parse_frontmatter(text)
    desc = (meta.get("description", "") + " " + meta.get("description_zh", "")).lower()
    body = text.lower()

    mental_score = sum(1 for kw in [
        "persistent", "every response",
        "始终开启", "每轮响应", "自动激活", "无需调用",
    ] if kw in body or kw in desc)

    packaged_score = sum(1 for kw in [
        "mode", "模式选择", "| 模式 |", "多种模式",
    ] if kw in body or kw in text)

    h2_count = len(get_sections(text))

    if mental_score >= 2 and packaged_score == 0:
        return "mental_model"
    if packaged_score >= 2 or (h2_count >= 4 and mental_score < 2):
        return "packaged"
    return "single_tool"


def format_diagnosis(name: str, skill_type: str, sections: List[str]) -> str:
    cn = SKILL_TYPES.get(skill_type, "未知类型")
    lines = [
        f"## 技能诊断：{name}",
        "",
        f"**类型**: {cn} (`{skill_type}`)",
        f"**H2 章节数**: {len(sections)}",
    ]
    if sections:
        lines.append("**子章节**:")
        for s in sections:
            lines.append(f"  - {s}")
    if skill_type == "mental_model":
        lines.extend(["", "> ⚠️ 该技能是心智模型，通常不适合外部化。但仍由你决定。"])
    elif skill_type == "packaged":
        lines.extend(["", "> 📦 打包技能，建议拆分为目录结构。每个子模式独立文件。"])
    else:
        lines.extend(["", "> 🔧 单模式工具型，可外部化为 1 个 workflow 文件。"])
    return "\n".join(lines)


# ── AGENTS.md 操作 ──

def find_trigger_section(text: str) -> Optional[int]:
    for i, line in enumerate(text.splitlines()):
        if re.match(r"^##\s+技能索引\s*$", line):
            return i
    return None


def add_trigger_entry(trigger_words: str, doc_path: str) -> bool:
    """在 AGENTS.md 技能索引区添加触发条目。已存在则跳过。找不到章节时自动创建。"""
    agents_path = ROOT / AGENTS_FILENAME
    text = read_file(agents_path)
    entry = f"- `{trigger_words}` → `{doc_path}`"

    if entry in text:
        return False

    idx = find_trigger_section(text)

    if idx is not None:
        # 已有章节：在末尾插入
        lines = text.splitlines()
        insert_at = len(lines)
        for i in range(idx + 1, len(lines)):
            if re.match(r"^##\s", lines[i]):
                insert_at = i
                break
        lines.insert(insert_at, entry)
        write_file(agents_path, "\n".join(lines))
    else:
        # 无章节：在文件尾追加
        lines = text.splitlines()
        # 去掉末尾空行
        while lines and lines[-1].strip() == "":
            lines.pop()
        lines.extend(["", "---", "", "## 技能索引", "", entry, ""])
        write_file(agents_path, "\n".join(lines))

    return True


def remove_trigger_entry(name: str) -> bool:
    """从 AGENTS.md 移除含 name 的触发条目。按 workflow 路径模式匹配，避免子串误杀。"""
    text = read_file(ROOT / AGENTS_FILENAME)
    lines = text.splitlines()
    new_lines = []
    found = False
    target = f"→ `{WORKFLOWS_DIR_NAME}/{name}"
    for line in lines:
        if not found and target in line:
            found = True
            continue
        new_lines.append(line)
    if found:
        write_file(ROOT / AGENTS_FILENAME, "\n".join(new_lines))
    return found


# ── 归档 ──

def archive_skill(name: str) -> Path:
    """将 skill 移动到 _archived 目录"""
    src = skill_dir(name)
    dst = archived_dir(name)
    if not src.exists():
        raise FileNotFoundError(f"skill 目录不存在: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            shutil.rmtree(str(dst))
        except OSError as e:
            print(f"⚠️ 清理目标归档目录失败: {e}")
    shutil.copytree(str(src), str(dst))
    try:
        shutil.rmtree(str(src))
    except OSError as e:
        print(f"⚠️ 删除源 skill 目录失败: {e}")
    return dst


def unarchive_skill(name: str) -> Path:
    """从 _archived 恢复 skill"""
    src = archived_dir(name)
    dst = skill_dir(name)
    if not src.exists():
        raise FileNotFoundError(f"归档不存在: {src}")
    if dst.exists():
        shutil.rmtree(str(dst))
    shutil.copytree(str(src), str(dst))
    return dst
