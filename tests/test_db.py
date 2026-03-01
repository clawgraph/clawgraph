"""Tests for the database layer."""

from clawgraph.db import DatabaseError, GraphDB


class TestGraphDB:
    """Tests for GraphDB using in-memory database."""

    def test_create_and_query(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.create_node_table("Entity", {"name": "STRING", "label": "STRING"})
        assert db.has_node_table("Entity")
        assert not db.has_node_table("NonExistent")

    def test_ensure_base_schema(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_node_table("Entity")
        assert db.has_rel_table("Relates")

    def test_ensure_base_schema_idempotent(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.ensure_base_schema()  # Should not raise
        assert db.has_node_table("Entity")

    def test_merge_entity(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'John'}) SET e.label = 'Person'")
        results = db.execute("MATCH (e:Entity) RETURN e.name, e.label")
        assert len(results) == 1
        assert results[0]["e.name"] == "John"
        assert results[0]["e.label"] == "Person"

    def test_merge_idempotent(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'John'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'John'}) SET e.label = 'Person'")
        results = db.execute("MATCH (e:Entity) RETURN e.name")
        assert len(results) == 1

    def test_relationship(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'John'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'Acme'}) SET e.label = 'Organization'")
        db.execute(
            "MATCH (a:Entity {name: 'John'}), (b:Entity {name: 'Acme'}) "
            "MERGE (a)-[r:Relates {type: 'WORKS_AT'}]->(b)"
        )
        results = db.execute(
            "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN a.name, r.type, b.name"
        )
        assert len(results) == 1
        assert results[0]["a.name"] == "John"
        assert results[0]["r.type"] == "WORKS_AT"
        assert results[0]["b.name"] == "Acme"

    def test_get_all_entities(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        entities = db.get_all_entities()
        assert len(entities) == 1
        assert entities[0]["e.name"] == "Alice"

    def test_get_all_relationships(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        db.execute("MERGE (e:Entity {name: 'Bob'}) SET e.label = 'Person'")
        db.execute(
            "MATCH (a:Entity {name: 'Alice'}), (b:Entity {name: 'Bob'}) "
            "MERGE (a)-[r:Relates {type: 'KNOWS'}]->(b)"
        )
        rels = db.get_all_relationships()
        assert len(rels) == 1

    def test_get_all_entities_empty(self) -> None:
        db = GraphDB(db_path=":memory:")
        assert db.get_all_entities() == []

    def test_database_error_on_bad_query(self) -> None:
        db = GraphDB(db_path=":memory:")
        try:
            db.execute("THIS IS NOT VALID CYPHER")
            assert False, "Should have raised DatabaseError"
        except DatabaseError:
            pass

    def test_create_rel_table(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.create_node_table("A", {"name": "STRING"})
        db.create_node_table("B", {"name": "STRING"})
        db.create_rel_table("LINKS", "A", "B")
        assert db.has_rel_table("LINKS")
        assert not db.has_rel_table("NonExistent")
