import asyncio
import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .mcp_client import MCPClient
from .servers import (
    MCP_SERVERS,
    build_server,
    find_tools_by_capability,
    group_tools_by_server,
    resolve_server_path,
    selected_server_names,
    split_tool_id,
    tool_matches_capability,
)

app = typer.Typer(help="Biomedical MCP workspace CLI")
console = Console()
SCHEMA_VERSION = 1
SUPPORTED_INIT_RUNTIMES = {"codex", "claude", "cursor"}


@app.command("list-servers")
def list_servers(
    json_output: bool = typer.Option(
        False, "--json", help="Print stable machine-readable JSON"
    ),
) -> None:
    """List configured MCP servers and local path status."""
    if json_output:
        _print_json(build_list_servers_payload())
        return

    table = Table(title="Biomedical MCP Servers", show_header=True, expand=False)
    table.add_column("Server", style="cyan", no_wrap=True)
    table.add_column("Status", style="white", no_wrap=True)
    table.add_column("Path", style="white", overflow="fold")
    table.add_column("Capabilities", style="yellow", overflow="fold")

    for server in build_list_servers_payload()["servers"]:
        table.add_row(
            server["name"],
            server["status"],
            server["path"],
            _capability_preview(server["capabilities"]),
        )

    console.print(table)


@app.command("list-tools")
def list_tools(
    servers: list[str] | None = typer.Option(
        None, "--server", "-s", help="Specific server to connect to"
    ),
    capability: str | None = typer.Option(
        None, "--capability", "-c", help="Filter tools by capability"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print stable machine-readable JSON"
    ),
) -> None:
    """List tools exposed by one or more MCP servers."""
    asyncio.run(_list_tools(servers, capability, json_output))


async def _list_tools(
    servers: list[str] | None,
    capability: str | None,
    json_output: bool,
) -> None:
    if json_output:
        _print_json(await build_list_tools_payload(servers, capability))
        return

    registry = await _connect_and_register(servers)
    if capability:
        matching_tools = find_tools_by_capability(registry, capability)
        console.print(
            f"\n[bold cyan]Tools matching '{capability}':[/bold cyan] "
            f"({len(matching_tools)} found)"
        )
        for tool_id in matching_tools:
            tool = registry[tool_id]["tool"]
            console.print(
                f"  [yellow]{tool_id}[/yellow]: "
                f"{tool.get('description', 'N/A')}"
            )
        return

    grouped_tools = group_tools_by_server(registry)
    total_tools = sum(len(items) for items in grouped_tools.values())
    console.print(f"\n[bold]Total tools available: {total_tools}[/bold]")

    for server_name, server_tools in grouped_tools.items():
        console.print(f"\n[bold cyan]{server_name}[/bold cyan] ({len(server_tools)} tools)")
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Tool", style="yellow")
        table.add_column("Description", style="white")
        for tool in server_tools[:10]:
            description = tool["description"]
            if len(description) > 80:
                description = description[:77] + "..."
            table.add_row(tool["id"], description)
        console.print(table)
        if len(server_tools) > 10:
            console.print(f"  [dim]... and {len(server_tools) - 10} more tools[/dim]")


@app.command("call-tool")
def call_tool(
    tool_id: str = typer.Argument(..., help="Tool ID, for example opentargets.search_entities"),
    args: str = typer.Argument(..., help="Tool arguments as a JSON object"),
) -> None:
    """Call one MCP tool directly."""
    try:
        arguments = json.loads(args)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("Tool arguments must be valid JSON") from exc
    if not isinstance(arguments, dict):
        raise typer.BadParameter("Tool arguments must be a JSON object")

    asyncio.run(_call_tool(tool_id, arguments))


async def _call_tool(tool_id: str, arguments: dict[str, Any]) -> None:
    server_name, tool_name = split_tool_id(tool_id)
    server = build_server(server_name)
    if not server.path.exists():
        raise typer.BadParameter(f"MCP server path does not exist: {server.path}")

    client = MCPClient(server)
    try:
        await client.connect()
        result = await client.call_tool(tool_name, arguments)
        console.print_json(json.dumps(result, indent=2, default=str))
    finally:
        await client.disconnect()


@app.command("doctor")
def doctor(
    servers: list[str] | None = typer.Option(
        None, "--server", "-s", help="Specific server to check"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print stable machine-readable JSON"
    ),
) -> None:
    """Check MCP server paths and tool-list connectivity."""
    asyncio.run(_doctor(servers, json_output))


