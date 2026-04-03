"""Tests for the import CLI command."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from clawgraph.cli import app
from clawgraph.memory import AddResult

runner = CliRunner()


def _mock_add_result() -> AddResult:
    """Create a successful AddResult for mocking."""
    return AddResult(
        entities=[{"name": "John", "label": "Person"}],
        relationships=[{"from": "John", "to": "Acme", "type": "WORKS_AT"}],
        executed=2,
        errors=[],
    )


class TestImportPlainText:
    """Tests for importing plain text files."""

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_text_file(
        self, mock_init: MagicMock, mock_batch: MagicMock, tmp_path: MagicMock
    ) -> None:
        facts_file = tmp_path / "facts.txt"
        facts_file.write_text("John works at Acme\nAlice is a data scientist\n")

        mock_batch.return_value = _mock_add_result()

        result = runner.invoke(app, ["import", str(facts_file)])

        assert result.exit_code == 0
        mock_batch.assert_called_once_with(
            ["John works at Acme", "Alice is a data scientist"]
        )

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_text_skips_blank_lines(
        self, mock_init: MagicMock, mock_batch: MagicMock, tmp_path: MagicMock
    ) -> None:
        facts_file = tmp_path / "facts.txt"
        facts_file.write_text("John works at Acme\n\n\nAlice is a data scientist\n")

        mock_batch.return_value = _mock_add_result()

        result = runner.invoke(app, ["import", str(facts_file)])

        assert result.exit_code == 0
        mock_batch.assert_called_once_with(
            ["John works at Acme", "Alice is a data scientist"]
        )


class TestImportJSON:
    """Tests for importing JSON files."""

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_json_file(
        self, mock_init: MagicMock, mock_batch: MagicMock, tmp_path: MagicMock
    ) -> None:
        facts_file = tmp_path / "facts.json"
        facts = ["John works at Acme", "Alice is a data scientist"]
        facts_file.write_text(json.dumps(facts))

        mock_batch.return_value = _mock_add_result()

        result = runner.invoke(app, ["import", str(facts_file)])

        assert result.exit_code == 0
        mock_batch.assert_called_once_with(facts)

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_json_autodetect_from_content(
        self, mock_init: MagicMock, mock_batch: MagicMock, tmp_path: MagicMock
    ) -> None:
        """JSON is auto-detected when content starts with '['."""
        facts_file = tmp_path / "facts.dat"
        facts = ["John works at Acme"]
        facts_file.write_text(json.dumps(facts))

        mock_batch.return_value = _mock_add_result()

        result = runner.invoke(app, ["import", str(facts_file)])

        assert result.exit_code == 0
        mock_batch.assert_called_once_with(facts)

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_json_invalid(
        self, mock_init: MagicMock, mock_batch: MagicMock, tmp_path: MagicMock
    ) -> None:
        facts_file = tmp_path / "bad.json"
        facts_file.write_text("[invalid json")

        result = runner.invoke(app, ["import", str(facts_file)])

        assert result.exit_code != 0
        mock_batch.assert_not_called()


class TestImportStdin:
    """Tests for importing from stdin."""

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_stdin(
        self, mock_init: MagicMock, mock_batch: MagicMock
    ) -> None:
        mock_batch.return_value = _mock_add_result()

        result = runner.invoke(
            app, ["import", "-"], input="John works at Acme\nAlice is a data scientist\n"
        )

        assert result.exit_code == 0
        mock_batch.assert_called_once_with(
            ["John works at Acme", "Alice is a data scientist"]
        )

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_stdin_json(
        self, mock_init: MagicMock, mock_batch: MagicMock
    ) -> None:
        facts = ["John works at Acme", "Alice is a data scientist"]
        mock_batch.return_value = _mock_add_result()

        result = runner.invoke(app, ["import", "-"], input=json.dumps(facts))

        assert result.exit_code == 0
        mock_batch.assert_called_once_with(facts)


class TestImportOutputFormat:
    """Tests for --output json support."""

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_json_output(
        self, mock_init: MagicMock, mock_batch: MagicMock, tmp_path: MagicMock
    ) -> None:
        facts_file = tmp_path / "facts.txt"
        facts_file.write_text("John works at Acme\n")

        mock_batch.return_value = _mock_add_result()

        result = runner.invoke(app, ["import", str(facts_file), "--output", "json"])

        assert result.exit_code == 0
        # Extract JSON from output (stderr progress messages may precede it)
        output = result.output
        json_start = output.index("{")
        data = json.loads(output[json_start:])
        assert data["imported"] == 1
        assert data["ok"] is True


class TestImportEdgeCases:
    """Tests for edge cases."""

    def test_import_file_not_found(self) -> None:
        result = runner.invoke(app, ["import", "/nonexistent/file.txt"])

        assert result.exit_code != 0

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_empty_file(
        self, mock_init: MagicMock, mock_batch: MagicMock, tmp_path: MagicMock
    ) -> None:
        facts_file = tmp_path / "empty.txt"
        facts_file.write_text("")

        result = runner.invoke(app, ["import", str(facts_file)])

        assert result.exit_code != 0
        mock_batch.assert_not_called()

    @patch("clawgraph.memory.Memory.add_batch")
    @patch("clawgraph.memory.Memory.__init__", return_value=None)
    def test_import_json_not_array(
        self, mock_init: MagicMock, mock_batch: MagicMock, tmp_path: MagicMock
    ) -> None:
        facts_file = tmp_path / "bad.json"
        facts_file.write_text('{"key": "value"}')

        result = runner.invoke(app, ["import", str(facts_file)])

        assert result.exit_code != 0
        mock_batch.assert_not_called()
