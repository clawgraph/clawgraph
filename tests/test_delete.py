"""Exact, transactional deletion and correction of stored graph facts."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from openai import OpenAIError
from typer.testing import CliRunner

from clawgraph.cli import app
from clawgraph.cypher import CypherValidationResult
from clawgraph.db import DatabaseError
from clawgraph.llm import LLMError
from clawgraph.memory import Memory
from clawgraph.ontology import Ontology


@pytest.fixture
def memory(tmp_path: Path) -> Iterator[Memory]:
    mem = Memory(db_path=":memory:", ontology_dir=str(tmp_path))
    with patch("clawgraph.memory.infer_ontology", return_value={
        "entities": [
            {"name": "Alice", "label": "Person"},
            {"name": "Bob", "label": "Person"},
            {"name": "Acme", "label": "Company"},
        ],
        "relationships": [
            {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
            {"from": "Bob", "to": "Acme", "type": "WORKS_AT"},
            {"from": "Bob", "to": "Alice", "type": "KNOWS"},
            {"from": "Alice", "to": "Alice", "type": "KNOWS"},
        ],
    }):
        assert mem.add("seed").ok
    yield mem
    mem.close()


def test_delete_entity_cascades_all_directions_and_is_idempotent(memory: Memory) -> None:
    assert hasattr(memory._db, "delete_entity")
    assert memory._db.delete_entity("Alice") is True
    assert memory._db.delete_entity("Alice") is False
    assert {row["e.name"] for row in memory.entities()} == {"Bob", "Acme"}
    assert memory.relationships() == [
        {"a.name": "Bob", "r.type": "WORKS_AT", "b.name": "Acme"},
    ]


def test_delete_relationship_is_exact_and_keeps_endpoints(memory: Memory) -> None:
    assert hasattr(memory._db, "delete_relationship")
    assert memory._db.delete_relationship("Alice", "Acme", "WORKS_AT") is True
    assert memory._db.delete_relationship("Alice", "Acme", "WORKS_AT") is False
    assert len(memory.entities()) == 3
    assert len(memory.relationships()) == 3
    assert {"a.name": "Bob", "r.type": "WORKS_AT", "b.name": "Acme"} in memory.relationships()


def test_memory_delete_prunes_only_unused_ontology_and_preserves_metadata(
    memory: Memory, tmp_path: Path,
) -> None:
    assert hasattr(memory, "delete_entity")
    ontology = Ontology(
        config_dir=tmp_path, allowed_labels=["Person", "Company", "Future"],
        allowed_relationship_types=["WORKS_AT", "KNOWS", "FUTURE"],
    )
    ontology.add_node_label("Person", {"custom": "STRING"})
    ontology.add_relationship_type("WORKS_AT", "Person", "Company", {"since": "STRING"})
    ontology.relationships["WORKS_AT"]["custom"] = "preserve"
    memory._ontology = ontology
    assert memory.delete_entity("Alice")
    assert ontology.nodes == {
        "Person": {"name": "STRING", "custom": "STRING"}, "Company": {"name": "STRING"},
    }
    assert ontology.relationships == {
        "WORKS_AT": {"from": "Person", "to": "Company",
                    "properties": {"since": "STRING"}, "custom": "preserve"},
    }
    assert memory.delete_entity("Acme")
    assert set(ontology.nodes) == {"Person"}
    assert ontology.relationships == {}
    assert ontology.allowed_labels == ["Person", "Company", "Future"]
    assert ontology.allowed_relationship_types == ["WORKS_AT", "KNOWS", "FUTURE"]
    assert Ontology(config_dir=tmp_path).nodes == ontology.nodes
    with patch.object(ontology, "_save") as save:
        assert not memory.delete_entity("missing")
        save.assert_not_called()


def test_deletion_rejects_invalid_arguments_and_binds_literal_data(memory: Memory) -> None:
    for invalid in (None, True, 4, [], "", " \t"):
        with pytest.raises(ValueError):
            memory._db.delete_entity(invalid)
        for args in ((invalid, "Acme", "WORKS_AT"), ("Alice", invalid, "WORKS_AT"),
                     ("Alice", "Acme", invalid)):
            with pytest.raises(ValueError):
                memory._db.delete_relationship(*args)
    name = "literal '\\\n) DETACH DELETE e //"
    rel_type = "type '\\\n"
    memory._db.execute("MERGE (:Entity {name: $name})", {"name": name})
    memory._db.execute(
        "MATCH (a:Entity {name: $name}), (b:Entity {name: 'Acme'}) "
        "MERGE (a)-[:Relates {type: $type}]->(b)", {"name": name, "type": rel_type},
    )
    with patch.object(memory._db, "execute", wraps=memory._db.execute) as execute:
        assert memory._db.delete_relationship(name, "Acme", rel_type)
        assert memory._db.delete_entity(name)
    assert all(name not in call.args[0] and rel_type not in call.args[0]
               for call in execute.call_args_list)
    assert len(memory.entities()) == 3


def test_retract_deletes_only_selected_existing_triples_and_keeps_endpoints(memory: Memory) -> None:
    assert hasattr(memory, "retract")
    old = {"from": "Alice", "to": "Acme", "type": "WORKS_AT"}
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "relationships": [old, old, {"from": "Missing", "to": "Acme", "type": "WORKS_AT"}],
        }))),
    ]
    memory._model = "chosen-model"
    with patch("clawgraph.llm._get_client", return_value=client):
        assert memory.retract("Alice no longer works at Acme") == 1
        assert memory.retract("Alice no longer works at Acme") == 0
    assert len(memory.entities()) == 3
    assert len(memory.relationships()) == 3
    assert {"a.name": "Bob", "r.type": "WORKS_AT", "b.name": "Acme"} in memory.relationships()
    assert "WORKS_AT" in memory.get_ontology().relationships
    assert client.chat.completions.create.call_args.kwargs["model"] == "chosen-model"


@pytest.mark.parametrize("response", [
    "", "not json", "null", "[]", "{}", '{"relationships":null}',
    '{"relationships":"Alice"}', '{"relationships":[null]}',
    '{"relationships":[{"from":"Alice","to":"Acme"}]}',
    '{"relationships":[{"from":"Alice","to":"Acme","type":3}]}',
    '{"relationships":[{"from":"","to":"Acme","type":"WORKS_AT"}]}',
    '{"relationships":[{"from":"Alice","to":"Acme","type":"WORKS_AT","extra":1}]}',
    '{"relationships":[],"extra":1}', None, MagicMock(choices=[]),
    MagicMock(choices=[None]), OpenAIError("provider unavailable"),
])
def test_retract_malformed_provider_selection_leaves_graph_unchanged(
    memory: Memory, response: object,
) -> None:
    before = memory.export()
    client = MagicMock()
    if isinstance(response, Exception):
        client.chat.completions.create.side_effect = response
    elif isinstance(response, str):
        client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=response)),
        ]
    else:
        client.chat.completions.create.return_value = response
    with patch("clawgraph.llm._get_client", return_value=client):
        with pytest.raises(LLMError):
            memory.retract("Alice works at Acme")
    assert memory.export() == before


@pytest.mark.parametrize("answer", ["n\n", "", None])
def test_delete_cli_decline_or_closed_stdin_never_opens_memory(answer: str | None) -> None:
    with patch("clawgraph.memory.Memory") as constructor:
        result = CliRunner().invoke(
            app, ["delete", "Alice", "--output", "json"], input=answer,
        )
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"status": "cancelled", "deleted": False}
    constructor.assert_not_called()


@pytest.mark.parametrize("replacement", [
    None, [], {}, {"entities": [], "relationships": []},
    {"entities": None, "relationships": []},
    {"entities": ["Alice"], "relationships": []},
    {"entities": [{"name": "Alice"}], "relationships": []},
    {"entities": [{"name": "Alice", "label": 3}], "relationships": []},
    {"entities": [{"name": "Alice", "label": "Person"}], "relationships": []},
    {"entities": [], "relationships": [{"from": "Alice", "to": "Missing", "type": "KNOWS"}]},
    {"entities": [], "relationships": [{"from": "Alice", "to": "Acme", "type": ""}]},
    {"entities": [], "relationships": [None]},
    {"entities": [], "relationships": [{"from": "Alice", "to": "Acme"}]},
    {"entities": [
        {"name": "Alice", "label": "Person"}, {"name": "Alice", "label": "Company"},
    ], "relationships": [{"from": "Alice", "to": "Acme", "type": "WORKS_AT"}]},
    {"entities": [], "relationships": [], "extra": True},
    AttributeError("malformed provider envelope"), LLMError("provider unavailable"),
])
def test_update_rejects_malformed_replacements_before_any_mutation(
    memory: Memory, replacement: object,
) -> None:
    before = memory.export()
    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[
            {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
        ]),
        patch("clawgraph.memory.infer_ontology") as infer,
        patch.object(memory._db, "replace_relationships") as mutate,
    ):
        if isinstance(replacement, Exception):
            infer.side_effect = replacement
        else:
            infer.return_value = replacement
        with pytest.raises(LLMError):
            memory.update("old fact", "new fact")
        mutate.assert_not_called()
    assert memory.export() == before


def test_retract_rolls_back_all_edges_and_ontology_on_second_delete_failure(memory: Memory) -> None:
    before = memory.export()
    execute = memory._db.execute
    deletions = 0

    def fail_second(cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        nonlocal deletions
        if cypher.endswith("DELETE r"):
            deletions += 1
            if deletions == 2:
                raise DatabaseError("injected second deletion failure")
        return execute(cypher, parameters)

    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[
            {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
            {"from": "Bob", "to": "Acme", "type": "WORKS_AT"},
        ]),
        patch.object(memory._db, "execute", side_effect=fail_second),
        patch.object(memory.get_ontology(), "_save") as save,
    ):
        with pytest.raises(DatabaseError):
            memory.retract("retract employment")
        save.assert_not_called()
    assert deletions == 2
    assert memory.export() == before


def test_retraction_candidate_shortlist_is_bounded_and_context_prioritized(memory: Memory) -> None:
    memory._db.execute(
        "UNWIND $types AS kind MATCH (a:Entity {name: 'Bob'}), (b:Entity {name: 'Acme'}) "
        "MERGE (a)-[:Relates {type: kind}]->(b)",
        {"types": [f"OTHER_{i}_" + "x" * 100 for i in range(220)]},
    )
    with patch("clawgraph.memory.select_relationships_for_retraction", return_value=[]) as select:
        assert memory.retract("Alice") == 0
    candidates = select.call_args.args[1]
    assert candidates[0]["from"] == "Alice"
    assert len(candidates) <= 200
    assert len(json.dumps(candidates)) <= 16000


def test_retract_rejects_empty_input_and_skips_provider_for_empty_graph(
    memory: Memory, tmp_path: Path,
) -> None:
    with patch("clawgraph.llm._get_client") as client:
        for value in (None, [], 1, "", " \n"):
            with pytest.raises(ValueError, match="statement"):
                memory.retract(value)
        empty = Memory(db_path=":memory:", ontology_dir=str(tmp_path / "empty"))
        try:
            assert empty.retract("anything") == 0
        finally:
            empty.close()
        client.assert_not_called()
    before = memory.export()
    with patch("clawgraph.memory.select_relationships_for_retraction", return_value=[]):
        assert memory.retract("ambiguous") == 0
    assert memory.export() == before


def test_update_atomically_replaces_fact_with_bound_values_and_preserves_timestamps(memory: Memory) -> None:
    assert hasattr(memory, "update")
    name = 'New "\\\nCompany'
    created = memory._db.execute(
        "MATCH (e:Entity {name: 'Alice'}) RETURN e.created_at AS created",
    )[0]["created"]
    entities = [{"name": "Alice", "label": "Person"}, {"name": name, "label": "Company"}]
    rel = {"from": "Alice", "to": name, "type": "WORKS_AT"}
    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[
            {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
        ]),
        patch("clawgraph.memory.infer_ontology", return_value={
            "entities": entities + [entities[0]], "relationships": [rel, rel],
        }),
        patch.object(memory._db, "execute", wraps=memory._db.execute) as execute,
    ):
        result = memory.update("Alice works at Acme", "Alice moved to a new company")
    assert result.ok and result.executed == 3
    assert result.entities == entities
    assert result.relationships == [rel]
    assert all(name not in call.args[0] for call in execute.call_args_list)
    assert [call.args[0] for call in execute.call_args_list].count("BEGIN TRANSACTION") == 1
    assert {"a.name": "Alice", "r.type": "WORKS_AT", "b.name": "Acme"} not in memory.relationships()
    assert {"a.name": "Bob", "r.type": "WORKS_AT", "b.name": "Acme"} in memory.relationships()
    assert {"a.name": "Alice", "r.type": "WORKS_AT", "b.name": name} in memory.relationships()
    assert memory._db.execute(
        "MATCH (e:Entity {name: 'Alice'}) RETURN e.created_at AS created",
    )[0]["created"] == created


def test_update_missing_old_or_invalid_arguments_never_adds_new_facts(memory: Memory) -> None:
    before = memory.export()
    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[]),
        patch("clawgraph.memory.infer_ontology") as infer,
    ):
        with pytest.raises(ValueError, match="old"):
            memory.update("not stored", "new fact")
        infer.assert_not_called()
    with patch("clawgraph.llm._get_client") as client:
        for invalid in ("", " \n", None, True, []):
            with pytest.raises(ValueError):
                memory.update(invalid, "new fact")
            with pytest.raises(ValueError):
                memory.update("old fact", invalid)
        client.assert_not_called()
    assert memory.export() == before


@pytest.mark.parametrize("label,rel_type", [
    ("Forbidden", "WORKS_AT"), ("Person", "FORBIDDEN"),
])
def test_update_enforces_ontology_constraints_before_mutation(
    memory: Memory, tmp_path: Path, label: str, rel_type: str,
) -> None:
    memory._ontology = Ontology(
        config_dir=tmp_path, allowed_labels=["Person", "Company"],
        allowed_relationship_types=["WORKS_AT", "KNOWS"],
    )
    before = memory.export()
    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[
            {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
        ]),
        patch("clawgraph.memory.infer_ontology", return_value={
            "entities": [{"name": "Alice", "label": label}],
            "relationships": [{"from": "Alice", "to": "Acme", "type": rel_type}],
        }),
    ):
        with pytest.raises(LLMError, match="allowed"):
            memory.update("old", "new")
    assert memory.export() == before


def test_update_identical_fact_preserves_edge_age_metadata_and_idempotency(memory: Memory) -> None:
    old = {"from": "Alice", "to": "Acme", "type": "WORKS_AT"}
    ontology = memory.get_ontology()
    ontology.add_node_label("Person", {"custom": "STRING"})
    ontology.add_relationship_type("WORKS_AT", "Person", "Company", {"since": "STRING"})
    before = memory.export()
    created = memory._db.execute(
        "MATCH (:Entity {name: 'Alice'})-[r:Relates {type: 'WORKS_AT'}]->"
        "(:Entity {name: 'Acme'}) RETURN r.created_at AS created",
    )[0]["created"]
    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[old]),
        patch("clawgraph.memory.infer_ontology", return_value={
            "entities": [], "relationships": [old],
        }),
    ):
        assert memory.update("old", "same").executed == 1
        assert memory.update("old", "same").executed == 1
    assert memory.export() == before
    assert memory._db.execute(
        "MATCH (:Entity {name: 'Alice'})-[r:Relates {type: 'WORKS_AT'}]->"
        "(:Entity {name: 'Acme'}) RETURN r.created_at AS created",
    )[0]["created"] == created


def test_update_rechecks_old_fact_after_provider_calls_before_writing(memory: Memory) -> None:
    old = {"from": "Alice", "to": "Acme", "type": "WORKS_AT"}

    def extract(*args: Any, **kwargs: Any) -> dict[str, Any]:
        memory._db.delete_relationship("Alice", "Acme", "WORKS_AT")
        return {
            "entities": [{"name": "New", "label": "Company"}],
            "relationships": [{"from": "Alice", "to": "New", "type": "WORKS_AT"}],
        }

    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[old]),
        patch("clawgraph.memory.infer_ontology", side_effect=extract),
        patch.object(memory.get_ontology(), "_save") as save,
    ):
        with pytest.raises(ValueError, match="old"):
            memory.update("old", "new")
        save.assert_not_called()
    assert "New" not in {row["e.name"] for row in memory.entities()}


@pytest.mark.parametrize("phase", ["late-merge", "commit"])
def test_update_rolls_back_old_fact_entities_timestamps_and_ontology_on_failure(
    memory: Memory, phase: str,
) -> None:
    before = memory.export()
    timestamps = "MATCH (e:Entity) RETURN e.name, e.created_at, e.updated_at ORDER BY e.name"
    before_timestamps = memory._db.execute(timestamps)
    execute = memory._db.execute
    merges = 0

    def fail(cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        nonlocal merges
        if "MERGE (a)-" in cypher:
            merges += 1
            if phase == "late-merge" and merges == 2:
                raise DatabaseError("injected late merge failure")
        if phase == "commit" and cypher == "COMMIT":
            raise DatabaseError("injected commit failure")
        return execute(cypher, parameters)

    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[
            {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
        ]),
        patch("clawgraph.memory.infer_ontology", return_value={
            "entities": [{"name": "New", "label": "Company"}, {"name": "Alice", "label": "Person"}],
            "relationships": [
                {"from": "Alice", "to": "New", "type": "WORKS_AT"},
                {"from": "Bob", "to": "New", "type": "WORKS_AT"},
            ],
        }),
        patch.object(memory._db, "execute", side_effect=fail),
        patch.object(memory.get_ontology(), "_save") as save,
    ):
        with pytest.raises(DatabaseError):
            memory.update("old", "new")
        save.assert_not_called()
    assert memory.export() == before
    assert memory._db.execute(timestamps) == before_timestamps


def test_entity_deletion_validates_before_execution_and_rolls_back_ontology(memory: Memory) -> None:
    before = memory.export()
    with (
        patch("clawgraph.db.validate_cypher", return_value=CypherValidationResult(False)),
        patch.object(memory._db, "execute") as execute,
    ):
        with pytest.raises(DatabaseError):
            memory.delete_entity("Alice")
        execute.assert_not_called()
    execute_real = memory._db.execute

    def fail_after_delete(cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = execute_real(cypher, parameters)
        if "DETACH DELETE" in cypher:
            raise DatabaseError("injected deletion failure")
        return rows

    with (
        patch.object(memory._db, "execute", side_effect=fail_after_delete),
        patch.object(memory.get_ontology(), "_save") as save,
    ):
        with pytest.raises(DatabaseError):
            memory.delete_entity("Alice")
        save.assert_not_called()
    assert memory.export() == before


@pytest.mark.parametrize("args,answer", [
    ([], "y\n"), (["--yes"], None), (["-y"], None),
])
def test_delete_cli_authorized_success_closes_memory(
    memory: Memory, args: list[str], answer: str | None,
) -> None:
    with (
        patch("clawgraph.memory.Memory", return_value=memory),
        patch.object(memory, "close", wraps=memory.close) as close,
    ):
        result = CliRunner().invoke(
            app, ["delete", "Alice", "--output", "json", *args], input=answer,
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {"status": "ok", "name": "Alice", "deleted": True}
        close.assert_called_once()


@pytest.mark.parametrize("phase", ["initialization", "operation"])
def test_mutation_cli_failures_are_structured_and_close_initialized_memory(
    memory: Memory, phase: str,
) -> None:
    with (
        patch("clawgraph.memory.Memory", return_value=memory) as constructor,
        patch.object(memory, "delete_entity", side_effect=DatabaseError("failed")),
        patch.object(memory, "close", wraps=memory.close) as close,
    ):
        if phase == "initialization":
            constructor.side_effect = RuntimeError("failed")
        result = CliRunner().invoke(app, ["delete", "Alice", "--yes", "--output", "json"])
        assert result.exit_code == 1
        assert json.loads(result.stdout) == {"status": "error", "error": "failed"}
        assert close.call_count == (phase == "operation")


@pytest.mark.parametrize("command", ["retract", "update"])
@pytest.mark.parametrize("output", ["json", "human"])
def test_retract_and_update_cli_emit_success_json_and_pass_model(
    memory: Memory, command: str, output: str,
) -> None:
    with (
        patch("clawgraph.memory.Memory", return_value=memory) as constructor,
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[
            {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
        ]),
        patch("clawgraph.memory.infer_ontology", return_value={
            "entities": [], "relationships": [{"from": "Bob", "to": "Acme", "type": "WORKS_AT"}],
        }),
        patch.object(memory, "close", wraps=memory.close) as close,
    ):
        args = [command, "Alice works at Acme"]
        if command == "update":
            args += ["Bob works at Acme"]
        result = CliRunner().invoke(app, [*args, "--output", output, "--model", "chosen"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["status"] == "ok"
        if command == "retract":
            assert payload == {"status": "ok", "removed": 1}
        else:
            assert payload["ok"] and payload["executed"] == 1 and payload["errors"] == []
        constructor.assert_called_once_with(model="chosen")
        close.assert_called_once()


def test_update_missing_endpoint_at_write_time_does_not_lose_old_fact(memory: Memory) -> None:
    replace = memory._db.replace_relationships

    def disappear(
        removals: list[dict[str, str]], entities: list[dict[str, str]],
        relationships: list[dict[str, str]],
    ) -> None:
        memory._db.delete_entity("Bob")
        replace(removals, entities, relationships)

    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[
            {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
        ]),
        patch("clawgraph.memory.infer_ontology", return_value={
            "entities": [], "relationships": [{"from": "Alice", "to": "Bob", "type": "KNOWS"}],
        }),
        patch.object(memory._db, "replace_relationships", side_effect=disappear),
        patch.object(memory._db, "execute", wraps=memory._db.execute) as execute,
    ):
        with pytest.raises(DatabaseError, match="endpoint"):
            memory.update("old", "new")
    assert not any("MERGE (a)-" in call.args[0] for call in execute.call_args_list)
    assert {"a.name": "Alice", "r.type": "WORKS_AT", "b.name": "Acme"} in memory.relationships()


@pytest.mark.parametrize("command,method,args", [
    ("delete", "delete_entity", ["Alice", "--yes"]),
    ("retract", "retract", ["old"]),
    ("update", "update", ["old", "new"]),
])
@pytest.mark.parametrize("output", ["json", "human"])
def test_all_mutation_cli_errors_preserve_literal_messages_and_close(
    memory: Memory, command: str, method: str, args: list[str], output: str,
) -> None:
    message = "[red]literal failure[/red]"
    with (
        patch("clawgraph.memory.Memory", return_value=memory),
        patch.object(memory, method, side_effect=LLMError(message)),
        patch.object(memory, "close", wraps=memory.close) as close,
    ):
        result = CliRunner().invoke(app, [command, *args, "--output", output])
        assert result.exit_code == 1
        close.assert_called_once()
    if output == "json":
        assert json.loads(result.stdout) == {"status": "error", "error": message}
    else:
        assert message in result.output


def test_update_rejects_entire_correction_when_one_of_several_old_edges_disappears(
    memory: Memory,
) -> None:
    old = [
        {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
        {"from": "Bob", "to": "Acme", "type": "WORKS_AT"},
    ]

    def extract(*args: Any, **kwargs: Any) -> dict[str, Any]:
        memory._db.delete_relationship("Bob", "Acme", "WORKS_AT")
        return {
            "entities": [{"name": "New", "label": "Company"}],
            "relationships": [{"from": "Alice", "to": "New", "type": "WORKS_AT"}],
        }

    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=old),
        patch("clawgraph.memory.infer_ontology", side_effect=extract),
        patch.object(memory.get_ontology(), "_save") as save,
    ):
        with pytest.raises(ValueError, match="old fact no longer exists"):
            memory.update("both old facts", "new fact")
        save.assert_not_called()
    assert "New" not in {row["e.name"] for row in memory.entities()}
    assert {"a.name": "Alice", "r.type": "WORKS_AT", "b.name": "Acme"} in memory.relationships()


def test_update_overlapping_replacement_preserves_retained_edge_creation_time(memory: Memory) -> None:
    retained = {"from": "Alice", "to": "Acme", "type": "WORKS_AT"}
    replaced = {"from": "Bob", "to": "Acme", "type": "WORKS_AT"}
    timestamp_query = (
        "MATCH (:Entity {name: 'Alice'})-[r:Relates {type: 'WORKS_AT'}]->"
        "(:Entity {name: 'Acme'}) RETURN r.created_at AS created"
    )
    created = memory._db.execute(timestamp_query)[0]["created"]
    with (
        patch("clawgraph.memory.select_relationships_for_retraction", return_value=[retained, replaced]),
        patch("clawgraph.memory.infer_ontology", return_value={
            "entities": [],
            "relationships": [retained, {"from": "Bob", "to": "Alice", "type": "KNOWS"}],
        }),
    ):
        result = memory.update("old facts", "overlapping replacement")
    assert result.ok and result.executed == 2
    assert memory._db.execute(timestamp_query) == [{"created": created}]
    assert {"a.name": "Bob", "r.type": "WORKS_AT", "b.name": "Acme"} not in memory.relationships()
    assert len(memory.relationships()) == 3
