# ponytail/audit

> 全仓库臃肿扫描，review 的全局版，按 ROI 排序精简机会。

## 扫描范围（排除 node_modules、.git、build）

- 标准库/平台已覆盖的依赖
- 单实现接口、单产品工厂、只代理的包装
- 导出单物的文件、死标志和配置
- 手写标准库替代

## 标签

与 review 相同：
- `delete:` 死代码、未用灵活性。替换：无。
- `stdlib:` 手写但标准库有的。命名函数。
- `native:` 依赖做但平台原生有的。命名特性。
- `yagni:` 单实现的抽象、没人设的配置、单调用的层。
- `shrink:` 同逻辑、更少行。展示简短形式。

## 输出

每行一条，按精简量排序。`<tag> <what to cut>. <replacement>. [path]`
结尾：`net: -<N> lines, -<M> deps possible.` 无可删：`Lean already. Ship.`

## 边界

同 review：只报不修（RULE-18）。一次性报告，不持久化。

## 参见

- [core 心智模型](06-core.md)
- [review](01-review.md) — diff 级别的过度工程审查
