# Review — 双轴审查

> 按需加载工作流。触发词：双轴审查|双轴

Two-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / PRD / spec?

Both axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

The issue tracker should have been provided to you — run `/setup-matt-pocock-skills` if `docs/agents/issue-tracker.md` is missing.

## 模式判断

根据用户输入中的关键词（从前到后匹配，首条命中即止），判断当前模式：

| 如果出现 | 模式 | 行为 |
|---------|------|------|
| `审查` `审计` `检查` `review` `audit` `看看` `review since` | **Review** | 只审查报告，不碰代码（默认模式）|
| `修复` `改` `修` `fix` `implement` | **Implement** | 按审查结果改代码 |

用户没有明确说"修"时，走 **Review 模式**（最窄最安全）。

---

## Review 模式（默认）

只审查报告，不修改代码。审查完成后将发现呈现给用户，等用户决定是否进入 Implement 模式。

### 1. Pin the fixed point

**若当前会话刚执行过 scope-check（上下文中有 Scope 声明表）：**

- 直接复用 scope 表中已确定的 diff 范围——scope 表已列出变更文件，`git status` / `git diff --stat` 已获取。
- **禁止重新询问**"跟哪个基准点比？"——范围已由 scope-check 确认。
- 用 scope 表使用的同一个 diff 命令捕获变更，跳过询问。

**否则（独立调用，无 scope 表上下文）：**

Whatever the user said is the fixed point — a commit SHA, branch name, tag, `main`, `HEAD~5`, etc. Don't be opinionated; pass it through. If they didn't specify one, ask: "Review against what — a branch, a commit, or `main`?" Don't proceed until you have it.

Capture the diff command once: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base). Also note the list of commits via `git log <fixed-point>..HEAD --oneline`.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, GitLab `!67`, etc.) — fetch via the workflow in `docs/agents/issue-tracker.md`.
2. A path the user passed as an argument.
3. A PRD/spec file under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent will skip and report "no spec available".

### 3. Identify the standards sources

Anything in the repo that documents how code should be written. For **this project (AI Workbench)**, the authoritative sources are:

- **`AGENTS.md`** — primary: hard rules, instruction specs, phase workflows, trigger words
- **`experience-index.md`** — secondary: aggregated cross-project experience patterns, troubleshooting references

Other common locations that may supplement:
- `CLAUDE.md`
- `CONTRIBUTING.md`
- `docs/adr/` (architectural decisions are standards)
- `.editorconfig`, `mypy.ini`, `pyproject.toml` (machine-enforced standards — note them but don't re-check what tooling already checks)
- Any `STYLE.md`, `STANDARDS.md`, or similar at the repo root or under `docs/`

Collect the list of files. The **Standards** sub-agent will read them. **Always include `AGENTS.md` and `experience-index.md`** for reviews in this project.

### 4. Spawn both sub-agents in parallel

Send a single message with two `Agent` tool calls. Use the `general-purpose` subagent for both.

**Standards sub-agent prompt** — include:

- The full diff command and commit list.
- The list of standards-source files you found in step 3. **For this project, `AGENTS.md` is the primary source of truth — treat its rules (§3 hard rules, §4 trigger-word instructions, §6 phase commands) as non-negotiable.** Use `experience-index.md` to cross-reference patterns and common pitfalls.
- The brief: "Read the standards docs, starting with `AGENTS.md` and `experience-index.md`. Then read the diff. Report — per file/hunk where relevant — every place the diff violates a documented standard. Cite the standard (file + the rule). Distinguish hard violations from judgement calls. Skip anything tooling enforces. Under 400 words."

**Spec sub-agent prompt** — include:

- The diff command and commit list.
- The path or fetched contents of the spec.
- The brief: "Read the spec. Then read the diff. Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

If the spec is missing, skip the Spec sub-agent and note this in the final report.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank findings — the two axes are deliberately separate so the user can see them independently.

End with a one-line summary: total findings per axis, and the worst single issue (if any) flagged.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.

---

## Implement 模式

用户明确说了"修/修复/改/fix"时，走这个分支。

前置条件：必须已经走完一次 Review 模式的审查流程（Standards + Spec），有审查报告可用。

如果用户直接说"修这个"但没有做过 review，先快速走一遍审查再修。

### 1. 确认审查发现

回顾本次会话中刚完成的审查报告，或快速重跑一次双轴审查获取发现。

### 2. 按优先级逐一修复

按审查报告中的发现问题，从 P0（阻塞级）到最低优先级逐条修复：

1. 读取问题涉及的文件，确认当前代码状态
2. 执行最小改动——只修报告指出的问题，不改方向
3. 不吸收新发现（任何审查时没发现的东西不属于本轮修复）

### 3. 验证

改完后确认：

- **Spec**：原始需求仍然满足
- **Standards**：改动不引入新的违规
- 没有因为修复某个问题而破坏了相邻功能

### 约束

- **不改方向**：Implement 模式是"按审查结果修"，不是"趁修的时候重构"
- **不吸收无关发现**：如果修的时候看到其他问题，可以顺手修复极小的边缘情况（变量名、注释），但结构性改动必须走新的一轮 Review 模式

## 确认

执行上述动作前，先向用户说明将要做什么，等待确认：
- `y` → 执行
- `n` → 取消
