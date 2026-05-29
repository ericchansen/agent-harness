---
description: Structured code review with explicit pass/fail security and performance checks. Use whenever the user asks to review, audit, or critique code.
---
## Code Review Protocol

When the user asks you to review code, follow this protocol.

**Pick a file fast.** If the user didn't name a file:
- Run list_files on "src" (or "." if no src) ONCE
- Pick the most interesting-looking source file (the main entry point, the
  largest non-test .py, or a file with a name like `agent.py`, `main.py`,
  `app.py`)
- Read that ONE file. Do not explore the whole tree.

**Output in this exact format.** No free-form prose. Use these
exact headers in this order:

### 📄 File reviewed
`path/to/file.py`

### ✅ What's good
- (bullet list)

### ⚠️ Concerns
- (bullet list)

### ❌ Bugs / Must fix
- (bullet list with file:line refs, or "none found")

### 🔒 Security check
- Hardcoded secrets: pass/fail
- Input validation: pass/fail
- Injection risk: pass/fail

### ⚡ Performance check
- Unbounded loops: pass/fail
- N+1 queries: pass/fail
- Blocking I/O: pass/fail

### 🏁 VERDICT
ship it | needs changes
