#!/usr/bin/env bash
# error-detector.sh — Bash 命令输出错误检测
# 在 Agent Coding 会话中使用，检测命令输出中的错误模式，提醒记录到 troubleshooting.md。
#
# 用法:
#   1. 管道模式: some_command 2>&1 | tee /dev/stderr | bash scripts/error-detector.sh
#   2. 参数模式: bash scripts/error-detector.sh "错误输出文本"
#   3. 环境变量模式: ERROR_OUTPUT="错误输出文本" bash scripts/error-detector.sh
#
# 输出: 如检测到错误模式，输出 <error-detected> XML 标签到 stdout

set -euo pipefail

# 获取输入
INPUT=""
if [ -n "${1:-}" ]; then
    INPUT="$1"
elif [ -n "${ERROR_OUTPUT:-}" ]; then
    INPUT="$ERROR_OUTPUT"
elif [ ! -t 0 ]; then
    INPUT=$(cat)
fi

[ -z "$INPUT" ] && exit 0

# 错误模式列表（不区分大小写匹配）
ERROR_PATTERNS=(
    "error:"
    "Error:"
    "ERROR:"
    "failed"
    "FAILED"
    "command not found"
    "No such file"
    "Permission denied"
    "fatal:"
    "Exception"
    "Traceback"
    "npm ERR!"
    "ModuleNotFoundError"
    "SyntaxError"
    "TypeError"
    "exit code"
    "non-zero"
    "Segmentation fault"
    "core dumped"
    "Cannot find module"
    "ENOENT"
    "EACCES"
    "ETIMEDOUT"
    "0xc0000139"
    "0xc0000005"
    "Unexpected token"
)

# 检测
found=false
for pattern in "${ERROR_PATTERNS[@]}"; do
    if [[ "$INPUT" == *"$pattern"* ]]; then
        found=true
        break
    fi
done

if [ "$found" = true ]; then
    cat << 'EOF'
<error-detected>
检测到命令输出中包含错误模式。建议：
- 如为非预期的错误，记录到 troubleshooting.md（按模板：现象/原因/解决）
- 如为已知问题，确认 troubleshooting.md 中已有对应条目
- 存档时运行 `python scripts/build-experience-index.py` 重建索引
</error-detected>
EOF
fi
