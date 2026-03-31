"""Tests for hybrid retrieval — vector index and Memory integration.

All embedding / LLM calls are mocked with deterministic fake data.
No network calls are made.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from clawgraph.memory import Memory
from clawgraph.vectors import VectorIndex, get_embeddings

# ---------------------------------------------------------------------------
# Helpers — deterministic fake embeddings
# ---------------------------------------------------------------------------

_DIM = 8  # small dimension for fast tests


def _fake_embedding(text: str) -> list[float]:
    """Generate a deterministic embedding from a text string.

    Uses a simple hash → float approach so the same text always maps
    to the same vector, but different texts map to different vectors.
    """
    rng = np.random.RandomState(abs(hash(text)) % (2**31))
    vec = rng.randn(_DIM).astype(np.float32)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def _mock_embeddings_create(input: list[str], **kwargs: object) -> MagicMock:
    """Return a mock OpenAI embeddings response."""
    data = []
    for i, text in enumerate(input):
        item = MagicMock()
        item.index = i
        item.embedding = _fake_embedding(text)
        data.append(item)
    resp = MagicMock()
    resp.data = data
    return resp


# ---------------------------------------------------------------------------
# VectorIndex unit tests
# ---------------------------------------------------------------------------


class TestVectorIndex:
    """Core VectorIndex operations."""

    def test_add_and_len(self) -> None:
        idx = VectorIndex()
        assert len(idx) == 0

        idx.add("Alice", _fake_embedding("Alice"))
        assert len(idx) == 1
        assert "Alice" in idx

    def test_add_duplicate_updates(self) -> None:
        idx = VectorIndex()
        idx.add("Alice", _fake_embedding("Alice"))
        idx.add("Alice", _fake_embedding("Alice v2"))
        assert len(idx) == 1

    def test_search_returns_sorted(self) -> None:
        idx = VectorIndex()
        idx.add("Alice", _fake_embedding("Alice"))
        idx.add("Bob", _fake_embedding("Bob"))
        idx.add("Carol", _fake_embedding("Carol"))

        results = idx.search(_fake_embedding("Alice"), top_k=2)
        assert len(results) == 2
        # First result should be Alice (exact match).
        assert results[0][0] == "Alice"
        assert results[0][1] >= results[1][1]  # sorted by similarity

    def test_search_empty_index(self) -> None:
        idx = VectorIndex()
        assert idx.search(_fake_embedding("anything")) == []

    def test_search_top_k_limits(self) -> None:
        idx = VectorIndex()
        for i in range(10):
            idx.add(f"e{i}", _fake_embedding(f"e{i}"))
        results = idx.search(_fake_embedding("e0"), top_k=3)
        assert len(results) == 3

    def test_dimension_mismatch_raises(self) -> None:
        idx = VectorIndex()
        idx.add("a", [1.0, 0.0, 0.0])
        with pytest.raises(ValueError, match="dimension mismatch"):
            idx.add("b", [1.0, 0.0])

    def test_contains(self) -> None:
        idx = VectorIndex()
        idx.add("X", _fake_embedding("X"))
        assert "X" in idx
        assert "Y" not in idx


class TestVectorIndexPersistence:
    """Disk persistence round-trip."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        persist = tmp_path / "vec_idx"
        idx = VectorIndex(persist_dir=str(persist))
        idx.add("Alice", _fake_embedding("Alice"))
        idx.add("Bob", _fake_embedding("Bob"))
        idx.save()

        # Verify files exist on disk.
        assert (persist / "vector_names.json").exists()
        assert (persist / "vector_data.npy").exists()

        # Load into a new instance.
        idx2 = VectorIndex(persist_dir=str(persist))
        assert len(idx2) == 2
        assert "Alice" in idx2
        assert "Bob" in idx2

        # Search should work identically.
        results = idx2.search(_fake_embedding("Alice"), top_k=1)
        assert results[0][0] == "Alice"

    def test_load_from_empty_dir(self, tmp_path: Path) -> None:
        persist = tmp_path / "empty_idx"
        persist.mkdir()
        idx = VectorIndex(persist_dir=str(persist))
        assert len(idx) == 0

    def test_save_noop_without_persist_dir(self) -> None:
        idx = VectorIndex()  # no persist_dir
        idx.add("X", _fake_embedding("X"))
        idx.save()  # should be a silent no-op


