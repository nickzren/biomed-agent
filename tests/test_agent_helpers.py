from core.agent import BiomedAgent


def _make_agent() -> BiomedAgent:
    agent = BiomedAgent(servers=["opentargets"])
    agent.tools_registry = {
        "opentargets.search_entities": {
            "tool": {
                "name": "search_entities",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query_string": {"type": "string"},
                        "page_size": {"type": "integer"},
                    },
                    "required": ["query_string"],
                },
            },
            "server": "opentargets",
            "client": None,
        }
    }
    return agent


def test_parse_llm_json_from_mixed_text():
    agent = _make_agent()
    content = """noise
{"thought":"t1","action":{"tool":"opentargets.search_entities","arguments":{"query_string":"BRAF"}},"is_final":false}
{"thought":"t2","is_final":true,"answer":"done"}
"""
    parsed = agent._parse_llm_json(content)
    assert parsed["is_final"] is False
    assert parsed["action"]["tool"] == "opentargets.search_entities"


def test_normalize_tool_id_removes_server_prefix():
    agent = _make_agent()
    assert agent._normalize_tool_id("server.opentargets.search_entities") == "opentargets.search_entities"


def test_sanitize_tool_arguments_filters_unknown_keys():
    agent = _make_agent()
    sanitized = agent._sanitize_tool_arguments(
        "opentargets.search_entities",
        {"query_string": "BRAF", "page_size": 5, "client": "x"},
    )
    assert sanitized == {"query_string": "BRAF", "page_size": 5}


def test_missing_required_tool_arguments_detected():
    agent = _make_agent()
    missing = agent._missing_required_tool_arguments(
        "opentargets.search_entities",
        {"page_size": 5},
    )
    assert missing == ["query_string"]


def test_merge_safety_note_prepends_once():
    agent = _make_agent()
    note = "general info only"
    merged = agent._merge_safety_note(["a", "b"], note)
    assert merged[0] == note
    merged_again = agent._merge_safety_note(merged, note)
    assert merged_again.count(note) == 1
