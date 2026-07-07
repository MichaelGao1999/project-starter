---
name: checkpoint
description: Lightweight git snapshot — add all, commit with summary, push. Use when user says "checkpoint", "拍照", "snapshot", or "快照".
description_zh: 轻量 git 快照 — add → commit → push。用户在开发过程中说"checkpoint"、"拍照"、"snapshot"或"快照"时使用。
---

# Checkpoint

与「存档」互补：存档是会话结束的正式记录，checkpoint 是开发中的安全网。

## 标准流程

1. `git add -A`
2. `git commit -m "checkpoint: {本轮改动摘要}"`
3. `git push`
4. 汇报完成（改动文件数、commit hash）

## 回滚

- **全部撤销**：`git revert HEAD`
- **单文件还原**：`git checkout HEAD~1 -- 文件名`
- **查看历史**：`git log --oneline | grep checkpoint`

> checkpoint 不更新 session-log、status.md，不做认知提取。
