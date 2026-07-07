"""externalize — Convert auto-loaded skills to on-demand trigger + workflow format.

Usage:
    convert:  python externalize.py convert <skill-name> [--target <dir>] [--skills-dir <dir>] [--agents-file <file>]
    new:      python externalize.py new --name <name> --trigger "<word|variant>" --actions "1. step1;;2. step2" [--no-confirm] [--target <dir>] [--skills-dir <dir>] [--agents-file <file>]
    new (modes): python externalize.py new --name <name> --trigger "<word>" --modes "review::desc::1. step1;;2. step2||audit::desc2::step1" [--mode-intro "text"] [--no-confirm]
    remove:   python externalize.py remove <name> [--target <dir>] [--skills-dir <dir>] [--agents-file <file>]

Examples:
    python externalize.py convert add-todo
    python externalize.py convert add-todo --skills-dir .claude/skills --agents-file CLAUDE.md
    python externalize.py new --name add-todo --trigger "计入待办|加到清单" --actions "1. 读取 status.md;;2. 追加待办条目;;3. 输出声明"
    python externalize.py remove add-todo
    python externalize.py new --name ponytail --trigger "懒人审查|ponytail" --modes "review::审查单段代码::1. AI 读取代码;;2. 对照阶梯检查;;3. 输出精简建议||audit::全仓臃肿扫描::1. 扫描文件结构;;2. 识别臃肿热点;;3. 生成精简机会清单" --mode-intro "AI 根据上下文自动选择模式，或用户直接指定："
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional


_DEFAULT_SKILLS_DIR = Path(".agents/skills")
_DEFAULT_AGENTS_FILE = Path("AGENTS.md")
_DEFAULT_TARGET = Path("docs/workflows")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML-like frontmatter between --- markers."""
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return {}
    fm: dict[str, str] = {}
    for line in match.group(1).split('\n'):
        line = line.strip()
        if ':' in line:
            key, _, value = line.partition(':')
            fm[key.strip()] = value.strip()
    return fm


def extract_trigger_words(description: str) -> list[str]:
    """Extract trigger words from description — Chinese quotes or explicit trigger phrases."""
    # Chinese quotation marks: "计入待办", "加到清单"
    words = re.findall(r'["""]\s*(.+?)\s*["»"]', description)
    # English quotes
    words += re.findall(r'"(.+?)"', description)
    # Deduplicate, keep order
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        w = w.strip()
        if w and w not in seen:
            seen.add(w)
            result.append(w)
    return result


def extract_body(text: str) -> str:
    """Extract body text after frontmatter."""
    match = re.search(r'^---\s*\n.*?\n---\s*\n(.*)', text, re.DOTALL)
    if not match:
        return text
    return match.group(1).strip()


def extract_action_section(body: str) -> str:
    """Extract numbered execution steps from SKILL.md and wrap in ## 标准动作 format.

    Priority: numbered lists (1. / 2、/ 3)) → content after H1 → bare fallback.
    Unlike the old version, this no longer copies raw H2/H3 sections verbatim.
    """
    lines = body.split('\n')
    numbered_steps: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^\d+[.、)]\s', stripped):
            numbered_steps.append(stripped)

    if numbered_steps:
        return f"## 标准动作\n\n" + '\n'.join(numbered_steps) + '\n'

    # Fallback: content after H1 heading, strip leading H2/H3 headers
    h1_end = re.search(r'^#\s+.*?\n', body)
    if h1_end:
        remaining = body[h1_end.end():].strip()
    else:
        remaining = body.strip()

    remaining = re.sub(r'^#{2,4}\s+.*?\n', '', remaining, flags=re.MULTILINE).strip()
    if remaining:
        return f"## 标准动作\n\n{remaining}\n"

    return f"## 标准动作\n\n1. 参考原始 skill\n"


def build_trigger_line(name: str, trigger_words: list[str], target_dir: Path) -> str:
    """Build the AGENTS.md trigger entry line."""
    triggers = '|'.join(trigger_words) if trigger_words else name
    return f'- `{triggers}` → `{target_dir}/{name}.md`'


