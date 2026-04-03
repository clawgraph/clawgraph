"""Tests for CLI commands."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from clawgraph.cli import app

runner = CliRunner()


def _extract_json(output: str) -> dict:
    """Extract JSON object from mixed CLI output."""
    # Look for pretty-printed JSON starting with { on its own line
    lines = output.split("\n")
    json_start = None
    for i, line in enumerate(lines):
        if line.strip() == "{":
            json_start = i
            break
    assert json_start is not None, f"No JSON found in output: {output}"
    json_str = "\n".join(lines[json_start:])
    return json.loads(json_str)


class TestVersion:
    """Tests for version output."""

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "clawgraph" in result.output

    def test_short_version_flag(self) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "clawgraph" in result.output


class TestConfig:
    """Tests for config command."""

    def test_show_all_config(self) -> None:
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "llm" in result.output

    def test_get_config_value(self) -> None:
        result = runner.invoke(app, ["config", "llm.model"])
        assert result.exit_code == 0
        assert result.output.strip() != ""

    def test_get_missing_key(self) -> None:
        result = runner.invoke(app, ["config", "nonexistent.key"])
        assert result.exit_code == 0
        assert "not set" in result.output


class TestOntology:
    """Tests for ontology command."""

    def test_show_ontology(self) -> None:
        result = runner.invoke(app, ["ontology"])
        assert result.exit_code == 0

    def test_ontology_json_output(self) -> None:
        result = runner.invoke(app, ["ontology", "--output", "json"])
        assert result.exit_code == 0


class TestExport:
    """Tests for export command."""

    def test_export_stdout(self) -> None:
        result = runner.invoke(app, ["export"])
        assert result.exit_code == 0

    def test_export_json(self, tmp_path: object) -> None:
        out_file = str(tmp_path) + "/export.json"  # type: ignore[operator]
        result = runner.invoke(app, ["export", out_file])
        assert result.exit_code == 0


class TestAdd:
    """Tests for add command with mocked LLM."""

    @patch("clawgraph.llm.infer_ontology")
    @patch("clawgraph.llm.build_merge_cypher")
    @patch("clawgraph.db.GraphDB")
    def test_add_json_output(
        self,
        mock_db_cls: MagicMock,
        mock_build: MagicMock,
        mock_infer: MagicMock,
    ) -> None:
        mock_infer.return_value = {
            "entities": [{"name": "John", "label": "Person"}],
            "relationships": [],
        }
        mock_build.return_value = "MERGE (e:Entity {name: 'John'}) SET e.label = 'Person'"
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db

        result = runner.invoke(app, ["add", "John is a person", "--output", "json"])
        assert result.exit_code == 0
        parsed = _extract_json(result.output)
        assert parsed["status"] == "ok"
        assert len(parsed["entities"]) == 1

    @patch("clawgraph.llm.infer_ontology")
    def test_add_llm_error(self, mock_infer: MagicMock) -> None:
        from clawgraph.llm import LLMError

        mock_infer.side_effect = LLMError("API failed")
        result = runner.invoke(app, ["add", "test fact"])
        assert result.exit_code == 1


class TestAddBatch:
    """Tests for add-batch command with mocked LLM."""

    @patch("clawgraph.cli.Memory")
    def test_add_batch_json(self, mock_mem_cls: MagicMock) -> None:
        from clawgraph.memory import AddResult

        mock_mem = MagicMock()
        mock_mem.add_batch.return_value = AddResult(
            entities=[{"name": "Bob", "label": "Person"}],
            relationships=[],
            executed=1,
            errors=[],
        )
        mock_mem_cls.return_value = mock_mem

        result = runner.invoke(
            app, ["add-batch", "Bob is a person", "--output", "json"]
        )
        assert result.exit_code == 0


class TestQuery:
    """Tests for query command with mocked LLM."""

    @patch("clawgraph.db.GraphDB")
    @patch("clawgraph.llm.generate_cypher")
    def test_query_json_output(
        self, mock_gen: MagicMock, mock_db_cls: MagicMock
    ) -> None:
        mock_gen.return_value = "MATCH (e:Entity) RETURN e.name"
        mock_db = MagicMock()
        mock_db.execute.return_value = [{"e.name": "John"}]
        mock_db_cls.return_value = mock_db

        result = runner.invoke(
            app, ["query", "Who is John?", "--output", "json"]
        )
        assert result.exit_code == 0
        parsed = _extract_json(result.output)
        assert parsed["count"] == 1
