"""LLM integration layer — generates Cypher from natural language."""

from __future__ import annotations

from typing import Any

import litellm

from clawgraph.config import load_config


def generate_cypher(
    statement: str,
    ontology_context: str = "",
    model: str | None = None,
) -> str:
    """Convert a natural language statement into a Cypher query.

    Args:
        statement: Natural language input from the user.
        ontology_context: Current schema/ontology for context.
        model: LLM model to use. Defaults to config value.

    Returns:
        A Cypher query string.
    """
    config = load_config()
    model = model or config.get("llm", {}).get("model", "gpt-4")

    system_prompt = _build_system_prompt(ontology_context)

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": statement},
        ],
        temperature=0.0,
    )

    cypher = response.choices[0].message.content.strip()
    return cypher


def infer_ontology(
    statement: str,
    existing_ontology: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    """Infer node labels, relationship types, and properties from a statement.

    Args:
        statement: Natural language input to analyze.
        existing_ontology: Current schema for consistency.
        model: LLM model to use.

    Returns:
        Dict with 'nodes', 'relationships', and 'properties'.
    """
    config = load_config()
    model = model or config.get("llm", {}).get("model", "gpt-4")

    system_prompt = (
        "You are a graph ontology designer. Given a natural language statement, "
        "extract the node labels, relationship types, and properties needed to "
        "represent it in a graph database.\n\n"
        "Respond with valid JSON only:\n"
        '{"nodes": [{"label": "...", "properties": {"key": "type"}}], '
        '"relationships": [{"type": "...", "from": "...", "to": "...", '
        '"properties": {"key": "type"}}]}\n\n'
    )
    if existing_ontology:
        system_prompt += f"Existing ontology:\n{existing_ontology}\n\n"
        system_prompt += "Reuse existing labels and types where possible.\n"

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": statement},
        ],
        temperature=0.0,
    )

    import json

    try:
        return json.loads(response.choices[0].message.content.strip())
    except json.JSONDecodeError as e:
        raise LLMError(f"Failed to parse ontology response: {e}") from e


def _build_system_prompt(ontology_context: str) -> str:
    """Build the system prompt for Cypher generation."""
    prompt = (
        "You are a Cypher query generator for a Kùzu graph database. "
        "Given a natural language statement, generate a valid Cypher query "
        "to store or retrieve the information.\n\n"
        "Rules:\n"
        "- Output ONLY the Cypher query, no explanation\n"
        "- Use MERGE instead of CREATE to prevent duplicates\n"
        "- Use parameterized values where appropriate\n"
        "- Follow the existing ontology schema if provided\n\n"
    )
    if ontology_context:
        prompt += f"Current ontology:\n{ontology_context}\n"
    return prompt


class LLMError(Exception):
    """Raised when an LLM operation fails."""
