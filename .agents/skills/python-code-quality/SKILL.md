---
name: python-code-quality
description: Run Python static analysis tools (ruff, mypy) to catch errors, type issues, and style violations. Use when working on Python files, before committing Python changes, or when user asks to check/fix Python code quality.
---

# Python Code Quality

Run these tools on Python files. They provide deterministic, reproducible diagnostics on demand — no need for an always-running LSP.

## Tools

| Tool | Purpose | Install |
|------|---------|---------|
| `ruff` | Fast linter + formatter. Syntax errors, unused imports, style violations. Autofix supported. | `pip install ruff` |
| `mypy` | Static type checker. Type mismatches, missing return types, None-safety. | `pip install mypy` |

Both are listed as optional dev dependencies: `pip install awb[dev]`

## Workflows

### Quick check (before commit)
```
ruff check scripts/ awb/ tests/
mypy scripts/ awb/ tests/
```

### Autofix + format
```
ruff check --fix scripts/ awb/ tests/
ruff format scripts/ awb/ tests/
```

### Check specific files
```
ruff check path/to/file.py
mypy path/to/file.py
```

## Run order

1. `ruff check` first (fast, catches surface-level issues)
2. `ruff format` (auto-format)
3. `mypy` last (deeper type analysis)

Stop and fix at each step before proceeding to the next.

## Diagnostics handling

When ruff or mypy reports errors:
1. Read the error location (`file:line:col`) and message
2. Fix the issue
3. Re-run the tool to verify
4. If the same error class appears in multiple files, fix all at once
