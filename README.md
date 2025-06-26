# Biomedical Agent

This AI-powered agent addresses biomedical research tasks by dynamically connecting to and reasoning across a selection of relevant MCP servers.

## Features

- **Plug-and-play MCP Integration**: Connects to multiple biomedical MCP servers
- **AI-Powered Reasoning**: Uses LLMs for intelligent query routing
- **Multi-Source Analysis**: Combines data from OpenTargets, Monarch, MyGene, MyChem and MyDisease 
- **Multiple Interfaces**: CLI, Web UI (Streamlit), and Python API
- **Extensible**: Easy to add new MCP servers or custom tools

## Prerequisites

- Python 3.12+
- uv (for package management)
- The following MCP servers installed:
  - [opentargets-mcp](https://github.com/nickzren/opentargets-mcp)
  - [monarch-mcp](https://github.com/nickzren/monarch-mcp)
  - [mygene-mcp](https://github.com/nickzren/mygene-mcp)
  - [mychem-mcp](https://github.com/nickzren/mychem-mcp)
  - [mydisease-mcp](https://github.com/nickzren/mydisease-mcp)

## Installation

1. Install dependencies:
```bash
cd biomed-agent
uv sync
```

2. Set up environment variables:
```bash
# Edit .env with your API keys and MCP server paths
vi .en
```

## CLI Testing Commands

### 1. Check Server Status
```bash
# List all MCP servers and their status
uv run python -m ui.cli list-servers
```

### 2. List Available Tools
```bash
# List all tools from all servers
uv run python -m ui.cli list-tools

# List tools from specific servers
uv run python -m ui.cli list-tools --server opentargets --server mychem

# Find tools by capability
uv run python -m ui.cli list-tools --capability drug
```

### 3. Quick Queries
```bash
uv run python -m ui.cli query "What is the mechanism of action of vemurafenib?"
```

### 4. Direct Tool Calls
```bash
uv run python -m ui.cli call-tool opentargets.search_entities '{"query_string": "BRAF", "entity_names": ["target"]}'
```

### 5. Using Specific Servers
```bash
# Use only specific servers
uv run python -m ui.cli query "What is BRAF?" --server opentargets --server mygene
```

### 6. Interactive Chat Mode
```bash
# Start interactive chat
uv run python -m ui.cli chat

# In chat, try:
# > What drugs are used to treat melanoma?
# > help
# > tools
# > servers
# > exit
```

## Streamlit App Testing

```bash
# Start the web interface
uv run streamlit run ui/app.py

# Then in browser:
# 1. Click "Connect" in sidebar
# 2. Try the chat tab with questions
# 3. Explore tools in Tools Explorer
# 4. Test direct queries in Direct Query tab
```