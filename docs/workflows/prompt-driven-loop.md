# Agent Loop Workflow — 自主循环式开发方法论

> 与 Agent Coding 五阶段 SOP 同级替代方案。适用于需求明确、适合一次交付的任务。
> 核心理念：**一次给足规格，Agent 在循环中自主决策执行，人仅确认起止与关键节点。**

---

## 适用场景 vs 五阶段 SOP

| 维度 | 五阶段 SOP | Loop 工作流 |
|------|-----------|------------|
| 核心模式 | 人决策 → Agent 执行 → 人确认 → 推进 | Agent 在循环中自主决策执行 |
| 会话边界 | 每个阶段一个会话 | 一个循环/会话完成 |
| 人参与度 | 每阶段结束必须确认 | 启动 + 异常介入 + 结果确认 |
| Agent 自主度 | 按阶段指令执行 | 自主拆解任务、决定执行顺序 |
| 适合场景 | 需求模糊的复杂项目 | 需求明确的开发/重构/审查任务 |
| Prompt 策略 | 分阶段逐步给出 | 一次给出完整规格 |
| 错误恢复 | 阶段内重试 | 循环内重试或降级为补丁循环 |
| 结果追溯 | 分阶段产物 | Execution Trace（全量操作日志）|

### 选型指南

| 项目状态 | 推荐流程 |
|---------|---------|
| 需求不明确，需要多轮讨论 | 五阶段 SOP（阶段一） |
| 需求明确（有 PRD/设计），实现策略清楚 | **Loop 工作流** |
| 纯编码任务（重构、修 bug、加功能） | **Loop 工作流** |
| 跨多个系统的复杂集成 | 五阶段 SOP |
| 实验性探索（验证某个思路可行性） | **Loop 工作流** |

---

## 项目起点判断

| 状态 | 切入方式 | 动作 |
|------|---------|------|
| **有完整需求**（PRD / 设计文档 / Issue） | 直接喂给 AI 辅助生成 Prompt | AI 阅读已有文档 → 输出 `prompt-scope.md` |
| **有粗略想法** | AI 辅助定界 | 对话方式确认范围 → AI 输出 `prompt-scope.md` |
| **有现有代码需要修改** | AI 评估 + 定界 | Agent 先读代码 → 输出变更范围和 `prompt-scope.md` |
| **有上一轮 execution trace** | 延续补丁循环 | 读取 trace 生成补丁 scope |

---

## 标准使用流程（推荐模式）

这是推荐的最高效路径。核心思想：**用一个 AI 帮另一个 AI 准备输入。**

### Phase 0（前置）：环境检测

> 在执行第零步之前，确认工具链就绪。如果工具链缺失，AI 辅助定界后也无法执行。

```
┌───────────────────────────────────────────────────────────┐
│ Phase 0: 环境检测                                         │
│                                                           │
│    检查项：编译器 / CLI / 项目目录 / 依赖                   │
│    任一失败 → 输出安装指引 → PAUSED                        │
│    全部通过 → 进入第零步                                    │
│                                                           │
│    * 将环境检查放在第零步之前，避免浪费 AI 定界的成本        │
└──────────────────────────────────────────────────────────┘
```

                          │
                          ▼

