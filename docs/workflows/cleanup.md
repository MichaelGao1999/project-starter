# 清理指令 — 完整执行流程

> **执行状态**: 📄 活跃引用文档 — 被 AGENTS.md §4.4 调用，按需读取

**触发词**：`清理`（去除标点后精确等于这两个字）

**防误触**：
- 消息精确匹配「清理」→ 执行清理流程
- 消息包含「清理」但还有其他内容 → 视为正常对话，不触发

**作用范围**：项目本身的 `ADR.md`、`experience-index.md`，不涉及其他项目。

---

## 确认流程

1. 输出将要执行的 6 步检查清单（见下方管线）
2. 等待用户输入 `y` 确认或 `n` 取消

---

## 标准动作序列（用户确认后执行）

### 管线总览

| 步 | 检查项 | 命令 | 修复策略 | Exit Condition | Decision Type |
|----|--------|------|---------|---------------|---------------|
| 1 | ADR 结构校验 | `python scripts/adr-restructure.py --verify` | 只读报告（标题格式 / 编号冲突 / 编号跳号 / 来源标签） | 报告已输出，无未决项 → 进入下一步 | Deterministic |
| 2 | 跨文件相似度去重检测 | `python scripts/analyze-duplicates.py` | 只读报告 + AI 语义复查 | AI 语义复查完成，候选报告已输出 → 进入下一步 | Deterministic + LLM |
| 3 | 知识文件健康检查 | `python scripts/self-repair.py knowledge --dry-run` | 乱码可修复（确认后执行），其余只读报告 | 用户已决策（修复/跳过），报告已输出 → 进入下一步 | Deterministic + Human Gate |
| 4 | 经验索引新鲜度 | `python scripts/self-repair.py index --dry-run` | 过期时询问 → `python scripts/build-experience-index.py` 重建 | 索引已最新或用户确认重建完成 → 进入下一步 | Deterministic + Human Gate |
| 5 | 敏感信息扫描 | `python scripts/sensitivity-check.py --dir .` | 只读报告 | 报告已输出 → 进入下一步 | Deterministic |
| 6 | 全量自修复（可选） | `python scripts/self-repair.py all --dry-run` | 备份 → 报告 → 确认 → 修复 | 用户已决策（执行/跳过），修复完成或跳过 → 流程结束 | Deterministic + Human Gate |

### 步 1 — ADR 结构校验

运行 `adr-restructure.py --verify`，检查 4 项：

- **标题格式**：是否以 `### repo_XXX/ADR-NNN：标题` 格式书写
- **编号冲突**：两个不同 ADR 使用同一编号
- **编号跳号**：编号序列中存在断层（如 ADR-007 后直接 ADR-009，缺少 ADR-008）
- **来源标签**：是否每个条目都标注 `[来源:xxx]`

### 步 2 — 跨文件相似度去重检测

1. 运行 `python scripts/analyze-duplicates.py --json --threshold 0.6`
2. 读取结构化 JSON 输出，按文件类型（ADR / lessons / troubleshooting）分组
3. AI 语义复查：检查候选对是否真正语义重复
4. 输出去重候选报告（含相似度分数、行号、文件名）

### 步 3 — 知识文件健康检查

运行 `self-repair.py knowledge --dry-run`，检查 3 项：

- **乱码**：U+FFFD 替换字符、零宽空格、空字节
- **来源标签重复**：同一条目中来源标签是否重复
- **LESSONS 编号跳号**：lessons-learned.md 的编号序列是否存在断层

可修复项（乱码）在用户确认后执行。

### 步 4 — 经验索引新鲜度

1. 运行 `python scripts/self-repair.py index --dry-run`
2. 内部调用 `python scripts/build-experience-index.py --check`
3. 如索引已最新 → 跳过
4. 如索引过期 → 询问用户是否重建
5. 用户确认后运行 `python scripts/build-experience-index.py`

### 步 5 — 敏感信息扫描

运行 `python scripts/sensitivity-check.py --dir .`，扫描 6 类敏感模式：

- 内网 IP（10.x / 172.x / 192.168.x）
- 本地文件路径
- 邮箱地址
- API 密钥 / Token
- 个人用户名（启发式）
- 占位符残留（如 `[日期]`、`TBD`）

有发现时追加到清理报告，不自动修改。

### 步 6 — 全量自修复（可选）

运行 `python scripts/self-repair.py all --dry-run`，依次执行：

1. **agents** — 检查 AGENTS.md 章节完整性，从 starter 补缺
2. **knowledge** — 乱码修复（同步 3，但已去掉 ADR 编号和去重检查）
3. **index** — 索引重建（同步 4）

- 支持 `--dry-run` 预览（默认）
- 执行前自动备份到 `.backup/`
- 每步完成后输出可视化报告
- 全部完成后输出审核决策面板

---

## 输出格式

每步检查完成后输出对应的可视化报告。全部完成后输出汇总决策面板。

### 步 1 输出 — ADR 结构问题表

| # | 行 | 问题类型 | 详情 |
|---|----|---------|------|
| - | -  | -       | 验证通过，无问题 |

如有问题则逐行列出。

