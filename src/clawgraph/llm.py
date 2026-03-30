"""LLM integration layer — generates Cypher from natural language.

Uses the OpenAI SDK directly (supports any OpenAI-compatible endpoint
via base_url config). Replaces the former litellm dependency.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, cast

from openai import OpenAI, OpenAIError

from clawgraph.config import load_config


def _load_dotenv() -> None:
    """Load .env file from cwd if present.

    .env values OVERRIDE system env vars so the project config wins.
    """
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and val:
                    os.environ[key] = val


_load_dotenv()


def _get_client() -> OpenAI:
    """Build an OpenAI client from config/env vars.

    Supports any OpenAI-compatible API by setting base_url in config
    or OPENAI_BASE_URL env var.

    Returns:
        Configured OpenAI client.

    Raises:
        LLMError: If no API key is found.
    """
    config = load_config()
    llm_config: dict[str, Any] = config.get("llm", {})

    api_key = os.environ.get("OPENAI_API_KEY") or llm_config.get("api_key")
    base_url = os.environ.get("OPENAI_BASE_URL") or llm_config.get("base_url")

    if not api_key:
        raise LLMError(
            "No API key found. Set OPENAI_API_KEY env var or "
            "configure llm.api_key in ~/.clawgraph/config.yaml"
        )

    return OpenAI(api_key=api_key, base_url=base_url)


def generate_cypher(
    statement: str,
    ontology_context: str = "",
    model: str | None = None,
    mode: str = "write",
) -> str:
    """Convert a natural language statement into a Cypher query.

    Args:
        statement: Natural language input from the user.
        ontology_context: Current schema/ontology for context.
        model: LLM model to use. Defaults to config value.
        mode: 'write' for MERGE/store, 'read' for MATCH/query.

    Returns:
        A Cypher query string.

    Raises:
        LLMError: If the LLM call fails or returns empty content.
    """
    config = load_config()
    model = model or config.get("llm", {}).get("model", "gpt-4o-mini")
    temperature = config.get("llm", {}).get("temperature", 0.0)

    system_prompt = _build_write_prompt(ontology_context) if mode == "write" else _build_read_prompt(ontology_context)

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": statement},
            ],
            temperature=temperature,
        )
    except OpenAIError as e:
        raise LLMError(f"LLM call failed: {e}") from e

    content: str | None = response.choices[0].message.content
    if not content:
        raise LLMError("LLM returned empty response")

    return content.strip()


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
        Dict with 'nodes' and 'relationships'.

    Raises:
        LLMError: If the LLM call fails or response is not valid JSON.
    """
    config = load_config()
    model = model or config.get("llm", {}).get("model", "gpt-4o-mini")

    system_prompt = (
        "You are a graph ontology designer for a Kùzu embedded graph database.\n"
        "Given a natural language statement, extract entities and relationships.\n\n"
        "IMPORTANT: We use a GENERIC schema:\n"
        "  - All entities are stored as Entity nodes with properties: name (STRING, PK), label (STRING)\n"
        "  - All relationships use Relates with property: type (STRING)\n\n"
        "Extract the entities and relationship from the statement.\n"
        "If ALLOWED labels or relationship types are specified below, you MUST only use those.\n"
        "Respond with ONLY valid JSON (no markdown fences):\n"
        "{\n"
        '  "entities": [\n'
        '    {"name": "actual name", "label": "Person|Organization|Place|etc"}\n'
        "  ],\n"
        '  "relationships": [\n'
        '    {"from": "entity name", "to": "entity name", "type": "WORKS_AT|KNOWS|etc"}\n'
        "  ]\n"
        "}\n\n"
    )
    if existing_ontology:
        system_prompt += f"Existing ontology:\n{existing_ontology}\n\n"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": statement},
            ],
            temperature=0.0,
        )
    except OpenAIError as e:
        raise LLMError(f"LLM call failed: {e}") from e

    content: str | None = response.choices[0].message.content
    if not content:
        raise LLMError("LLM returned empty response for ontology inference")

    # Strip code fences if present
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return cast(dict[str, Any], json.loads(cleaned))
    except json.JSONDecodeError as e:
        raise LLMError(f"Failed to parse ontology response: {e}\nRaw: {cleaned}") from e


