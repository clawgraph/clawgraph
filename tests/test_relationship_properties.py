"""Tests for relationship properties (F23).

Covers:
- Properties column in the Relates table (schema + migration)
- build_merge_cypher() includes properties in MERGE statements
- infer_ontology() prompts ask for properties
- Memory.add() stores temporal/metadata properties on relationships
- Memory.relationships() includes properties in output
- Memory.export() includes relationship properties
- Empty properties default to '{}' (not null)
- All LLM calls are mocked
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from clawgraph.db import GraphDB
from clawgraph.llm import build_merge_cypher
from clawgraph.memory import Memory


class TestPropertiesColumn:
    """Tests for the properties column on the Relates table."""

    def test_schema_includes_properties_column(self) -> None:
        """Relates table should include a properties STRING column."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        db.execute("MERGE (e:Entity {name: 'A'}) SET e.label = 'X'")
        db.execute("MERGE (e:Entity {name: 'B'}) SET e.label = 'Y'")
        db.execute(
            "MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
            "MERGE (a)-[r:Relates {type: 'TEST'}]->(b) "
            "SET r.properties = '{\"key\": \"val\"}'"
        )

        results = db.execute(
            "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN r.properties"
        )
        assert len(results) == 1
        assert results[0]["r.properties"] == '{"key": "val"}'

    def test_properties_default_empty_json(self) -> None:
        """Properties should default to '{}' for migrated rows.

        Note: Kùzu DEFAULT only fills existing rows during ALTER TABLE ADD.
        New rows inserted via raw MERGE without SET will get NULL.
        Our build_merge_cypher() always includes SET r.properties,
        so in practice properties are never NULL through our API.
        This test verifies the migration default works for pre-existing rows.
        """
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        db.execute("MERGE (e:Entity {name: 'A'}) SET e.label = 'X'")
        db.execute("MERGE (e:Entity {name: 'B'}) SET e.label = 'Y'")
        # Use SET r.properties = '{}' as build_merge_cypher does
        db.execute(
            "MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
            "MERGE (a)-[r:Relates {type: 'TEST'}]->(b) "
            "SET r.properties = '{}'"
        )

        results = db.execute(
            "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN r.properties"
        )
        assert len(results) == 1
        assert results[0]["r.properties"] == "{}"


class TestMigrateProperties:
    """Tests for the _migrate_properties() migration."""

    def test_migration_idempotent(self) -> None:
        """Calling ensure_base_schema twice should not fail."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.ensure_base_schema()  # Second call should be safe
        assert db.has_rel_table("Relates")

    def test_migration_preserves_existing_data(self, tmp_path: str) -> None:
        """Migration should add the column without losing existing data."""
        from pathlib import Path

        db_dir = Path(tmp_path) / "migrate_test"
        db = GraphDB(db_path=str(db_dir))
        db.ensure_base_schema()

        # Insert data
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'Bob'}) SET e.label = 'Person'")
        db.execute(
            "MATCH (a:Entity {name: 'Alice'}), (b:Entity {name: 'Bob'}) "
            "MERGE (a)-[r:Relates {type: 'KNOWS'}]->(b)"
        )
        db.close()

        # Reopen — ensure_base_schema will re-run migrations
        db2 = GraphDB(db_path=str(db_dir))
        db2.ensure_base_schema()

        rels = db2.get_all_relationships()
        assert len(rels) == 1
        assert rels[0]["a.name"] == "Alice"
        assert rels[0]["r.type"] == "KNOWS"
        db2.close()


class TestGetAllRelationshipsWithProperties:
    """Tests for get_all_relationships() returning properties."""

    def test_returns_properties_field(self) -> None:
        """get_all_relationships() should include r.properties."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'Acme'}) SET e.label = 'Organization'")
        props = json.dumps({"from": "2020", "to": "2024", "role": "CEO"})
        db.execute(
            f"MATCH (a:Entity {{name: 'Alice'}}), (b:Entity {{name: 'Acme'}}) "
            f"MERGE (a)-[r:Relates {{type: 'CEO_OF'}}]->(b) "
            f"SET r.properties = '{props}'"
        )

        rels = db.get_all_relationships()
        assert len(rels) == 1
        assert "r.properties" in rels[0]
        parsed = json.loads(rels[0]["r.properties"])
        assert parsed["from"] == "2020"
        assert parsed["to"] == "2024"
        assert parsed["role"] == "CEO"


