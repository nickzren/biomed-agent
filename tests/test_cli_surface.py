from typer.testing import CliRunner

from ui.cli import app


runner = CliRunner()


def test_cli_exposes_only_mechanical_diagnostics():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "list-servers" in result.output
    assert "list-tools" in result.output
    assert "call-tool" in result.output
    assert "doctor" in result.output
    assert "query" not in result.output
    assert "chat" not in result.output
