from pathlib import Path

from biomed_agent.servers import (
    MCP_SERVERS,
    build_server,
    find_tools_by_capability,
    group_tools_by_server,
    resolve_server_path,
    split_tool_id,
    tool_matches_capability,
)


def test_registry_tracks_expected_mcp_servers():
    assert set(MCP_SERVERS) == {
        "opentargets",
        "monarch",
        "mychem",
        "mydisease",
        "mygene",
    }


def test_mcp_server_descriptor_reexports_stay_compatible():
    from biomed_agent import MCPServer as package_mcp_server
    from biomed_agent.mcp_client import MCPServer as client_mcp_server
    from biomed_agent.servers import MCPServer as registry_mcp_server

    assert package_mcp_server is registry_mcp_server
    assert client_mcp_server is registry_mcp_server


def test_resolve_server_path_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENTARGETS_MCP_PATH", str(tmp_path))

    assert resolve_server_path("opentargets") == tmp_path


def test_build_server_uses_stdio_module_command(monkeypatch, tmp_path):
    monkeypatch.setenv("MYGENE_MCP_PATH", str(tmp_path))

    server = build_server("mygene")

    assert server.name == "mygene"
    assert server.path == tmp_path
    assert server.command == ["uv", "run", "python", "-m", "mygene_mcp.server"]


def test_split_tool_id_requires_server_and_tool_name():
    assert split_tool_id("opentargets.search_entities") == (
        "opentargets",
        "search_entities",
    )


def test_find_tools_by_capability_checks_name_description_and_server_caps():
    registry = {
        "opentargets.search_entities": {
            "server": "opentargets",
            "tool": {"name": "search_entities", "description": "Entity lookup"},
        },
        "mygene.get_gene_annotation": {
            "server": "mygene",
            "tool": {"name": "get_gene_annotation", "description": "Gene details"},
        },
    }

    assert find_tools_by_capability(registry, "drug") == ["opentargets.search_entities"]
    assert find_tools_by_capability(registry, "annotation") == [
        "mygene.get_gene_annotation"
    ]


def test_find_tools_by_capability_does_not_match_tool_id_text_only():
    registry = {
        "opentargets.entity_lookup": {
            "server": "opentargets",
            "tool": {"name": "entity_lookup", "description": "Entity lookup"},
        },
    }

    assert find_tools_by_capability(registry, "opentargets") == []


def test_tool_matches_capability_can_optionally_check_tool_id():
    tool = {"name": "entity_lookup", "description": "Entity lookup"}

    assert not tool_matches_capability(
        tool_id="opentargets.entity_lookup",
        server_name="opentargets",
        tool=tool,
        capability="opentargets",
    )
    assert tool_matches_capability(
        tool_id="opentargets.entity_lookup",
        server_name="opentargets",
        tool=tool,
        capability="opentargets",
        include_tool_id=True,
    )


def test_group_tools_by_server_sorts_tool_ids():
    registry = {
        "mygene.z_tool": {
            "server": "mygene",
            "tool": {"name": "z_tool", "description": "Z"},
        },
        "mygene.a_tool": {
            "server": "mygene",
            "tool": {"name": "a_tool", "description": "A"},
        },
    }

    grouped = group_tools_by_server(registry)

    assert [tool["id"] for tool in grouped["mygene"]] == [
        "mygene.a_tool",
        "mygene.z_tool",
    ]


def test_default_paths_are_sibling_repos_without_env(monkeypatch):
    monkeypatch.delenv("MONARCH_MCP_PATH", raising=False)

    assert resolve_server_path("monarch") == Path("../monarch-mcp")