def build_workflow(name: str, trigger_words: list[str], action: str,
                   no_confirm: bool = False) -> str:
    """Build the workflow markdown content with optional y/n gate."""
    triggers_str = '、'.join(trigger_words) if trigger_words else f'`{name}`'

    y_n_block = """
## 确认

执行上述动作前，先向用户说明将要做什么，等待确认：
- `y` → 执行
- `n` → 取消
"""
    content = f"""# {name}

> 按需加载工作流。触发词：{triggers_str}

{action}"""
    if not no_confirm:
        content += y_n_block
    return content


def build_workflow_with_modes(name: str, trigger_words: list[str],
                               modes: list[dict], intro_text: str = "",
                               no_confirm: bool = False) -> str:
    """Build a multi-mode workflow markdown with mode selection table."""
    triggers_str = '、'.join(trigger_words) if trigger_words else f'`{name}`'

    # Build mode selection table
    lines = [
        f"# {name}",
        "",
        f"> 按需加载工作流。触发词：{triggers_str}",
        "",
        "## 模式选择",
        "",
        intro_text or "AI 根据上下文自动选择模式，或用户指定：",
        "",
        "| 模式 | 说明 |",
        "|------|------|",
    ]
    for m in modes:
        lines.append(f"| **{m['name']}** | {m['description']} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    content = '\n'.join(lines)

    # Build per-mode action sections
    for m in modes:
        content += f"## {m['name']} — {m['description']}\n\n"
        content += '\n'.join(m['steps']) + '\n\n'

    # Confirmation gate
    if not no_confirm:
        content += (
            "## 确认\n"
            "\n"
            "执行上述动作前，先向用户说明将要做什么，等待确认：\n"
            "- `y` → 执行\n"
            "- `n` → 取消\n"
        )

    return content


def _parse_modes(modes_str: str) -> list[dict]:
    """Parse --modes string into list of mode dicts.

    Format:
        "name::description::step1;;step2||name2::desc2::step1"
    Each mode: name :: description :: action-steps (;; separated steps)
    Modes separated by ||
    """
    modes: list[dict] = []
    for mode_part in modes_str.split('||'):
        parts = mode_part.split('::', 2)
        if len(parts) < 3:
            print(f"[WARN] Invalid mode format, skipped: {mode_part}")
            continue
        name = parts[0].strip()
        description = parts[1].strip()
        actions_raw = parts[2].strip()

        steps: list[str] = []
        for line in actions_raw.split(';;'):
            line = line.strip()
            if not line:
                continue
            if re.match(r'^\d+[.、)]', line):
                steps.append(line)
            else:
                steps.append(f"- {line}")
        modes.append({"name": name, "description": description, "steps": steps})
    return modes


def insert_trigger_into_agents(trigger_line: str, agents_file: Path) -> Optional[str]:
    """Insert trigger line into AGENTS.md skill index section.
    Creates the section if it doesn't exist.
    """
    if not agents_file.exists():
        print(f"[ERROR] {agents_file} not found")
        return None

    content = agents_file.read_text(encoding='utf-8')
    lines = content.split('\n')

    # Look for existing skill index section
    skill_index_pattern = re.compile(r'^##\s+技能索引')
    insert_index: Optional[int] = None

    for i, line in enumerate(lines):
        if skill_index_pattern.match(line):
            # Find the last entry in this section (next ## section or blank line gap)
            for j in range(i + 1, len(lines)):
                if re.match(r'^##\s', lines[j]):
                    insert_index = j
                    break
                elif re.match(r'^---', lines[j]):
                    insert_index = j
                    break
            if insert_index is None:
                insert_index = len(lines)
            break

    if insert_index is not None:
        # Check if this trigger already exists
        trigger_name = trigger_line.split('→')[0].strip()
        for line in lines:
            if line.strip() == trigger_name:
                print(f"[SKIP] Trigger already exists: {trigger_name}")
                return None
        lines.insert(insert_index, trigger_line)
        lines.insert(insert_index, '')  # blank line before trigger
    else:
        # Append skill index section at end
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## 技能索引')
        lines.append('')
        lines.append(trigger_line)

    agents_file.write_text('\n'.join(lines), encoding='utf-8')
    return str(agents_file)


def archive_skill(name: str, skills_dir: Path) -> bool:
    """Move skill to _archived/ directory (reversible, zero data loss)."""
    import shutil

    src = skills_dir / name
    if not src.exists():
        print(f"[WARN] Skill not found for archive: {src}")
        return False
    dst = skills_dir / "_archived" / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            shutil.rmtree(str(dst))
        except OSError as e:
            print(f"[ERROR] Failed to remove existing archive destination {dst}: {e}")
            return False
    src.rename(dst)
    print(f"[OK] Archived: {src} → {dst}")
    return True


def convert_skill(name: str, target_dir: str, skills_dir: Path, agents_file: Path) -> bool:
    """Convert a skill from skills_dir/{name}/ to externalized format."""
    skill_path = skills_dir / name / "SKILL.md"
    if not skill_path.exists():
        print(f"[ERROR] Skill not found: {skill_path}")
        return False

    text = skill_path.read_text(encoding='utf-8')
    fm = parse_frontmatter(text)
    body = extract_body(text)

    # Extract trigger words
    description = fm.get('description', '') or fm.get('description_zh', '')
    trigger_words = extract_trigger_words(description)

    # Use name as fallback trigger
    skill_name = fm.get('name', name)
    if not trigger_words:
        trigger_words = [skill_name]
        print(f"[WARN] No trigger words found in description, using skill name: {skill_name}")

    # Extract action section
    action = extract_action_section(body)

    # Build outputs
    target_path = Path(target_dir)
    trigger_line = build_trigger_line(skill_name, trigger_words, target_path)
    workflow_content = build_workflow(skill_name, trigger_words, action)

    # Write workflow
    target_path.mkdir(parents=True, exist_ok=True)
    workflow_file = target_path / f"{skill_name}.md"
    workflow_file.write_text(workflow_content, encoding='utf-8')
    print(f"[OK] Workflow written: {workflow_file}")

    # Insert trigger into AGENTS.md
    result = insert_trigger_into_agents(trigger_line, agents_file)
    if result:
        print(f"[OK] Trigger added to: {result}")
        print(f"    {trigger_line}")

    # Archive original skill (reversible, zero data loss)
    archived = archive_skill(name, skills_dir)

    print(f"\n[SUMMARY] {skill_name} externalized:")
    print(f"  Trigger:  {trigger_line}")
    print(f"  Workflow: {workflow_file}")
    if archived:
        print(f"  Archived: {skills_dir}/_archived/{name}/")
    print(f"\n  Undo: move {skills_dir}/_archived/{name}/ back to {skills_dir}/{name}/")

    return True


def new_skill(name: str, trigger_words_str: str, actions: str,
              target_dir: str, skills_dir: Path, agents_file: Path,
              no_confirm: bool = False,
              modes_str: str = "", mode_intro: str = "") -> bool:
    """Create a new externalized skill from AI-converged interview answers.

    Called by the AI after the 5-round interview has converged.
    Uses the same build_workflow() + insert_trigger_into_agents() as convert,
    guaranteeing identical output format.

    Supports two modes of operation:
    - Linear workflow: provide --actions (;; separated steps)
    - Multi-mode workflow: provide --modes (|| separated modes)

    Args:
        name: Skill name (used for workflow filename, e.g. "add-todo")
        trigger_words_str: Pipe-separated trigger words (e.g. "计入待办|加到清单")
        actions: Action steps, ;; separated (e.g. "1. step1;;2. step2")
        target_dir: Output directory for workflow files
        no_confirm: If True, skip the y/n gate in the workflow
        modes_str: Multi-mode spec (e.g. "mode::desc::step1;;step2||mode2::desc2::step1")
        mode_intro: Custom intro text for mode selection section
    """
    trigger_words = [w.strip() for w in trigger_words_str.split('|') if w.strip()]
    if not trigger_words:
        print("[ERROR] No trigger words provided")
        return False

    # Parse modes if provided
    if modes_str:
        modes = _parse_modes(modes_str)
        if not modes:
            print("[ERROR] No valid modes parsed from --modes")
            return False
        workflow_content = build_workflow_with_modes(
            name, trigger_words, modes,
            intro_text=mode_intro, no_confirm=no_confirm
        )
    elif actions:
        # Build action section in standard format (## 标准动作)
        action_lines: list[str] = [
            "## 标准动作",
            "",
        ]
        for line in actions.split(';;'):
            line = line.strip()
            if not line:
                continue
            if re.match(r'^\d+[.、)]', line):
                action_lines.append(line)
            else:
                action_lines.append(f"- {line}")
        action_lines.append("")
        action_section = '\n'.join(action_lines)

        workflow_content = build_workflow(name, trigger_words, action_section,
                                          no_confirm=no_confirm)
    else:
        print("[ERROR] Either --actions (linear) or --modes (multi-mode) is required")
        return False

    # Write workflow file
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)
    workflow_file = target_path / f"{name}.md"
    workflow_file.write_text(workflow_content, encoding='utf-8')
    print(f"[OK] Workflow written: {workflow_file}")

    # Build trigger line (after target_path is resolved)
    trigger_line = build_trigger_line(name, trigger_words, target_path)

    # Insert trigger into AGENTS.md
    result = insert_trigger_into_agents(trigger_line, agents_file)
    if result:
        print(f"[OK] Trigger added to: {result}")
        print(f"    {trigger_line}")

    # Show mode count in summary if applicable
    mode_info = ""
    if modes_str:
        modes = _parse_modes(modes_str)
        if modes:
            mode_info = f"  Modes:     {len(modes)} ({', '.join(m['name'] for m in modes)})\n"

    print(f"\n[SUMMARY] {name} created:")
    print(f"  Trigger:  {trigger_line}")
    if mode_info:
        print(mode_info, end='')
    print(f"  Workflow: {workflow_file}")

    return True


