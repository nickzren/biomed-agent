import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import json
from typing import List, Optional
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from core import BiomedAgent

app = typer.Typer(help="Biomedical Research Agent CLI")
console = Console()

@app.command()
def list_servers():
    """List all available MCP servers and their status."""
    from core.agent import MCP_SERVERS
    
    table = Table(title="Available MCP Servers", show_header=True)
    table.add_column("Server", style="cyan", width=15)
    table.add_column("Description", style="green", width=50)
    table.add_column("Capabilities", style="yellow", width=40)
    table.add_column("Status", style="white", width=10)
    
    for name, config in MCP_SERVERS.items():
        env_var = f"{name.upper()}_MCP_PATH"
        path = Path(os.getenv(env_var, f"../{name}-mcp"))
        status = "✓ Found" if path.exists() else "✗ Missing"
        status_color = "green" if path.exists() else "red"
        
        # Format capabilities (show first few)
        caps = config["capabilities"]
        caps_display = ", ".join(caps[:5])
        if len(caps) > 5:
            caps_display += f" (+{len(caps)-5} more)"
        
        table.add_row(
            name,
            config["description"],
            caps_display,
            f"[{status_color}]{status}[/{status_color}]"
        )
        
    console.print(table)

@app.command()
def list_tools(
    servers: Optional[List[str]] = typer.Option(
        None, "--server", "-s", help="Specific servers to connect to"
    ),
    capability: Optional[str] = typer.Option(
        None, "--capability", "-c", help="Filter tools by capability"
    )
):
    """List all available tools from connected MCP servers."""
    asyncio.run(_list_tools(servers, capability))

async def _list_tools(servers: Optional[List[str]], capability: Optional[str]):
    """Async implementation of list_tools."""
    agent = BiomedAgent(servers)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting to MCP servers...", total=None)
        await agent.connect()
        progress.remove_task(task)
    
    if capability:
        # Find tools by capability
        matching_tools = agent.find_tools_by_capability(capability)
        console.print(f"\n[bold cyan]Tools matching '{capability}':[/bold cyan] ({len(matching_tools)} found)")
        
        for tool_id in matching_tools:
            tool_info = agent.tools_registry[tool_id]
            console.print(f"  [yellow]{tool_id}[/yellow]: {tool_info['tool'].get('description', 'N/A')}")
    else:
        # List all tools
        tools = agent.list_all_tools()
        
        total_tools = sum(len(server_tools) for server_tools in tools.values())
        console.print(f"\n[bold]Total tools available: {total_tools}[/bold]")
        
        for server, server_tools in tools.items():
            console.print(f"\n[bold cyan]{server}[/bold cyan] ({len(server_tools)} tools)")
            
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("Tool", style="yellow")
            table.add_column("Description", style="white")
            
            for tool in server_tools[:10]:  # Show first 10
                desc = tool["description"][:80] + "..." if len(tool["description"]) > 80 else tool["description"]
                table.add_row(tool["id"], desc)
                
            console.print(table)
            
            if len(server_tools) > 10:
                console.print(f"  [dim]... and {len(server_tools) - 10} more tools[/dim]")
    
    await agent.disconnect()

@app.command()
def query(
    question: str = typer.Argument(..., help="Your biomedical question"),
    servers: Optional[List[str]] = typer.Option(
        None, "--server", "-s", help="Specific servers to use"
    ),
    max_steps: int = typer.Option(10, "--max-steps", help="Maximum reasoning steps")
):
    """Ask a biomedical question and let the agent find the answer."""
    asyncio.run(_query(question, servers, max_steps))

async def _query(question: str, servers: Optional[List[str]], max_steps: int):
    """Async implementation of query."""
    console.print(Panel(f"[bold blue]Question: {question}[/bold blue]", expand=False))
    
    agent = BiomedAgent(servers)
    
    try:
        with console.status("Connecting to MCP servers..."):
            await agent.connect()
            
        with console.status("Thinking and researching..."):
            response = await agent.reason_and_act(question, max_steps)
            
        # Display answer
        console.print("\n[bold green]Answer:[/bold green]")
        console.print(response["answer"])
        
        # Optionally show reasoning steps
        if console.input("\n[dim]Show reasoning steps? (y/N):[/dim] ").lower() == "y":
            console.print("\n[bold]Reasoning steps:[/bold]")
            for i, step in enumerate(response["steps"]):
                console.print(f"\n[cyan]Step {i+1}:[/cyan]")
                console.print_json(json.dumps(step, indent=2))
                
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        
    finally:
        await agent.disconnect()