def infer_ontology_batch(
    statements: list[str],
    existing_ontology: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    """Infer entities and relationships from multiple statements in one LLM call.

    This is much faster than calling infer_ontology() in a loop because
    it batches everything into a single API request.

    Args:
        statements: List of natural language statements.
        existing_ontology: Current schema for consistency.
        model: LLM model to use.

    Returns:
        Combined dict with 'entities' and 'relationships'.

    Raises:
        LLMError: If the LLM call fails or response is not valid JSON.
    """
    config = load_config()
    model = model or config.get("llm", {}).get("model", "gpt-4o-mini")

    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(statements))

    system_prompt = (
        "You are a graph ontology designer for a Kùzu embedded graph database.\n"
        "Given MULTIPLE natural language statements, extract ALL entities and relationships.\n\n"
        "IMPORTANT: We use a GENERIC schema:\n"
        "  - All entities are stored as Entity nodes with properties: name (STRING, PK), label (STRING)\n"
        "  - All relationships use Relates with property: type (STRING)\n\n"
        "Deduplicate entities — if the same entity appears in multiple statements, include it only once.\n"
        "If ALLOWED labels or relationship types are specified below, you MUST only use those.\n"
        "Respond with ONLY valid JSON (no markdown fences):\n"
        "{\n"
        '  "entities": [\n'
        '    {"name": "actual name", "label": "Person|Organization|Place|etc"}\n'
        "  ],\n"
        '  "relationships": [\n'
        '    {"from": "entity name", "to": "entity name", "type": "WORKS_AT|KNOWS|etc"}\n'
        "  ]\n"
        "}\n\n"
    )
    if existing_ontology:
        system_prompt += f"Existing ontology:\n{existing_ontology}\n\n"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": numbered},
            ],
            temperature=0.0,
        )
    except OpenAIError as e:
        raise LLMError(f"LLM call failed: {e}") from e

    content: str | None = response.choices[0].message.content
    if not content:
        raise LLMError("LLM returned empty response for batch ontology inference")

    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return cast(dict[str, Any], json.loads(cleaned))
    except json.JSONDecodeError as e:
        raise LLMError(f"Failed to parse batch ontology response: {e}\nRaw: {cleaned}") from e


def build_merge_cypher(entities: list[dict[str, str]], relationships: list[dict[str, str]]) -> str:
    """Build MERGE Cypher statements from extracted entities and relationships.

    This generates Kùzu-compatible MERGE queries using the generic
    Entity/Relates schema.

    Args:
        entities: List of dicts with 'name' and 'label'.
        relationships: List of dicts with 'from', 'to', and 'type'.

    Returns:
        Multi-line Cypher string with MERGE statements.
    """
    from clawgraph.db import GraphDB

    now = GraphDB.now_iso()
    lines: list[str] = []

    for entity in entities:
        name = entity["name"].replace("'", "\\'")
        label = entity.get("label", "Unknown").replace("'", "\\'")
        lines.append(
            f"MERGE (e:Entity {{name: '{name}'}}) "
            f"SET e.label = '{label}', e.updated_at = '{now}';"
        )

    for rel in relationships:
        from_name = rel["from"].replace("'", "\\'")
        to_name = rel["to"].replace("'", "\\'")
        rel_type = rel.get("type", "RELATED_TO").replace("'", "\\'")
        lines.append(
            f"MATCH (a:Entity {{name: '{from_name}'}}), (b:Entity {{name: '{to_name}'}}) "
            f"MERGE (a)-[r:Relates {{type: '{rel_type}'}}]->(b);"
        )

    return "\n".join(lines)


def _build_write_prompt(ontology_context: str) -> str:
    """Build the system prompt for Cypher write (MERGE) generation."""
    prompt = (
        "You are a Cypher query generator for a Kùzu embedded graph database.\n"
        "Given a natural language statement about facts or relationships,\n"
        "generate Cypher MERGE queries to store the information.\n\n"
        "CRITICAL RULES:\n"
        "- Output ONLY Cypher queries, no explanation or markdown fences\n"
        "- Use MERGE instead of CREATE to prevent duplicates\n"
        "- The database uses a GENERIC schema:\n"
        "  - Entity nodes: Entity(name STRING PRIMARY KEY, label STRING)\n"
        "  - Relationships: Relates(FROM Entity TO Entity, type STRING)\n"
        "- For entities: MERGE (e:Entity {name: 'Name'}) SET e.label = 'Type'\n"
        "- For relationships: First MATCH both entities, then MERGE the relationship\n"
        "  MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
        "MERGE (a)-[r:Relates {type: 'REL_TYPE'}]->(b)\n"
        "- Each statement should be on its own line ending with ;\n"
        "- Do NOT use CREATE NODE TABLE or CREATE REL TABLE\n"
        "- Do NOT use parameters ($param) — use literal string values\n\n"
    )
    if ontology_context:
        prompt += f"Current ontology:\n{ontology_context}\n"
    return prompt


def _build_read_prompt(ontology_context: str) -> str:
    """Build the system prompt for Cypher read (MATCH) generation."""
    prompt = (
        "You are a Cypher query generator for a Kùzu embedded graph database.\n"
        "Given a natural language question, generate a Cypher MATCH query\n"
        "to retrieve the requested information.\n\n"
        "CRITICAL RULES:\n"
        "- Output ONLY the Cypher query, no explanation or markdown fences\n"
        "- The database uses a GENERIC schema:\n"
        "  - Entity nodes: Entity(name STRING PRIMARY KEY, label STRING)\n"
        "  - Relationships: Relates(FROM Entity TO Entity, type STRING)\n"
        "- Use MATCH and RETURN\n"
        "- For finding entities: MATCH (e:Entity {label: 'Type'}) RETURN e.name, e.label\n"
        "- For finding relationships: MATCH (a:Entity)-[r:Relates]->(b:Entity) "
        "WHERE r.type = 'REL_TYPE' RETURN a.name, r.type, b.name\n"
        "- For general queries: MATCH (a:Entity)-[r:Relates]->(b:Entity) "
        "RETURN a.name, r.type, b.name\n"
        "- Do NOT use parameters ($param) — use literal string values\n"
        "- Output a single query only, no semicolons\n\n"
    )
    if ontology_context:
        prompt += f"Current ontology:\n{ontology_context}\n"
    return prompt


class LLMError(Exception):
    """Raised when an LLM operation fails."""
