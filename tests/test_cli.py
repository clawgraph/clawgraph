"""Tests for the CLI entry point."""

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from clawgraph.cli import OutputFormat, app

runner = CliRunner()


class TestCliAdd:
    """Tests for the add command."""

    def test_add_json_reports_logical_execution_count(self, tmp_path: Path) -> None:
        payload: dict[str, object] = {}

        inferred = {
            "entities": [
                {"name": "John", "label": "Person"},
                {"name": "Acme", "label": "Organization"},
            ],
            "relationships": [
                {"from": "John", "to": "Acme", "type": "WORKS_AT"},
            ],
        }

        def capture_output(data: dict[str, object], fmt: OutputFormat) -> None:
            assert fmt == OutputFormat.json
            payload.update(data)

        with (
            patch("clawgraph.llm.infer_ontology", return_value=inferred),
            patch(
                "clawgraph.config.load_config",
                return_value={"db": {"path": ":memory:"}, "llm": {}},
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("clawgraph.cli._output", side_effect=capture_output),
        ):
            result = runner.invoke(
                app,
                ["add", "John works at Acme", "--output", "json"],
            )

        assert result.exit_code == 0
        assert payload["executed"] == 3


class TestCliConfig:
    """Tests for the config command."""

    def test_config_supports_json_output_flag(self) -> None:
        payload: dict[str, object] = {}
        config_data = {
            "llm": {"model": "gpt-4o-mini", "temperature": 0.0},
            "output": {"format": "human"},
        }

        def capture_output(data: dict[str, object], fmt: OutputFormat) -> None:
            assert fmt == OutputFormat.json
            payload.update(data)

        with (
            patch("clawgraph.config.load_config", return_value=config_data),
            patch("clawgraph.cli._output", side_effect=capture_output),
        ):
            result = runner.invoke(app, ["config", "--output", "json"])

        assert result.exit_code == 0
        assert payload == config_data

    def test_config_key_returns_json_payload(self) -> None:
        payload: dict[str, object] = {}

        def capture_output(data: dict[str, object], fmt: OutputFormat) -> None:
            assert fmt == OutputFormat.json
            payload.update(data)

        with (
            patch("clawgraph.config.get_config_value", return_value="gpt-4o-mini"),
            patch("clawgraph.cli._output", side_effect=capture_output),
        ):
            result = runner.invoke(app, ["config", "llm.model", "--output", "json"])

        assert result.exit_code == 0
        assert payload == {"key": "llm.model", "value": "gpt-4o-mini"}

    def test_missing_config_key_returns_null_json_payload(self) -> None:
        payload: dict[str, object] = {}

        def capture_output(data: dict[str, object], fmt: OutputFormat) -> None:
            assert fmt == OutputFormat.json
            payload.update(data)

        with (
            patch("clawgraph.config.get_config_value", return_value=None),
            patch("clawgraph.cli._output", side_effect=capture_output),
        ):
            result = runner.invoke(app, ["config", "missing.key", "--output", "json"])

        assert result.exit_code == 0
        assert payload == {"key": "missing.key", "value": None}


class TestCliQuery:
    """Tests for the query command."""

    def test_query_json_uses_output_contract(self, tmp_path: Path) -> None:
        payload: dict[str, object] = {}
        cypher = "MATCH (e:Entity) RETURN e.name, e.label"
        rows = [{"e.name": "John", "e.label": "Person"}]

        def capture_output(data: dict[str, object], fmt: OutputFormat) -> None:
            assert fmt == OutputFormat.json
            payload.update(data)

        with (
            patch("clawgraph.llm.generate_cypher", return_value=cypher),
            patch(
                "clawgraph.config.load_config",
                return_value={"db": {"path": ":memory:"}, "llm": {}},
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("clawgraph.db.GraphDB.execute", return_value=rows),
            patch("clawgraph.cli._output", side_effect=capture_output),
        ):
            result = runner.invoke(app, ["query", "Who is John?", "--output", "json"])

        assert result.exit_code == 0
        assert payload == {"query": cypher, "results": rows, "count": 1}

    def test_query_exits_on_invalid_generated_cypher(self, tmp_path: Path) -> None:
        with (
            patch("clawgraph.llm.generate_cypher", return_value="DROP TABLE Person"),
            patch("pathlib.Path.home", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["query", "Do something unsafe"])

        assert result.exit_code == 1


class TestCliExport:
    """Tests for the export command."""

    def test_export_json_uses_output_contract_and_includes_ontology(
        self,
        tmp_path: Path,
    ) -> None:
        payload: dict[str, object] = {}

        def capture_output(data: dict[str, object], fmt: OutputFormat) -> None:
            assert fmt == OutputFormat.json
            payload.update(data)

        with (
            patch(
                "clawgraph.config.load_config",
                return_value={"db": {"path": ":memory:"}, "llm": {}},
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("clawgraph.cli._output", side_effect=capture_output),
        ):
            result = runner.invoke(app, ["export", "--output", "json"])

        assert result.exit_code == 0
        assert "entities" in payload
        assert "relationships" in payload
        assert "ontology" in payload

    def test_export_file_includes_ontology(self, tmp_path: Path) -> None:
        output_path = tmp_path / "graph.json"

        with (
            patch(
                "clawgraph.config.load_config",
                return_value={"db": {"path": ":memory:"}, "llm": {}},
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["export", str(output_path)])

        assert result.exit_code == 0
        exported = json.loads(output_path.read_text(encoding="utf-8"))
        assert "entities" in exported
        assert "relationships" in exported
        assert "ontology" in exported
