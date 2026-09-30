"""Portable function definitions, without opening memory or executing tools."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ToolFormat(str, Enum):
    """Supported portable and provider-specific tool schema formats."""

    json_schema = "json-schema"
    openai = "openai"
    anthropic = "anthropic"


def get_tool_definitions(format: str = "json-schema") -> list[dict[str, Any]]:
    """Return fresh JSON-serializable definitions of implemented Memory tools.

    Args:
        format: Output format: json-schema, openai, or anthropic.

    Returns:
        Tool definitions with strict object schemas. Names match Memory methods;
        callers are responsible for explicitly binding and executing operations.

    Raises:
        ValueError: If format is not supported.
    """
    if not isinstance(format, str) or format not in tuple(ToolFormat):
        raise ValueError("Unsupported tool format; use json-schema, openai, or anthropic")
    operations: list[tuple[str, str, dict[str, Any], list[str]]] = [
        ("add", "Store one natural-language fact in graph memory.", {
            "statement": {"type": "string", "description": "Fact to store."},
        }, ["statement"]),
        ("add_batch", "Store multiple facts with one LLM extraction call.", {
            "statements": {"type": "array", "items": {"type": "string"},
                           "description": "Facts to store; an empty list is a no-op."},
        }, ["statements"]),
        ("query", "Query graph memory with a natural-language question.", {
            "question": {"type": "string", "description": "Question about stored facts."},
        }, ["question"]),
        ("recall", "Recall ranked, escaped fact lines for agent context injection.", {
            "context": {"type": "string", "description": "Context used to select relevant existing entities."},
            "max_tokens": {
                "type": "integer", "minimum": 0, "default": 2000,
                "description": "Conservative approximate budget (one UTF-8 byte per token); zero returns empty text.",
            },
            "hops": {"type": "integer", "enum": [1, 2], "default": 2,
                     "description": "Maximum neighborhood distance."},
        }, ["context"]),
        ("entities", "List all stored entities with their names and labels.", {}, []),
        ("relationships", "List all stored directed relationships.", {}, []),
        ("export", "Export entities, relationships, and ontology as a dictionary.", {}, []),
        ("delete_entity", "Delete an exact entity, cascading all incoming/outgoing relationships. Requires caller authorization.", {
            "name": {"type": "string", "minLength": 1, "description": "Exact nonempty entity name."},
        }, ["name"]),
        ("retract", "Atomically remove explicitly selected relationships, retaining entities. Requires caller authorization.", {
            "statement": {"type": "string", "minLength": 1, "description": "Nonempty fact to retract; ambiguous matches are a no-op."},
        }, ["statement"]),
        ("update", "Atomically correct existing relationships; unmatched old facts fail without writes. Requires caller authorization.", {
            "old": {"type": "string", "minLength": 1, "description": "Existing fact to replace."},
            "new": {"type": "string", "minLength": 1, "description": "Replacement fact containing at least one relationship."},
        }, ["old", "new"]),
    ]
    definitions = [
        {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object", "properties": properties,
                "required": required, "additionalProperties": False,
            },
        }
        for name, description, properties, required in operations
    ]
    if format == "openai":
        return [{"type": "function", "function": tool} for tool in definitions]
    if format == "anthropic":
        return [
            {"name": tool["name"], "description": tool["description"],
             "input_schema": tool["parameters"]}
            for tool in definitions
        ]
    return definitions