async def _doctor(servers: list[str] | None, json_output: bool) -> None:
    if json_output:
        _print_json(await build_doctor_payload(servers))
        return

    names = selected_server_names(servers)
    table = Table(title="Biomedical MCP Doctor", show_header=True)
    table.add_column("Server", style="cyan")
    table.add_column("Path", style="white")
    table.add_column("Status", style="green")
    table.add_column("Tools", justify="right")

    for server_name in names:
        probe = await _probe_server_tools(server_name)
        status = probe["status"]
        if status == "error":
            status = f"error: {probe['error']}"
        table.add_row(
            server_name,
            str(probe["path"]),
            status,
            str(probe["tool_count"]),
        )

    console.print(table)


@app.command("init")
def init(
    runtime: str = typer.Option(
        ..., "--runtime", "-r", help="Runtime to initialize: codex, claude, or cursor"
    ),
    print_config: bool = typer.Option(
        False, "--print", help="Print config and guidance without writing files"
    ),
    mcp_base: str = typer.Option(
        "../",
        "--mcp-base",
        help="Base directory containing sibling MCP repos",
    ),
) -> None:
    """Print MCP config and agent guidance for a coding-agent runtime."""
    runtime = runtime.lower()
    if runtime not in SUPPORTED_INIT_RUNTIMES:
        raise typer.BadParameter(
            "Runtime must be one of: " + ", ".join(sorted(SUPPORTED_INIT_RUNTIMES))
        )
    if not print_config:
        raise typer.BadParameter("init is read-only; pass --print to print config")

    _print_json(build_init_payload(runtime, mcp_base))


async def _connect_and_register(
    servers: list[str] | None,
) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for server_name in selected_server_names(servers):
        probe = await _probe_server_tools(server_name)
        if probe["status"] == "missing":
            console.print(f"[yellow]Skipping missing server path:[/yellow] {probe['path']}")
            continue
        if probe["status"] == "error":
            raise RuntimeError(str(probe["error"]))

        for tool in probe["tools"]:
            tool_name = tool.get("name")
            if not tool_name:
                continue
            registry[f"{server_name}.{tool_name}"] = {
                "server": server_name,
                "tool": tool,
            }

    if not registry:
        raise typer.BadParameter("No MCP tools were available from the selected servers")
    return registry


async def _probe_server_tools(server_name: str) -> dict[str, Any]:
    server = build_server(server_name)
    probe: dict[str, Any] = {
        "name": server_name,
        "path": str(server.path),
        "status": "missing",
        "tool_count": 0,
        "tools": [],
    }
    if not server.path.exists():
        return probe

    client = MCPClient(server)
    try:
        await client.connect()
        tools = await client.list_tools()
        probe.update(
            {
                "status": "ok",
                "tool_count": len(tools),
                "tools": tools,
            }
        )
    except Exception as exc:
        probe.update({"status": "error", "error": str(exc)})
    finally:
        await client.disconnect()
    return probe


def _print_json(payload: dict[str, Any]) -> None:
    console.print_json(data=payload, default=str)


def build_list_servers_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "servers": [
            _server_config_payload(server_name)
            for server_name in selected_server_names(None)
        ],
    }


def _server_config_payload(server_name: str) -> dict[str, Any]:
    config = MCP_SERVERS[server_name]
    path = resolve_server_path(server_name)
    exists = path.exists()
    return {
        "name": server_name,
        "description": config.description,
        "module": config.module,
        "path": str(path),
        "exists": exists,
        "status": "found" if exists else "missing",
        "capabilities": list(config.capabilities),
    }


def _capability_preview(capabilities: list[str]) -> str:
    preview = ", ".join(capabilities[:5])
    if len(capabilities) > 5:
        preview += f" (+{len(capabilities) - 5} more)"
    return preview


async def build_list_tools_payload(
    servers: list[str] | None,
    capability: str | None,
) -> dict[str, Any]:
    names = selected_server_names(servers)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "servers": [],
        "total_tools": 0,
    }
    if capability:
        payload["capability"] = capability
        payload["tools"] = []

    for server_name in names:
        probe = await _probe_server_tools(server_name)
        server_payload: dict[str, Any] = {
            "name": server_name,
            "path": probe["path"],
            "status": probe["status"],
            "tool_count": probe["tool_count"],
            "tools": [],
        }
        if probe["status"] == "missing":
            payload["servers"].append(server_payload)
            continue
        if probe["status"] == "error":
            server_payload["error"] = probe["error"]
        else:
            tools = [_tool_payload(server_name, tool) for tool in probe["tools"]]
            if capability:
                tools = [
                    tool for tool in tools if _tool_matches_capability(tool, capability)
                ]
            server_payload.update(
                {
                    "status": "ok",
                    "tool_count": len(tools),
                    "tools": tools,
                }
            )
            payload["total_tools"] += len(tools)
            if capability:
                payload["tools"].extend(tools)
        payload["servers"].append(server_payload)

    return payload