def remove_skill(name: str, target_dir: str, skills_dir: Path, agents_file: Path) -> bool:
    """Remove externalized trigger + workflow; prompt about archive if it exists."""
    if not agents_file.exists():
        print(f"[ERROR] {agents_file} not found")
        return False

    import shutil

    # 1. Remove trigger line from AGENTS.md
    content = agents_file.read_text(encoding='utf-8')
    lines = content.split('\n')

    # Find lines containing the workflow reference
    trigger_pattern = f"{target_dir}/{name}.md"
    removed_line = None
    new_lines: list[str] = []
    for i, line in enumerate(lines):
        if trigger_pattern in line:
            removed_line = line.strip()
            # Skip this line and the preceding blank line if present
            if new_lines and new_lines[-1] == '':
                new_lines.pop()
            continue
        new_lines.append(line)

    if removed_line is None:
        print(f"[WARN] No trigger line found in {agents_file} referencing {trigger_pattern}")
    else:
        agents_file.write_text('\n'.join(new_lines), encoding='utf-8')
        print(f"[OK] Trigger removed: {removed_line}")

    # 2. Remove workflow file
    workflow_file = Path(target_dir) / f"{name}.md"
    if workflow_file.exists():
        try:
            workflow_file.unlink()
            print(f"[OK] Workflow deleted: {workflow_file}")
        except OSError as e:
            print(f"[ERROR] Failed to delete workflow {workflow_file}: {e}")
    else:
        print(f"[WARN] Workflow not found: {workflow_file}")

    # 3. Check archive
    archive_path = skills_dir / "_archived" / name
    archive_existed = archive_path.exists()
    archive_purged = False
    if archive_existed:
        print()
        print(f"  ┌{'─'*47}┐")
        print(f"  │ 归档备份 _archived/{name}/ 还在{'':<16}│")
        print(f"  │ y → 一并删除{'':<23}│")
        print(f"  │ n → 保留{'':<27}│")
        print(f"  │ 或告诉我你的想法{'':<18}│")
        print(f"  └{'─'*47}┘")
        try:
            choice = input("  ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = 'n'
        if choice == 'y':
            try:
                shutil.rmtree(str(archive_path))
                archive_purged = True
                print(f"[OK] Archive purged: {archive_path}")
            except OSError as e:
                print(f"[ERROR] Failed to purge archive {archive_path}: {e}")
        elif choice == 'n':
            print(f"[OK] Archive kept: {archive_path}")
        else:
            print(f"\n  「{choice}」—— 交给 Agent 处理。")
            return True
    else:
        print(f"[OK] No archive found")

    print(f"\n[SUMMARY] {name} removed:")
    print(f"  Trigger removed:  {'yes' if removed_line else 'no'}")
    print(f"  Workflow deleted:  {'yes' if not workflow_file.exists() else 'no'}")
    if archive_purged:
        archive_status = "purged"
    elif archive_existed:
        archive_status = "kept"
    else:
        archive_status = "n/a"
    print(f"  Archive status:    {archive_status}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert auto-loaded skills to on-demand format"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Shared optional arguments for path overrides
    _skills_help = f"Skills directory (default: {_DEFAULT_SKILLS_DIR})"
    _agents_help = f"Agent entry file (default: {_DEFAULT_AGENTS_FILE})"
    _target_help = f"Output directory for workflow files (default: {_DEFAULT_TARGET})"

    convert_parser = subparsers.add_parser("convert", help="Convert an existing skill")
    convert_parser.add_argument("name", help="Skill name (directory under skills dir)")
    convert_parser.add_argument("--target", default=str(_DEFAULT_TARGET), help=_target_help)
    convert_parser.add_argument("--skills-dir", default=str(_DEFAULT_SKILLS_DIR), help=_skills_help)
    convert_parser.add_argument("--agents-file", default=str(_DEFAULT_AGENTS_FILE), help=_agents_help)

    new_parser = subparsers.add_parser("new", help="Create a new skill from AI-converged interview answers")
    new_parser.add_argument("--name", required=True, help="Skill name (used for workflow filename)")
    new_parser.add_argument("--trigger", required=True, help="Pipe-separated trigger words (e.g. '计入待办|加到清单')")
    new_parser.add_argument("--actions", default="", help="Action steps, ;; separated (e.g. '1. step1;;2. step2'). Use --modes instead for multi-mode.")
    new_parser.add_argument("--modes", default="", help="Multi-mode spec: 'name::desc::step1;;step2||name2::desc2::step1' (mutually exclusive with --actions)")
    new_parser.add_argument("--mode-intro", default="", help="Custom intro text for mode selection section (default: AI auto-detects)")
    new_parser.add_argument("--no-confirm", action="store_true", help="Skip the y/n confirmation gate")
    new_parser.add_argument("--target", default=str(_DEFAULT_TARGET), help=_target_help)
    new_parser.add_argument("--skills-dir", default=str(_DEFAULT_SKILLS_DIR), help=_skills_help)
    new_parser.add_argument("--agents-file", default=str(_DEFAULT_AGENTS_FILE), help=_agents_help)

    remove_parser = subparsers.add_parser("remove", help="Remove an externalized skill (trigger + workflow)")
    remove_parser.add_argument("name", help="Skill name to remove")
    remove_parser.add_argument("--target", default=str(_DEFAULT_TARGET), help=_target_help)
    remove_parser.add_argument("--skills-dir", default=str(_DEFAULT_SKILLS_DIR), help=_skills_help)
    remove_parser.add_argument("--agents-file", default=str(_DEFAULT_AGENTS_FILE), help=_agents_help)

    args = parser.parse_args()

    if args.command == "convert":
        success = convert_skill(args.name, args.target,
                                Path(args.skills_dir), Path(args.agents_file))
        return 0 if success else 1
    elif args.command == "new":
        success = new_skill(args.name, args.trigger, args.actions or "",
                            args.target, Path(args.skills_dir), Path(args.agents_file),
                            no_confirm=args.no_confirm,
                            modes_str=args.modes or "", mode_intro=args.mode_intro or "")
        return 0 if success else 1
    elif args.command == "remove":
        success = remove_skill(args.name, args.target,
                               Path(args.skills_dir), Path(args.agents_file))
        return 0 if success else 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
