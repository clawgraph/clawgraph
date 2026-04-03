"""Vector index for hybrid retrieval — cosine similarity over entity embeddings.

Uses numpy for lightweight vector operations and the OpenAI embeddings API
(same client already configured for chat completions) for embedding generation.

This module is only loaded when ``enable_vectors=True`` is passed to
:class:`~clawgraph.memory.Memory`.  numpy must be installed separately::

    pip install clawgraph[vectors]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# numpy is an optional dependency — callers must handle ImportError.
try:
    import numpy as np
    import numpy.typing as npt

    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    _HAS_NUMPY = False


def _require_numpy() -> None:
    """Raise a helpful error if numpy is not installed."""
    if not _HAS_NUMPY:
        raise ImportError(
            "Vector support requires numpy. "
            "Install it with:  pip install clawgraph[vectors]"
        )


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


def get_embeddings(
    texts: list[str],
    model: str = "text-embedding-3-small",
) -> list[list[float]]:
    """Compute embeddings via the OpenAI embeddings API.

    Args:
        texts: Strings to embed.
        model: Embedding model name.

    Returns:
        List of embedding vectors (one per input text).

    Raises:
        LLMError: If the API call fails.
    """
    from clawgraph.llm import LLMError, _get_client

    if not texts:
        return []

    try:
        client = _get_client()
        response = client.embeddings.create(input=texts, model=model)
    except Exception as exc:
        raise LLMError(f"Embedding call failed: {exc}") from exc

    # Sort by index to guarantee input order.
    data = sorted(response.data, key=lambda d: d.index)
    return [d.embedding for d in data]


# ---------------------------------------------------------------------------
# VectorIndex
# ---------------------------------------------------------------------------


class VectorIndex:
    """In-memory vector index with optional disk persistence.

    Stores ``(entity_name, embedding)`` pairs and supports cosine-similarity
    search.  The on-disk format is two files inside *persist_dir*:

    * ``vector_names.json``  — ordered list of entity names
    * ``vector_data.npy``    — ``(N, D)`` float32 numpy array

    Args:
        persist_dir: Directory for saving / loading the index.
                     ``None`` keeps the index purely in-memory.
    """

    _NAMES_FILE = "vector_names.json"
    _DATA_FILE = "vector_data.npy"

    def __init__(self, persist_dir: str | Path | None = None) -> None:
        _require_numpy()
        self._persist_dir = Path(persist_dir) if persist_dir else None
        self._names: list[str] = []
        # D=0 means "dimension not yet known"
        self._vectors: npt.NDArray[np.float32] = np.empty(
            (0, 0), dtype=np.float32
        )

        # Try to load existing index from disk.
        if self._persist_dir is not None:
            self._try_load()

    # -- public API ---------------------------------------------------------

    def add(self, name: str, embedding: list[float]) -> None:
        """Add or update an entity embedding.

        Args:
            name: Entity name (used as unique key).
            embedding: Dense vector for the entity.
        """
        vec = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        dim = vec.shape[1]

        if name in self._names:
            idx = self._names.index(name)
            # Handle dimension change on first real insert.
            if self._vectors.shape[1] == 0:
                self._vectors = vec
            else:
                self._vectors[idx] = vec[0]
            return

        self._names.append(name)

        if self._vectors.shape[0] == 0 or self._vectors.shape[1] == 0:
            self._vectors = vec
        else:
            if self._vectors.shape[1] != dim:
                raise ValueError(
                    f"Embedding dimension mismatch: index has "
                    f"{self._vectors.shape[1]}, got {dim}"
                )
            self._vectors = np.vstack([self._vectors, vec])

    def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[tuple[str, float]]:
        """Find the *top_k* closest entity names by cosine similarity.

        Args:
            query_embedding: Query vector.
            top_k: Maximum number of results.

        Returns:
            List of ``(entity_name, similarity_score)`` tuples sorted by
            descending similarity.
        """
        if len(self._names) == 0 or self._vectors.shape[1] == 0:
            return []

        query = np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)

        # Cosine similarity = dot(a, b) / (||a|| * ||b||)
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []

        # Avoid division by zero for stored vectors.
        safe_norms = np.where(norms == 0, 1.0, norms)
        similarities = (self._vectors @ query.T).flatten() / (
            safe_norms.flatten() * query_norm
        )

        k = min(top_k, len(self._names))
        top_indices = np.argsort(similarities)[::-1][:k]

        return [
            (self._names[int(i)], float(similarities[int(i)]))
            for i in top_indices
        ]

    def save(self) -> None:
        """Persist the index to *persist_dir*.

        No-op when ``persist_dir`` is ``None`` (in-memory mode).
        """
        if self._persist_dir is None:
            return

        self._persist_dir.mkdir(parents=True, exist_ok=True)
        names_path = self._persist_dir / self._NAMES_FILE
        data_path = self._persist_dir / self._DATA_FILE

        with open(names_path, "w") as f:
            json.dump(self._names, f)
        np.save(str(data_path), self._vectors)

    def __len__(self) -> int:
        return len(self._names)

    def __contains__(self, name: str) -> bool:
        return name in self._names

    # -- internal -----------------------------------------------------------

    def _try_load(self) -> None:
        """Load index from disk if files exist."""
        if self._persist_dir is None:
            return

        names_path = self._persist_dir / self._NAMES_FILE
        data_path = self._persist_dir / self._DATA_FILE

        if names_path.exists() and data_path.exists():
            with open(names_path) as f:
                loaded: Any = json.load(f)
            self._names = list(loaded)
            self._vectors = np.load(str(data_path)).astype(np.float32)