def _tool_payload(server_name: str, tool: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(tool.get("name", ""))
    return {
        "id": f"{server_name}.{tool_name}" if tool_name else server_name,
        "server": server_name,
        "name": tool_name,
        "description": tool.get("description", ""),
    }


def _tool_matches_capability(tool: dict[str, Any], capability: str) -> bool:
    server_name = str(tool["server"])
    return tool_matches_capability(
        tool_id=str(tool["id"]),
        server_name=server_name,
        tool=tool,
        capability=capability,
        include_tool_id=True,
    )


async def build_doctor_payload(servers: list[str] | None) -> dict[str, Any]:
    server_payloads = []
    for server_name in selected_server_names(servers):
        probe = await _probe_server_tools(server_name)
        item: dict[str, Any] = {
            "name": server_name,
            "path": probe["path"],
            "status": probe["status"],
            "tool_count": probe["tool_count"],
        }
        if probe["status"] == "error":
            item["error"] = probe["error"]
        server_payloads.append(item)

    return {
        "schema_version": SCHEMA_VERSION,
        "servers": server_payloads,
        "total_tools": sum(item["tool_count"] for item in server_payloads),
    }


def build_init_payload(runtime: str, mcp_base: str) -> dict[str, Any]:
    mcp_config, server_paths = _build_mcp_config(mcp_base)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "runtime": runtime,
        "mode": "print-only",
        "writes_files": False,
        "mcp_base": mcp_base,
        "server_paths": server_paths,
        "mcp_config": mcp_config,
        "agent_guidance": _agent_guidance(runtime),
    }
    if runtime == "codex":
        payload["codex_config_toml"] = _build_codex_toml(mcp_config)
    elif runtime == "cursor":
        payload["cursor_agent_instructions"] = _cursor_agent_instructions()
    return payload


def _build_mcp_config(mcp_base: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base = Path(mcp_base)
    exists_base = base.expanduser()
    mcp_servers = {}
    server_paths = []
    for server_name, config in MCP_SERVERS.items():
        repo_dir = config.default_path.name
        cwd = base / repo_dir
        exists_path = exists_base / repo_dir
        server_config = {
            "transport": "stdio",
            "command": "uv",
            "args": ["run", "python", "-m", config.module],
            "cwd": cwd.as_posix(),
        }
        mcp_servers[server_name] = server_config
        server_paths.append(
            {
                "name": server_name,
                "cwd": cwd.as_posix(),
                "exists": exists_path.exists(),
                "status": "found" if exists_path.exists() else "missing",
            }
        )
    return {"mcpServers": mcp_servers}, server_paths


def _build_codex_toml(mcp_config: dict[str, Any]) -> str:
    lines = []
    for server_name, server_config in mcp_config["mcpServers"].items():
        lines.append(f"[mcp_servers.{server_name}]")
        lines.append(f"command = {json.dumps(server_config['command'])}")
        lines.append(f"args = {json.dumps(server_config['args'])}")
        lines.append(f"cwd = {json.dumps(server_config['cwd'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _agent_guidance(runtime: str) -> dict[str, Any]:
    return {
        "contract": "Use AGENTS.md as the canonical orchestration contract.",
        "skill": "Use skills/biomed-research/SKILL.md for source-backed synthesis.",
        "routing_summary": [
            "opentargets: target-disease evidence, drugs, genetics, variants, studies",
            "monarch: HPO phenotypes, rare disease, model organisms, similarity",
            "mygene: gene annotation, IDs, expression, GO, orthologs",
            "mychem: chemical identifiers, structures, mechanisms, bioactivity",
            "mydisease: disease annotation, OMIM, Orphanet, MONDO, HPO",
        ],
        "safety_boundary": (
            "Research and educational use only; do not diagnose, prescribe, dose, "
            "or recommend patient-specific treatment."
        ),
        "runtime_note": _runtime_note(runtime),
    }


def _runtime_note(runtime: str) -> str:
    if runtime == "codex":
        return "Add the MCP TOML snippet to your Codex MCP configuration."
    if runtime == "claude":
        return "Add the mcp_config JSON to Claude's MCP configuration."
    return (
        "Add the mcp_config JSON to Cursor MCP settings and paste the "
        "cursor_agent_instructions text into Cursor rules or agent instructions."
    )


def _cursor_agent_instructions() -> str:
    return (
        "Use this workspace as an agent-native biomedical research environment. "
        "Route factual biomedical questions through the configured MCP servers, "
        "resolve names to stable IDs before deeper calls, attribute material "
        "claims to tool observations, state limitations, and follow the safety "
        "boundary: no diagnosis, prescribing, dosing, or patient-specific "
        "treatment advice."
    )


if __name__ == "__main__":
    app()
