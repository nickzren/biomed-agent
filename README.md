# Biomedical Agent Workspace

Agent-facing biomedical research workspace for Codex and Claude Code.

This repo no longer owns an LLM reasoning loop or Streamlit UI. Codex or Claude Code should call the five biomedical MCP servers directly, guided by [AGENTS.md](AGENTS.md) and [skills/biomed-research/SKILL.md](skills/biomed-research/SKILL.md).

## What Stays Here

- MCP server registry and local path handling.
- A tiny diagnostics CLI for server/tool inspection.
- The cross-server research contract for agents.
- Example MCP registration in [mcp.json](mcp.json).

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

## Diagnostics

```bash
uv run python -m ui.cli list-servers
uv run python -m ui.cli list-tools
uv run python -m ui.cli list-tools --server opentargets
uv run python -m ui.cli call-tool opentargets.search_entities '{"query_string":"BRAF","entity_names":["target"]}'
uv run python -m ui.cli doctor
```

## Tests

```bash
uv run pytest tests/ -q
```

## Safety

Research and educational use only. This is not a clinical decision system and must not provide diagnosis, prescribing, dosing, or patient-specific treatment advice.
