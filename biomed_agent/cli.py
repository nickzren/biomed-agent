import asyncio
import json
from typing import Any, Optional

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
)

app = typer.Typer(help="Biomedical MCP diagnostics CLI")
console = Console()


@app.command("list-servers")
def list_servers() -> None:
    """List configured MCP servers and local path status."""
    table = Table(title="Biomedical MCP Servers", show_header=True, expand=False)
    table.add_column("Server", style="cyan", no_wrap=True)
    table.add_column("Status", style="white", no_wrap=True)
    table.add_column("Path", style="white", overflow="fold")
    table.add_column("Capabilities", style="yellow", overflow="fold")

    for server_name, config in MCP_SERVERS.items():
        path = resolve_server_path(server_name)
        capabilities = ", ".join(config.capabilities[:5])
        if len(config.capabilities) > 5:
            capabilities += f" (+{len(config.capabilities) - 5} more)"
        table.add_row(
            server_name,
            "found" if path.exists() else "missing",
            str(path),
            capabilities,
        )

    console.print(table)


@app.command("list-tools")
def list_tools(
    servers: Optional[list[str]] = typer.Option(
        None, "--server", "-s", help="Specific server to connect to"
    ),
    capability: Optional[str] = typer.Option(
        None, "--capability", "-c", help="Filter tools by capability"
    ),
) -> None:
    """List tools exposed by one or more MCP servers."""
    asyncio.run(_list_tools(servers, capability))


async def _list_tools(
    servers: Optional[list[str]],
    capability: Optional[str],
) -> None:
    clients: list[MCPClient] = []
    try:
        registry = await _connect_and_register(servers, clients)
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
    finally:
        await _disconnect_all(clients)


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
    servers: Optional[list[str]] = typer.Option(
        None, "--server", "-s", help="Specific server to check"
    ),
) -> None:
    """Check MCP server paths and tool-list connectivity."""
    asyncio.run(_doctor(servers))


async def _doctor(servers: Optional[list[str]]) -> None:
    names = selected_server_names(servers)
    table = Table(title="Biomedical MCP Doctor", show_header=True)
    table.add_column("Server", style="cyan")
    table.add_column("Path", style="white")
    table.add_column("Status", style="green")
    table.add_column("Tools", justify="right")

    for server_name in names:
        server = build_server(server_name)
        if not server.path.exists():
            table.add_row(server_name, str(server.path), "missing", "0")
            continue

        client = MCPClient(server)
        try:
            await client.connect()
            tools = await client.list_tools()
            table.add_row(server_name, str(server.path), "ok", str(len(tools)))
        except Exception as exc:
            table.add_row(server_name, str(server.path), f"error: {exc}", "0")
        finally:
            await client.disconnect()

    console.print(table)


async def _connect_and_register(
    servers: Optional[list[str]],
    clients: list[MCPClient],
) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for server_name in selected_server_names(servers):
        server = build_server(server_name)
        if not server.path.exists():
            console.print(f"[yellow]Skipping missing server path:[/yellow] {server.path}")
            continue

        client = MCPClient(server)
        await client.connect()
        clients.append(client)

        for tool in await client.list_tools():
            tool_name = tool.get("name")
            if not tool_name:
                continue
            registry[f"{server_name}.{tool_name}"] = {
                "server": server_name,
                "tool": tool,
                "client": client,
            }

    if not registry:
        raise typer.BadParameter("No MCP tools were available from the selected servers")
    return registry


async def _disconnect_all(clients: list[MCPClient]) -> None:
    await asyncio.gather(
        *(client.disconnect() for client in clients),
        return_exceptions=True,
    )


if __name__ == "__main__":
    app()
