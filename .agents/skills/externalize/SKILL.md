---
name: externalize
description: Convert auto-loaded skills to on-demand AGENTS.md trigger-word + docs/workflows/ format, or interview the user to create a new externalized skill. Use when the user says "externalize", "外部化", or asks to reduce skill context bloat.
description_zh: 将自动加载技能转化为AGENTS.md触发词 + docs/workflows/按需加载格式，或采访用户新建外挂技能。用户说"外部化"时使用。
---

# Externalize — Skill 外挂化工具

> 将自动加载 skill 转化为按需外挂（AGENTS.md 触发词 + `docs/workflows/` 实现），或采访用户新建外挂 skill。

## 分工

| 角色 | 做什么 |
|------|--------|
| **脚本族**（`.agents/skills/externalize/*.py`） | 多脚本模式，一个脚本一个职责。详见下方多脚本模式章节 |
| **本 SKILL.md**（AI） | 运行脚本，检查产出，处理边界情况；打包技能场合负责评估是否拆分为目录结构 |

## 技能类型

每次处理前，AI 读取目标 `SKILL.md` 全文并判断类型：

| 类型 | 特征 | 建议 |
|------|------|------|
| **心智模型** | 全场景自动激活、无触发词、每轮持久。如审核前必须检查的不变量 | 不适合外部化，建议保留 auto-loaded。**决定权在用户** |
| **单模式工具型** | 有明确触发条件、有步骤序列、一次性输出。如 triage | 外部化为 1 个 workflow 文件 |
| **打包技能** | 1 个 skill 内含多个子模式。如 Ponytail（含 review/audit/debt/gain/help/core） | 评估是否拆分为目录结构（见下文） |

**关键原则：前置判断是提醒，决定权在用户。** 即使判断为"建议保留"，也向用户说明理由，由用户最终决定。

### 打包技能拆分评估

当判定为打包技能时，AI 评估是否适合拆分为 `docs/workflows/{name}/` 目录结构：

- 子模式有独立触发条件或独立边界 → 适合拆分
- 子模式高度耦合、必须按序执行 → 不适合拆分，用单文件多章节

评估结果向用户说明：**子模式数量和各自边界、建议拆分方案**，由用户确认。

## 多脚本模式

一个脚本一个职责：

| 脚本 | 职责 |
|------|------|
| `classify.py` | 读取 SKILL.md，输出技能类型诊断 + 建议方案。AI 基于诊断与用户确认 |
| `convert-single.py` | 转化单模式 skill → 1 个 AGENTS.md 触发条目 + 1 个 workflow 文件 |
| `convert-pack.py` | 转化打包技能 → AGENTS.md 触发条目 + `docs/workflows/{name}/` 目录（`_index.md` + 子文件） |
| `new-single.py` | 新建单模式 skill（AI 采访收敛后 → 骨架文件） |
| `new-pack.py` | 新建打包技能（AI 采访收敛后 → 目录骨架 + 子文件） |
| `remove.py` | 移除外部化技能（检测单文件/目录分别处理） |

脚本命名风格统一为 `.agents/skills/externalize/` 目录下的小写短名。

## AI 检查清单

脚本执行完毕后，AI 必须逐项检查，**仅在异常时手动修正**：

### 通用检查（所有类型）

| # | 检查项 | 通过标准 | 失败动作 |
|---|--------|---------|---------|
| C1 | AGENTS.md 技能索引存在 | `## 技能索引` 章节出现在文件中 | 手动追加章节 + 触发条目 |
| C2 | 触发条目格式正确 | 每行格式为 `` - `{词|变体}` → `docs/workflows/{name}.md` `` 或 `docs/workflows/{name}/_index.md` | 手动修正格式 |
| C3 | workflow 文件存在且可读 | 路径上的文件可打开 | 重新运行脚本 |
| C4 | workflow 含 `## 确认`（除非 `--no-confirm`） | 确认章节存在 | 手动追加默认确认块 |
| C5 | convert 路径：原 skill 已归档 | `.agents/skills/_archived/{name}/` 存在 | 手动 `mv` |

> **注意**：`## 标准动作` 不再列为必检项——单模式技能应有，打包技能的模式各自有独立动作描述。

### 打包技能专项检查

当拆分为目录结构时，额外检查：

| # | 检查项 | 通过标准 | 失败动作 |
|---|--------|---------|---------|
| P1 | `_index.md` 模式选择表有编号 | 表头为 `| # | 模式 | 说明 |`，编号从 1 递增 | 手动修正编号 |
| P2 | 模式编号 1:1 映射文件 | `1` → `01-{name}.md`，每个编号都有对应文件 | 补充缺失的子文件 |
| P3 | 心智模型模式已标注特殊性 | 子文件中有"始终开启"、"无需显式调用"等标注 | 补充标注 |
| P4 | 每个子模式有独立调用入口 | `_index.md` 中可定位到每个子模式的文档位置 | 补充子模式文档路径 |

### 检查失败处理

- 标记失败的检查项编号（如 C1、P2）
- **仅在清单指定的「失败动作」范围内手动修正**
- 清单未覆盖的问题 → 回到用户确认

---

## 模式一：转化已有 skill

用户说 `externalize convert <name>` → AI 执行：

