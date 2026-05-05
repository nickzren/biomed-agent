# Biomedical Agent Workspace

Connecting AI to biomedical data.

`biomed-agent` is an MCP-backed biomedical research workspace for Claude Code, Codex, and other coding agents. It provides server registration, diagnostics, and source-backed routing guidance across OpenTargets, Monarch, MyGene, MyChem, and MyDisease.

## What It Provides

- MCP server registry and local path handling.
- A tiny diagnostics CLI for server/tool inspection.
- The cross-server research contract for agents.
- Example MCP registration in [mcp.json](mcp.json).

## Architecture

```mermaid
flowchart TB
    user["User"] --> runtime["Codex / Claude Code"]

    subgraph repo["biomed-agent"]
        contract["AGENTS.md<br/>canonical contract"]
        skill["skills/biomed-research<br/>research workflow"]
        config["mcp.json<br/>server registration"]
        diagnostics["Diagnostics CLI<br/>list, inspect, call, doctor"]
        client["biomed_agent/servers.py + biomed_agent/mcp_client.py<br/>mechanical MCP access"]
    end

    runtime --> contract
    contract --> skill
    contract --> config
    diagnostics --> client

    config --> servers["5 biomedical MCP servers"]
    client --> servers
    servers --> sources["OpenTargets, Monarch, MyGene,<br/>MyChem, MyDisease data"]
```

## MCP Servers

The default setup expects sibling repos:

- `../opentargets-mcp`
- `../monarch-mcp`
- `../mygene-mcp`
- `../mychem-mcp`
- `../mydisease-mcp`

Override paths with `OPENTARGETS_MCP_PATH`, `MONARCH_MCP_PATH`, `MYGENE_MCP_PATH`, `MYCHEM_MCP_PATH`, or `MYDISEASE_MCP_PATH`.

## Setup

```bash
uv sync
```

## Install From Git

```bash
uvx --from git+https://github.com/nickzren/biomed-agent biomed-agent doctor
```

`doctor` needs the MCP repos at the expected sibling paths or matching `*_MCP_PATH` environment variables.

## Diagnostics

```bash
uv run biomed-agent list-servers
uv run biomed-agent list-servers --json
uv run biomed-agent list-tools
uv run biomed-agent list-tools --json
uv run biomed-agent list-tools --server opentargets
uv run biomed-agent call-tool opentargets.search_entities '{"query_string":"BRAF","entity_names":["target"]}'
uv run biomed-agent doctor
uv run biomed-agent doctor --json
```

## Init Config

`init` is print-only. It does not edit Codex, Claude Code, or Cursor settings.

```bash
uv run biomed-agent init --runtime codex --print
uv run biomed-agent init --runtime claude --print
uv run biomed-agent init --runtime cursor --print
uv run biomed-agent init --runtime codex --print --mcp-base ../
```

## Tests

```bash
uv run pytest tests/ -q
```

## Safety

Research and educational use only. This is not a clinical decision system and must not provide diagnosis, prescribing, dosing, or patient-specific treatment advice.
