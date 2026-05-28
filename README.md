# Agent Harness

Minimal AI agent harness for live demos. Shows how tools like Claude Code and GitHub Copilot CLI work under the hood.

## What This Teaches

1. **The agent loop** — model calls tools, we execute them, feed results back, repeat
2. **Tool descriptions steer behavior** — change a description, rerun same prompt, different behavior
3. **Tools are just data** — add/remove a tool from `tools.json`, the agent gains/loses capability
4. **Skills inject expertise** — drop a markdown file in `skills/`, the system prompt changes
5. **MCP provides external tools** — a separate server process advertises tools over a protocol
6. **Permissions gate actions** — same prompt, different permission mode, different outcome

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

This creates an AI Services resource with a `gpt-4o` deployment and grants you data-plane access. The output shows your endpoint.

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

Edit files in VS Code while the agent runs — changes apply on the next prompt:

| File | What it controls |
|------|-----------------|
| `config.json` | Model, permission mode, MCP server, verbosity |
| `tools.json` | Tool definitions (name, description, schema, permission) |
| `skills/*.md` | Drop-in prompt modules appended to system prompt |

The current working directory is the workspace root. In `read_only` and `workspace_write`, file tools stay inside it.

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

### 4. Skill injection

With `skills/code-review.md` present:

```
you> Review agent.py
  → structured checklist with ✅ / ⚠️ / ❌ markers
```

Delete the file, rerun — answer becomes freeform.

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

## Architecture

```
src/
├── agent_harness/        # the agent package
│   ├── agent.py          # REPL + agent loop
│   ├── api.py            # Azure OpenAI client (Entra ID auth)
│   ├── mcp_client.py     # MCP tool discovery + execution
│   ├── prompt.py         # system prompt builder + skill loading
│   └── tools.py          # tool registry + built-in handlers
└── mcp_server/           # standalone MCP server (separate process)
    └── __main__.py        # exposes get_current_time, word_count
```

```
┌────────────┐     ┌──────────────┐     ┌─────────────┐
│  User      │────▶│  Agent Loop  │────▶│  Azure      │
│  (terminal)│     │  (agent.py)  │◀────│  OpenAI     │
└────────────┘     └──────┬───────┘     └─────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌─────────┐ ┌──────────┐
        │tools.json│ │skills/  │ │mcp_server│
        │(handlers)│ │(prompt) │ │(external)│
        └──────────┘ └─────────┘ └──────────┘
```

The key insight: the model doesn't "have" tools. It receives tool definitions as JSON in every API call, reads the descriptions, and decides what to use. Change the descriptions, change the behavior.
