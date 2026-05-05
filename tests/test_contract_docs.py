import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ABOUT_LINE = "Connecting AI to biomedical data"


def test_positioning_tagline_is_canonical():
    readme = (ROOT / "README.md").read_text()
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert readme.startswith(f"# Biomedical Agent Workspace\n\n{ABOUT_LINE}.\n")
    assert pyproject["project"]["description"] == ABOUT_LINE


def test_agent_guide_points_to_skill_and_mcp_config():
    text = (ROOT / "AGENTS.md").read_text()

    assert "skills/biomed-research/SKILL.md" in text
    assert "mcp.json" in text
    assert "core/agent.py" in text
    assert "legacy" in text.lower()


def test_biomed_skill_preserves_research_contract():
    text = (ROOT / "skills" / "biomed-research" / "SKILL.md").read_text()

    for phrase in [
        "confidence",
        "citations",
        "limitations",
        "safety_note",
        "personalized medical advice",
        "diagnose",
        "opentargets",
        "monarch",
        "mygene",
        "mychem",
        "mydisease",
    ]:
        assert phrase in text


def test_mcp_config_lists_all_servers_with_stdio_commands():
    text = (ROOT / "mcp.json").read_text()

    for server in ["opentargets", "monarch", "mygene", "mychem", "mydisease"]:
        assert f'"{server}"' in text
        assert f"../{server}-mcp" in text
        assert f"{server}_mcp.server" in text
