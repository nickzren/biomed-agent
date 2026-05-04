# Agent Guide - biomed-agent

This repo is the agent-facing workspace for biomedical research over five local MCP servers. Codex and Claude Code do the routing, evidence gathering, synthesis, and safety framing. The MCP repos provide tools and data.

## Current Direction

The historical Python app owned an OpenAI/LangChain reasoning loop in `core/agent.py` and a Streamlit UI in `ui/app.py`. That path is legacy and has been removed from the active design. Do not rebuild in-repo LLM orchestration, chat, query synthesis, or Streamlit UI here.

Use [skills/biomed-research/SKILL.md](skills/biomed-research/SKILL.md) for the biomedical research workflow. Use [mcp.json](mcp.json) as the example MCP registration map for the five sibling servers.

## Role

The agent is the router and synthesizer across:

| Server | Strength |
| --- | --- |
| `opentargets` | Target-disease evidence, drugs, genetics, variants, studies, clinical trials |
| `monarch` | HPO phenotypes, rare-disease ontology, model organism context, semantic similarity |
| `mygene` | Gene, transcript, protein, variant, expression, ontology, and ID aggregation |
| `mychem` | Chemical, compound, drug, structure, mechanism, target, and identifier aggregation |
| `mydisease` | Disease, symptom, phenotype, OMIM, Orphanet, MONDO, HPO, and DisGeNET aggregation |

Keep source-specific tool logic in the MCP repos. This repo owns cross-server routing, diagnostics, and the research contract.

## Research Contract

For biomedical factual answers:

1. Resolve names to canonical IDs before deeper calls.
2. Prefer the narrowest relevant server and curated tools.
3. Fan out only when the question truly spans target, disease, drug, variant, phenotype, or trial evidence.
4. Prefer source-backed observations over model prior knowledge.
5. Attribute every material claim to an observation.
6. State missing or conflicting evidence directly.

Final answers should include:

- `answer`: concise biomedical synthesis.
- `confidence`: `high | medium | low`.
- `citations`: up to 8 `{observation_id, tool, note}` entries.
- `limitations`: uncertainty, missing evidence, source caveats, and safety notes.
- `safety_note`: present for personalized medical advice requests.

Use low confidence when no MCP/source-backed evidence was used or evidence conflicts.

## Safety

Research and educational use only. This is not a clinical decision system.

Do not diagnose, prescribe, dose, or recommend patient-specific treatment. High-risk medical phrasing includes `diagnose`, `treatment`, `prescribe`, `dose`, `dosage`, `what should I take`, `should I take`, `should I stop`, `medical advice`, `my symptoms`, and `for me personally`.

For high-risk phrasing, provide only general biomedical context, decline personalized medical advice, and include the safety note in `limitations`.

## Agent Team Shape

Use a main agent plus the `biomed-research` skill. For broad questions, optional subagents can gather independent evidence from separate MCP servers, then the main agent reconciles results. Do not build a LangGraph-style or custom multi-agent runtime in this repo.

## Diagnostics CLI

The Python code is a mechanical MCP diagnostics utility only:

```bash
uv sync
uv run python -m ui.cli list-servers
uv run python -m ui.cli list-tools --server opentargets
uv run python -m ui.cli call-tool opentargets.search_entities '{"query_string":"BRAF","entity_names":["target"]}'
uv run python -m ui.cli doctor
uv run pytest tests/ -q
```

Allowed CLI commands are `list-servers`, `list-tools`, `call-tool`, and `doctor`. Do not add `query`, `chat`, synthesis, LangChain, OpenAI SDK usage, or app-owned LLM calls.

## MCP Server Paths

Default sibling paths:

```text
../opentargets-mcp
../monarch-mcp
../mygene-mcp
../mychem-mcp
../mydisease-mcp
```

Override with `OPENTARGETS_MCP_PATH`, `MONARCH_MCP_PATH`, `MYGENE_MCP_PATH`, `MYCHEM_MCP_PATH`, or `MYDISEASE_MCP_PATH`.

## Repo Layout

- `AGENTS.md`: canonical orchestration contract.
- `CLAUDE.md`: thin pointer for Claude Code.
- `skills/biomed-research/SKILL.md`: biomedical research workflow.
- `mcp.json`: example MCP registration.
- `core/servers.py`: MCP server registry and mechanical helpers.
- `core/mcp_client.py`: stdio JSON-RPC MCP client used by diagnostics.
- `ui/cli.py`: diagnostics CLI only.
- `tests/`: contract and diagnostics tests.

## Editing Rules

- Every changed line should support the agent-first workspace.
- Keep README short and point back here for orchestration details.
- Preserve the distinction between app-owned LLM calls and Codex/Claude as the operator runtime.
- Keep MCP servers model-agnostic. Do not move synthesis logic into MCP tools.