┌───────────────────────────────────────────────────────────┐
│ 第零步：AI 辅助定界                                       │
│                                                           │
│   你: "我要做一个 X" ← 一句模糊需求就够了                   │
│       ↓                                                   │
│   AI（Claude）:                                           │
│      - 追问确认关键信息（技术栈、边界、交付物）              │
│      - 输出 prompt-scope.md（格式见后）                     │
│      - 你可以手动修改/补充                                  │
│       ↓                                                   │
│   产出: prompt-scope.md（执行循环的输入）                   │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────┐
│ 第一步：执行循环（AgentLoop）                              │
│                                                           │
│   编排器自动执行 while not done:                           │
│      1. AgentDriver.step(messages) → 获取决策              │
│      2. 有 tool_calls → ToolExecutor.execute → 追加结果    │
│      3. 无 tool_calls → 循环结束                           │
│                                                           │
│   编排器在后台运行，每 5 轮自动执行一次 verify 门禁         │
│   Agent 在标准 I/O 管道中与编排器通信，零人工介入           │
│   Ctrl+C 中断 → 保存状态后断点恢复                          │
│       ↓                                                   │
│   产出: 全部交付物                                        │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────┐
│ 第二步：结果验证                                           │
│                                                           │
│  （可手动或交给另一个 AI 做）                               │
│                                                           │
│    1. 对照交付清单检查所有产物是否存在                       │
│    2. 运行测试看是否通过                                    │
│    3. 阅读 trace.json 了解 Agent 做了什么                   │
│       ↓                                                   │
│    决策:                                                   │
│      ✅ 满意 → 完成                                        │
│      🔄 有小问题 → AI 生成补丁 scope → 再跑一轮            │
│      ❌ 大方向错 → 回到第零步重新定界                       │
└──────────────────────────────────────────────────────────┘
```

### 使用模式的变体

Loop 工作流的核心是 AgentDriver 接口——不同的后端决定执行方式：

| 变体 | 定界方式 | AgentDriver | 自动化程度 | 需要 |
|------|---------|------------|-----------|------|
| **C（推荐）** | AI 辅助定界 | StdioDriver → 外部 Agent CLI（stdin/stdout 管道） | 全自动 | CLI Agent 支持 |
| B | AI 辅助定界 / 手动写 scope | 无编排器；pipeline 模式：直接粘贴给 Agent IDE | 半自动 | 人工粘贴 + 确认 |
| A | 全手动 | 无编排器；手写代码 | 手动 | — |

**模式 C 是推荐路径**：编排器通过 StdioDriver 与外部 Agent CLI 通信，
每次 `step()` 交换结构化 JSON（messages → ToolCall[]），
零人工介入。适用于任何支持 stdin/stdout 协议的 Agent。

**模式 B** 是降级路径：Agent 无 CLI 接口时退化为人工粘贴。
约等于编排器不存在，Loop 概念退化为"一次给足 scope 交给 Agent"。

### 编排器驱动模式

Loop 工作流的编排器（如 trae-loop.py）可由终端人类或 AI Agent 驱动。
二者对编排器输出（指引文本）的解读方式不同：

| 驱动方式 | 角色分配 | 第零步执行者 | 输出解读 |
|---------|---------|------------|---------|
| **人工驱动** | 人读取输出 → 按指引操作 | 人 + 独立 Claude 对话 | 直接指令，人执行每一步 |
| **AI 驱动** | Agent 读取输出 → 引导人操作 | Agent（当前会话）或人 | 角色标记输出，Agent 转达 |

**AI 驱动模式的核心规则**：

- **R-01**：编排器脚本输出中的「用户操作」标记内容由人类执行，AI 编排器不得自行代劳
- **R-02**：第零步（生成 prompt-scope.md）可由 AI 编排器直接承担——读取 spec.md → 按标准格式输出 scope，无需人操作中间步骤
- **R-03**：执行阶段（将 scope 喂给执行器）在无 CLI 时必须由人类操作，AI 编排器只能引导
- **R-04**：AI 编排器读到「用户操作」标记时，应主动向人类转述操作内容并提示执行，不可跳过

**AI 编排器的身份边界**：编排器输出中引用「Claude」时必须显式指定上下文
（如「当前会话」「Trae IDE 的 Claude」），避免引发 Agent 对自身身份的误判。
编排器应始终将自身定位为「引导者 + 验证者」，而非「执行者」。

---

## 核心循环模型

Agent 进入执行阶段后的内部逻辑：

```
while not done:
    observation = observe_current_state()
    # 读取文件、git diff、测试结果

    action = plan_next_action(observation, prompt_scope)
    # 决定下一步：写代码/读文件/跑测试

    result = execute_tool(action)
    # 调用工具：edit_tool / bash / read

    done = evaluate_completion(result, delivery_checklist)
    # 自我评估：交付物是否全部完成？

