"""Portable, strict schemas for the implemented Memory operations."""

import importlib.util
import inspect
import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from clawgraph.cli import app
from clawgraph.memory import Memory


def test_default_tool_definitions_match_callable_memory_arguments() -> None:
    assert importlib.util.find_spec("clawgraph.tools") is not None
    from clawgraph.tools import get_tool_definitions

    definitions = get_tool_definitions()
    assert json.loads(json.dumps(definitions)) == definitions
    samples = {
        "add": {"statement": "Alice works at Acme"},
        "add_batch": {"statements": ["Alice works at Acme"]},
        "query": {"question": "Who works at Acme?"},
        "recall": {"context": "deployment", "max_tokens": 1000, "hops": 1},
        "entities": {}, "relationships": {}, "export": {},
        "delete_entity": {"name": "Alice"},
        "retract": {"statement": "Alice works at Acme"},
        "update": {"old": "Alice works at Acme", "new": "Alice works at NewCo"},
    }
    assert [tool["name"] for tool in definitions] == list(samples)
    for tool in definitions:
        assert set(tool) == {"name", "description", "parameters"}
        assert isinstance(tool["description"], str) and tool["description"]
        if tool["name"] in ("delete_entity", "retract", "update"):
            assert "authorization" in tool["description"].lower()
        if tool["name"] == "delete_entity":
            assert "cascad" in tool["description"].lower()
        schema = tool["parameters"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        method = getattr(Memory, tool["name"])
        signature = inspect.signature(method)
        assert set(schema["properties"]) == set(signature.parameters) - {"self"}
        required = [
            name for name, param in signature.parameters.items()
            if name != "self" and param.default is inspect.Parameter.empty
        ]
        assert schema["required"] == required
        signature.bind(None, **samples[tool["name"]])
        signature.bind(None, **{
            name: samples[tool["name"]][name] for name in required
        })
        for name, prop in schema["properties"].items():
            if name in ("max_tokens", "hops"):
                assert prop["type"] == "integer"
                assert prop["default"] == signature.parameters[name].default
            elif name == "statements":
                assert prop["type"] == "array" and prop["items"] == {"type": "string"}
            else:
                assert prop["type"] == "string"
    recall = next(tool for tool in definitions if tool["name"] == "recall")
    assert recall["parameters"]["properties"]["max_tokens"]["minimum"] == 0
    assert recall["parameters"]["properties"]["hops"]["enum"] == [1, 2]


@pytest.mark.parametrize("format", ["openai", "anthropic"])
def test_provider_tool_envelopes_preserve_schemas(format: str) -> None:
    from clawgraph.tools import get_tool_definitions

    base = get_tool_definitions()
    actual = get_tool_definitions(format)
    assert len(actual) == len(base)
    for portable, provider in zip(base, actual):
        if format == "openai":
            assert provider == {"type": "function", "function": portable}
        else:
            assert provider == {
                "name": portable["name"], "description": portable["description"],
                "input_schema": portable["parameters"],
            }
    assert json.loads(json.dumps(actual)) == actual


@pytest.mark.parametrize("format", ["xml", "", "OPENAI", None, [], 3])
def test_unknown_tool_formats_are_rejected(format: object) -> None:
    from clawgraph.tools import get_tool_definitions

    with pytest.raises(ValueError, match="format"):
        get_tool_definitions(format)


@pytest.mark.parametrize("format", ["json-schema", "openai", "anthropic"])
@pytest.mark.parametrize("output", [None, "json", "human"])
def test_tools_cli_exports_consumable_json_without_memory_or_credentials(
    format: str, output: str | None,
) -> None:
    from clawgraph.tools import get_tool_definitions

    args = ["tools", "export", "--format", format]
    if output:
        args += ["--output", output]
    with (
        patch("clawgraph.memory.Memory", side_effect=AssertionError("Memory opened")),
        patch("clawgraph.db.GraphDB", side_effect=AssertionError("Database opened")),
        patch("clawgraph.llm._get_client", side_effect=AssertionError("LLM opened")),
        patch("clawgraph.config.load_config", side_effect=AssertionError("Config loaded")),
    ):
        result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == get_tool_definitions(format)


@pytest.mark.parametrize("format", ["json-schema", "openai", "anthropic"])
def test_tool_definitions_are_deeply_isolated_between_calls(format: str) -> None:
    from clawgraph.tools import get_tool_definitions

    baseline = get_tool_definitions(format)
    changed = get_tool_definitions(format)
    recall = changed[3]["function"] if format == "openai" else changed[3]
    schema_key = "input_schema" if format == "anthropic" else "parameters"
    recall[schema_key]["properties"]["hops"]["enum"].append(99)
    recall[schema_key]["required"].append("model")
    changed.pop()
    assert get_tool_definitions(format) == baseline
    assert get_tool_definitions()[3]["parameters"]["properties"]["hops"]["enum"] == [1, 2]


def test_tools_cli_defaults_to_json_schema_and_rejects_invalid_format() -> None:
    from clawgraph.tools import get_tool_definitions

    runner = CliRunner()
    result = runner.invoke(app, ["tools", "export"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == get_tool_definitions()
    invalid = runner.invoke(app, ["tools", "export", "--format", "xml"])
    assert invalid.exit_code == 2
    assert "Invalid value" in invalid.output
