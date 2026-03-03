"""Tests for source provenance tracking."""

from unittest.mock import MagicMock, patch

from clawgraph.db import GraphDB
from clawgraph.llm import build_merge_cypher
from clawgraph.memory import Memory


class TestProvenanceDB:
    """Tests for provenance columns in the database layer."""

    def test_relates_has_provenance_columns(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'A'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'B'}) SET e.label = 'Person'")
        db.execute(
            "MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
            "MERGE (a)-[r:Relates {type: 'KNOWS'}]->(b) "
            "SET r.source_agent = 'my-agent', "
            "r.source_session = 'sess-1', "
            "r.source_input = 'A knows B'"
        )
        rels = db.get_all_relationships()
        assert len(rels) == 1
        assert rels[0]["r.source_agent"] == "my-agent"
        assert rels[0]["r.source_session"] == "sess-1"
        assert rels[0]["r.source_input"] == "A knows B"

    def test_provenance_defaults_when_unset(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'X'}) SET e.label = 'Thing'")
        db.execute("MERGE (e:Entity {name: 'Y'}) SET e.label = 'Thing'")
        db.execute(
            "MATCH (a:Entity {name: 'X'}), (b:Entity {name: 'Y'}) "
            "MERGE (a)-[r:Relates {type: 'LINKS'}]->(b)"
        )
        rels = db.get_all_relationships()
        assert len(rels) == 1
        # Provenance columns exist but are not set
        assert "r.source_agent" in rels[0]
        assert "r.source_session" in rels[0]
        assert "r.source_input" in rels[0]

    def test_migration_adds_provenance_columns(self) -> None:
        """Simulate a DB created before provenance columns existed."""
        db = GraphDB(db_path=":memory:")
        # Create the old schema without provenance columns
        db.create_node_table(
            "Entity",
            {"name": "STRING", "label": "STRING",
             "created_at": "STRING", "updated_at": "STRING"},
        )
        db.create_rel_table(
            "Relates", "Entity", "Entity",
            {"type": "STRING", "created_at": "STRING"},
        )
        # Add data with old schema
        db.execute("MERGE (e:Entity {name: 'A'}) SET e.label = 'P'")
        db.execute("MERGE (e:Entity {name: 'B'}) SET e.label = 'P'")
        db.execute(
            "MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
            "MERGE (a)-[r:Relates {type: 'K'}]->(b)"
        )

        # Now run ensure_base_schema which triggers migration
        db.ensure_base_schema()

        # Old data should still be there
        rels = db.get_all_relationships()
        assert len(rels) == 1
        assert rels[0]["r.type"] == "K"
        # Provenance columns should exist with empty defaults
        assert rels[0]["r.source_agent"] == ""


class TestProvenanceCypher:
    """Tests for provenance in build_merge_cypher."""

    def test_cypher_includes_source_metadata(self) -> None:
        entities = [
            {"name": "John", "label": "Person"},
            {"name": "Acme", "label": "Organization"},
        ]
        relationships = [
            {"from": "John", "to": "Acme", "type": "WORKS_AT"},
        ]
        source = {"agent": "my-agent", "session": "abc123", "input": "John works at Acme"}
        cypher = build_merge_cypher(entities, relationships, source=source)

        assert "source_agent" in cypher
        assert "my-agent" in cypher
        assert "source_session" in cypher
        assert "abc123" in cypher
        assert "source_input" in cypher

    def test_cypher_without_source(self) -> None:
        entities = [{"name": "John", "label": "Person"}]
        relationships = [{"from": "John", "to": "John", "type": "SELF"}]
        cypher = build_merge_cypher(entities, relationships)
        assert "source_agent" not in cypher

    def test_cypher_partial_source(self) -> None:
        entities = []
        relationships = [{"from": "A", "to": "B", "type": "X"}]
        source = {"agent": "bot"}
        cypher = build_merge_cypher(entities, relationships, source=source)
        assert "source_agent" in cypher
        assert "bot" in cypher
        assert "source_session" not in cypher

    def test_cypher_escapes_source_values(self) -> None:
        entities = []
        relationships = [{"from": "A", "to": "B", "type": "X"}]
        source = {"agent": "O'Brien's agent"}
        cypher = build_merge_cypher(entities, relationships, source=source)
        assert "O\\'Brien" in cypher


