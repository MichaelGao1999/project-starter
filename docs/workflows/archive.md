# 存档指令 — 完整执行流程

> **执行状态**: 📄 通用引用文档 — 被 AGENTS.md §4.1 调用
>
> 本文件实现存档流程，采用**线性步序 + STOP 门禁**模式。**必须逐行按顺序执行，不可跳步、合并、重排。每步完成后输出 `[步骤 N ✅]` 标记方可进入下一步。**
>
> 适用于所有配置了 `AGENTS.md` 的项目。部分步骤（记忆系统等）以条件块标注，无对应工具时自动跳过。

---

## 前置规则（不可违反）

| 规则 | 内容 |
|------|------|
| **线性步序** | 步0→1→2a→2b→3→4→5→6→7 严格执行，每步完成后方可进入下一步 |
| **用户确认** | 步2a 和步2b 未获用户`y`（或序号选择）之前，不得进入后续任何写入操作 |
| **Git fetch 先于写** | 步3 必须先 `git fetch origin`，不可从缓存推测远程状态 |
| **不提前结束** | 存档流程全部完成前，不得主动结束会话或退出存档 |
| **失败回滚** | 任何步失败（未产出所需产出物），应尝试从步0 快照回滚 |

---

## 确认流程（步2a + 步2b）

存档的交互确认分两阶段：

- **步2a — 草稿确认**：输出 session-log 草稿 + status 修改预览。用户输入：
  - `y` → 草稿无误，继续
  - 修改意见 → AI 修正后重新输出，等待再次确认
  - `n` → 取消存档，退出
- **步2b — 认知候选选择**：如有 0-5 条认知候选，输出候选清单。用户输入：
  - `y` → 全选所有候选，继续
  - `n` → 跳过认知提取，继续存档
  - 序号选择（如 `1,3` 或 `1-3`）→ 仅处理选中的候选
  - `redo` → 重新提炼候选

---

## 管线总览

| 步 | 阶段 | 动作 | 产出物 | Exit Condition | Decision Type | 用户交互 |
|----|------|------|--------|---------------|---------------|---------|
| 0 | 快照 | `git rev-parse HEAD` 记录回滚锚点 | `.archive/rollback-ref.txt` | HEAD 已记录 | Deterministic | — |
| 1 | 回顾 | 回顾本轮+生成草稿+认知候选 | session-log 草稿 + 0-5 候选 | 草稿内容就绪 | LLM Reasoning | — |
| 2a | 草稿确认 | 输出草稿+预览，等待用户确认 | `确认: y` 或修改后反复 | 获用户 y | Human Gate | ✅ |
| 2b | 认知选择 | 输出候选清单，等待用户选择 | 用户选择结果（y/n/序号/redo） | 获用户决策 | Human Gate | ✅ |
| 3 | 文档更新 | git fetch → status.md → 知识文件 → 记忆捕获 | 各文件已修改 | 全部文件更新完成 | Deterministic + LLM | — |
| 4 | 定稿 | session-log.md 追加（头部插入） | session-log.md 已追加 | 写入完成 | Deterministic | — |
| 5 | 后处理+审查 | 敏感信息扫描 → 认知提取 | 审查通过 | 脚本执行通过 | Deterministic | — |
| 6 | Git 提交 | `git add → commit [session] → push` | Git 历史 | push 完成 | Deterministic | — |
| 7 | 汇报 | 输出完成摘要 | 摘要文本 | 输出完成 | LLM Reasoning | — |

---

## 步 0 — 前置快照

**目标**：记录 HEAD 作为回滚锚点，中间步骤失败时有恢复基准。

> **STOP.** 执行前确认当前工作目录是项目根目录，无未提交的破坏性变更。

```bash
mkdir -p .archive
git rev-parse HEAD > .archive/rollback-ref.txt
echo "回滚锚点: $(cat .archive/rollback-ref.txt)"
```

**产出物**：`.archive/rollback-ref.txt`（当前 HEAD commit hash）

**Exit Condition**：文件已写入，内容为有效 commit hash。

---

## 步 1 — 回顾 + 草稿生成

**目标**：回顾本轮会话内容，生成 session-log 草稿；同时从认知角度提炼 0-5 条候选条目。

> **STOP.** 在阅读本节之前，确认步0 的 `.archive/rollback-ref.txt` 已存在。如不存在，先执行步0。

