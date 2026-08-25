from typer.testing import CliRunner

from dagwright import __version__
from dagwright.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "[ok] python:" in result.stdout
    assert result.stdout.endswith("DAGwright is ready.\n")


def test_no_command_shows_help() -> None:
    result = runner.invoke(app)

    assert result.exit_code == 2
    assert "Usage:" in result.stdout
