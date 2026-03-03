"""Tests for CLI commands."""

from unittest.mock import patch

from typer.testing import CliRunner

from clawgraph.cli import app

runner = CliRunner()


class TestVersionCommand:
    """Tests for the version subcommand."""

    def test_version_subcommand(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "clawgraph" in result.output

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "clawgraph" in result.output


class TestStatsCommand:
    """Tests for the stats subcommand using real in-memory DB."""

    def test_stats_human(self, tmp_path: str) -> None:
        from clawgraph.db import GraphDB

        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")

        with patch("clawgraph.db.GraphDB", return_value=db), \
             patch("clawgraph.ontology.Ontology.to_context_string",
                   return_value="No ontology defined yet."):
            result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "1" in result.output

    def test_stats_json(self) -> None:
        from clawgraph.db import GraphDB

        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        with patch("clawgraph.db.GraphDB", return_value=db), \
             patch("clawgraph.ontology.Ontology.to_context_string",
                   return_value="No ontology defined yet."):
            result = runner.invoke(app, ["stats", "--output", "json"])
        assert result.exit_code == 0
        assert '"entities"' in result.output
        assert '"relationships"' in result.output


class TestDeleteCommand:
    """Tests for the delete subcommand."""

    def test_delete_with_yes(self) -> None:
        from clawgraph.db import GraphDB

        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")

        with patch("clawgraph.db.GraphDB", return_value=db):
            result = runner.invoke(app, ["delete", "Alice", "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_aborted(self) -> None:
        result = runner.invoke(app, ["delete", "Alice"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output


class TestClearCommand:
    """Tests for the clear subcommand."""

    def test_clear_with_yes(self) -> None:
        from clawgraph.db import GraphDB

        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        with patch("clawgraph.db.GraphDB", return_value=db):
            result = runner.invoke(app, ["clear", "--yes"])
        assert result.exit_code == 0
        assert "cleared" in result.output

    def test_clear_aborted(self) -> None:
        result = runner.invoke(app, ["clear"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output


class TestAuthErrorHandling:
    """Tests for better error messages on missing API keys."""

    def test_is_auth_error_detection(self) -> None:
        from clawgraph.cli import _is_auth_error

        assert _is_auth_error(Exception("AuthenticationError: invalid api key"))
        assert _is_auth_error(Exception("401 Unauthorized"))
        assert not _is_auth_error(Exception("timeout error"))
