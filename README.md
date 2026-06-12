# [项目名]

> 从 [母库/来源] 复制的工作区。

## 快速开始

### 1. 安装 starter/ 工作区

**注意：复制的是 starter/ 里面的文件，不是 starter/ 目录本身。**

```bash
# 复制 starter/ 内的文件到本项目根目录（不要复制 starter/ 目录）
cp -r agent-coding-skeleton/starter/* ./my-project/
cd my-project

# 运行安全安装向导
python install.py
```

### 2. 填写项目信息

- 修改 `AGENTS.md` 中的「1. 项目定位」
- 修改 `status.md` 中的项目名和环境备忘

### 3. 按五阶段推进

参考 `agent-coding-workflow.md`，根据项目当前状态选择切入阶段。

## 文件说明

| 文件 | 职责 |
|------|------|
| `AGENTS.md` | 硬规则 + 自然语言触发词（恢复 / 存档） |
| `status.md` | 当前进度、待办清单 |
| `session-log.md` | 会话历史记录 |
| `agent-coding-workflow.md` | 五阶段 workflow 参考 |
| `anti-patterns-checklist.md` | 阶段二设计自检 |
| `config/github-sync.json` | 母库同步配置（已预填） |
| `scripts/sync-knowledge.py` | 同步引擎 |

## 母库来源

- 仓库：[your-github-username/project-starter](https://github.com/your-github-username/project-starter)
- 启动包：[starter/](https://github.com/your-github-username/project-starter/tree/main/starter)
