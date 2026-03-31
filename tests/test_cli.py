"""Tests for CLI shell command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from clawgraph.cli import app

try:
    from typer.testing import CliRunner
except ImportError:
    from click.testing import CliRunner  # type: ignore[assignment]


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_add_result(
    entities: list[dict[str, str]] | None = None,
    relationships: list[dict[str, str]] | None = None,
    errors: list[str] | None = None,
) -> MagicMock:
    """Create a mock AddResult."""
    result = MagicMock()
    result.entities = entities or [{"name": "Alice", "label": "Person"}]
    result.relationships = relationships or []
    result.errors = errors or []
    result.ok = len(result.errors) == 0
    return result


def _mock_memory(**overrides: object) -> MagicMock:
    """Return a mock Memory instance with sensible defaults."""
    mem = MagicMock()
    mem.add.return_value = _make_add_result()
    mem.query.return_value = [{"name": "Alice", "role": "engineer"}]
    mem.entities.return_value = [{"name": "Alice"}]
    mem.relationships.return_value = []
    mem.export.return_value = {"entities": [], "relationships": [], "ontology": {}}
    ont = MagicMock()
    ont.to_context_string.return_value = "No ontology defined yet."
    mem.get_ontology.return_value = ont
    for key, val in overrides.items():
        setattr(mem, key, val)
    return mem


# ---------------------------------------------------------------------------
# Shell tests
# ---------------------------------------------------------------------------

class TestShellQuit:
    """Tests for exiting the shell."""

    def test_quit_command(self) -> None:
        """/quit exits the shell cleanly."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0

    def test_exit_command(self) -> None:
        """/exit exits the shell cleanly."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["/exit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0

    def test_eof_exits(self) -> None:
        """Ctrl+D (EOF) exits the shell cleanly."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=EOFError):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0

    def test_keyboard_interrupt_exits(self) -> None:
        """Ctrl+C exits the shell cleanly."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0


class TestShellAdd:
    """Tests for adding facts in the shell."""

    def test_add_fact(self) -> None:
        """Typing a statement adds it as a fact."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["Alice is an engineer", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mem.add.assert_called_once_with("Alice is an engineer")

    def test_add_fact_with_errors(self) -> None:
        """Partial add shows error count."""
        mem = _mock_memory()
        mem.add.return_value = _make_add_result(errors=["some error"])
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["bad fact", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0

    def test_add_fact_exception(self) -> None:
        """LLM errors are caught and shown."""
        mem = _mock_memory()
        mem.add.side_effect = Exception("LLM failed")
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["bad fact", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0


class TestShellQuery:
    """Tests for querying in the shell."""

    def test_query(self) -> None:
        """? prefix triggers a query."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["? Who is Alice?", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mem.query.assert_called_once_with("Who is Alice?")

    def test_query_no_results(self) -> None:
        """Empty query results show a message."""
        mem = _mock_memory()
        mem.query.return_value = []
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["? unknown", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0

    def test_query_empty_question(self) -> None:
        """? with no text shows a warning."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["?", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mem.query.assert_not_called()

    def test_query_exception(self) -> None:
        """Query errors are caught and shown."""
        mem = _mock_memory()
        mem.query.side_effect = Exception("query failed")
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["? boom", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0


class TestShellCommands:
    """Tests for slash commands in the shell."""

    def test_export(self) -> None:
        """/export calls mem.export()."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["/export", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mem.export.assert_called_once()

    def test_stats(self) -> None:
        """/stats shows entity and relationship counts."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["/stats", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mem.entities.assert_called()
        mem.relationships.assert_called()

    def test_ontology(self) -> None:
        """/ontology shows the current ontology."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["/ontology", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mem.get_ontology.assert_called()

    def test_clear(self) -> None:
        """/clear clears the ontology."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["/clear", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mem.get_ontology.return_value.clear.assert_called_once()

    def test_empty_line_ignored(self) -> None:
        """Empty lines are skipped."""
        mem = _mock_memory()
        with patch("clawgraph.memory.Memory", return_value=mem):
            with patch("builtins.input", side_effect=["", "  ", "/quit"]):
                result = runner.invoke(app, ["shell"])
        assert result.exit_code == 0
        mem.add.assert_not_called()
