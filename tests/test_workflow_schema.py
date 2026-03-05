"""Tests for workflow schema creation, migration, and ontology registration."""

from pathlib import Path

from clawgraph.db import GraphDB
from clawgraph.ontology import Ontology

# ---------------------------------------------------------------------------
# DB schema — new database
# ---------------------------------------------------------------------------


class TestWorkflowSchemaCreation:
    """Workflow node/rel tables are created by ensure_base_schema()."""

    def test_workflow_node_table_exists(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_node_table("Workflow")

    def test_step_node_table_exists(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_node_table("Step")

    def test_tool_node_table_exists(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_node_table("Tool")

    def test_application_node_table_exists(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_node_table("Application")

    def test_has_step_rel_table_exists(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_rel_table("HAS_STEP")

    def test_used_tool_rel_table_exists(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_rel_table("USED_TOOL")

    def test_next_rel_table_exists(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_rel_table("NEXT")

    def test_accessed_app_rel_table_exists(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_rel_table("ACCESSED_APP")

    def test_ensure_base_schema_idempotent_with_workflow_tables(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.ensure_base_schema()  # Should not raise
        assert db.has_node_table("Workflow")
        assert db.has_rel_table("HAS_STEP")


# ---------------------------------------------------------------------------
# DB schema — workflow node properties
# ---------------------------------------------------------------------------


class TestWorkflowNodeProperties:
    """Workflow nodes can be merged with all required properties."""

    def test_workflow_node_merge(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute(
            "MERGE (w:Workflow {name: 'wf1'}) "
            "SET w.started_at = '2024-01-01T00:00:00+00:00', "
            "    w.status = 'running', w.step_count = 0, "
            "    w.total_duration_ms = 0"
        )
        rows = db.execute("MATCH (w:Workflow) RETURN w.name, w.status")
        assert len(rows) == 1
        assert rows[0]["w.name"] == "wf1"
        assert rows[0]["w.status"] == "running"

    def test_step_node_merge(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute(
            "MERGE (s:Step {id: 'step-001'}) "
            "SET s.tool_name = 'search', s.status = 'done', "
            "    s.order_index = 1, s.duration_ms = 42"
        )
        rows = db.execute("MATCH (s:Step) RETURN s.id, s.tool_name")
        assert len(rows) == 1
        assert rows[0]["s.id"] == "step-001"
        assert rows[0]["s.tool_name"] == "search"

    def test_tool_node_merge(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute(
            "MERGE (t:Tool {name: 'web_search'}) "
            "SET t.description = 'Searches the web'"
        )
        rows = db.execute("MATCH (t:Tool) RETURN t.name, t.description")
        assert len(rows) == 1
        assert rows[0]["t.name"] == "web_search"

    def test_application_node_merge(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute(
            "MERGE (a:Application {name: 'vscode'}) "
            "SET a.description = 'Code editor'"
        )
        rows = db.execute("MATCH (a:Application) RETURN a.name")
        assert len(rows) == 1
        assert rows[0]["a.name"] == "vscode"


# ---------------------------------------------------------------------------
# DB schema — relationships
# ---------------------------------------------------------------------------


class TestWorkflowRelationships:
    """Workflow relationship tables can be used to connect nodes."""

    def test_has_step_relationship(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (w:Workflow {name: 'wf1'})")
        db.execute("MERGE (s:Step {id: 'step-001'})")
        db.execute(
            "MATCH (w:Workflow {name: 'wf1'}), (s:Step {id: 'step-001'}) "
            "MERGE (w)-[:HAS_STEP]->(s)"
        )
        rows = db.execute(
            "MATCH (w:Workflow)-[:HAS_STEP]->(s:Step) RETURN w.name, s.id"
        )
        assert len(rows) == 1
        assert rows[0]["w.name"] == "wf1"
        assert rows[0]["s.id"] == "step-001"

    def test_used_tool_relationship(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (s:Step {id: 'step-001'})")
        db.execute("MERGE (t:Tool {name: 'search'})")
        db.execute(
            "MATCH (s:Step {id: 'step-001'}), (t:Tool {name: 'search'}) "
            "MERGE (s)-[:USED_TOOL]->(t)"
        )
        rows = db.execute(
            "MATCH (s:Step)-[:USED_TOOL]->(t:Tool) RETURN s.id, t.name"
        )
        assert len(rows) == 1

    def test_next_relationship(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (s1:Step {id: 'step-001'})")
        db.execute("MERGE (s2:Step {id: 'step-002'})")
        db.execute(
            "MATCH (s1:Step {id: 'step-001'}), (s2:Step {id: 'step-002'}) "
            "MERGE (s1)-[:NEXT]->(s2)"
        )
        rows = db.execute(
            "MATCH (s1:Step)-[:NEXT]->(s2:Step) RETURN s1.id, s2.id"
        )
        assert len(rows) == 1
        assert rows[0]["s1.id"] == "step-001"
        assert rows[0]["s2.id"] == "step-002"

    def test_accessed_app_relationship(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (s:Step {id: 'step-001'})")
        db.execute("MERGE (a:Application {name: 'vscode'})")
        db.execute(
            "MATCH (s:Step {id: 'step-001'}), (a:Application {name: 'vscode'}) "
            "MERGE (s)-[:ACCESSED_APP]->(a)"
        )
        rows = db.execute(
            "MATCH (s:Step)-[:ACCESSED_APP]->(a:Application) RETURN s.id, a.name"
        )
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Migration — existing DB is not affected
# ---------------------------------------------------------------------------


class TestWorkflowSchemaMigration:
    """Adding workflow tables to a pre-existing DB must not lose existing data."""

    def test_migration_does_not_lose_entity_data(self, tmp_path: Path) -> None:
        db_dir = tmp_path / "testdb"

        # Simulate an older DB that only has Entity/Relates
        db = GraphDB(db_path=str(db_dir))
        db.create_node_table(
            "Entity",
            {"name": "STRING", "label": "STRING", "created_at": "STRING", "updated_at": "STRING"},
        )
        db.create_rel_table(
            "Relates", "Entity", "Entity",
            {"type": "STRING", "created_at": "STRING"},
        )
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        db.close()

        # Re-open and call ensure_base_schema() (migration path)
        db2 = GraphDB(db_path=str(db_dir))
        db2.ensure_base_schema()

        # Existing entity must still be present
        entities = db2.get_all_entities()
        assert any(row["e.name"] == "Alice" for row in entities)

        # New workflow tables must now exist
        assert db2.has_node_table("Workflow")
        assert db2.has_node_table("Step")
        assert db2.has_node_table("Tool")
        assert db2.has_node_table("Application")
        assert db2.has_rel_table("HAS_STEP")
        assert db2.has_rel_table("USED_TOOL")
        assert db2.has_rel_table("NEXT")
        assert db2.has_rel_table("ACCESSED_APP")
        db2.close()

    def test_entity_relates_tables_still_exist_after_migration(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        assert db.has_node_table("Entity")
        assert db.has_rel_table("Relates")


# ---------------------------------------------------------------------------
# Ontology — register_workflow_defaults
# ---------------------------------------------------------------------------


class TestOntologyWorkflowDefaults:
    """register_workflow_defaults() populates the ontology correctly."""

    def test_workflow_node_registered(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        assert "Workflow" in ont.nodes

    def test_step_node_registered(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        assert "Step" in ont.nodes

    def test_tool_node_registered(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        assert "Tool" in ont.nodes

    def test_application_node_registered(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        assert "Application" in ont.nodes

    def test_has_step_rel_registered(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        assert "HAS_STEP" in ont.relationships
        assert ont.relationships["HAS_STEP"]["from"] == "Workflow"
        assert ont.relationships["HAS_STEP"]["to"] == "Step"

    def test_used_tool_rel_registered(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        assert "USED_TOOL" in ont.relationships
        assert ont.relationships["USED_TOOL"]["from"] == "Step"
        assert ont.relationships["USED_TOOL"]["to"] == "Tool"

    def test_next_rel_registered(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        assert "NEXT" in ont.relationships
        assert ont.relationships["NEXT"]["from"] == "Step"
        assert ont.relationships["NEXT"]["to"] == "Step"

    def test_accessed_app_rel_registered(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        assert "ACCESSED_APP" in ont.relationships
        assert ont.relationships["ACCESSED_APP"]["from"] == "Step"
        assert ont.relationships["ACCESSED_APP"]["to"] == "Application"

    def test_register_workflow_defaults_idempotent(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        ont.register_workflow_defaults()  # Should not raise or duplicate
        assert list(ont.nodes.keys()).count("Workflow") == 1

    def test_register_workflow_defaults_persists(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()

        ont2 = Ontology(config_dir=tmp_path)
        assert "Workflow" in ont2.nodes
        assert "HAS_STEP" in ont2.relationships


# ---------------------------------------------------------------------------
# Ontology — summary()
# ---------------------------------------------------------------------------


class TestOntologySummary:
    """Ontology.summary() returns correct structure and workflow types."""

    def test_summary_returns_dict(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        result = ont.summary()
        assert isinstance(result, dict)

    def test_summary_keys(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        result = ont.summary()
        assert "node_count" in result
        assert "relationship_count" in result
        assert "node_labels" in result
        assert "relationship_types" in result

    def test_summary_empty_ontology(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        result = ont.summary()
        assert result["node_count"] == 0
        assert result["relationship_count"] == 0
        assert result["node_labels"] == []
        assert result["relationship_types"] == []

    def test_summary_includes_workflow_types(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        result = ont.summary()
        assert "Workflow" in result["node_labels"]
        assert "Step" in result["node_labels"]
        assert "Tool" in result["node_labels"]
        assert "Application" in result["node_labels"]
        assert "HAS_STEP" in result["relationship_types"]
        assert "USED_TOOL" in result["relationship_types"]
        assert "NEXT" in result["relationship_types"]
        assert "ACCESSED_APP" in result["relationship_types"]

    def test_summary_counts(self, tmp_path: Path) -> None:
        ont = Ontology(config_dir=tmp_path)
        ont.register_workflow_defaults()
        result = ont.summary()
        assert result["node_count"] == 4
        assert result["relationship_count"] == 4
