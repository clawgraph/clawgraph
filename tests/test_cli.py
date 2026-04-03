"""Tests for CLI commands (stats, clear, API key errors)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from clawgraph.cli import app

runner = CliRunner()


class TestStatsCommand:
    """Tests for the stats command."""

    @patch("clawgraph.db.GraphDB")
    def test_stats_empty_db(self, mock_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_entity_count.return_value = 0
        mock_db.get_relationship_count.return_value = 0
        mock_db.get_label_distribution.return_value = []
        mock_db.get_relationship_type_distribution.return_value = []

        result = runner.invoke(app, ["stats", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["entity_count"] == 0
        assert data["relationship_count"] == 0
        assert data["label_distribution"] == {}
        assert data["relationship_type_distribution"] == {}

    @patch("clawgraph.db.GraphDB")
    def test_stats_with_data(self, mock_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_entity_count.return_value = 3
        mock_db.get_relationship_count.return_value = 2
        mock_db.get_label_distribution.return_value = [
            {"label": "Person", "count": 2},
            {"label": "Organization", "count": 1},
        ]
        mock_db.get_relationship_type_distribution.return_value = [
            {"type": "WORKS_AT", "count": 1},
            {"type": "KNOWS", "count": 1},
        ]

        result = runner.invoke(app, ["stats", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["entity_count"] == 3
        assert data["relationship_count"] == 2
        assert data["label_distribution"]["Person"] == 2
        assert data["label_distribution"]["Organization"] == 1
        assert data["relationship_type_distribution"]["WORKS_AT"] == 1
        assert data["relationship_type_distribution"]["KNOWS"] == 1

    @patch("clawgraph.db.GraphDB")
    def test_stats_human_output(self, mock_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_entity_count.return_value = 5
        mock_db.get_relationship_count.return_value = 3
        mock_db.get_label_distribution.return_value = [
            {"label": "Person", "count": 5},
        ]
        mock_db.get_relationship_type_distribution.return_value = [
            {"type": "KNOWS", "count": 3},
        ]

        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        # Human output goes to stderr console, but tables go to stdout
        # Just verify it doesn't crash


class TestClearCommand:
    """Tests for the clear command."""

    @patch("clawgraph.db.GraphDB")
    def test_clear_with_confirmation(self, mock_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.clear_all.return_value = {
            "entities_deleted": 5,
            "relationships_deleted": 3,
        }

        result = runner.invoke(app, ["clear"], input="y\n")
        assert result.exit_code == 0
        mock_db.clear_all.assert_called_once()

    @patch("clawgraph.db.GraphDB")
    def test_clear_aborted(self, mock_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db

        result = runner.invoke(app, ["clear"], input="n\n")
        assert result.exit_code != 0
        mock_db.clear_all.assert_not_called()

    @patch("clawgraph.db.GraphDB")
    def test_clear_with_yes_flag(self, mock_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.clear_all.return_value = {
            "entities_deleted": 2,
            "relationships_deleted": 1,
        }

        result = runner.invoke(app, ["clear", "--yes"])
        assert result.exit_code == 0
        mock_db.clear_all.assert_called_once()

    @patch("clawgraph.db.GraphDB")
    def test_clear_json_output(self, mock_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.clear_all.return_value = {
            "entities_deleted": 4,
            "relationships_deleted": 2,
        }

        result = runner.invoke(app, ["clear", "--yes", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["entities_deleted"] == 4
        assert data["relationships_deleted"] == 2


class TestApiKeyError:
    """Tests for API key error handling in add and query commands."""

    @patch("clawgraph.llm._get_client")
    @patch("clawgraph.ontology.Ontology")
    def test_add_shows_api_key_help(
        self, mock_ont_cls: MagicMock, mock_get_client: MagicMock
    ) -> None:
        from clawgraph.llm import LLMError

        mock_ont = MagicMock()
        mock_ont_cls.return_value = mock_ont
        mock_ont.to_context_string.return_value = ""

        mock_get_client.side_effect = LLMError(
            "No API key found. Set OPENAI_API_KEY env var or "
            "configure llm.api_key in ~/.clawgraph/config.yaml"
        )

        result = runner.invoke(app, ["add", "John works at Acme"])
        assert result.exit_code == 1
        assert "API Key Required" in result.output

    @patch("clawgraph.llm._get_client")
    @patch("clawgraph.ontology.Ontology")
    def test_query_shows_api_key_help(
        self, mock_ont_cls: MagicMock, mock_get_client: MagicMock
    ) -> None:
        from clawgraph.llm import LLMError

        mock_ont = MagicMock()
        mock_ont_cls.return_value = mock_ont
        mock_ont.to_context_string.return_value = ""

        mock_get_client.side_effect = LLMError(
            "No API key found. Set OPENAI_API_KEY env var or "
            "configure llm.api_key in ~/.clawgraph/config.yaml"
        )

        result = runner.invoke(app, ["query", "Where does John work?"])
        assert result.exit_code == 1
        assert "API Key Required" in result.output

    @patch("clawgraph.llm._get_client")
    @patch("clawgraph.ontology.Ontology")
    def test_add_shows_generic_error_for_other_llm_errors(
        self, mock_ont_cls: MagicMock, mock_get_client: MagicMock
    ) -> None:
        from clawgraph.llm import LLMError

        mock_ont = MagicMock()
        mock_ont_cls.return_value = mock_ont
        mock_ont.to_context_string.return_value = ""

        mock_get_client.side_effect = LLMError("LLM call failed: timeout")

        result = runner.invoke(app, ["add", "John works at Acme"])
        assert result.exit_code == 1
        assert "API Key Required" not in result.output


class TestStatsIntegration:
    """Integration tests for stats using real in-memory DB."""

    def test_stats_with_real_db(self) -> None:
        from clawgraph.db import GraphDB

        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'Acme'}) SET e.label = 'Organization'")
        db.execute(
            "MATCH (a:Entity {name: 'Alice'}), (b:Entity {name: 'Acme'}) "
            "MERGE (a)-[r:Relates {type: 'WORKS_AT'}]->(b)"
        )

        assert db.get_entity_count() == 2
        assert db.get_relationship_count() == 1

        labels = db.get_label_distribution()
        assert len(labels) == 2
        label_map = {r["label"]: int(r["count"]) for r in labels}
        assert label_map["Person"] == 1
        assert label_map["Organization"] == 1

        rel_types = db.get_relationship_type_distribution()
        assert len(rel_types) == 1
        assert rel_types[0]["type"] == "WORKS_AT"
        assert int(rel_types[0]["count"]) == 1


class TestClearIntegration:
    """Integration tests for clear using real in-memory DB."""

    def test_clear_removes_all_data(self) -> None:
        from clawgraph.db import GraphDB

        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'Bob'}) SET e.label = 'Person'")
        db.execute(
            "MATCH (a:Entity {name: 'Alice'}), (b:Entity {name: 'Bob'}) "
            "MERGE (a)-[r:Relates {type: 'KNOWS'}]->(b)"
        )

        result = db.clear_all()
        assert result["entities_deleted"] == 2
        assert result["relationships_deleted"] == 1
        assert db.get_entity_count() == 0
        assert db.get_relationship_count() == 0

    def test_clear_empty_db(self) -> None:
        from clawgraph.db import GraphDB

        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        result = db.clear_all()
        assert result["entities_deleted"] == 0
        assert result["relationships_deleted"] == 0