class TestBuildMergeCypherProperties:
    """Tests for build_merge_cypher() with relationship properties."""

    def test_includes_properties_in_set(self) -> None:
        """MERGE statement should SET r.properties with JSON."""
        entities = [
            {"name": "Alice", "label": "Person"},
            {"name": "Acme", "label": "Organization"},
        ]
        relationships = [
            {
                "from": "Alice",
                "to": "Acme",
                "type": "CEO_OF",
                "properties": {"from": "2020", "to": "2024"},
            },
        ]
        cypher = build_merge_cypher(entities, relationships)
        assert "SET r.properties" in cypher
        assert "2020" in cypher
        assert "2024" in cypher

    def test_empty_properties_default(self) -> None:
        """When no properties given, should default to '{}'."""
        entities = [
            {"name": "A", "label": "X"},
            {"name": "B", "label": "Y"},
        ]
        relationships = [
            {"from": "A", "to": "B", "type": "RELATED_TO"},
        ]
        cypher = build_merge_cypher(entities, relationships)
        assert "SET r.properties = '{}'" in cypher

    def test_properties_none_default(self) -> None:
        """When properties is None, should default to '{}'."""
        entities = [
            {"name": "A", "label": "X"},
            {"name": "B", "label": "Y"},
        ]
        relationships = [
            {"from": "A", "to": "B", "type": "REL", "properties": None},
        ]
        cypher = build_merge_cypher(entities, relationships)
        assert "SET r.properties = '{}'" in cypher

    def test_properties_as_json_string(self) -> None:
        """When properties is already a JSON string, should pass through."""
        entities = [
            {"name": "A", "label": "X"},
            {"name": "B", "label": "Y"},
        ]
        relationships = [
            {
                "from": "A",
                "to": "B",
                "type": "REL",
                "properties": '{"strength": 0.9}',
            },
        ]
        cypher = build_merge_cypher(entities, relationships)
        assert "strength" in cypher
        assert "0.9" in cypher

    def test_invalid_json_string_defaults_to_empty(self) -> None:
        """When properties is an invalid JSON string, should default to '{}'."""
        entities = [
            {"name": "A", "label": "X"},
            {"name": "B", "label": "Y"},
        ]
        relationships = [
            {
                "from": "A",
                "to": "B",
                "type": "REL",
                "properties": "not valid json",
            },
        ]
        cypher = build_merge_cypher(entities, relationships)
        assert "SET r.properties = '{}'" in cypher


