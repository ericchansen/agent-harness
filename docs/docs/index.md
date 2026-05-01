---
slug: /
title: Agent Harness
---

# Agent Harness

A minimal Python agent harness for live demos. Shows how tools like Claude Code and GitHub Copilot CLI work under the hood — by building one from scratch.

:::tip Looking for the SDK version?
There's a [companion repo using the GitHub Copilot SDK](https://ericchansen.github.io/agent-harness-copilot-sdk/) that achieves the same result in 1/3 the code. Compare them side-by-side.
:::

## What This Teaches

| Concept | How it's demonstrated |
|---------|----------------------|
| **The agent loop** | Model calls tools → we execute them → feed results back → repeat |
| **Tool descriptions steer behavior** | Change a description in `tools.json`, rerun same prompt, get different behavior |
| **Tools are just data** | Add/remove a tool from `tools.json` — the agent gains/loses capability |
| **Skills inject expertise** | Drop a markdown file in `skills/` — the system prompt changes |
| **MCP provides external tools** | A separate server process advertises tools over the MCP protocol |
| **Permissions gate actions** | Same prompt, different permission mode, different outcome |

## Setup

```bash
# Prerequisites: Python 3.11+, Azure CLI logged in
pip install -e .

# Copy the example config and set your endpoint
cp config.example.json config.json
```

Or rehearse without Azure:

```bash
python -m agent_harness --mock --preflight
python -m agent_harness --mock --prompt "What files are in the current directory?"
```

Set your Azure AI Services endpoint in `config.json`:

```json
{
  "azure_endpoint": "https://your-resource.cognitiveservices.azure.com/"
}
```

**Don't have one?** Deploy with the included Bicep:

```bash
PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)

az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters deployerPrincipalId=$PRINCIPAL_ID
```

## Running the Demo

```bash
# Validate the setup
python -m agent_harness --preflight

# Interactive REPL
python -m agent_harness

# One-shot prompt
python -m agent_harness --prompt "What files are in the current directory?"

# Deterministic rehearsal mode
python -m agent_harness --mock --prompt "What files are in the current directory?"
```

Edit files in VS Code while the agent runs — changes apply on the next prompt:

| File | What it controls |
|------|-----------------|
| `config.json` | Model, permission mode, MCP server, verbosity |
| `tools.json` | Tool definitions (name, description, schema, permission) |
| `skills/*.md` | Drop-in prompt modules appended to the system prompt |

The current working directory is the workspace root. In `read_only` and `workspace_write`, file tools stay inside it.

## Demo Playbook

### 1. Basic Tool Use

```
you> What files are in the current directory?
  🔧 list_files({"path": "."})
  📎 → agent.py, api.py, config.json, ...
```

The model chose `list_files` because the description says "List files and directories at a path" and the user asked about files.

### 2. Tool Removal

Delete `run_command` from `tools.json`, then:

```
you> Run echo hello
  → model explains it can't execute commands
```

**Teaching point**: When a tool is removed from `tools.json`, the model literally cannot use it — it's not in the API call.

### 3. Description Steering

Change `read_file` description in `tools.json` to:

> Read a file. IMPORTANT: Always read at least one relevant file before answering ANY question.

```
you> What is 2 + 2?
  🔧 read_file({"path": "README.md"})   ← reads a file for a math question!
```

**Teaching point**: The model reads tool descriptions on every API call. The description is an instruction.

### 4. Skill Injection

With `skills/code-review.md` present:

```
you> Review agent.py
  → structured checklist with ✅ / ⚠️ / ❌ markers
```

Delete the file, rerun — answer becomes freeform.

**Teaching point**: Skills are just markdown files appended to the system prompt. They change how the model _thinks_, not what it _can do_.

### 5. MCP Tools

With `"mcp_server": "mcp_server"` in `config.json`:

```
you> What time is it?
  🔌 MCP: loaded 2 tools from mcp_server
  🔧 mcp__get_current_time({})
  📎 [mcp] → 2026-04-22 03:50:25 UTC
```

Remove the `mcp_server` key — those tools disappear.

**Teaching point**: MCP adds tools from an external process. Skills change the prompt. Both are just injecting context — one into the tool list, the other into the system prompt.

### 6. Permission Gating

Set `"permission_mode": "read_only"` in `config.json`:

```
you> Write hello to test.txt
  🔧 write_file({"path": "test.txt", "content": "hello"})
  🚫 Permission denied: 'write_file' requires 'workspace_write'
```

**Teaching point**: The model still _tries_ to use the tool. The permission system stops execution after the model decides.

In `workspace_write`, file tools can modify files inside the current workspace but not outside it. Use `dangerous` only when you intentionally want to remove that boundary.

## Architecture

```
src/
├── agent_harness/        # the agent package
│   ├── agent.py          # REPL + agent loop
│   ├── api.py            # Azure OpenAI client (Entra ID auth)
│   ├── models.py         # Config and ToolSpec dataclasses
│   ├── mcp_client.py     # MCP tool discovery + execution
│   ├── prompt.py         # system prompt builder + skill loading
│   └── tools.py          # tool registry + built-in handlers
└── mcp_server/           # standalone MCP server (separate process)
    └── __main__.py        # exposes get_current_time, word_count
```

The key insight: **the model doesn't "have" tools**. It receives tool definitions as JSON in every API call, reads the descriptions, and decides what to use. Change the descriptions, change the behavior.
