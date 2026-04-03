"""Tests for the Memory Python API."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from clawgraph.memory import AddResult, Memory
from clawgraph.ontology import Ontology


class TestMemoryAdd:
    """Tests for Memory.add() with mocked LLM."""

    @patch("clawgraph.llm._get_client")
    def test_add_single_fact(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "John", "label": "Person"}, {"name": "Acme", "label": "Organization"}], "relationships": [{"from": "John", "to": "Acme", "type": "WORKS_AT"}]}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        result = mem.add("John works at Acme")

        assert result.ok
        assert len(result.entities) == 2
        assert len(result.relationships) == 1
        assert result.executed == 3  # 2 entities + 1 relationship

    @patch("clawgraph.llm._get_client")
    def test_add_idempotent(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "John", "label": "Person"}], "relationships": []}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("John is a person")
        mem.add("John is a person")

        entities = mem.entities()
        assert len(entities) == 1

    @patch("clawgraph.llm._get_client")
    def test_add_preserves_created_at_on_repeat(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "John", "label": "Person"}], "relationships": []}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        first_ts = "2026-04-03T00:00:00+00:00"
        second_ts = "2026-04-03T00:00:01+00:00"

        mem = Memory(db_path=":memory:")
        with patch("clawgraph.db.GraphDB.now_iso", side_effect=[first_ts, second_ts]):
            mem.add("John is a person")
            mem.add("John is a person")

        rows = mem._db.execute(
            "MATCH (e:Entity {name: 'John'}) RETURN e.created_at, e.updated_at"
        )

        assert len(rows) == 1
        assert rows[0]["e.created_at"] == first_ts
        assert rows[0]["e.updated_at"] == second_ts

    @patch("clawgraph.llm._get_client")
    def test_entities_and_relationships(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "A", "label": "Person"}, {"name": "B", "label": "Person"}], "relationships": [{"from": "A", "to": "B", "type": "KNOWS"}]}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("A knows B")

        entities = mem.entities()
        rels = mem.relationships()
        assert len(entities) == 2
        assert len(rels) == 1
        assert rels[0]["r.type"] == "KNOWS"


class TestMemoryAddBatch:
    """Tests for Memory.add_batch() with mocked LLM."""

    @patch("clawgraph.llm._get_client")
    def test_batch_multiple_facts(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "John", "label": "Person"}, {"name": "Acme", "label": "Organization"}, {"name": "Alice", "label": "Person"}], "relationships": [{"from": "John", "to": "Acme", "type": "WORKS_AT"}, {"from": "John", "to": "Alice", "type": "KNOWS"}]}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        result = mem.add_batch([
            "John works at Acme",
            "John knows Alice",
        ])

        assert result.ok
        assert len(result.entities) == 3
        assert len(result.relationships) == 2
        # Only 1 LLM call for 2 statements
        assert mock_client.chat.completions.create.call_count == 1

    def test_batch_empty_list(self) -> None:
        mem = Memory(db_path=":memory:")
        result = mem.add_batch([])
        assert result.ok
        assert result.executed == 0


class TestMemoryQuery:
    """Tests for Memory.query() with mocked LLM."""

    @patch("clawgraph.llm._get_client")
    def test_query_returns_results(self, mock_get_client: MagicMock) -> None:
        # First call: infer_ontology for add
        add_resp = '{"entities": [{"name": "John", "label": "Person"}], "relationships": []}'
        # Second call: generate_cypher for query
        query_resp = "MATCH (e:Entity) RETURN e.name, e.label"

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=add_resp))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=query_resp))]),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("John is a person")
        results = mem.query("List all people")

        assert len(results) == 1
        assert results[0]["e.name"] == "John"


class TestMemoryExport:
    """Tests for Memory.export()."""

    @patch("clawgraph.llm._get_client")
    def test_export_structure(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "X", "label": "Thing"}], "relationships": []}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("X is a thing")

        export = mem.export()
        assert "entities" in export
        assert "relationships" in export
        assert "ontology" in export


class TestAddResult:
    """Tests for AddResult."""

    def test_repr(self) -> None:
        r = AddResult(entities=[{"name": "A"}], relationships=[], executed=1, errors=[])
        assert "entities=1" in repr(r)

    def test_to_dict(self) -> None:
        r = AddResult(entities=[], relationships=[], executed=0, errors=["err"])
        d = r.to_dict()
        assert d["ok"] is False
        assert d["errors"] == ["err"]

    def test_to_dict_returns_independent_state(self) -> None:
        r = AddResult(
            entities=[{"name": "A"}],
            relationships=[{"from": "A", "to": "B", "type": "KNOWS"}],
            executed=1,
            errors=[],
        )

        payload = r.to_dict()
        payload["entities"][0]["name"] = "mutated"
        payload["errors"].append("err")

        assert r.entities[0]["name"] == "A"
        assert r.errors == []


class TestMemoryConstraints:
    """Tests for Memory with ontology constraints."""

    def test_memory_passes_allowed_labels(self) -> None:
        mem = Memory(
            db_path=":memory:",
            allowed_labels=["Person", "Company"],
        )
        assert mem._ontology.allowed_labels == ["Person", "Company"]

    def test_memory_passes_allowed_relationship_types(self) -> None:
        mem = Memory(
            db_path=":memory:",
            allowed_relationship_types=["WORKS_AT"],
        )
        assert mem._ontology.allowed_relationship_types == ["WORKS_AT"]

    def test_memory_accepts_ontology_object(self) -> None:
        ont = Ontology(
            allowed_labels=["Patient", "Doctor"],
            allowed_relationship_types=["TREATS"],
        )
        mem = Memory(db_path=":memory:", ontology=ont)
        assert mem._ontology is ont
        assert mem._ontology.allowed_labels == ["Patient", "Doctor"]

    def test_ontology_object_overrides_params(self) -> None:
        ont = Ontology(allowed_labels=["X"])
        mem = Memory(
            db_path=":memory:",
            allowed_labels=["Y"],  # should be ignored
            ontology=ont,
        )
        assert mem._ontology.allowed_labels == ["X"]

    @patch("clawgraph.llm._get_client")
    def test_add_with_constraints_passes_context(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "Alice", "label": "Person"}], "relationships": []}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(
            db_path=":memory:",
            allowed_labels=["Person", "Company"],
        )
        result = mem.add("Alice is a person")
        assert result.ok

        # Verify the LLM was called with constraint context
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        assert "Person" in system_msg


class TestMemoryConfigInjection:
    """Tests for Memory config dict parameter."""

    def test_config_sets_model(self) -> None:
        mem = Memory(
            db_path=":memory:",
            config={"llm": {"model": "gpt-4o"}},
        )
        assert mem._model == "gpt-4o"

    def test_explicit_model_overrides_config(self) -> None:
        mem = Memory(
            db_path=":memory:",
            model="claude-3-opus-20240229",
            config={"llm": {"model": "gpt-4o"}},
        )
        assert mem._model == "claude-3-opus-20240229"

    def test_config_empty_dict(self) -> None:
        mem = Memory(db_path=":memory:", config={})
        assert mem._model is None


class TestMemoryInitFacts:
    """Tests for Memory init_facts parameter."""

    @patch("clawgraph.llm._get_client")
    def test_init_facts_seeds_on_creation(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "Alice", "label": "Person"}], "relationships": []}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        mem = Memory(
            db_path=":memory:",
            init_facts=["Alice is a person"],
        )
        entities = mem.entities()
        assert len(entities) == 1
        assert entities[0]["e.name"] == "Alice"

    def test_init_facts_none(self) -> None:
        mem = Memory(db_path=":memory:", init_facts=None)
        assert mem.entities() == []

    def test_init_facts_empty_list(self) -> None:
        mem = Memory(db_path=":memory:", init_facts=[])
        assert mem.entities() == []


class TestMemorySnapshot:
    """Tests for Memory snapshot save/restore."""

    @patch("clawgraph.llm._get_client")
    def test_save_and_restore_snapshot(self, mock_get_client: MagicMock, tmp_path: Path) -> None:
        json_resp = '{"entities": [{"name": "Alice", "label": "Person"}, {"name": "Bob", "label": "Person"}], "relationships": [{"from": "Alice", "to": "Bob", "type": "KNOWS"}]}'
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # Create and populate
        db_dir = tmp_path / "original"
        mem = Memory(db_path=str(db_dir))
        mem.add("Alice knows Bob")

        # Snapshot
        archive = mem.save_snapshot(tmp_path / "backup.tar.gz")
        assert archive.exists()
        mem.close()

        # Restore to a separate directory (avoids lock conflicts)
        restored = Memory.from_snapshot(archive, tmp_path / "restored")
        entities = restored.entities()
        rels = restored.relationships()
        assert len(entities) == 2
        assert len(rels) == 1
        restored.close()
