"""Property-based tests for Cypher sanitization and validation."""

from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from clawgraph.cypher import sanitize_cypher, validate_cypher

SAFE_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + " _()[]{}:,\n\t",
    max_size=80,
)
WHITESPACE = st.text(alphabet=" \t\r\n", max_size=8)
DANGEROUS_QUERY = st.sampled_from(
    [
        "DROP TABLE Person",
        "delete database clawgraph",
        "CALL DBMS.SHOW_TABLES()",
    ]
)


class TestSanitizeCypherProperties:
    """Property tests for sanitize_cypher."""

    @given(raw=st.text())
    def test_property_sanitize_is_idempotent(self, raw: str) -> None:
        cleaned = sanitize_cypher(raw)
        assert sanitize_cypher(cleaned) == cleaned

    @given(inner=SAFE_TEXT, leading=WHITESPACE, trailing=WHITESPACE)
    def test_property_sanitize_removes_outer_formatting(
        self,
        inner: str,
        leading: str,
        trailing: str,
    ) -> None:
        raw = f"{leading}```cypher\n{inner}\n```;;;{trailing}"
        cleaned = sanitize_cypher(raw)

        assert "```" not in cleaned
        assert not cleaned.endswith(";")


class TestValidateCypherProperties:
    """Property tests for validate_cypher."""

    @given(query=DANGEROUS_QUERY, padding=WHITESPACE)
    def test_property_dangerous_queries_are_rejected(
        self,
        query: str,
        padding: str,
    ) -> None:
        result = validate_cypher(f"{padding}{query}{padding}")

        assert not result.is_valid
        assert result.errors
