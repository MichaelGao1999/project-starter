# ponytail

> 按需加载工作流。触发词：懒人审查、ponytail、lazy、yagni、simplest
>
> 入口文件。加载后根据用户意图选择具体模式。

## 模式选择

| # | 模式 | 说明 |
|---|------|------|
| 1 | **review** | 审查代码过度工程，对照阶梯删繁就简 |
| 2 | **audit** | 全仓库臃肿扫描，按 ROI 排序精简机会 |
| 3 | **debt** | 收割 `ponytail:` 注释债务台账 |
| 4 | **gain** | 展示 Ponytail 效果记分板 |
| 5 | **help** | 快速参考卡片 |
| 6 | **core** | 始终开启的懒人资深开发者心智模型 |

AI 根据上下文自动选择模式，或用户直接指定。模式文件见对应编号文档：
- [1. review](01-review.md)
- [2. audit](02-audit.md)
- [3. debt](03-debt.md)
- [4. gain](04-gain.md)
- [5. help](05-help.md)
- [6. core](06-core.md)（始终开启）

## 强度级别

| 级别 | 触发 | 行为 |
|------|------|------|
| **lite** | `ponytail lite` | 按需构建，一行提更懒替代 |
| **full** | `ponytail` | 阶梯实施。默认 |
| **ultra** | `ponytail ultra` | YAGNI 极端派，删优先于加 |

停用：说 `stop ponytail` 或 `normal mode`。
