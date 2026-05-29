# Agent Harness

Minimal AI agent harness for live demos. Shows how tools like Claude Code and GitHub Copilot CLI work under the hood — and lets you edit the agent's tools, skills, and config **while it's running**.

## What This Teaches

1. **The agent loop** — model calls tools, we execute them, feed results back, repeat
2. **Tool descriptions steer behavior** — change a description, rerun same prompt, different behavior
3. **Tools are just data** — add/remove a tool from `tools.json`, the agent gains/loses capability
4. **Skills are tools too** — skill name + description is advertised; the model invokes the `skill` tool to load the full instructions on demand (same pattern as Copilot CLI / Claude Code)
5. **MCP provides external tools** — a separate server process advertises tools over a protocol
6. **Permissions gate actions** — same prompt, different permission mode, different outcome
7. **Reasoning models think out loud** — `gpt-5-mini` / `o-series` stream reasoning summaries you can read live

## Setup

```bash
# Prerequisites: Python 3.11+, uv, Azure CLI logged in (az login)
uv sync --dev

# Copy the example config
cp config.example.json config.json

# Set your Azure endpoint in a .env file (gitignored, never read by the agent)
cp .env.example .env
# Edit .env and set AZURE_ENDPOINT
```

Or rehearse locally without Azure:

```bash
uv run python -m agent_harness --mock --preflight
uv run python -m agent_harness --mock --prompt "What files are in the current directory?"
```

Set `AZURE_ENDPOINT` to your Azure AI Services endpoint — either in `.env` or exported in your shell:

```bash
# .env file (recommended)
AZURE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/

# or export directly
export AZURE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
```

**Don't have an endpoint?** Deploy one with the included Bicep:

```bash
# Get your principal ID for RBAC assignment
PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)

az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters deployerPrincipalId=$PRINCIPAL_ID
```

This creates an AI Services resource with `gpt-4o` and `o4-mini` deployments and grants you data-plane access. To get streaming **reasoning summaries** in the demo, deploy a `gpt-5-mini` model via the Azure CLI:

```bash
az cognitiveservices account deployment create \
  --resource-group <rg-name> --name <account-name> \
  --deployment-name gpt-5-mini --model-name gpt-5-mini --model-version 2025-08-07 \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10
```

Then set `azure_deployment` in `config.json` to `"gpt-5-mini"` with `azure_api_version: "2025-04-01-preview"`.

## Usage

```bash
# Show the current local setup
uv run python -m agent_harness --preflight

# Interactive REPL
uv run python -m agent_harness

# One-shot prompt
uv run python -m agent_harness --prompt "What files are in the current directory?"

# Deterministic rehearsal mode (no Azure call)
uv run python -m agent_harness --mock --prompt "What files are in the current directory?"
```

`--preflight` checks local config, tool loading, skills, and MCP availability. It does **not** verify live Azure connectivity or deployment health.

At the REPL: type `quit` to exit, `reset` to clear conversation history.

### What you'll see

With a reasoning model (`gpt-5-mini`), every turn streams:

```
you> Review the agent code

  💭 The user is asking for a code review. I see a `code-review` skill
     advertised — I should call the skill tool first to load its protocol.
  🔧 skill({"name":"code-review"})
  🎯 Skill activated: code-review — Structured code review with explicit
     pass/fail security and performance checks...
  📎 → ## Code Review Protocol\nWhen the user asks you to review code...
  💭 Now I'll pick a single file fast — agent.py is the obvious entry point.
  🔧 read_file({"path":"src/agent_harness/agent.py"})
  📎 → """Agent harness — the core loop...

### 📄 File reviewed
`src/agent_harness/agent.py`
...

  ⚡ tokens: 4231 in / 612 out
```

| Symbol | Meaning |
|--------|---------|
| 💭     | Streamed reasoning summary (reasoning models only) |
| 🔧     | Tool call (streamed live as the model emits arguments) |
| 🎯     | Skill activated — the model invoked the `skill` tool |
| 📎     | Tool result (truncated preview) |
| 🚫     | Tool denied by permission check |
| ⚡     | Token usage at end of turn |

### Files you edit during a demo

Edit these in VS Code while the agent runs — changes apply on the **next** prompt (no restart):

| File | What it controls |
|------|-----------------|
| `config.json` | Model, permission mode, MCP server, verbosity |
| `tools.json` | Tool definitions (name, description, schema, permission) |
| `skills/*.md` | Drop-in skill modules with frontmatter `description:` |

The current working directory is the workspace root. In `read_only` and `workspace_write`, file tools stay inside it.

### Config knobs

```jsonc
{
  "azure_deployment": "gpt-5-mini",
  "azure_api_version": "2025-04-01-preview",
  "permission_mode": "workspace_write",  // read_only | workspace_write | dangerous
  "max_iterations": 10,
  "show_system_prompt": false,           // true = print the full system prompt + tool/skill inventory each turn
  "show_tool_calls": true,               // false = hide 🔧 lines
  "mcp_server": "mcp_server"             // null = disable MCP
}
```