# 循环结束，进入交付后行为
report_completion()
# 输出完成报告后停止，等待编排器验证
# 不询问用户"下一步做什么"，不扩展 scope
```

### 执行规则

| 规则 | 说明 |
|------|------|
| **执行自主** | Agent 自主决定文件创建顺序和实现策略 |
| **交付物导向** | Agent 以交付清单为终点，不偏离 scope |
| **自检自查** | 每个文件创建后 Agent 自行验证正确性 |
| **工具优先** | 用工具执行而非生成建议（直接 edit / bash） |
| **循环不中断** | 除非到达检查点或异常，Agent 持续循环 |
| **不猜测需求** | Scope 中未定义的不做 |
| **交付后停止** | 交付清单全部完成 → 输出完成报告 → 停止，等待编排器验证。不要询问用户下一步或建议 scope 外任务 |

---

## 停止条件

Agent 停止条件分三个层面：

| 层面 | 机制 | 当前状态 |
|------|------|---------|
| LLM 自判 | Agent 无更多 tool call 时认为完成 | 不可靠，经常过早/过晚停止 |
| 安全网 | 最大循环次数 / 超时 / 错误上限 | ✅ 已验证：2 次重试 → PAUSED |
| 验证门禁 | 外部检查交付清单 + 内容质量 + trace | ✅ 已验证：详见下方 |

### 实验数据（来自 Claude Code Island 项目）

> 本部分基于 `trae-loop` 编排器的真实运行数据。

**验证门禁的三层检查**（已完成实验验证）：

```
┌─ 验证门禁（一次通过全部检查）─────────────────────────────┐
│                                                            │
│  1. 文件存在性    PhaseChecker 确认交付件文件都存在          │
│                   问题：空 stub 文件（28 字节）也会通过      │
│                                                            │
│  2. 内容质量      TraceAnalyzer 补充检查：                   │
│                    - 文件大小 >= 最小阈值（如 50 字节）       │
│                    - 关键章节/关键字在文件内容中              │
│                    - 非占位符内容                             │
│                                                            │
│  3. Execution     CLI 模式: trace.json 字段完整              │
│      Trace       IDE 模式: 标记为「无 trace 属正常」         │
│                                                            │
│  检查不通过 → bump_attempt → 重试（最多 2 次）              │
│  2 次仍不通过 → PAUSED（人工排查）                          │
└────────────────────────────────────────────────────────────┘
```

**补丁循环触发流程**（已完成实验验证）：

```
验证结果 → 决策 → 下一动作
─────────   ──   ────────
全部通过, 人满意       → done
全部通过, 人不满意     → redo（回到执行阶段，bump_attempt）
文件缺失, attempt ≤ 2 → 自动重试（注入失败上下文）
文件缺失, attempt > 2 → PAUSED（人工介入）
大方向错               → 回到第零步重新定界
```

### 待实验问题（欢迎贡献数据）

- Agent 自判完成 vs 外部验证门禁，哪个作为最终停止判定？
- 除文件大小外，还有哪些高效的内容质量检查指标？
- 合理的超时阈值？
- 补丁循环是否应该在 PAUSED 后自动「降级为补丁」还是必须人工决定？

---

## 关键输入：Prompt Scope

`prompt-scope.md` 是执行循环的唯一输入。由第零步 AI 辅助生成。

### 标准结构

```markdown
# [项目名] — Agent Loop Scope

## 任务目标
[一句话描述要完成什么]

## 交付清单
- [ ] 文件/功能 A（可验证条件：如文件存在、测试通过）
- [ ] 文件/功能 B

## 约束条件
- 技术栈
- 禁止事项
- 已知边界

## 质量标准
- 测试要求
- 代码规范
- 验收条件

## 已知上下文
- 现有代码结构（如果有）
- 关键设计决策
- 历史踩坑经验

## 风险提示
- 可能的陷阱
- 参考链接

## 检查点配置（可选）
- checkpoint: highrisk  # 高风险操作前暂停
- checkpoint: never    # 全自动，不暂停

