"""Tests for LLM integration layer."""

from unittest.mock import MagicMock, patch

from hypothesis import given
from hypothesis import strategies as st

from clawgraph.llm import LLMError, build_merge_cypher

SAFE_CYPHER_TEXT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-'",
    min_size=1,
    max_size=20,
)


class TestBuildMergeCypher:
    """Tests for build_merge_cypher."""

    def test_single_entity(self) -> None:
        entities = [{"name": "John", "label": "Person"}]
        cypher = build_merge_cypher(entities, [])
        assert "MERGE" in cypher
        assert "John" in cypher
        assert "Person" in cypher

    def test_entity_and_relationship(self) -> None:
        entities = [
            {"name": "John", "label": "Person"},
            {"name": "Acme", "label": "Organization"},
        ]
        relationships = [
            {"from": "John", "to": "Acme", "type": "WORKS_AT"},
        ]
        cypher = build_merge_cypher(entities, relationships)
        assert "MERGE" in cypher
        assert "John" in cypher
        assert "Acme" in cypher
        assert "WORKS_AT" in cypher

    def test_empty_input(self) -> None:
        cypher = build_merge_cypher([], [])
        assert cypher == ""

    def test_escapes_single_quotes(self) -> None:
        entities = [{"name": "O'Brien", "label": "Person"}]
        cypher = build_merge_cypher(entities, [])
        assert "O\\'Brien" in cypher

    def test_default_label(self) -> None:
        entities = [{"name": "Thing"}]
        cypher = build_merge_cypher(entities, [])
        assert "Unknown" in cypher

    def test_includes_updated_at_timestamp(self) -> None:
        entities = [{"name": "John", "label": "Person"}]
        cypher = build_merge_cypher(entities, [])
        assert "updated_at" in cypher
        # Timestamp should be ISO format with T separator
        assert "T" in cypher

    @given(
        entities=st.lists(
            st.fixed_dictionaries(
                {
                    "name": SAFE_CYPHER_TEXT,
                    "label": SAFE_CYPHER_TEXT,
                }
            ),
            min_size=1,
            max_size=5,
        ),
        relationships=st.lists(
            st.fixed_dictionaries(
                {
                    "from": SAFE_CYPHER_TEXT,
                    "to": SAFE_CYPHER_TEXT,
                    "type": SAFE_CYPHER_TEXT,
                }
            ),
            max_size=5,
        ),
    )
    def test_property_includes_schema_timestamps(
        self,
        entities: list[dict[str, str]],
        relationships: list[dict[str, str]],
    ) -> None:
        cypher = build_merge_cypher(entities, relationships)
        lines = [line for line in cypher.splitlines() if line.strip()]

        assert len(lines) == (2 * len(entities)) + (2 * len(relationships))

        entity_merge_lines = [
            line for line in lines if line.startswith("MERGE (e:Entity")
        ]
        entity_created_at_lines = [
            line
            for line in lines
            if line.startswith("MATCH (e:Entity") and "created_at" in line
        ]
        relationship_merge_lines = [
            line for line in lines if "MERGE (a)-[r:Relates" in line
        ]
        relationship_created_at_lines = [
            line for line in lines if "WHERE r.created_at" in line
        ]

        assert len(entity_merge_lines) == len(entities)
        assert len(entity_created_at_lines) == len(entities)
        assert len(relationship_merge_lines) == len(relationships)
        assert len(relationship_created_at_lines) == len(relationships)

        for line in entity_merge_lines:
            assert "updated_at" in line

        for line in entity_created_at_lines + relationship_created_at_lines:
            assert "created_at" in line


class TestGenerateCypher:
    """Tests for generate_cypher with mocked LLM."""

    @patch("clawgraph.llm._get_client")
    def test_returns_cypher(self, mock_get_client: MagicMock) -> None:
        from clawgraph.llm import generate_cypher

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="MERGE (e:Entity {name: 'Test'})"))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generate_cypher("Test fact")
        assert "MERGE" in result

    @patch("clawgraph.llm._get_client")
    def test_raises_on_empty(self, mock_get_client: MagicMock) -> None:
        from clawgraph.llm import generate_cypher

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=None))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        try:
            generate_cypher("Test fact")
            assert False, "Should have raised LLMError"
        except LLMError:
            pass

    @patch("clawgraph.llm._get_client")
    def test_raises_on_api_error(self, mock_get_client: MagicMock) -> None:
        from openai import APIConnectionError

        from clawgraph.llm import generate_cypher

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        mock_get_client.return_value = mock_client

        try:
            generate_cypher("Test fact")
            assert False, "Should have raised LLMError"
        except LLMError as e:
            assert "LLM call failed" in str(e)


class TestInferOntology:
    """Tests for infer_ontology with mocked LLM."""

    @patch("clawgraph.llm._get_client")
    def test_parses_json_response(self, mock_get_client: MagicMock) -> None:
        from clawgraph.llm import infer_ontology

        json_resp = '{"entities": [{"name": "John", "label": "Person"}], "relationships": []}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json_resp))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = infer_ontology("John is a person")
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "John"

    @patch("clawgraph.llm._get_client")
    def test_strips_code_fences(self, mock_get_client: MagicMock) -> None:
        from clawgraph.llm import infer_ontology

        json_resp = '```json\n{"entities": [{"name": "X", "label": "Y"}], "relationships": []}\n```'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json_resp))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = infer_ontology("X is a Y")
        assert len(result["entities"]) == 1

    @patch("clawgraph.llm._get_client")
    def test_raises_on_bad_json(self, mock_get_client: MagicMock) -> None:
        from clawgraph.llm import infer_ontology

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="not json at all"))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        try:
            infer_ontology("bad data")
            assert False, "Should have raised LLMError"
        except LLMError:
            pass