1. **运行 classify**：`python .agents/skills/externalize/classify.py <name>` → 读取 SKILL.md，输出类型诊断
2. **向用户汇报诊断结果**：类型 + 建议方案。**classify 自动从 description 提取触发词建议**（引号内的词），用户确认或修改
3. **根据用户确认的类型和触发词选择脚本**：
   - 单模式 → `python .agents/skills/externalize/convert-single.py <name> [--trigger "词|变体"]`
   - 打包技能 → `python .agents/skills/externalize/convert-pack.py <name> [--trigger "词|变体"] --sub-modes "1:..."`（或 `--auto-detect`）
   
   `--trigger` 可选：不传则脚本自动从 description 提取；传则覆盖自动提取的结果。
4. **按「AI 检查清单」逐项验证产出**
5. **归档**：脚本自动归档原 skill 至 `.agents/skills/_archived/{name}/`
6. **如需恢复**：`mv .agents/skills/_archived/{name}/ .agents/skills/{name}/`

---

## 模式二：新建外挂 skill

用户说「我想新建一个能力用来 XXX」→ AI 启动采访：

### 采访原则

- **逐轮提问，每次只问一个问题**
- **能通过读代码回答的，先读代码再问**
- **收敛到决策树每个分支都解决**（上限 5 轮）
- 不猜测用户意图——不明确处必须问

### 必问项

1. 这个能力要解决什么问题？达到什么效果？
2. 触发条件是什么？用户说什么/做什么时该加载？
3. 加载后执行什么动作？（步骤序列、格式要求、判断逻辑）
4. 需要 y/n 确认吗？（默认需要；如果动作无副作用可说不需要）
5. 触发词用什么？（你用哪些词喊它？）
6. **（如果判断为打包技能）** 子模式有哪些？各自什么触发条件？

### 收敛后调脚本生成

AI 判断技能类型，选择对应脚本：

```bash
# 单模式（可加 --judgment 提供判断逻辑）
python .agents/skills/externalize/new-single.py --name {name} --trigger "{词|变体}" --actions "1. 步骤1;;2. 步骤2;;..." [--judgment "条件→动作;;条件2→动作2"] [--desc "说明"]

# 打包技能（需先确认目录结构）
python .agents/skills/externalize/new-pack.py --name {name} --trigger "{词|变体}" --sub-modes "1:模式1:说明;;2:模式2:说明;;..."
```

AI 随后检查产出。

---

## 模式三：移除已外部化技能

用户说「删除 xxx 外部化」→ AI 执行：

1. **运行脚本**：`python .agents/skills/externalize/remove.py <name>`
2. 脚本自动完成：
   - 删除 AGENTS.md 中对应的触发行
   - 检测是单文件还是目录结构 → 删除对应路径
   - 检测到 `_archived/{name}/` 存在时弹出交互选择
   - `y` → 删除归档（不可恢复）
   - `n` → 保留归档
   - **其他任何输入** → 脚本退出，AI 接手与用户继续对话

---

## 生成格式参考

### 单模式 workflow 文件

```markdown
# {名称}

> 按需加载工作流。触发词：{触发词列表}

## 标准动作

1. {步骤1}
2. {步骤2}
3. ...

## 判断逻辑（可选）

- {条件} → {动作}

## 确认

执行上述动作前，先向用户说明将要做什么，等待确认：
- `y` → 执行
- `n` → 取消
```

### 打包技能目录结构

```
docs/workflows/{name}/
├── _index.md       # 模式选择表 + 导航
├── 01-{mode}.md    # 子模式 1
├── 02-{mode}.md    # 子模式 2
└── ...             # 递增
```

`_index.md` 规范格式：

```markdown
# {名称}

> 按需加载工作流。触发词：{触发词列表}

## 模式选择

| # | 模式 | 说明 |
|---|------|------|
| 1 | **{模式1}** | {简要说明} |
| 2 | **{模式2}** | {简要说明} |
| 3 | **{模式3}** | {简要说明} |

AI 根据上下文自动选择模式，或用户直接指定。模式文件见对应编号文档：
- [1. {模式1}](01-{模式1}.md)
- [2. {模式2}](02-{模式2}.md)
- ...
```

**编号规则**：简单从 `1` 开始递增，不加缩写前缀。文件名用 `01-`、`02-` 前缀保持排序稳定。

---

## 触发机制

- **关键词精确匹配**：Agent 扫描 AGENTS.md 技能索引，精确匹配触发词后加载 workflow
- **y/n 门控**：加载后先说明将要做什么，等用户确认再执行
- **窄触发优先**：触发词偏窄而非偏宽——宁可漏触发，不要误触发

## 触发扫描规则

Agent 启动时按以下逻辑解析技能索引：

1. 扫描 AGENTS.md 全文，定位 `## 技能索引` 章节
2. 解析该章节下所有 `` - `{词|变体}` → `docs/workflows/{path}.md` `` 行
3. 用户消息到达时，对每条触发词的每个管道分支做**完整字符串精确匹配**（非子串匹配）
4. 匹配成功 → 加载对应 `docs/workflows/{path}`，按模式选择逻辑执行
5. 未匹配 → 不加载任何外部化 workflow

> **与 §4.x 精确匹配的关系**：两套机制独立运作，互不干扰。§4.x 负责内置指令（存档、恢复、清理等），`## 技能索引` 负责外部化 skill。Agent 启动时同时初始化两套扫描，消息到达时两套并行匹配。
