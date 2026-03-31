"""Tests for delete, retract, and update functionality."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from clawgraph.cli import app
from clawgraph.db import GraphDB
from clawgraph.memory import AddResult, DeleteResult, Memory, UpdateResult

# ---------------------------------------------------------------------------
# Helper to populate a DB with test data (no LLM calls needed)
# ---------------------------------------------------------------------------

def _seed_graph(db: GraphDB) -> None:
    """Insert Alice→Acme (WORKS_AT) and Alice→Bob (KNOWS) into the DB."""
    db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
    db.execute("MERGE (e:Entity {name: 'Bob'}) SET e.label = 'Person'")
    db.execute("MERGE (e:Entity {name: 'Acme'}) SET e.label = 'Organization'")
    db.execute(
        "MATCH (a:Entity {name: 'Alice'}), (b:Entity {name: 'Acme'}) "
        "MERGE (a)-[r:Relates {type: 'WORKS_AT'}]->(b)"
    )
    db.execute(
        "MATCH (a:Entity {name: 'Alice'}), (b:Entity {name: 'Bob'}) "
        "MERGE (a)-[r:Relates {type: 'KNOWS'}]->(b)"
    )


# ===========================================================================
# DB-layer tests (no LLM, no Memory)
# ===========================================================================


class TestDBDeleteEntity:
    """Tests for GraphDB.delete_entity()."""

    def test_delete_existing_entity(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _seed_graph(db)

        assert db.delete_entity("Alice") is True
        assert db.get_all_entities() == [
            {"e.name": "Bob", "e.label": "Person"},
            {"e.name": "Acme", "e.label": "Organization"},
        ]

    def test_cascade_deletes_relationships(self) -> None:
        """DETACH DELETE should remove relationships connected to the entity."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _seed_graph(db)

        db.delete_entity("Alice")
        rels = db.get_all_relationships()
        assert len(rels) == 0  # both Alice→Acme and Alice→Bob gone

    def test_delete_nonexistent_entity(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        assert db.delete_entity("Ghost") is False

    def test_delete_entity_no_schema(self) -> None:
        """delete_entity on a DB with no Entity table returns False."""
        db = GraphDB(db_path=":memory:")
        assert db.delete_entity("Ghost") is False


class TestDBDeleteRelationship:
    """Tests for GraphDB.delete_relationship()."""

    def test_delete_existing_relationship(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _seed_graph(db)

        assert db.delete_relationship("Alice", "Acme", "WORKS_AT") is True
        rels = db.get_all_relationships()
        assert len(rels) == 1
        assert rels[0]["r.type"] == "KNOWS"

    def test_entities_intact_after_rel_delete(self) -> None:
        """Deleting a relationship should NOT delete the connected entities."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _seed_graph(db)

        db.delete_relationship("Alice", "Acme", "WORKS_AT")
        entities = db.get_all_entities()
        names = {e["e.name"] for e in entities}
        assert names == {"Alice", "Bob", "Acme"}

    def test_delete_nonexistent_relationship(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _seed_graph(db)

        assert db.delete_relationship("Alice", "Bob", "MARRIED_TO") is False

    def test_delete_relationship_no_schema(self) -> None:
        db = GraphDB(db_path=":memory:")
        assert db.delete_relationship("X", "Y", "Z") is False


# ===========================================================================
# Memory-layer tests (mocked LLM)
# ===========================================================================


class TestMemoryDeleteEntity:
    """Tests for Memory.delete_entity()."""

    def test_delete_entity_removes_entity_and_rels(self) -> None:
        mem = Memory(db_path=":memory:")
        _seed_graph(mem._db)

        result = mem.delete_entity("Alice")
        assert result.ok
        assert "Alice" in result.deleted_entities
        assert mem.entities() == [
            {"e.name": "Bob", "e.label": "Person"},
            {"e.name": "Acme", "e.label": "Organization"},
        ]
        assert mem.relationships() == []

    def test_delete_entity_not_found(self) -> None:
        mem = Memory(db_path=":memory:")
        result = mem.delete_entity("Ghost")
        assert not result.ok
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]


class TestMemoryRetract:
    """Tests for Memory.retract() with mocked LLM."""

    @patch("clawgraph.llm._get_client")
    def test_retract_removes_relationship(self, mock_get_client: MagicMock) -> None:
        """retract('Alice works at Acme') should remove the WORKS_AT edge."""
        retract_resp = (
            '{"relationships": [{"from": "Alice", "to": "Acme", "type": "WORKS_AT"}],'
            ' "entities": []}'
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=retract_resp))]
        )
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        _seed_graph(mem._db)

        result = mem.retract("Alice works at Acme")
        assert result.ok
        assert len(result.deleted_relationships) == 1
        assert "WORKS_AT" in result.deleted_relationships[0]

        # Alice→Bob (KNOWS) should still exist
        rels = mem.relationships()
        assert len(rels) == 1
        assert rels[0]["r.type"] == "KNOWS"

    @patch("clawgraph.llm._get_client")
    def test_retract_relationship_not_found(self, mock_get_client: MagicMock) -> None:
        retract_resp = (
            '{"relationships": [{"from": "Alice", "to": "Mars", "type": "LIVES_ON"}],'
            ' "entities": []}'
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=retract_resp))]
        )
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        _seed_graph(mem._db)

        result = mem.retract("Alice lives on Mars")
        assert not result.ok
        assert len(result.errors) == 1

    @patch("clawgraph.llm._get_client")
    def test_retract_incomplete_target(self, mock_get_client: MagicMock) -> None:
        """If LLM returns a relationship missing a field, we record an error."""
        retract_resp = '{"relationships": [{"from": "Alice", "to": "", "type": "WORKS_AT"}], "entities": []}'
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=retract_resp))]
        )
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        _seed_graph(mem._db)

        result = mem.retract("Alice works at ???")
        assert not result.ok
        assert any("Incomplete" in e for e in result.errors)


class TestMemoryUpdate:
    """Tests for Memory.update() with mocked LLM."""

    @patch("clawgraph.llm._get_client")
    def test_update_replaces_fact(self, mock_get_client: MagicMock) -> None:
        """update('Alice works at Acme', 'Alice works at NewCo') should
        remove WORKS_AT→Acme and add WORKS_AT→NewCo."""
        retract_resp = (
            '{"relationships": [{"from": "Alice", "to": "Acme", "type": "WORKS_AT"}],'
            ' "entities": []}'
        )
        add_resp = (
            '{"entities": [{"name": "Alice", "label": "Person"},'
            ' {"name": "NewCo", "label": "Organization"}],'
            ' "relationships": [{"from": "Alice", "to": "NewCo", "type": "WORKS_AT"}]}'
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=retract_resp))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=add_resp))]),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        _seed_graph(mem._db)

        result = mem.update("Alice works at Acme", "Alice works at NewCo")
        assert isinstance(result, UpdateResult)
        assert result.ok
        assert result.retracted.ok
        assert result.added.ok

        # Verify Acme WORKS_AT is gone and NewCo WORKS_AT exists
        rels = mem.relationships()
        types = {(r["a.name"], r["r.type"], r["b.name"]) for r in rels}
        assert ("Alice", "WORKS_AT", "Acme") not in types
        assert ("Alice", "WORKS_AT", "NewCo") in types
        # KNOWS should still be there
        assert ("Alice", "KNOWS", "Bob") in types


# ===========================================================================
# Result classes
# ===========================================================================


class TestDeleteResult:
    """Tests for DeleteResult."""

    def test_repr(self) -> None:
        r = DeleteResult(ok=True, deleted_entities=["A"], deleted_relationships=[])
        assert "ok=True" in repr(r)

    def test_to_dict(self) -> None:
        r = DeleteResult(
            ok=False,
            deleted_entities=[],
            deleted_relationships=[],
            errors=["oops"],
        )
        d = r.to_dict()
        assert d["ok"] is False
        assert d["errors"] == ["oops"]

    def test_defaults(self) -> None:
        r = DeleteResult(ok=True, deleted_entities=[], deleted_relationships=[])
        assert r.errors == []


class TestUpdateResult:
    """Tests for UpdateResult."""

    def test_to_dict(self) -> None:
        dr = DeleteResult(ok=True, deleted_entities=[], deleted_relationships=["x"])
        ar = AddResult(entities=[], relationships=[], executed=1, errors=[])
        r = UpdateResult(ok=True, retracted=dr, added=ar)
        d = r.to_dict()
        assert d["ok"] is True
        assert "retracted" in d
        assert "added" in d


# ===========================================================================
# CLI tests
# ===========================================================================


runner = CliRunner()


class TestDeleteCLI:
    """Tests for `clawgraph delete` command."""

    @patch("clawgraph.db.GraphDB")
    def test_delete_entity_confirmed(self, mock_graph_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db.delete_entity.return_value = True
        mock_graph_db_cls.return_value = mock_db

        result = runner.invoke(app, ["delete", "Alice", "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.output or "deleted" in result.output.lower()

    @patch("clawgraph.db.GraphDB")
    def test_delete_entity_not_found(self, mock_graph_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db.delete_entity.return_value = False
        mock_graph_db_cls.return_value = mock_db

        result = runner.invoke(app, ["delete", "Ghost", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("clawgraph.db.GraphDB")
    def test_delete_entity_json_output(self, mock_graph_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db.delete_entity.return_value = True
        mock_graph_db_cls.return_value = mock_db

        result = runner.invoke(app, ["delete", "Alice", "--yes", "--output", "json"])
        assert result.exit_code == 0
        assert '"ok": true' in result.output

    @patch("clawgraph.db.GraphDB")
    def test_delete_entity_json_not_found(self, mock_graph_db_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db.delete_entity.return_value = False
        mock_graph_db_cls.return_value = mock_db

        result = runner.invoke(
            app, ["delete", "Ghost", "--yes", "--output", "json"]
        )
        assert result.exit_code == 1
        assert '"ok": false' in result.output

    @patch("clawgraph.db.GraphDB")
    def test_delete_aborted(self, mock_graph_db_cls: MagicMock) -> None:
        """If the user types 'n' at the confirmation prompt, abort."""
        result = runner.invoke(app, ["delete", "Alice"], input="n\n")
        assert result.exit_code == 0
        mock_graph_db_cls.return_value.delete_entity.assert_not_called()


class TestRetractCLI:
    """Tests for `clawgraph retract` command."""

    @patch("clawgraph.memory.Memory")
    def test_retract_success(self, mock_memory_cls: MagicMock) -> None:
        mock_mem = MagicMock()
        mock_result = DeleteResult(
            ok=True,
            deleted_entities=[],
            deleted_relationships=["Alice-[WORKS_AT]->Acme"],
        )
        mock_mem.retract.return_value = mock_result
        mock_memory_cls.return_value = mock_mem

        result = runner.invoke(app, ["retract", "Alice works at Acme"])
        assert result.exit_code == 0
        assert "Done" in result.output or "Removed" in result.output

    @patch("clawgraph.memory.Memory")
    def test_retract_not_found(self, mock_memory_cls: MagicMock) -> None:
        mock_mem = MagicMock()
        mock_result = DeleteResult(
            ok=False,
            deleted_entities=[],
            deleted_relationships=[],
            errors=["Relationship not found"],
        )
        mock_mem.retract.return_value = mock_result
        mock_memory_cls.return_value = mock_mem

        result = runner.invoke(app, ["retract", "Alice lives on Mars"])
        assert result.exit_code == 0  # not a crash, just informational
        assert "No matching" in result.output

    @patch("clawgraph.memory.Memory")
    def test_retract_json_output(self, mock_memory_cls: MagicMock) -> None:
        mock_mem = MagicMock()
        mock_result = DeleteResult(
            ok=True,
            deleted_entities=[],
            deleted_relationships=["Alice-[WORKS_AT]->Acme"],
        )
        mock_mem.retract.return_value = mock_result
        mock_memory_cls.return_value = mock_mem

        result = runner.invoke(
            app, ["retract", "Alice works at Acme", "--output", "json"]
        )
        assert result.exit_code == 0
        assert '"ok": true' in result.output

    @patch("clawgraph.memory.Memory")
    def test_retract_error_exits(self, mock_memory_cls: MagicMock) -> None:
        """If Memory.retract() raises, CLI should exit 1."""
        mock_memory_cls.return_value.retract.side_effect = Exception("LLM down")

        result = runner.invoke(app, ["retract", "something"])
        assert result.exit_code == 1
        assert "Error" in result.output
