# ponytail/review

> 审查代码过度工程。只查复杂度，不查正确性/安全/性能，不自动修。

## 输出格式

每行一条，`<文件>:L<行号>: <标签> <什么可删>. <替换>.`

### 标签

- `delete:` 死代码、未用灵活性。替换：无。
- `stdlib:` 手写但标准库有的。命名函数。
- `native:` 依赖做但平台原生有的。命名特性。
- `yagni:` 单实现的抽象、没人设的配置、单调用的层。
- `shrink:` 同逻辑、更少行。展示简短形式。

### 示例

❌ "This EmailValidator class might be more complex than necessary…"
✅ `L12-38: stdlib: 27-line validator class. "@" in email, 1 line, real validation is the confirmation mail.`

### 评分

结尾：`net: -<N> lines possible.` 没可删的：`Lean already. Ship.`

## 边界

范围：过度工程和复杂度。不涉及正确性、安全、性能——交给正常 review。**只输出报告，不自行修改**（RULE-18）。

## 参见

- [core 心智模型](06-core.md) — 始终开启的懒人决策阶梯
- [audit](02-audit.md) — 同模式的全仓库版