1. **回顾会话**：回顾本轮所有对话、修改、决策，形成结构化摘要
2. **生成 session-log 草稿**：按 session-log.md 格式撰写本轮记录
3. **提炼认知候选（0-5 条）**：从认知角度提取。每候选格式：
   ```
   [类型] 标签 → 一句话价值
   ```
   类型可选：`概念顿悟` / `决策逻辑` / `思维模型` / `踩坑教训` / `工具心智`

   **跳过条件**（满足任意一条即不产出候选）：
   - 本轮无原创认知突破（仅为机械执行、错误修复、操作流水）
   - 有效候选不足 1 条

   **负面过滤**（以下类型不算认知候选，分别归入对应文件）：
   - 错误修复步骤 → `troubleshooting.md`
   - 架构决策 → `ADR.md`
   - 工程方法 → `lessons-learned.md`
   - 操作流水 → `session-log.md`

**产出物**：
- session-log 草稿（内存中）
- 认知候选清单（0-5 条）或「无候选」

**Exit Condition**：草稿内容就绪，候选清单就绪（0 条时标记「无候选」）。

---

## 步 2a — 草稿确认

**目标**：将草稿呈现给用户，获确认后方可继续。

> **STOP.** 步1 的草稿必须已就绪。如步1 未完成（草稿为空或部分），回到步1。

1. 输出 session-log 草稿 + status 修改预览
2. 等待用户输入：
   - `y` → 草稿无误，进入步2b
   - 修改意见 → 如涉及回顾遗漏或认知偏差，**回到步1** 重新回顾后再次输出草稿；如仅是措辞/格式问题，AI 直接修正后再次输出。两类都需再次等待确认
   - `n` → 取消存档，退出

**产出物**：记录的 `确认: y`（或修改后的草稿版本）

**Exit Condition**：获用户 `y` 确认。未确认不得推进。

---

## 步 2b — 认知候选选择

**目标**：如步1 识别出认知候选，提交用户选择是否及哪些写入 cognitive-log.md。

> **STOP.** 步2a 的产出物 `确认: y` 必须存在。如尚未获用户确认，回到步2a。

1. 如有认知候选（1-5 条），输出候选清单：
   - 每条包含 `[类型] 标签 → 一句话价值`
2. 如无候选，跳过此步（直接进入步3）
3. 等待用户输入：
   - `y` → 全选所有候选，继续
   - `n` → 跳过认知提取，继续存档
   - 序号选择（如 `1,3` 或 `1-3`）→ 仅处理选中的候选
   - `redo` → 回到步1 重新回顾（重新扫描会话提炼候选）
4. 用户选择后，记录选择结果

**产出物**：用户选择结果（y/n/序号/redo）

**Exit Condition**：获用户决策。未选择不得进入步3。

---

## 步 3 — 文档更新

**目标**：按最新远程状态，更新所有受本轮影响的文档。

> **STOP.** 步2b（如有候选）必须已完成用户选择。此外，本节包含 `git fetch`，**不可从缓存推测远程状态**——必须先 fetch 再更新。

### 3a. 文件系统确认

在写入任何文件前，确认目标文件当前存在：

```bash
ls -la status.md session-log.md docs/tasks/task-progress.md 2>/dev/null || echo "警告：部分文件缺失，确认前请勿继续"
```

如文件结构与预期不符（某文件被移动/重命名），先纠正路径再进入下一步。

### 3b. Git 前置同步

```bash
git fetch origin
```

- 远程有超前提交 → 本地脏则 `git stash`，然后 `git pull --rebase`，有 stash 则 `git stash pop`；本地干净则直接 `git pull --rebase`
- 远程无超前提交 → 跳过 pull

### 3c. 更新 status.md

- 对照 `git diff --stat` 逐条核销待办
- 已完成的打勾（`- [ ]` → `- [x]`）
- **删除已完成的 `[x]` 待办项**：打勾后从待办清单删除，历史完成记录保留在更新记录表
- ⚠️ 若 `git diff --stat` 为空：跳过文件对照核销，仅基于 session-log 内容更新待办勾选 + 新增待办 + 更新记录表

### 3d. 更新 task 文件

- `docs/tasks/task-progress.md` + `docs/tasks/task-{module}.md`
- 基于回顾结果，扫描各模块任务文件的 `[ ]` checkbox，勾选本轮完成的子任务（`[ ]` → `[x]`），更新模块进度表

### 3e. 更新知识文件

本轮条件 | 目标文件
有报错 | `troubleshooting.md`
有经验 | `lessons-learned.md`
有决策 | `ADR.md`

### 3f. 记忆捕获（如可用）

> 仅当项目配置了记忆系统（如 `awb CLI` 或等效工具）时执行。否则跳过。

```bash
if command -v awb &>/dev/null; then
    awb memory add "<内容>" --type <类型> --scope-id "project/live"
fi
```

`--type` 可选值：`user` / `feedback` / `project` / `reference`

触发条件（符合任一条）：
1. 用户的**原创观点/观察/顿悟**
2. 用户给出的**偏好/边界条件**
3. 用户确认的**设计决策及其理由**
4. 会话中发现的**根因/阻塞/意外行为**
5. 用户明确说"记住这个"