class TestProvenanceMemory:
    """Tests for provenance in the Memory API."""

    @patch("clawgraph.llm.litellm")
    def test_add_with_source_stores_provenance(self, mock_litellm: MagicMock) -> None:
        json_resp = (
            '{"entities": [{"name": "John", "label": "Person"}, '
            '{"name": "Acme", "label": "Organization"}], '
            '"relationships": [{"from": "John", "to": "Acme", "type": "WORKS_AT"}]}'
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        mem = Memory(db_path=":memory:")
        result = mem.add(
            "John works at Acme",
            source={"agent": "my-agent", "session": "abc123"},
        )

        assert result.ok
        rels = mem.relationships()
        assert len(rels) == 1
        assert rels[0]["r.source_agent"] == "my-agent"
        assert rels[0]["r.source_session"] == "abc123"

    @patch("clawgraph.llm.litellm")
    def test_add_without_source(self, mock_litellm: MagicMock) -> None:
        json_resp = (
            '{"entities": [{"name": "A", "label": "X"}, {"name": "B", "label": "X"}], '
            '"relationships": [{"from": "A", "to": "B", "type": "REL"}]}'
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        mem = Memory(db_path=":memory:")
        result = mem.add("A relates to B")

        assert result.ok
        rels = mem.relationships()
        assert len(rels) == 1
        # Provenance columns exist but are not populated
        assert "r.source_agent" in rels[0]

    @patch("clawgraph.llm.litellm")
    def test_add_batch_with_source(self, mock_litellm: MagicMock) -> None:
        json_resp = (
            '{"entities": [{"name": "A", "label": "X"}, {"name": "B", "label": "X"}], '
            '"relationships": [{"from": "A", "to": "B", "type": "LINKS"}]}'
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        mem = Memory(db_path=":memory:")
        result = mem.add_batch(
            ["A links to B"],
            source={"agent": "batch-agent", "session": "s1"},
        )

        assert result.ok
        rels = mem.relationships()
        assert len(rels) == 1
        assert rels[0]["r.source_agent"] == "batch-agent"

    @patch("clawgraph.llm.litellm")
    def test_query_filters_by_source_agent(self, mock_litellm: MagicMock) -> None:
        # Set up two relationships from different agents
        json_resp1 = (
            '{"entities": [{"name": "A", "label": "X"}, {"name": "B", "label": "X"}], '
            '"relationships": [{"from": "A", "to": "B", "type": "R1"}]}'
        )
        json_resp2 = (
            '{"entities": [{"name": "C", "label": "X"}, {"name": "D", "label": "X"}], '
            '"relationships": [{"from": "C", "to": "D", "type": "R2"}]}'
        )
        mock_litellm.completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=json_resp1))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=json_resp2))]),
        ]

        mem = Memory(db_path=":memory:")
        mem.add("A relates to B", source={"agent": "agent-1"})
        mem.add("C relates to D", source={"agent": "agent-2"})

        results = mem.query("anything", source_agent="agent-1")
        assert len(results) == 1
        assert results[0]["r.source_agent"] == "agent-1"
        assert results[0]["a.name"] == "A"

    @patch("clawgraph.llm.litellm")
    def test_query_source_agent_no_match(self, mock_litellm: MagicMock) -> None:
        json_resp = (
            '{"entities": [{"name": "A", "label": "X"}, {"name": "B", "label": "X"}], '
            '"relationships": [{"from": "A", "to": "B", "type": "R"}]}'
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        mem = Memory(db_path=":memory:")
        mem.add("A relates to B", source={"agent": "agent-1"})

        results = mem.query("anything", source_agent="nonexistent")
        assert len(results) == 0

    @patch("clawgraph.llm.litellm")
    def test_export_includes_provenance(self, mock_litellm: MagicMock) -> None:
        json_resp = (
            '{"entities": [{"name": "A", "label": "X"}, {"name": "B", "label": "X"}], '
            '"relationships": [{"from": "A", "to": "B", "type": "REL"}]}'
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        mem = Memory(db_path=":memory:")
        mem.add("A relates to B", source={"agent": "export-agent", "session": "s1"})

        export = mem.export()
        rels = export["relationships"]
        assert len(rels) == 1
        assert rels[0]["r.source_agent"] == "export-agent"
        assert rels[0]["r.source_session"] == "s1"
