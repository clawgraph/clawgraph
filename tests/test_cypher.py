"""Tests for Cypher validation and sanitization."""

from clawgraph.cypher import sanitize_cypher, validate_cypher


class TestValidateCypher:
    """Tests for validate_cypher."""

    def test_valid_merge(self) -> None:
        result = validate_cypher("MERGE (p:Person {name: 'John'})")
        assert result.is_valid

    def test_valid_match(self) -> None:
        result = validate_cypher("MATCH (p:Person) RETURN p")
        assert result.is_valid

    def test_empty_query(self) -> None:
        result = validate_cypher("")
        assert not result.is_valid
        assert "Empty query" in result.errors

    def test_drop_blocked(self) -> None:
        result = validate_cypher("DROP TABLE Person")
        assert not result.is_valid
        assert any("DROP" in e for e in result.errors)

    def test_unbalanced_parens(self) -> None:
        result = validate_cypher("MATCH (p:Person RETURN p")
        assert not result.is_valid
        assert any("parentheses" in e for e in result.errors)

    def test_bool_conversion(self) -> None:
        valid = validate_cypher("MATCH (n) RETURN n")
        invalid = validate_cypher("")
        assert bool(valid) is True
        assert bool(invalid) is False


class TestSanitizeCypher:
    """Tests for sanitize_cypher."""

    def test_strips_whitespace(self) -> None:
        assert sanitize_cypher("  MATCH (n) RETURN n  ") == "MATCH (n) RETURN n"

    def test_removes_code_fences(self) -> None:
        raw = "```cypher\nMATCH (n) RETURN n\n```"
        assert sanitize_cypher(raw) == "MATCH (n) RETURN n"

    def test_removes_trailing_semicolon(self) -> None:
        assert sanitize_cypher("MATCH (n) RETURN n;") == "MATCH (n) RETURN n"

    def test_handles_plain_fences(self) -> None:
        raw = "```\nMATCH (n) RETURN n\n```"
        assert sanitize_cypher(raw) == "MATCH (n) RETURN n"