### 3g. `.memory/` 归整（如可用）

```bash
if command -v awb &>/dev/null; then
    awb memory push
fi
```

**产出物**：所有受影响的文件已修改 + 记忆已捕获（如可用）

**Exit Condition**：全部文件更新完成。可通过 `git diff --stat` 验证文件有变更（或合理确认无变更）。

---

## 步 4 — 定稿 session-log

**目标**：将本轮存档记录定稿写入 session-log.md。

> **STOP.** 步3 的所有文档更新（含记忆捕获）必须已完成。未完成则回到步3。

**追加模式**：读取现有文件 → 在文件头部插入本轮新条目 → 写回，禁止全量覆盖。

**产出物**：session-log.md 已追加本轮记录

**Exit Condition**：文件写入完成。

---

## 步 5 — 后处理 + 审查

**目标**：运行敏感信息扫描和认知提取。

> **STOP.** 步4 的 session-log.md 定稿必须已完成。未完成则回到步4。

### 5a. 敏感信息扫描（如可用）

```bash
if command -v python &>/dev/null && [ -f scripts/sensitivity-check.py ]; then
    python scripts/sensitivity-check.py
else
    # 手动检查 session-log 和知识文件中是否有 IP、本地路径、邮箱等
    echo "请手动确认无敏感信息泄露"
fi
```

扫描拟写入内容中的 IP 地址、本地路径、邮箱等敏感信息。

### 5b. 认知提取（如步2b 选中，且脚本存在）

```bash
if [ -f scripts/cognitive-extract.py ]; then
    python scripts/cognitive-extract.py
fi
```


**产出物**：
- 扫描报告（通过或需修复项）
- cognitive-log.md 已更新（如需）
- 记忆条目已写入（如可用）

**Exit Condition**：审查通过。敏感信息扫描无未处理问题。

---

## 步 6 — Git 提交

**目标**：全量提交至 Git 仓库。

> **STOP.** 步5 的所有定稿和审查必须已完成。未完成则回到步5。

### 前置检查

⚠️ 确认 `session-log.md` 已在本步修改：

```bash
git diff --stat session-log.md
```

如为空则报错：「session-log.md 未变更，存档中止」

### 执行

```bash
git add -A
git commit -m "[session] <摘要>"
git push
```

⚠️ `git push` 可能因网络/权限延迟，启动后继续汇报。如失败则提示用户手动 push。

**产出物**：Git 历史新增 commit

**Exit Condition**：`git push` 成功（或合理失败提示）。

---

## 步 7 — 汇报

**目标**：输出存档完成摘要。

> **STOP.** 步6 的 Git 提交必须已完成。如提交失败，报告原因并提供手动恢复指引。

输出格式：

```
【存档完成】

📦 本轮概要：<2-3 句话概述>
📄 更新文件：
  - status.md（待办更新 + 记录更新）
  - session-log.md（追加本轮记录）
  - docs/tasks/...
  - <其他文件: troubleshooting/lessons/ADR/memory 等>
🔗 Git commit: <commit hash>
```

**Exit Condition**：用户看到完成摘要。存档流程结束。

---

## 末尾 Self-check（必做）

存档完成后，逐项核验：

- [ ] 步0 — `.archive/rollback-ref.txt` 存在
- [ ] 步1 — 草稿内容已生成
- [ ] 步2a — 用户 `y` 确认已获取
- [ ] 步2b — 认知候选选择已完成（或无候选时跳过）
- [ ] 步3 — 所有文档已更新（`git diff --stat` 验证）
- [ ] 步3 — `git fetch origin` 已执行（非缓存推测）
- [ ] 步4 — session-log.md 已追加（`--stat` 非空）
- [ ] 步5 — 敏感信息扫描已通过
- [ ] 步6 — `git push` 已成功
- [ ] 步序 — 步0→1→2a→2b→3→4→5→6→7 线性执行，未跳步

**任一项未勾选 → 回到对应步骤补做。**

---

## 附录 A：半路失败回滚方案

存档过程中任一步失败时：

### 未写入文件时（步2a/2b 失败）

用户 `n` 取消 → 直接结束，无磁盘变更。删除 `.archive/rollback-ref.txt`。

### 已写入文件时（步3 后失败）

```bash
# 1. 恢复文件到步0 快照
git checkout $(cat .archive/rollback-ref.txt) -- .
# 2. 重置工作树到快照
git reset $(cat .archive/rollback-ref.txt) -- .
# 3. 删除存档状态标记
rm -rf .archive/
```

### push 失败后

1. 提示用户手动 push：
   ```bash
   git push
   ```
2. 如无法解决，输出错误信息和建议解决路径。