## Demo Playbook

### 1. Basic tool use

```
you> What files are in the current directory?
  🔧 list_files({"path": "."})
```

### 2. Tool removal

Delete `run_command` from `tools.json`, then:

```
you> Run echo hello
  → model explains it can't execute commands
```

### 3. Description steering

Change `read_file` description in `tools.json` to:

> Read a file. IMPORTANT: Always read at least one file before answering ANY question.

```
you> What is 2 + 2?
  🔧 read_file({"path": "README.md"})   ← reads a file for a math question
```

### 4. Skills — name + description only (Copilot CLI pattern)

Skills mirror the Copilot CLI / Claude Code design: only **name + description** are advertised to the model in the system prompt. The full body loads only when the model decides to invoke the `skill` tool.

Open `skills/code-review.md`:

```markdown
---
description: Structured code review with explicit pass/fail security and performance checks. Use whenever the user asks to review, audit, or critique code.
---
## Code Review Protocol
...
```

Run:

```
you> Please review agent.py
  💭 The user asked for a review — the code-review skill matches. Load it.
  🔧 skill({"name":"code-review"})
  🎯 Skill activated: code-review — Structured code review with...
  → structured output with 📄 / ✅ / ⚠️ / ❌ / 🔒 / ⚡ / 🏁 headers
```

Now **edit the description** to something narrower like `Use only for security-focused audits` and ask `Please review agent.py` again. The model decides it doesn't match, doesn't call the skill tool, and you get a generic prose review.

Set `show_system_prompt: true` to show the audience what the model actually sees — a tiny `<available_skills>` block with name + description, **not** the body:

```xml
<available_skills>
  <skill>
    <name>code-review</name>
    <description>Structured code review with...</description>
  </skill>
</available_skills>
```

### 5. MCP tools

With `"mcp_server": "mcp_server"` in `config.json`:

```
you> What time is it?
  🔌 MCP: loaded 2 tools from mcp_server
  🔧 mcp__get_current_time({})
```

Remove the `mcp_server` key from config — those tools disappear.

### 6. Permission gating

Set `"permission_mode": "read_only"` in `config.json`:

```
you> Write hello to test.txt
  🔧 write_file({"path": "test.txt", "content": "hello"})
  🚫 Permission denied: 'write_file' requires 'workspace_write'
```

In `workspace_write`, file tools can modify files inside the current workspace but not outside it. Use `dangerous` only when you intentionally want to remove that boundary.

### 7. Reasoning models

Switch `azure_deployment` to `gpt-5-mini` (or any `o*` / `gpt-5*` model) and you'll get streamed **reasoning summaries** (💭) before every tool call and response. The runtime routes these models to the Azure **Responses API** because Chat Completions hides reasoning server-side.

Edit a tool description live, ask the same question again, and the audience can read the model *reasoning about your edit* in real time.

## Architecture

```
src/
├── agent_harness/         # the agent package (public surface)
│   ├── agent.py           # the core agent loop
│   ├── prompt.py          # system prompt + skill loading/advertising
│   ├── tools.py           # tool registry, permissions, built-in handlers
│   ├── models.py          # Config, ToolSpec, Skill dataclasses
│   ├── mcp_client.py      # MCP tool discovery + execution
│   └── _runtime/          # CLI + provider plumbing (private)
│       ├── cli.py         # argparse, REPL, provider selection
│       ├── api.py         # Azure clients + streaming (Chat + Responses)
│       ├── config.py      # config loader with .env support
│       ├── preflight.py   # --preflight diagnostics
│       └── mock/          # deterministic responses for rehearsal mode
└── mcp_server/            # standalone MCP server (separate process)
    └── __main__.py         # exposes get_current_time, word_count
```

```
┌────────────┐     ┌──────────────┐     ┌──────────────────────┐
│  User      │────▶│  Agent Loop  │────▶│  Azure OpenAI        │
│  (terminal)│     │  (agent.py)  │◀────│  Chat or Responses   │
└────────────┘     └──────┬───────┘     └──────────────────────┘
                          │
              ┌───────────┼────────────┐
              ▼           ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │tools.json│ │skills/   │ │mcp_server│
        │(handlers)│ │(name+desc│ │(external)│
        │          │ │ advertise│ │          │
        │          │ │ body via │ │          │
        │          │ │`skill`   │ │          │
        │          │ │ tool)    │ │          │
        └──────────┘ └──────────┘ └──────────┘
```

**Key insight:** the model doesn't "have" tools or skills. It receives JSON tool definitions and a short `<available_skills>` catalog in every API call, reads the descriptions, and decides what to invoke. The runtime intercepts tool calls — including the special `skill` tool — and feeds results back. Change the descriptions, change the behavior. The model is just a function; the harness is the agent.
