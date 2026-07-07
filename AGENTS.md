# <项目名> — Agent 启动指令

---

## 0. 项目基础设施

### 基础设施层

| 文件 | 职责 |
|------|------|
| `AGENTS.md` | 项目硬规则 + 模块速查 |
| `docs/workflows/agent-coding-workflow.md` | 五阶段 workflow 参考 |
| `status.md` | 当前进度、待办清单 |
| `session-log.md` | 会话历史记录 |
| `ADR.md` | 关键决策记录 |
| `troubleshooting.md` | 问题索引 |
| `lessons-learned.md` | 经验沉淀 |
| `.gitattributes` | 统一换行符(LF) + 标记二进制文件 |
| `config/github-sync.json` | 跨项目知识同步配置 |

### 技能（Skills）

项目自带一组 AI 助手技能（路径：`.claude/skills/`），覆盖代码审查、调试、归档等场景。技能文件为 markdown 指令，由 AI 助手按需加载。

**可用技能清单**见 `MANIFEST.txt`（`starter/.agents/skills/`，`init-skeleton.py` 或 `distribute.py` 自动安装）。

### 阶段产出层（按 SOP 五阶段逐步创建）

| 阶段 | 产出文件 |
|------|---------|
| 阶段一 | `docs/proposal.md` |
| 阶段二 | `docs/design.md`、`docs/brief.md`、`docs/database.md`（条件性，T-01②/③）、`docs/frontend.md`（条件性，T-05②） |
| 阶段三 | `docs/tasks/task-{module}.md` |
| 阶段四 | `prompt.md` |
| 阶段五 | `src/`、`tests/`、各模块源码 |

---

## 1. 项目定位

[一句话描述项目]

- **形态**：[Web / App / CLI / 桌面 / 嵌入式]
- **技术栈**：[语言 + 框架]
- **目标用户**：[谁会用]

> 环境详情（版本号、构建/测试命令）见 `status.md`「环境备忘」。

---

## 2. 必读上下文（按顺序，5 分钟）

1. `AGENTS.md` — 本文件（硬规则）
2. `status.md` — 当前进度、待办清单、环境备忘
3. `session-log.md` — 前几轮怎么走到这里的
4. `docs/design.md` — 概要设计（如需改架构或接口）
5. `troubleshooting.md`（条件性）— 如用户当前遇到具体报错
6. `docs/workflows/anti-patterns-checklist.md`（阶段二进入时必读）— 运行反模式检查，确保设计不重复踩坑

> **新项目启动时额外阅读**：`docs/workflows/agent-coding-workflow.md` — 五阶段 Agent Coding workflow。

**禁止**：在未阅读 `status.md` 前直接写代码。

---

<!-- @sync:id=core-constraints -->
## 3. 核心约束（硬规则，不可违反）

| 规则 ID | 规则内容 | 违反后果 |
|---------|---------|---------|
| **RULE-01** | **必须先建立基础设施层，再按阶段创建产出层** | 过程无记录、状态不可追踪 |
| **RULE-02** | **所有文件 I/O（`open()` / `read_text()` / `write_text()`）和 `subprocess.run()` 必须显式传入 `encoding` 参数** | 依赖系统默认编码会在 Windows GBK 下崩溃 |
| **RULE-03** | **触及以下清单时，暂停，输出 Scope 声明表（见下），等用户确认后方可继续：**<br>【文件哨兵】`AGENTS.md` / `TRIGGERS.md` / `config/*.json` / `docs/workflows/*.md` / `.claude/skills/`<br>【高危操作】文件删除 / `git push` / 单次触及 >3 个文件<br>【安全门禁】向 `C:\Windows`、`/System`、`/etc` 等系统关键目录写入 | 职责边界破坏、下游污染、系统污染、不可逆操作绕过审查 |
| **RULE-04** | **实现任何功能前，按"依赖决策门禁"决策：优先 stdlib/手写，不满足才引入库；安全/正确性敏感域优先审计库**<br>详见下方执行步骤 | 重量级依赖膨胀、许可证入侵、版本锁死 |
| **RULE-05** | **阶段口令是启动器而非执行器：口令只负责检查前置条件、说明目标、确认启动，不通过则禁止启动该阶段。具体执行细节严格引用 `docs/workflows/agent-coding-workflow.md` 对应章节，禁止在口令逻辑中重写执行规范。** | 跳步导致产出无上下文；规则在两处维护导致版本分歧 |

### RULE-04 依赖决策门禁（执行步骤）

实现任何功能前，按以下顺序评估，满足则停：

| 档 | 评估问题 | 怎么做 | 典型例子 |
|----|---------|--------|---------|
| **A — stdlib/手写** | 标准库或手写（适度规模、领域特定）能给出稳健实现？且**非**安全/正确性敏感域？ | 直接用，不引入任何依赖 | CLI (`argparse`)、Web (`http.server`)、DB (`sqlite3`)、`difflib`、`tomllib`、领域 Markdown 解析（re）、简单 schema 校验、JSON merge、GBK 兼容包装 |
| **B — 引入依赖** | A 不可行，**或** 域为安全/正确性敏感（加密/鉴权/解析不可信输入/时区/YAML-JSON schema），**或** 通用问题用成熟库总成本低？ | **导入前**完成：① 许可证兼容 ② transient deps 数量 ③ 若 > 800MB（如 torch）做成可插拔、默认关闭 ④ 写 ADR | `requests`、语义向量 `sentence-transformers`（可插拔）、测试框架 |

> **原则**：不是「复用优先」也不是「手写优先」——按成本梯度从低到高选；但**安全/正确性敏感域优先用经过审计的成熟库**，即便能手写。
> **已 sanction 的依赖（非"零依赖"的例外清单）**：① `requests`（`sync-knowledge.py`）② ADR 批准的可插拔后端 `sqlite-vec` / `sentence-transformers`（惰性导入、默认关闭）。母库核心仍坚持零外部依赖；引入新依赖必须走 B 档评估 + ADR。
> **作用域**：对 `starter/` 与对外分发的脚本**强制**；本地一次性 helper 可放宽。
> **违规症状（两侧都要防）**：
> - 过度依赖：用 5 个包替代 15 行手写 → `npm audit` 高危 → 版本锁死。
> - 过度手写：为避依赖自写安全/正确性敏感逻辑（自写 YAML/JSON 解析、鉴权、时区）→ 隐性 bug，比审计库更致命。
<!-- /@sync -->

---

## 4. 阶段指令

> 五阶段 SOP 的完整定义见 `docs/workflows/agent-coding-workflow.md`（阶段启动机制、阶段定义速查、产出要求）。口令是启动器而非执行器（RULE-05）。

### 当前阶段

> 完整执行流程见 `docs/workflows/current-phase.md`。

---

## 5. 技能索引

> 所有触发词均采用**精确匹配**：消息去除标点后精确等于触发词时触发。包含触发词但还有其他内容 → 视为正常对话，不触发。

- `存档` → `docs/workflows/archive.md`
- `恢复` → `docs/workflows/resume.md`
- `清理` → `docs/workflows/cleanup.md`
- `项目审查` → `docs/workflows/project-review.md`
- `立项` → `docs/workflows/lightweight-dev.md`
- `当前阶段` → `docs/workflows/current-phase.md`
- `懒人审查|ponytail|lazy|yagni|simplest` → `docs/workflows/ponytail/_index.md`
- `双轴审查|双轴` → `docs/workflows/dual-axis-review.md`