### 步 2 输出 — AI 语义复查报告

对每个候选对输出 diff 对比：

```
### N. ADR-XXX vs ADR-YYY (sim=0.7x)
  ADR-XXX (L123): [标题] [来源:...]
  ADR-YYY (L456): [标题] [来源:...]
  --- 正文差异 ---
  ADR-XXX: | **问题** | ... |
  ADR-YYY: | **问题** | ... |
  ---
```

| 判断 | 操作 |
|------|------|
| 建议合并 / 非重复 / 需人工判断 | 具体操作说明 |

末尾统计：

```
【AI 语义复查报告】
✅ ADR-003 vs ADR-045 (sim=0.72) → 重复，建议合并 — 两者都讨论 XXX
⏭️  ADR-010 vs ADR-099 (sim=0.71) → 非重复 — 前为缓存，后为持久化
⚠️  ADR-007 vs ADR-022 (sim=0.65) → 需人工判断 — 标题相似但 context 不同

📊 合计：候选 X 对 → 建议合并 Y 对 / 非重复 Z 对 / 需人工 W 对
```

### 步 5 输出 — 敏感信息审核表

| # | 文件 | 行 | 类别 | 片段 | 判断 |
|---|------|----|------|------|------|
| 1 | ADR.md | 162 | 邮箱 | `git@github.com:...` | 假阳性（SSH 伪邮箱） |
| 2 | lessons-learned.md | 170 | 路径 | `C:\Users\<user>\...` | 假阳性（已脱敏） |

**规则**：
- 判断列由 AI 预标注：`假阳性（原因）` / `待确认` / `需处理`
- 同类假阳性合并为一行 + 计数（如 `[12 处] git@github.com 伪邮箱`），减少噪音
- 末尾统计：`假阳性 X 项 / 待确认 Y 项 / 需处理 Z 项`

### 汇总决策面板

全部检查完成后输出：

```
【清理报告 — 审核决策面板】

  ADR 结构       | N/N 条目通过
  ADR 重复分析   | 无冲突
  知识文件健康   | 乱码 0 / 标签重复 0 / 编号跳号 0
  经验索引       | 已是最新

  敏感信息 (X 处)
  - [ ] #1-N 全部假阳性，忽略
  回复：确认全部假阳性 / 处理 #N

  重复条目 (Y 候选)
  - [ ] ADR-027 → 合并到 ADR-059
  - [ ] TS-84 vs TS-92 → 非重复，跳过
  回复：执行合并 / 执行删除 / 全部跳过
```

---

## ✅ 完成确认清单

在宣布清理流程完成前，确认以下全部成立：

- [ ] 步 1~5 全部执行完毕，每步 Exit Condition 已满足
- [ ] 步 6（如执行）已完成或用户明确跳过
- [ ] 所有只读报告已输出给用户
- [ ] 所有需要用户决策的项（乱码修复、索引重建、修复执行）均已获得用户确认
- [ ] 已告知用户「清理完成」，输出汇总决策面板
- [ ] 不擅自执行不属于清理流程的动作（不分发、不 Git 提交、不修改敏感信息）

---

## 限制边界

- AI 复查不自动合并，只输出建议
- ADR 结构问题只报告不自动修复（`--verify` 只读模式）
- 索引重建需用户二次确认
- 敏感信息不自动修改，由用户结合审核表逐项决策
- 不调用分发管线
- 不操作 Git

---

## 自检测脚本清单（所有参与管线的脚本）

| 脚本 | 职责 | 所在步骤 |
|------|------|---------|
| `scripts/adr-restructure.py --verify` | ADR 格式/编号/来源标签校验 | 步 1 |
| `scripts/analyze-duplicates.py` | ADR/lessons/troubleshooting 相似度去重 | 步 2 |
| `scripts/self-repair.py knowledge --dry-run` | 知识文件乱码/标签重复/编号跳号 | 步 3 |
| `scripts/self-repair.py index --dry-run` | 经验索引新鲜度检查 | 步 4 |
| `scripts/build-experience-index.py --check` | 索引过期检测（被步 4 内部调用） | 步 4 |
| `scripts/sensitivity-check.py --dir .` | 敏感信息扫描 | 步 5 |
| `scripts/self-repair.py all --dry-run` | 全量自修复 | 步 6 |

---

## 各步互斥保证

| 检查项 | 唯一归属 | 排他理由 |
|--------|---------|---------|
| ADR 格式/编号/来源标签 | 步 1 | adr-restructure.py 是 ADR 专用 |
| 跨文件相似度去重 | 步 2 | 步 3/6 已移除内部 analyze-duplicates 调用 |
| 知识文件乱码 | 步 3 | self-repair knowledge 独有 |
| LESSONS 编号跳号 | 步 3 | self-repair knowledge 独有 |
| 来源标签重复（非ADR） | 步 3 | self-repair knowledge 独有 |
| 索引新鲜度 | 步 4 | build-experience-index.py 专有 |
| 敏感信息 | 步 5 | sensitivity-check.py 专有 |
| AGENTS 章节同步 | 步 6 | self-repair agents 独有 |
