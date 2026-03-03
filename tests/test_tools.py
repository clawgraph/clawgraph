"""Tests for tool-use function definitions."""

from __future__ import annotations

import json
import subprocess
import sys

from clawgraph.tools import get_tool_definitions

EXPECTED_TOOL_NAMES = [
    "clawgraph_add",
    "clawgraph_query",
    "clawgraph_export",
    "clawgraph_add_batch",
]


class TestOpenAIFormat:
    """Tests for OpenAI function-calling format."""

    def test_returns_list(self) -> None:
        tools = get_tool_definitions("openai")
        assert isinstance(tools, list)
        assert len(tools) == 4

    def test_tool_structure(self) -> None:
        tools = get_tool_definitions("openai")
        for tool in tools:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"

    def test_tool_names(self) -> None:
        tools = get_tool_definitions("openai")
        names = [t["function"]["name"] for t in tools]
        assert names == EXPECTED_TOOL_NAMES

    def test_add_has_required_statement(self) -> None:
        tools = get_tool_definitions("openai")
        add_tool = tools[0]["function"]
        assert add_tool["name"] == "clawgraph_add"
        params = add_tool["parameters"]
        assert "statement" in params["properties"]
        assert "statement" in params["required"]

    def test_query_has_required_question(self) -> None:
        tools = get_tool_definitions("openai")
        query_tool = tools[1]["function"]
        assert query_tool["name"] == "clawgraph_query"
        params = query_tool["parameters"]
        assert "question" in params["properties"]
        assert "question" in params["required"]

    def test_export_has_no_required_params(self) -> None:
        tools = get_tool_definitions("openai")
        export_tool = tools[2]["function"]
        assert export_tool["name"] == "clawgraph_export"
        assert export_tool["parameters"]["required"] == []

    def test_add_batch_has_required_statements(self) -> None:
        tools = get_tool_definitions("openai")
        batch_tool = tools[3]["function"]
        assert batch_tool["name"] == "clawgraph_add_batch"
        params = batch_tool["parameters"]
        assert "statements" in params["properties"]
        assert params["properties"]["statements"]["type"] == "array"
        assert "statements" in params["required"]


class TestAnthropicFormat:
    """Tests for Anthropic tool-use format."""

    def test_returns_list(self) -> None:
        tools = get_tool_definitions("anthropic")
        assert isinstance(tools, list)
        assert len(tools) == 4

    def test_tool_structure(self) -> None:
        tools = get_tool_definitions("anthropic")
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            # Anthropic format should NOT have "type": "function" wrapper
            assert "type" not in tool
            assert "function" not in tool

    def test_tool_names(self) -> None:
        tools = get_tool_definitions("anthropic")
        names = [t["name"] for t in tools]
        assert names == EXPECTED_TOOL_NAMES

    def test_add_has_required_statement(self) -> None:
        tools = get_tool_definitions("anthropic")
        add_tool = tools[0]
        assert add_tool["name"] == "clawgraph_add"
        schema = add_tool["input_schema"]
        assert "statement" in schema["properties"]
        assert "statement" in schema["required"]


class TestInvalidFormat:
    """Tests for unsupported format handling."""

    def test_raises_on_unknown_format(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Unsupported format"):
            get_tool_definitions("unknown")


class TestSchemaValidity:
    """Tests that generated schemas are valid JSON Schema."""

    def test_openai_serializes_to_json(self) -> None:
        tools = get_tool_definitions("openai")
        raw = json.dumps(tools)
        parsed = json.loads(raw)
        assert parsed == tools

    def test_anthropic_serializes_to_json(self) -> None:
        tools = get_tool_definitions("anthropic")
        raw = json.dumps(tools)
        parsed = json.loads(raw)
        assert parsed == tools

    def test_parameters_follow_json_schema_spec(self) -> None:
        """Verify parameter schemas have valid JSON Schema structure."""
        tools = get_tool_definitions("openai")
        for tool in tools:
            params = tool["function"]["parameters"]
            assert params["type"] == "object"
            assert isinstance(params["properties"], dict)
            assert isinstance(params["required"], list)
            for prop in params["properties"].values():
                assert "type" in prop
                assert "description" in prop


class TestCLIExport:
    """Tests for the CLI tools export command."""

    def test_cli_tools_export_openai(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "clawgraph", "tools", "export", "--format", "openai"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 4
        assert data[0]["type"] == "function"

    def test_cli_tools_export_anthropic(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "clawgraph", "tools", "export", "--format", "anthropic"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 4
        assert "input_schema" in data[0]

    def test_cli_tools_export_default_is_openai(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "clawgraph", "tools", "export"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data[0]["type"] == "function"