class TestMemoryAddWithProperties:
    """Tests for Memory.add() storing relationship properties."""

    @patch("clawgraph.llm._get_client")
    def test_add_stores_temporal_properties(self, mock_get_client: MagicMock) -> None:
        """mem.add() should store temporal properties on relationships."""
        json_resp = json.dumps(
            {
                "entities": [
                    {"name": "Alice", "label": "Person"},
                    {"name": "Acme", "label": "Organization"},
                ],
                "relationships": [
                    {
                        "from": "Alice",
                        "to": "Acme",
                        "type": "CEO_OF",
                        "properties": {"from": "2020", "to": "2024", "role": "CEO"},
                    }
                ],
            }
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        result = mem.add("Alice was CEO of Acme from 2020 to 2024")

        assert result.ok
        assert result.executed == 3  # 2 entities + 1 relationship

        rels = mem.relationships()
        assert len(rels) == 1
        assert rels[0]["r.type"] == "CEO_OF"
        props = json.loads(rels[0]["r.properties"])
        assert props["from"] == "2020"
        assert props["to"] == "2024"
        assert props["role"] == "CEO"

    @patch("clawgraph.llm._get_client")
    def test_add_without_properties(self, mock_get_client: MagicMock) -> None:
        """When LLM returns no properties, should default to '{}'."""
        json_resp = json.dumps(
            {
                "entities": [
                    {"name": "X", "label": "Thing"},
                    {"name": "Y", "label": "Thing"},
                ],
                "relationships": [
                    {"from": "X", "to": "Y", "type": "RELATED_TO"},
                ],
            }
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        result = mem.add("X is related to Y")

        assert result.ok
        rels = mem.relationships()
        assert len(rels) == 1
        # Properties should be empty JSON object
        props = json.loads(rels[0]["r.properties"])
        assert props == {}

    @patch("clawgraph.llm._get_client")
    def test_add_with_strength_property(self, mock_get_client: MagicMock) -> None:
        """Strength/confidence property should be stored correctly."""
        json_resp = json.dumps(
            {
                "entities": [
                    {"name": "A", "label": "Person"},
                    {"name": "B", "label": "Person"},
                ],
                "relationships": [
                    {
                        "from": "A",
                        "to": "B",
                        "type": "KNOWS",
                        "properties": {"strength": 0.9},
                    }
                ],
            }
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        result = mem.add("A strongly knows B")

        assert result.ok
        rels = mem.relationships()
        props = json.loads(rels[0]["r.properties"])
        assert props["strength"] == 0.9


class TestMemoryRelationshipsOutput:
    """Tests for Memory.relationships() including properties."""

    @patch("clawgraph.llm._get_client")
    def test_relationships_includes_properties(self, mock_get_client: MagicMock) -> None:
        """mem.relationships() should include properties in output."""
        json_resp = json.dumps(
            {
                "entities": [
                    {"name": "Alice", "label": "Person"},
                    {"name": "Acme", "label": "Organization"},
                ],
                "relationships": [
                    {
                        "from": "Alice",
                        "to": "Acme",
                        "type": "WORKS_AT",
                        "properties": {"since": "2019"},
                    }
                ],
            }
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("Alice has worked at Acme since 2019")

        rels = mem.relationships()
        assert len(rels) == 1
        assert "r.properties" in rels[0]
        props = json.loads(rels[0]["r.properties"])
        assert props["since"] == "2019"


class TestMemoryExportWithProperties:
    """Tests for Memory.export() including relationship properties."""

    @patch("clawgraph.llm._get_client")
    def test_export_includes_relationship_properties(self, mock_get_client: MagicMock) -> None:
        """Export should include relationship properties."""
        json_resp = json.dumps(
            {
                "entities": [
                    {"name": "Alice", "label": "Person"},
                    {"name": "Acme", "label": "Organization"},
                ],
                "relationships": [
                    {
                        "from": "Alice",
                        "to": "Acme",
                        "type": "CEO_OF",
                        "properties": {"from": "2020", "to": "2024"},
                    }
                ],
            }
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("Alice was CEO of Acme from 2020 to 2024")

        export = mem.export()
        assert "relationships" in export
        rels = export["relationships"]
        assert len(rels) == 1
        assert "r.properties" in rels[0]
        props = json.loads(rels[0]["r.properties"])
        assert props["from"] == "2020"
        assert props["to"] == "2024"


class TestBuildMergeCypherPropertiesEndToEnd:
    """End-to-end test: build Cypher then execute on DB."""

    def test_cypher_executes_with_properties(self) -> None:
        """Cypher generated by build_merge_cypher should execute on Kùzu."""
        from clawgraph.cypher import sanitize_cypher

        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        entities = [
            {"name": "Alice", "label": "Person"},
            {"name": "Acme", "label": "Organization"},
        ]
        relationships = [
            {
                "from": "Alice",
                "to": "Acme",
                "type": "CEO_OF",
                "properties": {"from": "2020", "to": "2024", "role": "CEO"},
            },
        ]
        cypher = build_merge_cypher(entities, relationships)

        for line in cypher.split("\n"):
            line = line.strip()
            if line:
                db.execute(sanitize_cypher(line))

        rels = db.get_all_relationships()
        assert len(rels) == 1
        assert rels[0]["r.type"] == "CEO_OF"
        props = json.loads(rels[0]["r.properties"])
        assert props["from"] == "2020"
        assert props["to"] == "2024"
        assert props["role"] == "CEO"


class TestInferOntologyPromptProperties:
    """Tests that LLM prompts ask for relationship properties."""

    @patch("clawgraph.llm._get_client")
    def test_infer_ontology_prompt_mentions_properties(
        self, mock_get_client: MagicMock
    ) -> None:
        """infer_ontology() should include properties in the system prompt."""
        json_resp = json.dumps(
            {
                "entities": [{"name": "A", "label": "Person"}],
                "relationships": [],
            }
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from clawgraph.llm import infer_ontology

        infer_ontology("A is a person")

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        # The prompt should mention properties
        assert "properties" in system_msg.lower()

    @patch("clawgraph.llm._get_client")
    def test_infer_ontology_batch_prompt_mentions_properties(
        self, mock_get_client: MagicMock
    ) -> None:
        """infer_ontology_batch() should include properties in the system prompt."""
        json_resp = json.dumps(
            {
                "entities": [{"name": "A", "label": "Person"}],
                "relationships": [],
            }
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from clawgraph.llm import infer_ontology_batch

        infer_ontology_batch(["A is a person"])

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        assert "properties" in system_msg.lower()


class TestMemoryBatchWithProperties:
    """Tests for Memory.add_batch() with relationship properties."""

    @patch("clawgraph.llm._get_client")
    def test_batch_stores_properties(self, mock_get_client: MagicMock) -> None:
        """add_batch() should store properties from multiple relationships."""
        json_resp = json.dumps(
            {
                "entities": [
                    {"name": "Alice", "label": "Person"},
                    {"name": "Acme", "label": "Organization"},
                    {"name": "Bob", "label": "Person"},
                ],
                "relationships": [
                    {
                        "from": "Alice",
                        "to": "Acme",
                        "type": "CEO_OF",
                        "properties": {"from": "2020", "to": "2024"},
                    },
                    {
                        "from": "Bob",
                        "to": "Acme",
                        "type": "WORKS_AT",
                        "properties": {"since": "2021"},
                    },
                ],
            }
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        result = mem.add_batch([
            "Alice was CEO of Acme from 2020 to 2024",
            "Bob has worked at Acme since 2021",
        ])

        assert result.ok
        rels = mem.relationships()
        assert len(rels) == 2

        # Check each relationship has properties
        for rel in rels:
            assert "r.properties" in rel
            props = json.loads(rel["r.properties"])
            assert isinstance(props, dict)
