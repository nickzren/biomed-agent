import asyncio
import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from biomed_agent import cli
from biomed_agent.cli import app


runner = CliRunner()


def test_cli_exposes_only_mechanical_diagnostics():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "list-servers" in result.output
    assert "list-tools" in result.output
    assert "call-tool" in result.output
    assert "doctor" in result.output
    assert "init" in result.output
    assert "query" not in result.output
    assert "chat" not in result.output


def test_list_servers_json_uses_stable_schema():
    result = runner.invoke(app, ["list-servers", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert {server["name"] for server in payload["servers"]} == {
        "opentargets",
        "monarch",
        "mychem",
        "mydisease",
        "mygene",
    }
    assert all("status" in server for server in payload["servers"])


def test_init_is_print_only_and_outputs_codex_guidance():
    missing_print = runner.invoke(app, ["init", "--runtime", "codex"])

    assert missing_print.exit_code != 0
    assert "pass --print" in missing_print.output

    result = runner.invoke(
        app,
        ["init", "--runtime", "codex", "--print", "--mcp-base", "../"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["runtime"] == "codex"
    assert payload["mode"] == "print-only"
    assert payload["writes_files"] is False
    assert "mcpServers" in payload["mcp_config"]
    assert "codex_config_toml" in payload
    assert "AGENTS.md" in payload["agent_guidance"]["contract"]
    assert "skills/biomed-research/SKILL.md" in payload["agent_guidance"]["skill"]


def test_cursor_init_includes_agent_instruction_text():
    result = runner.invoke(app, ["init", "--runtime", "cursor", "--print"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["runtime"] == "cursor"
    assert "cursor_agent_instructions" in payload
    assert "patient-specific treatment advice" in payload["cursor_agent_instructions"]


def test_probe_server_tools_reports_missing_path(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing"
    server = SimpleNamespace(name="mygene", path=missing_path)
    monkeypatch.setattr(cli, "build_server", lambda server_name: server)

    payload = asyncio.run(cli._probe_server_tools("mygene"))

    assert payload == {
        "name": "mygene",
        "path": str(missing_path),
        "status": "missing",
        "tool_count": 0,
        "tools": [],
    }


def test_probe_server_tools_reports_connected_tools(monkeypatch, tmp_path):
    disconnected = False
    server = SimpleNamespace(name="mygene", path=tmp_path)
    tools = [{"name": "lookup_gene", "description": "Gene lookup"}]

    class FakeClient:
        def __init__(self, server):
            self.server = server

        async def connect(self):
            return None

        async def list_tools(self):
            return tools

        async def disconnect(self):
            nonlocal disconnected
            disconnected = True

    monkeypatch.setattr(cli, "build_server", lambda server_name: server)
    monkeypatch.setattr(cli, "MCPClient", FakeClient)

    payload = asyncio.run(cli._probe_server_tools("mygene"))

    assert payload["status"] == "ok"
    assert payload["tool_count"] == 1
    assert payload["tools"] == tools
    assert disconnected is True


def test_probe_server_tools_reports_connection_error(monkeypatch, tmp_path):
    disconnected = False
    server = SimpleNamespace(name="mygene", path=tmp_path)

    class FakeClient:
        def __init__(self, server):
            self.server = server

        async def connect(self):
            raise RuntimeError("connect failed")

        async def list_tools(self):
            raise AssertionError("list_tools should not be called")

        async def disconnect(self):
            nonlocal disconnected
            disconnected = True

    monkeypatch.setattr(cli, "build_server", lambda server_name: server)
    monkeypatch.setattr(cli, "MCPClient", FakeClient)

    payload = asyncio.run(cli._probe_server_tools("mygene"))

    assert payload["status"] == "error"
    assert payload["tool_count"] == 0
    assert payload["tools"] == []
    assert payload["error"] == "connect failed"
    assert disconnected is True


def test_probe_server_tools_reports_success_with_no_tools(monkeypatch, tmp_path):
    server = SimpleNamespace(name="mygene", path=tmp_path)

    class FakeClient:
        def __init__(self, server):
            self.server = server

        async def connect(self):
            return None

        async def list_tools(self):
            return []

        async def disconnect(self):
            return None

    monkeypatch.setattr(cli, "build_server", lambda server_name: server)
    monkeypatch.setattr(cli, "MCPClient", FakeClient)

    payload = asyncio.run(cli._probe_server_tools("mygene"))

    assert payload["status"] == "ok"
    assert payload["tool_count"] == 0
    assert payload["tools"] == []


def test_list_tools_json_preserves_tool_id_capability_matching(monkeypatch):
    async def fake_probe(server_name):
        return {
            "name": server_name,
            "path": "../opentargets-mcp",
            "status": "ok",
            "tool_count": 1,
            "tools": [{"name": "entity_lookup", "description": "Entity lookup"}],
        }

    monkeypatch.setattr(cli, "_probe_server_tools", fake_probe)

    payload = asyncio.run(cli.build_list_tools_payload(["opentargets"], "opentargets"))

    assert payload["total_tools"] == 1
    assert payload["tools"][0]["id"] == "opentargets.entity_lookup"


def test_human_list_tools_aborts_on_probe_error(monkeypatch):
    async def fake_probe(server_name):
        return {
            "name": server_name,
            "path": "../mygene-mcp",
            "status": "error",
            "tool_count": 0,
            "tools": [],
            "error": "connect failed",
        }

    monkeypatch.setattr(cli, "_probe_server_tools", fake_probe)

    with pytest.raises(RuntimeError, match="connect failed"):
        asyncio.run(cli._connect_and_register(["mygene"]))


def test_human_doctor_renders_probe_error(monkeypatch):
    async def fake_probe(server_name):
        return {
            "name": server_name,
            "path": "../mygene-mcp",
            "status": "error",
            "tool_count": 0,
            "tools": [],
            "error": "connect failed",
        }

    monkeypatch.setattr(cli, "_probe_server_tools", fake_probe)

    result = runner.invoke(app, ["doctor", "--server", "mygene"])

    assert result.exit_code == 0
    assert "error: connect failed" in result.output