@app.command()
def chat(
    servers: Optional[List[str]] = typer.Option(
        None, "--server", "-s", help="Specific servers to use"
    )
):
    """Interactive chat mode with the biomedical agent."""
    asyncio.run(_chat_mode(servers))

async def _chat_mode(servers: Optional[List[str]]):
    """Async implementation of chat mode."""
    console.print(Panel("[bold cyan]Biomedical Agent Chat Mode[/bold cyan]\nType 'exit' to quit, 'help' for commands", expand=False))
    
    agent = BiomedAgent(servers)
    
    try:
        with console.status("Connecting to MCP servers..."):
            await agent.connect()
            
        tools_summary = agent.list_all_tools()
        total_tools = sum(len(tools) for tools in tools_summary.values())
        console.print(f"[green]Connected! {total_tools} tools available from {len(tools_summary)} servers.[/green]\n")
        
        while True:
            query = console.input("[bold blue]You:[/bold blue] ")
            
            if query.lower() in ["exit", "quit", "bye"]:
                break
            elif query.lower() == "help":
                console.print("\n[yellow]Commands:[/yellow]")
                console.print("  exit/quit/bye - Exit chat")
                console.print("  help - Show this help")
                console.print("  tools - List available tools")
                console.print("  servers - Show connected servers")
                console.print("\n[yellow]Tips:[/yellow]")
                console.print("  - Ask about drugs, diseases, genes, or variants")
                console.print("  - Use specific IDs when known (ENSG, CHEMBL, EFO)")
                console.print("  - Questions can span multiple databases\n")
                continue
            elif query.lower() == "tools":
                total = sum(len(tools) for tools in tools_summary.values())
                console.print(f"\n[cyan]Available tools ({total} total):[/cyan]")
                for server, tools in tools_summary.items():
                    console.print(f"  {server}: {len(tools)} tools")
                console.print("\nUse 'list-tools' command for details.\n")
                continue
            elif query.lower() == "servers":
                console.print(f"\n[cyan]Connected servers:[/cyan]")
                for server in agent.clients.keys():
                    console.print(f"  - {server}")
                console.print()
                continue
                
            try:
                # Process the query and get response
                with console.status("Thinking..."):
                    response = await agent.reason_and_act(query)
                    
                # Display the answer after status is done
                console.print(f"\n[bold green]Agent:[/bold green] {response['answer']}\n")
                
                # Ask about reasoning outside of status context
                if console.input("[dim]Show reasoning? (y/N):[/dim] ").lower() == "y":
                    console.print("\n[dim]Reasoning steps:[/dim]")
                    for i, step in enumerate(response["steps"]):
                        if "thought" in step:
                            console.print(f"[cyan]Step {i+1}:[/cyan] {step['thought']}")
                        if "observation" in step and "error" in step["observation"]:
                            console.print(f"[red]Error:[/red] {step['observation']['error']}")
                    console.print()
                    
            except Exception as e:
                console.print(f"[red]Error: {str(e)}[/red]\n")
                    
    finally:
        await agent.disconnect()
        console.print("\n[yellow]Goodbye![/yellow]")

@app.command()
def call_tool(
    tool_id: str = typer.Argument(..., help="Tool ID (e.g., 'opentargets.search_entities')"),
    args: str = typer.Argument(..., help="Tool arguments as JSON string"),
    servers: Optional[List[str]] = typer.Option(
        None, "--server", "-s", help="Specific servers to use"
    )
):
    """Call a specific tool directly."""
    try:
        arguments = json.loads(args)
    except json.JSONDecodeError:
        console.print("[red]Invalid JSON arguments[/red]")
        return
        
    asyncio.run(_call_tool(tool_id, arguments, servers))

async def _call_tool(tool_id: str, arguments: dict, servers: Optional[List[str]]):
    """Async implementation of tool calling."""
    agent = BiomedAgent(servers)
    
    try:
        with console.status("Connecting to MCP servers..."):
            await agent.connect()
            
        console.print(f"[bold]Calling tool:[/bold] {tool_id}")
        console.print(f"[bold]Arguments:[/bold] {json.dumps(arguments, indent=2)}")
        
        result = await agent.call_tool(tool_id, arguments)
        
        console.print("\n[bold green]Result:[/bold green]")
        console.print_json(json.dumps(result, indent=2))
        
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        
    finally:
        await agent.disconnect()

if __name__ == "__main__":
    app()