## 交付后行为 ⚠️ 必填
- 完成交付清单后: 停止执行, 等待编排器验证（不要在终端询问用户"下一步做什么"）
- 自主决定事项: 执行期间不要询问用户优先级或选择, 自己决定顺序
- 交付格式: 完成所有交付物后仅输出简要完成报告, 不要建议新的 scope 外任务
```

### 编写原则

| 原则 | 说明 |
|------|------|
| **一次给足** | 所有信息在定界阶段输入，执行期间不补充 |
| **具体可验证** | 交付清单每项应是可检查的（文件存在/pass） |
| **约束前置** | 禁止事项写最前面，避免走偏 |
| **上下文完整** | 有现有代码时包含文件结构和关键接口 |
| **例子胜过描述** | 提供输入/输出样例比抽象描述更有效 |
| **行为显式化** | 明确告诉 Agent 完成交付后做什么——它默认会问用户"下一步"，需要显式阻止 |

---

## 关键输出：Execution Trace

Agent 执行循环产生的操作日志。格式取决于 Agent 实现（如 trae-cli 输出 trajectory.json）。

### 推荐结构化字段

```json
{
  "execution": [
    {"step": 1, "action": "create_file", "file": "src/main.py"},
    {"step": 2, "action": "run_test", "output": "PASS"}
  ],
  "prompt":   "任务描述（简短）",
  "scope":    "完整 prompt-scope.md 内容",
  "duration": 120.5,
  "errors":   []
}
```

| 字段 | 必需 | 说明 |
|------|------|------|
| `execution` | ✅ | 操作记录列表，每个 step 含 action/file/output。必须是非空数组。 |
| `prompt` | ✅ | 喂给 Agent 的任务提示（简短摘要） |
| `scope` | ✅ | 完整 prompt-scope.md 内容（用于追溯输入） |
| `duration` | 可选 | Agent 执行耗时（秒） |
| `errors` | ✅ | 错误列表，空数组 = 无错误 |

### 用途

| 用途 | 说明 |
|------|------|
| **结果验证** | 确认 Agent 完成了哪些操作、创建了哪些文件 |
| **内容质量检查** | 结合 TraceAnalyzer 检查文件最小大小、关键字存在、非占位符内容 |
| **错误追溯** | 失败时查看具体哪一步出错；`errors` 字段中的严重错误标记 |
| **审计** | 了解 Agent 决策过程 |
| **补丁生成** | 下一轮循环可基于 trace 继续 |

### IDE 粘贴模式说明（模式 B，降级路径）

IDE 粘贴模式下 Agent 不会自动输出 trace.json。属于正常情况，验证阶段应跳过 trace 检查，通过 PhaseChecker + 内容质量检查补偿。
推荐使用模式 C（AgentLoop + AgentDriver），trace 由编排器在 messages 中完整记录。

---

## 错误恢复策略

| 错误类型 | 恢复方式 |
|---------|---------|
| Agent 单步失败 | 自动重试（最多 2 次） |
| Agent 偏离 scope | 触发检查点，人工纠正后继续 |
| 达到最大循环次数 | 强制暂停，输出已完成的中间产物 |
| 环境问题 | 输出环境检查报告，修复后继续 |
| 需求变更 | 不在执行中变更，记录后重新定界。**例外**：审查检查点处可细化已有 scope section |

---

## 审查检查点（Developer Feedback Loop）

通过 `--review-every N` 标志，在每 N 次迭代后暂停，让开发者介入审查。

### 使用方式

```
agent-loop run -s prompt-scope.md --review-every 5
```

配置中持久化：
```yaml
loop:
  review_interval: 5
```

### 检查点流程

循环暂停发生在 **agent 决定工具调用之后、执行之前**（最安全的审查位置）：

1. Agent 完成决策，编排器收到待执行的工具调用列表
2. 编排器打印审查摘要：迭代编号、交付物状态、scope 变更检测
3. 开发者输入：
   - `c` / `continue` → 继续执行
   - `abort` → 保存状态并停止
   - 其他文本 → 作为 `[DEVELOPER FEEDBACK]` 系统消息注入给 agent
4. 同时检测 scope 文件变更：如有 section 变更（非增删 section），计算 delta 并告知 agent

### Scope 变更路径

检查点 → 开发者改 scope 文件 → 编排器重读检测 delta → 更新 agent 上下文 + 注入 delta 消息 → agent 后续步骤感知新约束

> PhaseChecker 每次都从磁盘重读 scope，天然兼容 scope 文件变更。

---

## 跨循环通用规则

| 规则 | 说明 |
|------|------|
| L-01 | Scope 确定后不新增需求，遗漏归入补丁列表。**例外**：审查检查点（`--review-every`）处，开发者可细化已有 section 内容（目标/约束/门禁/交付清单），不可新增 section |
| L-02 | Agent 自主决定执行顺序，人不干预中间步骤 |
| L-03 | 每项交付物必须有可验证的完成条件 |
| L-04 | 失败重试不超过 2 次，之后触发检查点 |
| L-05 | Execution Trace 是官方记录，人可通过 trace 审计每一步 |
| L-06 | 检查点触发时，Agent 必须先输出状态摘要再等待输入 |
| L-07 | 补丁循环不修改 scope，只修正偏差 |
| L-08 | Agent 完成全部交付物后立即停止执行，等待编排器验证；不得扩展 scope、不得询问用户下一步优先级，建议归入补丁列表 |

---

## 与五阶段 SOP 的互操作

两个方法论可以混合使用：

```
模糊需求 → SOP 阶段一 → docs/proposal.md
    │
    ├── 复杂的 → 继续 SOP
    │
    └── 需求明确了 → 转为 Loop 工作流
            │
            AI 读 proposal.md → 输出 prompt-scope.md
            │
            AgentLoop(scope) → 交付物 → 验证完成
```

---

## 附录 A：编排器 CLI 实现示例

### 标准流程

```bash
# Phase 0：环境检测
python3 trae-loop.py --env-check

