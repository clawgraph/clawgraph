"""Generate JSON Schema tool definitions for ClawGraph operations.

Exports tool definitions in OpenAI function-calling and Anthropic
tool-use formats for use with LLM tool/function calling APIs.
"""

from __future__ import annotations

from typing import Any


def _base_tool_definitions() -> list[dict[str, Any]]:
    """Return the canonical list of ClawGraph tool definitions.

    Each definition follows a neutral schema with name, description,
    and a JSON Schema ``parameters`` object.

    Returns:
        List of tool definition dicts.
    """
    return [
        {
            "name": "clawgraph_add",
            "description": (
                "Add a single fact or relationship to ClawGraph memory. "
                "The statement is parsed by an LLM to extract entities and "
                "relationships, which are then stored in the graph database."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": (
                            "Natural language statement describing a fact "
                            "or relationship (e.g., 'John works at Acme Corp')."
                        ),
                    },
                },
                "required": ["statement"],
            },
        },
        {
            "name": "clawgraph_query",
            "description": (
                "Query the ClawGraph memory using natural language. "
                "The question is converted to a Cypher query and executed "
                "against the graph database."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "Natural language question to query the graph "
                            "(e.g., 'Who works at Acme Corp?')."
                        ),
                    },
                },
                "required": ["question"],
            },
        },
        {
            "name": "clawgraph_export",
            "description": (
                "Export the full ClawGraph memory as a JSON object containing "
                "all entities, relationships, and the current ontology."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "clawgraph_add_batch",
            "description": (
                "Add multiple facts to ClawGraph memory in a single operation. "
                "All statements are processed in one LLM call, making this "
                "significantly faster than calling add repeatedly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "statements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of natural language statements to add "
                            "(e.g., ['Alice is a data scientist', "
                            "'Bob works at Netflix'])."
                        ),
                    },
                },
                "required": ["statements"],
            },
        },
    ]


def get_tool_definitions(fmt: str = "openai") -> list[dict[str, Any]]:
    """Get ClawGraph tool definitions in the specified format.

    Args:
        fmt: Output format — ``"openai"`` or ``"anthropic"``.

    Returns:
        List of tool definitions in the requested format.

    Raises:
        ValueError: If *fmt* is not a supported format.
    """
    base = _base_tool_definitions()

    if fmt == "openai":
        return _to_openai(base)
    elif fmt == "anthropic":
        return _to_anthropic(base)
    else:
        raise ValueError(f"Unsupported format: {fmt!r}. Use 'openai' or 'anthropic'.")


def _to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert base definitions to OpenAI function-calling format.

    Args:
        tools: Base tool definitions.

    Returns:
        OpenAI-formatted tool definitions.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in tools
    ]


def _to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert base definitions to Anthropic tool-use format.

    Args:
        tools: Base tool definitions.

    Returns:
        Anthropic-formatted tool definitions.
    """
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        }
        for tool in tools
    ]
