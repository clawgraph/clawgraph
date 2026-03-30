"""Tests for confidence scoring on relationships."""

from unittest.mock import MagicMock, patch

from clawgraph.db import GraphDB
from clawgraph.llm import build_merge_cypher
from clawgraph.memory import Memory


class TestConfidenceSchema:
    """Tests for confidence column in Relates schema."""

    def test_relates_has_confidence_column(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'A'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'B'}) SET e.label = 'Person'")
        db.execute(
            "MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
            "MERGE (a)-[r:Relates {type: 'KNOWS'}]->(b) "
            "SET r.confidence = 0.85"
        )
        results = db.execute(
            "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN r.confidence"
        )
        assert len(results) == 1
        assert abs(results[0]["r.confidence"] - 0.85) < 0.001

    def test_confidence_defaults_to_1(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'A'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'B'}) SET e.label = 'Person'")
        db.execute(
            "MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
            "MERGE (a)-[r:Relates {type: 'KNOWS'}]->(b)"
        )
        results = db.execute(
            "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN r.confidence"
        )
        assert len(results) == 1
        assert abs(results[0]["r.confidence"] - 1.0) < 0.001

    def test_get_all_relationships_returns_confidence(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'A'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'B'}) SET e.label = 'Person'")
        db.execute(
            "MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
            "MERGE (a)-[r:Relates {type: 'KNOWS'}]->(b) "
            "SET r.confidence = 0.9"
        )
        rels = db.get_all_relationships()
        assert len(rels) == 1
        assert "r.confidence" in rels[0]
        assert abs(rels[0]["r.confidence"] - 0.9) < 0.001

    def test_migration_adds_confidence(self) -> None:
        """Verify ensure_base_schema is idempotent with confidence column."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.ensure_base_schema()  # Should not raise
        assert db.has_rel_table("Relates")


class TestBuildMergeCypherConfidence:
    """Tests for confidence in build_merge_cypher."""

    def test_includes_confidence_in_cypher(self) -> None:
        entities = [
            {"name": "John", "label": "Person"},
            {"name": "Acme", "label": "Organization"},
        ]
        relationships: list[dict[str, str]] = [
            {"from": "John", "to": "Acme", "type": "WORKS_AT", "confidence": "0.95"},
        ]
        cypher = build_merge_cypher(entities, relationships)
        assert "confidence" in cypher
        assert "0.95" in cypher

    def test_default_confidence_is_1(self) -> None:
        entities = [
            {"name": "A", "label": "Person"},
            {"name": "B", "label": "Person"},
        ]
        relationships = [
            {"from": "A", "to": "B", "type": "KNOWS"},
        ]
        cypher = build_merge_cypher(entities, relationships)
        assert "confidence" in cypher
        assert "1.0" in cypher


class TestLLMPromptConfidence:
    """Tests that LLM prompts include confidence instructions."""

    @patch("clawgraph.llm.litellm")
    def test_infer_ontology_prompt_mentions_confidence(
        self, mock_litellm: MagicMock
    ) -> None:
        from clawgraph.llm import infer_ontology

        json_resp = '{"entities": [{"name": "John", "label": "Person"}], "relationships": [{"from": "John", "to": "Acme", "type": "WORKS_AT", "confidence": 0.9}]}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        infer_ontology("John works at Acme")

        call_args = mock_litellm.completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        assert "confidence" in system_msg.lower()

    @patch("clawgraph.llm.litellm")
    def test_infer_ontology_batch_prompt_mentions_confidence(
        self, mock_litellm: MagicMock
    ) -> None:
        from clawgraph.llm import infer_ontology_batch

        json_resp = '{"entities": [{"name": "John", "label": "Person"}], "relationships": []}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        infer_ontology_batch(["John is a person"])

        call_args = mock_litellm.completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        assert "confidence" in system_msg.lower()


class TestMemoryQueryConfidenceFilter:
    """Tests for Memory.query() min_confidence filter."""

    @patch("clawgraph.llm.litellm")
    def test_query_filters_low_confidence(self, mock_litellm: MagicMock) -> None:
        # First call: infer_ontology for add (returns confidence)
        add_resp = '{"entities": [{"name": "A", "label": "Person"}, {"name": "B", "label": "Person"}, {"name": "C", "label": "Person"}], "relationships": [{"from": "A", "to": "B", "type": "KNOWS", "confidence": 0.9}, {"from": "A", "to": "C", "type": "KNOWS", "confidence": 0.5}]}'
        # Second call: generate_cypher for query (returns cypher that includes r.confidence)
        query_resp = "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN a.name, r.type, b.name, r.confidence"

        mock_litellm.completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=add_resp))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=query_resp))]),
        ]

        mem = Memory(db_path=":memory:")
        mem.add("A knows B and C")

        results = mem.query("Who does A know?", min_confidence=0.8)
        assert len(results) == 1
        assert results[0]["b.name"] == "B"

    @patch("clawgraph.llm.litellm")
    def test_query_no_filter_returns_all(self, mock_litellm: MagicMock) -> None:
        add_resp = '{"entities": [{"name": "X", "label": "Person"}, {"name": "Y", "label": "Person"}], "relationships": [{"from": "X", "to": "Y", "type": "KNOWS", "confidence": 0.3}]}'
        query_resp = "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN a.name, r.type, b.name, r.confidence"

        mock_litellm.completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=add_resp))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=query_resp))]),
        ]

        mem = Memory(db_path=":memory:")
        mem.add("X knows Y")

        results = mem.query("Who does X know?")
        assert len(results) == 1

    @patch("clawgraph.llm.litellm")
    def test_add_stores_confidence(self, mock_litellm: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "John", "label": "Person"}, {"name": "Acme", "label": "Organization"}], "relationships": [{"from": "John", "to": "Acme", "type": "WORKS_AT", "confidence": 0.85}]}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        mem = Memory(db_path=":memory:")
        result = mem.add("John probably works at Acme")

        assert result.ok
        rels = mem.relationships()
        assert len(rels) == 1
        assert abs(rels[0]["r.confidence"] - 0.85) < 0.001
