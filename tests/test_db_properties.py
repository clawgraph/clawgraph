"""Property-based tests for the database layer."""

from __future__ import annotations

import string
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, rule

from clawgraph.db import GraphDB

DB_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + "_-",
    min_size=1,
    max_size=12,
)


@settings(max_examples=25, stateful_step_count=20, deadline=None)
class GraphDBWorkflowMachine(RuleBasedStateMachine):
    """Exercise GraphDB across random merge workflows."""

    entity_names = Bundle("entity_names")

    def __init__(self) -> None:
        super().__init__()
        self._tmp_dir = TemporaryDirectory()
        self._root = Path(self._tmp_dir.name)
        self._db = GraphDB(db_path=str(self._root / "db"))
        self._db.ensure_base_schema()
        self._expected_entities: dict[str, str] = {}
        self._expected_relationships: set[tuple[str, str, str]] = set()

    def teardown(self) -> None:
        self._db.close()
        self._tmp_dir.cleanup()

    @rule(target=entity_names, name=DB_TEXT, label=DB_TEXT)
    def merge_entity(self, name: str, label: str) -> str:
        self._db.execute(
            f"MERGE (e:Entity {{name: '{name}'}}) SET e.label = '{label}'"
        )
        self._expected_entities[name] = label
        return name

    @rule(entity_name=entity_names, label=DB_TEXT)
    def merge_existing_entity(self, entity_name: str, label: str) -> None:
        self._db.execute(
            f"MERGE (e:Entity {{name: '{entity_name}'}}) SET e.label = '{label}'"
        )
        self._expected_entities[entity_name] = label

    @rule(left=entity_names, right=entity_names, rel_type=DB_TEXT)
    def merge_relationship(self, left: str, right: str, rel_type: str) -> None:
        self._db.execute(
            f"MATCH (a:Entity {{name: '{left}'}}), (b:Entity {{name: '{right}'}}) "
            f"MERGE (a)-[r:Relates {{type: '{rel_type}'}}]->(b)"
        )
        self._expected_relationships.add((left, rel_type, right))

    @invariant()
    def entity_model_matches_db(self) -> None:
        rows = self._db.execute("MATCH (e:Entity) RETURN e.name, e.label")
        actual = {(row["e.name"], row["e.label"]) for row in rows}
        expected = set(self._expected_entities.items())
        assert actual == expected

    @invariant()
    def relationship_model_matches_db(self) -> None:
        rows = self._db.execute(
            "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN a.name, r.type, b.name"
        )
        actual = {(row["a.name"], row["r.type"], row["b.name"]) for row in rows}
        assert actual == self._expected_relationships


TestGraphDBWorkflowMachine = GraphDBWorkflowMachine.TestCase


@st.composite
def graph_inputs(draw: st.DrawFn) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    entities = draw(st.lists(st.tuples(DB_TEXT, DB_TEXT), min_size=1, max_size=6))
    entity_names = [name for name, _ in entities]
    relationships = draw(
        st.lists(
            st.tuples(
                st.sampled_from(entity_names),
                st.sampled_from(entity_names),
                DB_TEXT,
            ),
            max_size=8,
        )
    )
    return entities, relationships


class TestGraphDBSnapshotProperties:
    """Property tests for GraphDB snapshots."""

    @settings(max_examples=20, deadline=None)
    @given(graph=graph_inputs())
    def test_property_snapshot_roundtrip_preserves_graph(
        self,
        graph: tuple[list[tuple[str, str]], list[tuple[str, str, str]]],
    ) -> None:
        entities, relationships = graph
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_dir = tmp_path / "graph"
            db = GraphDB(db_path=str(db_dir))
            db.ensure_base_schema()

            expected_entities: dict[str, str] = {}
            for name, label in entities:
                db.execute(
                    f"MERGE (e:Entity {{name: '{name}'}}) SET e.label = '{label}'"
                )
                expected_entities[name] = label

            expected_relationships: set[tuple[str, str, str]] = set()
            for left, right, rel_type in relationships:
                db.execute(
                    f"MATCH (a:Entity {{name: '{left}'}}), (b:Entity {{name: '{right}'}}) "
                    f"MERGE (a)-[r:Relates {{type: '{rel_type}'}}]->(b)"
                )
                expected_relationships.add((left, rel_type, right))

            archive = db.save_snapshot(tmp_path / "snapshot.tar.gz")
            db.close()

            restored = GraphDB.load_snapshot(archive, tmp_path / "restored")
            restored.ensure_base_schema()

            entity_rows = restored.execute("MATCH (e:Entity) RETURN e.name, e.label")
            relationship_rows = restored.execute(
                "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN a.name, r.type, b.name"
            )

            actual_entities = {(row["e.name"], row["e.label"]) for row in entity_rows}
            actual_relationships = {
                (row["a.name"], row["r.type"], row["b.name"])
                for row in relationship_rows
            }

            assert actual_entities == set(expected_entities.items())
            assert actual_relationships == expected_relationships

            restored.close()