# 第零步：AI 辅助生成 prompt-scope.md（用另一个 Agent 完成）

# 第一步：执行循环（while not done 自动运行）
python3 trae-loop.py --run

# 第二步：验证结果
python3 trae-loop.py --verify
```

### 补丁循环

```bash
# 第一轮
python3 trae-loop.py --run

# 验证发现缺陷 → 生成补丁 scope → prompt-scope-patch.md

# 第二轮（用补丁 scope 覆盖旧 scope）
cp prompt-scope-patch.md execution/prompt-scope.md
python3 trae-loop.py --run
```

---

## 附录 B：与设计文档的关系

Loop 工作流不强制生成设计文档序列。但如果项目已有：

| 已有文档 | 在 prompt-scope 中的用途 |
|---------|------------------------|
| `docs/proposal.md` | 作为"任务目标"来源 |
| `docs/design.md` | 作为"约束条件"和"已知上下文" |
| `docs/brief.md` | 作为"关键决策"约束 Agent 行为 |
| `docs/tasks/*.md` | 作为"交付清单"参考 |
| `anti-patterns-checklist.md` | 作为"风险提示" |

---

## 附录 C：编排器参考模式（真正的 Agent Loop）

当需要为 Loop 工作流建造自动化编排器时，以下组件结构可重复使用。

**核心变更**：编排器不再是人机交互界面。编排器就是一个 `while not done` 循环：
它管理 messages 上下文，通过 AgentDriver 调用外部 Agent CLI 获取决策，
通过 ToolExecutor 执行工具（创建文件、编辑文件、运行命令），
将执行结果追加回 messages，循环直至 Agent 无更多工具调用。

### 核心组件

```
编排器
│
├── AgentLoop      while not done 主循环
│                   方法: run(scope) → (success, summary)
│                   流程:
│                     1. 构建初始 messages（system prompt + scope）
│                     2. agent.step(messages) → AgentResponse
│                     3. 有 tool_calls → 逐一 execute → 追加结果 → 回第 2 步
│                     4. 无 tool_calls → check_all() 验证 → 返回
│                   边界: 最多 20 轮迭代, 超限视为失败
│
├── AgentDriver    外部 Agent CLI 通信接口
│                   方法: step(messages) → AgentResponse{tool_calls | end_turn}
│                   输入: messages (list[dict], OpenAI/Anthropic 格式)
│                   输出: ToolCall[] (type + params) 或 stop_reason="end_turn"
│                   实现方式:
│                      StdioDriver: stdin/stdout 管道 → 外部 CLI 进程
│                      StubDriver:  返回预定义响应（测试用）
│
├── ToolExecutor   执行 Agent 决策的工具调用
│                   方法: execute(tool_call) → str（执行结果）
│                   支持的工具:
│                      create_file(path, content)  → 写文件
│                      edit_file(path, old, new)   → 编辑文件
│                      run_command(command)        → 子进程执行
│                      verify()                    → 调用 PhaseChecker.check_all()
│                   安全: 路径白名单检查, 禁止越界写
│
├── StateManager   持久化运行状态（断点恢复）
│                   字段: currentPhase, status, history, errors
│                   支持: advance, pause, bump_attempt, append_error
│                   （新增字段: iterations, lastMessages 用于恢复）
│
├── PhaseChecker   交付物存在 + 内容质量联合检查
│                   方法: check_all() → (ok, missing, details)
│                   检查: 文件存在, 最小大小, 关键字, 关键章节
│
└── TraceAnalyzer  execution trace 结构化校验（可选）
                    方法: load, validate, summarize
                    检查: 必需字段, 非空 execution, errors 字段
```

### 循环伪代码

```python
class AgentLoop:
    """while not done — 真正的 Agent 循环。"""

    def __init__(self, driver: AgentDriver, executor: ToolExecutor,
                 checker: PhaseChecker, max_iter: int = 20):
        self.driver = driver
        self.executor = executor
        self.checker = checker
        self.max_iter = max_iter

    def run(self, scope: str) -> tuple[bool, str]:
        messages = [
            {"role": "system", "content": self._system_prompt(scope)},
            {"role": "user",   "content": "请逐步创建交付物，每步只做一件事。"},
        ]

        for iteration in range(self.max_iter):
            # 1. 获取 Agent 决策
            response = self.driver.step(messages)

            # 2. Agent 自判完成
            if response.stop_reason == "end_turn":
                ok, _, details = self.checker.check_all()
                return ok, details

            # 3. 执行每个工具调用
            for tc in response.tool_calls:
                result = self.executor.execute(tc)
                messages.append({
                    "role": "user",
                    "content": f"[Tool: {tc.type}] {result}",
                })

            # 4. 定期质量门禁（每 5 轮）
            if iteration > 0 and iteration % 5 == 0:
                ok, missing, details = self.checker.check_all()
                summary = f"交付情况: {'✅ 全部通过' if ok else f'⚠️ 缺 {len(missing)} 项'}"
                if not ok:
                    summary += f"\n缺失: {', '.join(missing)}"
                messages.append({"role": "system", "content": summary})

        return False, "达到最大迭代次数"
```

### `AgentDriver` 接口定义

```python
@dataclass
class ToolCall:
    id: str
    type: str       # "create_file" | "edit_file" | "run_command" | "verify"
    params: dict    # {"path":"...","content":"..."} 或 {"command":"..."}

@dataclass
class AgentResponse:
    has_tool_calls: bool
    tool_calls: list[ToolCall]
    content: str          # Agent 的文字输出
    stop_reason: str      # "tool_use" | "end_turn"

class AgentDriver(ABC):
    """外部 Agent CLI 的抽象接口。

    step() 发送 messages 给 Agent CLI，接收一步决策。
    Agent 不需要内部执行工具——它只需决定「调什么工具、传什么参数」，
    由 ToolExecutor 在编排器侧执行。
    """
    @abstractmethod
    def step(self, messages: list[dict]) -> AgentResponse: ...
```

### `ToolExecutor` 工具集

Agent 可以调用的工具类型：

| 工具 | 参数 | 执行逻辑 |
|------|------|---------|
| `create_file` | path, content | 路径合法性校验 → 创建目录 → 写文件 → 返回大小 |
| `edit_file` | path, old_string, new_string | 读文件 → 精确替换 → 写回 → 返回改了多少处 |
| `run_command` | command | subprocess.run → 返回 stdout + stderr |
| `verify` | （无） | 调用 PhaseChecker.check_all() → 返回检查结果 |

路径安全性：所有 `path` 参数必须解析到项目目录内，禁止 `../` 逃逸。

### 编排器 vs 旧架构

```
旧架构（流水线）:
    编排器 → Bridge → IDE 粘贴 → 等人 done → check → y/n → 收工

新架构（真正循环）:
    编排器 → Agent.step() → ToolExecutor.execute() → 追加结果 → 循环
         ↑                                                        │
         └────────────── Agent 看到结果, 决策下一步 ──────────────┘
```

| 维度 | 旧架构 | 新架构 |
|------|--------|--------|
| 循环驱动力 | 外部文件存在检查 | Agent 自判 tool_use vs end_turn |
| 迭代粒度 | 一次粘贴全量文件 | 单步工具调用 |
| 上下文连续性 | 每次粘贴 = 新会话 | 同一 messages 持续累积 |
| 反馈回路 | 人重新粘贴同一 scope | Agent 在 messages 中看到结果 |
| 停止条件 | PhaseChecker + y/n | Agent end_turn + check_all 验证 |
| 端到端自动化 | 否（需人工粘贴 + 确认） | 是（CLI 管道，零人工介入） |

### 错误恢复流

```
        ┌─ AgentLoop.run() ───────────────────────────────────────┐
        │                                                          │
        │  Agent.step() 失败（超时/协议错）→ 重试 2 次后 PAUSED    │
        │                                                          │
        │  ToolExecutor.execute() 失败 → 追加错误到 messages       │
        │  让 Agent 知道出错并自主决定如何处理                      │
        │                                                          │
        │  check_all() 中期检查失败 → 注入缺失信息到 messages       │
        │  Agent 看到后补文件                                     │
        │                                                          │
        │  迭代超限（20 轮） → PAUSED, 输出已完成的部分中间产物     │
        │                                                          │
        │  Ctrl+C 中断 → 保存 state + messages → 重启后从断点继续  │
        │                                                          │
        └──────────────────────────────────────────────────────────┘
```

### 关键设计原则

- **编排器不替 Agent 决策**——它只传递 messages、执行工具、递送结果
- **Agent 看到自己的每一步结果**——每轮工具执行结果以 user/tool 消息追加回上下文
- **验证是门禁不是驱动**——check_all() 用于报告状态和阻断，不决定 Agent 下一步做什么
- **停止由 Agent 自判**——Agent 没有更多工具调用时视为完成，编排器做最终验证
