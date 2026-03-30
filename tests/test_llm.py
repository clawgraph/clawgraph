"""Tests for LLM integration layer."""

from unittest.mock import MagicMock, patch

from clawgraph.llm import LLMError, build_merge_cypher


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
