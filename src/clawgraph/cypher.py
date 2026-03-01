"""Cypher query validation and safety checks."""

from __future__ import annotations

import re


# Patterns that should never appear in generated Cypher
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\bDROP\b", "DROP statements are not allowed"),
    (r"\bDELETE\s+DATABASE\b", "Database deletion is not allowed"),
    (r"\bCALL\s+dbms\b", "DBMS calls are not allowed"),
]

# Basic structural patterns that valid Cypher should match
_VALID_STARTS: list[str] = [
    "CREATE",
    "MERGE",
    "MATCH",
    "RETURN",
    "WITH",
    "CALL",
    "UNWIND",
]


def validate_cypher(cypher: str) -> CypherValidationResult:
    """Validate a Cypher query for safety and basic correctness.

    Args:
        cypher: The Cypher query to validate.

    Returns:
        CypherValidationResult with is_valid flag and any errors.
    """
    errors: list[str] = []

    if not cypher or not cypher.strip():
        return CypherValidationResult(is_valid=False, errors=["Empty query"])

    cleaned = cypher.strip()

    # Check for dangerous patterns
    for pattern, message in _DANGEROUS_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            errors.append(message)

    # Check for valid start keyword
    first_word = cleaned.split()[0].upper() if cleaned.split() else ""
    if first_word not in _VALID_STARTS:
        errors.append(
            f"Query starts with '{first_word}', expected one of: {', '.join(_VALID_STARTS)}"
        )

    # Check for balanced parentheses and brackets
    if cleaned.count("(") != cleaned.count(")"):
        errors.append("Unbalanced parentheses")
    if cleaned.count("[") != cleaned.count("]"):
        errors.append("Unbalanced brackets")
    if cleaned.count("{") != cleaned.count("}"):
        errors.append("Unbalanced braces")

    return CypherValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        query=cleaned,
    )


def sanitize_cypher(cypher: str) -> str:
    """Clean up a Cypher query from LLM output.

    Strips markdown code fences, leading/trailing whitespace,
    and trailing semicolons.

    Args:
        cypher: Raw Cypher string from LLM.

    Returns:
        Cleaned Cypher string.
    """
    cleaned = cypher.strip()

    # Remove markdown code fences
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```cypher or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Remove trailing semicolons (Kùzu doesn't need them)
    cleaned = cleaned.rstrip(";").strip()

    return cleaned


class CypherValidationResult:
    """Result of Cypher validation."""

    def __init__(
        self,
        is_valid: bool,
        errors: list[str] | None = None,
        query: str = "",
    ) -> None:
        self.is_valid = is_valid
        self.errors = errors or []
        self.query = query

    def __bool__(self) -> bool:
        return self.is_valid

    def __repr__(self) -> str:
        return f"CypherValidationResult(is_valid={self.is_valid}, errors={self.errors})"
