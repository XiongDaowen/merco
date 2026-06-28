"""CLI smoke tests — verifies `merco run --help` boots without import errors.

Phase 3 lesson: unit + mock-LLM integration tests do not cover import-time
errors (e.g., `cli/main.py` passing a removed `skill_registry` kwarg into
`Agent(...)`). These tests exercise the real CLI bootstrap path via
`typer.testing.CliRunner` but only check Typer help output, not the LLM
call path.
"""

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_merco_run_help_succeeds(cli_runner):
    """`merco run --help` boots, exits 0, prints Usage."""
    from cli.main import app

    result = cli_runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0, (
        f"stdout={result.stdout!r} "
        f"stderr={getattr(result, 'stderr', None) or ''!r}"
    )
    assert "Usage:" in result.stdout


def test_merco_root_help_succeeds(cli_runner):
    """`merco --help` boots without errors."""
    from cli.main import app

    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout


def test_merco_init_help_succeeds(cli_runner):
    """`merco init --help` boots without errors."""
    from cli.main import app

    result = cli_runner.invoke(app, ["init", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
