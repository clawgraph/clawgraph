"""Tests for the CLI entry point."""

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
