import json

from typer.testing import CliRunner

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