# ---------------------------------------------------------------------------
# get_embeddings helper tests (mocked OpenAI)
# ---------------------------------------------------------------------------


class TestGetEmbeddings:
    """get_embeddings() with mocked OpenAI client."""

    @patch("clawgraph.llm._get_client")
    def test_returns_embeddings(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = _mock_embeddings_create
        mock_get_client.return_value = mock_client

        result = get_embeddings(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == _DIM

    @patch("clawgraph.llm._get_client")
    def test_empty_input(self, mock_get_client: MagicMock) -> None:
        result = get_embeddings([])
        assert result == []
        mock_get_client.assert_not_called()

    @patch("clawgraph.llm._get_client")
    def test_api_error_raises_llm_error(self, mock_get_client: MagicMock) -> None:
        from clawgraph.llm import LLMError

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = RuntimeError("boom")
        mock_get_client.return_value = mock_client

        with pytest.raises(LLMError, match="Embedding call failed"):
            get_embeddings(["test"])


# ---------------------------------------------------------------------------
# Memory integration tests with vectors
# ---------------------------------------------------------------------------


class TestMemoryVectors:
    """Memory with enable_vectors=True."""

    def _mock_add_and_query(
        self,
        mock_get_client: MagicMock,
        add_json: str,
        query_cypher: str,
        query_returns_empty: bool = False,
    ) -> MagicMock:
        """Wire up a mock client for add() then query() flow."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = _mock_embeddings_create

        responses = [
            # infer_ontology for add()
            MagicMock(choices=[MagicMock(message=MagicMock(content=add_json))]),
            # generate_cypher for query()
            MagicMock(choices=[MagicMock(message=MagicMock(content=query_cypher))]),
        ]
        mock_client.chat.completions.create.side_effect = responses
        mock_get_client.return_value = mock_client
        return mock_client

    @patch("clawgraph.llm._get_client")
    def test_add_stores_embeddings(self, mock_get_client: MagicMock) -> None:
        """add() should also store embeddings when vectors are enabled."""
        add_json = json.dumps({
            "entities": [
                {"name": "Alice", "label": "Person"},
                {"name": "Acme", "label": "Organization"},
            ],
            "relationships": [
                {"from": "Alice", "to": "Acme", "type": "WORKS_AT"},
            ],
        })
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = _mock_embeddings_create
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=add_json))]
        )
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:", enable_vectors=True)
        result = mem.add("Alice works at Acme")

        assert result.ok
        # Embeddings API should have been called for entity names.
        mock_client.embeddings.create.assert_called_once()
        call_input = mock_client.embeddings.create.call_args
        assert "Alice" in call_input.kwargs.get("input", call_input[1].get("input", []))
        # Vector index should contain the entities.
        assert mem._vector_index is not None
        assert "Alice" in mem._vector_index
        assert "Acme" in mem._vector_index

    @patch("clawgraph.llm._get_client")
    def test_query_uses_graph_first(self, mock_get_client: MagicMock) -> None:
        """query() should return graph results when Cypher works."""
        add_json = json.dumps({
            "entities": [{"name": "John", "label": "Person"}],
            "relationships": [],
        })
        mock_client = self._mock_add_and_query(
            mock_get_client,
            add_json=add_json,
            query_cypher="MATCH (e:Entity) RETURN e.name, e.label",
        )
        del mock_client  # used only for side-effects

        mem = Memory(db_path=":memory:", enable_vectors=True)
        mem.add("John is a person")
        results = mem.query("List all people")

        assert len(results) == 1
        assert results[0]["e.name"] == "John"

    @patch("clawgraph.llm._get_client")
    def test_query_falls_back_to_vectors(self, mock_get_client: MagicMock) -> None:
        """query() should fall back to vector search when Cypher returns empty."""
        add_json = json.dumps({
            "entities": [
                {"name": "Alice", "label": "Person"},
                {"name": "Acme Corp", "label": "Organization"},
            ],
            "relationships": [
                {"from": "Alice", "to": "Acme Corp", "type": "WORKS_AT"},
            ],
        })
        # Cypher that matches nothing (simulating name mismatch).
        bad_cypher = (
            "MATCH (e:Entity {name: 'ACME project'}) RETURN e.name, e.label"
        )
        mock_client = self._mock_add_and_query(
            mock_get_client,
            add_json=add_json,
            query_cypher=bad_cypher,
        )
        del mock_client  # used only for side-effects

        mem = Memory(db_path=":memory:", enable_vectors=True)
        mem.add("Alice works at Acme Corp")
        results = mem.query("Tell me about the ACME project")

        # Should have fallen back and found Acme Corp via vector similarity.
        assert len(results) > 0

    @patch("clawgraph.llm._get_client")
    def test_vector_fallback_includes_neighbourhood(
        self, mock_get_client: MagicMock
    ) -> None:
        """Vector fallback should return entity + relationship context."""
        add_json = json.dumps({
            "entities": [
                {"name": "Alice", "label": "Person"},
                {"name": "Acme Corp", "label": "Organization"},
            ],
            "relationships": [
                {"from": "Alice", "to": "Acme Corp", "type": "WORKS_AT"},
            ],
        })
        # Cypher that deliberately misses.
        bad_cypher = (
            "MATCH (e:Entity {name: 'Acme'}) RETURN e.name, e.label"
        )
        mock_client = self._mock_add_and_query(
            mock_get_client,
            add_json=add_json,
            query_cypher=bad_cypher,
        )
        del mock_client  # used only for side-effects

        mem = Memory(db_path=":memory:", enable_vectors=True)
        mem.add("Alice works at Acme Corp")
        results = mem.query("Tell me about Acme")

        # Should include entity rows and relationship rows.
        names_found = set()
        for row in results:
            for val in row.values():
                if isinstance(val, str):
                    names_found.add(val)
        # At a minimum, we should see at least one of the entities from the
        # neighbourhood traversal.
        assert names_found & {"Alice", "Acme Corp"}


class TestMemoryVectorsDisabled:
    """Memory with enable_vectors=False (default)."""

    def test_default_no_vectors(self) -> None:
        mem = Memory(db_path=":memory:")
        assert mem._vectors_enabled is False
        assert mem._vector_index is None

    @patch("clawgraph.llm._get_client")
    def test_query_no_fallback(self, mock_get_client: MagicMock) -> None:
        """Without vectors, an empty Cypher result stays empty."""
        add_json = json.dumps({
            "entities": [{"name": "Alice", "label": "Person"}],
            "relationships": [],
        })
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=add_json))]),
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content="MATCH (e:Entity {name: 'NoOne'}) RETURN e.name"
                        )
                    )
                ]
            ),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("Alice is a person")
        results = mem.query("Who is NoOne?")
        assert results == []


class TestMemoryVectorsMissingNumpy:
    """Behaviour when numpy is not installed."""

    def test_missing_numpy_raises(self) -> None:
        """enable_vectors=True without numpy should raise ImportError."""
        import clawgraph.vectors as vec_mod

        original = vec_mod._HAS_NUMPY
        try:
            vec_mod._HAS_NUMPY = False
            with pytest.raises(ImportError, match="numpy"):
                VectorIndex()
        finally:
            vec_mod._HAS_NUMPY = original


class TestMemoryVectorsPersistence:
    """Vector index persistence alongside Kùzu DB."""

    @patch("clawgraph.llm._get_client")
    def test_vectors_persist_to_disk(
        self, mock_get_client: MagicMock, tmp_path: Path
    ) -> None:
        add_json = json.dumps({
            "entities": [{"name": "Alice", "label": "Person"}],
            "relationships": [],
        })
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = _mock_embeddings_create
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=add_json))]
        )
        mock_get_client.return_value = mock_client

        db_dir = tmp_path / "db"
        mem = Memory(db_path=str(db_dir), enable_vectors=True)
        mem.add("Alice is a person")
        mem.close()

        # Vector files should exist alongside the DB.
        vec_dir = tmp_path / "vectors"
        assert vec_dir.exists()
        assert (vec_dir / "vector_names.json").exists()
        assert (vec_dir / "vector_data.npy").exists()
