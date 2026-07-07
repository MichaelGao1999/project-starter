# ponytail/debt

> 收割 `ponytail:` 注释债务台账，追踪刻意简化的技术债务。

## 扫描

```
grep -rnE '(#|//) ?ponytail:' .
```

## 输出

按文件分组，每行：
`<文件>:<行>, <简化什么>. ceiling: <限制>. upgrade: <触发条件>.`

### 风险标记

未指名升级路径的 `ponytail:` 注释 → `no-trigger` 标记。这些可能静默腐烂。

### 结尾

`<N> markers, <M> with no trigger.` 无发现：`No ponytail: debt. Clean ledger.`

## 边界

**只读报告，不修改代码。** 如需持久化，写入 `PONYTAIL-DEBT.md`。

## 约定

Ponytail 简化注释格式：
- `# ponytail: <ceiling>, <upgrade path>`
- 例：`# ponytail: global lock, per-account locks if throughput matters`

## 参见

- [core 心智模型](06-core.md)
