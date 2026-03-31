"""Python API for ClawGraph — use this in agentic loops.

Usage::

    from clawgraph.memory import Memory

    mem = Memory()
    mem.add("John works at Acme Corp")
    mem.add("Alice is a data scientist at Google")
    results = mem.query("Who works where?")

    # Batch mode — one LLM call for multiple facts
    mem.add_batch([
        "Bob is a designer at Netflix",
        "Carol manages the engineering team at Acme",
        "Bob and Carol are married",
    ])

    # Direct access
    mem.entities()
    mem.relationships()
    mem.export()

    # Persistence — init_facts bootstraps the graph on first run
    mem = Memory(init_facts=["Alice is a data scientist"])

    # Snapshots
    mem.save_snapshot("backup.tar.gz")
    restored = Memory.from_snapshot("backup.tar.gz", "/tmp/restored_db")

    # Config injection — bypass config files entirely
    mem = Memory(config={"llm": {"model": "gpt-4o"}, "db": {"path": ":memory:"}})

    # Hybrid retrieval — enable vector fallback for fuzzy matching
    mem = Memory(enable_vectors=True)
    mem.add("Alice works at Acme Corp")
    # If Cypher returns no results, falls back to vector similarity search
    mem.query("Tell me about the company Acme Corp")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clawgraph.cypher import sanitize_cypher, validate_cypher
from clawgraph.db import GraphDB
from clawgraph.llm import (
    LLMError,
    build_merge_cypher,
    generate_cypher,
    infer_ontology,
    infer_ontology_batch,
)
from clawgraph.ontology import Ontology

if TYPE_CHECKING:
    from clawgraph.vectors import VectorIndex

log = logging.getLogger(__name__)


class Memory:
    """High-level Python API for graph memory operations.

    Designed for use inside agentic loops where performance matters.
    The DB and ontology are initialized once and reused across calls.
    """

    def __init__(
        self,
        db_path: str | None = None,
        model: str | None = None,
        ontology_dir: str | None = None,
        allowed_labels: list[str] | None = None,
        allowed_relationship_types: list[str] | None = None,
        ontology: Ontology | None = None,
        init_facts: list[str] | None = None,
        config: dict[str, Any] | None = None,
        enable_vectors: bool = False,
    ) -> None:
        """Initialize the memory layer.

        Args:
            db_path: Path to Kùzu database. Defaults to ~/.clawgraph/data.
                     Use ':memory:' for ephemeral storage.
            model: LLM model override. Defaults to config value.
            ontology_dir: Path to ontology storage dir.
            allowed_labels: Constrain entity extraction to these labels.
            allowed_relationship_types: Constrain relationship extraction
                                        to these types.
            ontology: Pass a pre-configured Ontology instance directly.
                      Overrides ontology_dir, allowed_labels, and
                      allowed_relationship_types if provided.
            init_facts: List of facts to seed on first initialization.
                        Uses MERGE so repeated init is idempotent.
            config: Dict to override config-file values. Supports
                    keys like ``{"llm": {"model": "..."}, "db": {"path": "..."}}``.
                    Explicit ``db_path`` / ``model`` params take priority.
            enable_vectors: Enable vector embeddings for hybrid retrieval.
                            When ``True``, entity names are embedded and
                            stored in a vector index.  If a Cypher query
                            returns no results, the system falls back to
                            cosine-similarity search and traverses the
                            graph neighbourhood of matching entities.
                            Requires numpy: ``pip install clawgraph[vectors]``
        """
        # Apply config dict if provided
        if config:
            if db_path is None:
                db_path = config.get("db", {}).get("path")
            if model is None:
                model = config.get("llm", {}).get("model")

        self._db = GraphDB(db_path=db_path)
        self._db.ensure_base_schema()
        if ontology is not None:
            self._ontology = ontology
        else:
            self._ontology = Ontology(
                config_dir=ontology_dir,
                allowed_labels=allowed_labels,
                allowed_relationship_types=allowed_relationship_types,
            )
        self._model = model

        # Vector support (optional — requires numpy)
        self._vectors_enabled = enable_vectors
        self._vector_index: VectorIndex | None = None
        if enable_vectors:
            self._init_vectors()

        # Seed initial facts (idempotent via MERGE)
        if init_facts:
            self.add_batch(init_facts)

    def add(self, statement: str) -> AddResult:
        """Add a single fact to graph memory.

        Args:
            statement: Natural language statement (e.g., "John works at Acme").

        Returns:
            AddResult with entities, relationships, and execution status.
        """
        inferred = infer_ontology(
            statement,
            existing_ontology=self._ontology.to_context_string(),
            model=self._model,
        )

        entities = inferred.get("entities", [])
        relationships = inferred.get("relationships", [])

        result = self._execute_inferred(entities, relationships)
        if self._vectors_enabled:
            self._store_embeddings(entities)
        return result

    def add_batch(self, statements: list[str]) -> AddResult:
        """Add multiple facts in a single LLM call.

        This is significantly faster than calling add() in a loop
        because it batches all statements into one LLM request.

        Args:
            statements: List of natural language statements.

        Returns:
            Combined AddResult for all statements.
        """
        if not statements:
            return AddResult(entities=[], relationships=[], executed=0, errors=[])

        inferred = infer_ontology_batch(
            statements,
            existing_ontology=self._ontology.to_context_string(),
            model=self._model,
        )

        entities = inferred.get("entities", [])
        relationships = inferred.get("relationships", [])

        result = self._execute_inferred(entities, relationships)
        if self._vectors_enabled:
            self._store_embeddings(entities)
        return result

    def query(self, question: str) -> list[dict[str, Any]]:
        """Query graph memory with natural language.

        When ``enable_vectors=True`` and the Cypher query returns no
        results, the system falls back to vector similarity search over
        entity names and then traverses the graph neighbourhood of
        matching entities (1-2 hops).

        Args:
            question: Natural language question.

        Returns:
            List of result rows as dictionaries.
        """
        raw_cypher = generate_cypher(
            question,
            ontology_context=self._ontology.to_context_string(),
            model=self._model,
            mode="read",
        )

        cypher = sanitize_cypher(raw_cypher)
        validation = validate_cypher(cypher)

        if not validation:
            raise LLMError(f"Generated invalid Cypher: {validation.errors}")

        results = self._db.execute(cypher)

        if not results and self._vectors_enabled:
            results = self._vector_fallback(question)

        return results

    def entities(self) -> list[dict[str, Any]]:
        """Get all entities in the graph."""
        return self._db.get_all_entities()

    def relationships(self) -> list[dict[str, Any]]:
        """Get all relationships in the graph."""
        return self._db.get_all_relationships()

    def export(self) -> dict[str, Any]:
        """Export the full graph as a dictionary."""
        return {
            "entities": self._db.get_all_entities(),
            "relationships": self._db.get_all_relationships(),
            "ontology": self._ontology.to_dict(),
        }

    def get_ontology(self) -> Ontology:
        """Get the ontology manager."""
        return self._ontology

    def close(self) -> None:
        """Close the database connection."""
        self._db.close()

    def save_snapshot(self, output_path: str | Path) -> Path:
        """Save a snapshot of the database as a .tar.gz archive.

        Args:
            output_path: Path for the output archive.

        Returns:
            The Path to the created archive.
        """
        return self._db.save_snapshot(output_path)

    @classmethod
    def from_snapshot(
        cls,
        archive_path: str | Path,
        target_dir: str | Path,
        **kwargs: Any,
    ) -> Memory:
        """Restore a Memory instance from a snapshot archive.

        Args:
            archive_path: Path to the .tar.gz archive.
            target_dir: Directory to extract the DB into.
            **kwargs: Additional arguments forwarded to Memory.__init__()
                      (e.g., model, ontology_dir, allowed_labels).

        Returns:
            A new Memory instance backed by the restored database.
        """
        restored_db = GraphDB.load_snapshot(archive_path, target_dir)
        db_path = restored_db.db_path
        restored_db.close()
        return cls(db_path=db_path, **kwargs)

    def _execute_inferred(
        self,
        entities: list[dict[str, str]],
        relationships: list[dict[str, str]],
    ) -> AddResult:
        """Execute inferred entities/relationships against the DB."""
        cypher = build_merge_cypher(entities, relationships)

        executed: list[str] = []
        errors: list[str] = []

        for line in cypher.split("\n"):
            line = line.strip()
            if not line:
                continue

            clean = sanitize_cypher(line)
            validation = validate_cypher(clean)

            if not validation:
                errors.append(f"Validation failed: {clean} — {validation.errors}")
                continue

            try:
                self._db.execute(clean)
                executed.append(clean)
            except Exception as e:
                errors.append(f"DB error: {e}")

        # Update ontology
        for entity in entities:
            self._ontology.add_node_label(
                entity.get("label", "Unknown"), {"name": "STRING"}
            )
        for rel in relationships:
            from_label = self._find_label(rel.get("from", ""), entities)
            to_label = self._find_label(rel.get("to", ""), entities)
            self._ontology.add_relationship_type(
                rel.get("type", "RELATED_TO"), from_label, to_label
            )

        return AddResult(
            entities=entities,
            relationships=relationships,
            executed=len(executed),
            errors=errors,
        )

    @staticmethod
    def _find_label(name: str, entities: list[dict[str, str]]) -> str:
        """Find the label for an entity by name."""
        for entity in entities:
            if entity.get("name") == name:
                return entity.get("label", "Unknown")
        return "Unknown"

    # -- vector helpers -----------------------------------------------------

    def _init_vectors(self) -> None:
        """Initialize the vector index (called when ``enable_vectors=True``)."""
        try:
            from clawgraph.vectors import VectorIndex
        except ImportError:
            raise ImportError(
                "Vector support requires numpy. "
                "Install it with:  pip install clawgraph[vectors]"
            ) from None

        persist_dir: str | None = None
        db_path_str = self._db.db_path
        if db_path_str != ":memory:":
            persist_dir = str(Path(db_path_str).parent / "vectors")

        self._vector_index = VectorIndex(persist_dir=persist_dir)

    def _store_embeddings(self, entities: list[dict[str, str]]) -> None:
        """Compute and store embeddings for entity names."""
        if self._vector_index is None:
            return

        from clawgraph.vectors import get_embeddings

        names = [e["name"] for e in entities if "name" in e]
        if not names:
            return

        try:
            embeddings = get_embeddings(names)
        except Exception:
            log.debug("Failed to compute embeddings — skipping vector store")
            return

        for name, emb in zip(names, embeddings):
            self._vector_index.add(name, emb)
        self._vector_index.save()

    def _vector_fallback(self, question: str) -> list[dict[str, Any]]:
        """Fall back to vector similarity search when Cypher yields nothing.

        Embeds the *question*, searches the vector index for the closest
        entity names, then traverses 1-2 hops in the graph to collect
        related context.
        """
        if self._vector_index is None or len(self._vector_index) == 0:
            return []

        from clawgraph.vectors import get_embeddings

        try:
            query_emb = get_embeddings([question])[0]
        except Exception:
            log.debug("Failed to compute query embedding — skipping fallback")
            return []

        matches = self._vector_index.search(query_emb, top_k=5)
        if not matches:
            return []

        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for entity_name, _score in matches:
            neighbourhood = self._get_neighbourhood(entity_name)
            for row in neighbourhood:
                key = str(row)
                if key not in seen:
                    seen.add(key)
                    results.append(row)

        return results

    def _get_neighbourhood(
        self, entity_name: str, hops: int = 2
    ) -> list[dict[str, Any]]:
        """Retrieve the graph neighbourhood of an entity.

        Fetches the entity itself plus all entities and relationships
        reachable within *hops* traversal steps.
        """
        safe_name = entity_name.replace("'", "\\'")

        # Start with the entity itself.
        entity_rows = self._db.execute(
            f"MATCH (e:Entity {{name: '{safe_name}'}}) "
            f"RETURN e.name, e.label"
        )

        # 1-hop neighbourhood.
        hop1 = self._db.execute(
            f"MATCH (a:Entity {{name: '{safe_name}'}})-[r:Relates]-(b:Entity) "
            f"RETURN a.name, r.type, b.name"
        )

        # 2-hop neighbourhood (only when hops >= 2 and 1-hop found results).
        hop2: list[dict[str, Any]] = []
        if hops >= 2 and hop1:
            hop2 = self._db.execute(
                f"MATCH (a:Entity {{name: '{safe_name}'}})"
                f"-[r1:Relates]-(mid:Entity)"
                f"-[r2:Relates]-(b:Entity) "
                f"WHERE b.name <> '{safe_name}' "
                f"RETURN a.name AS `a.name`, r1.type AS `r1.type`, "
                f"mid.name AS `mid.name`, r2.type AS `r2.type`, "
                f"b.name AS `b.name`"
            )

        return entity_rows + hop1 + hop2


class AddResult:
    """Result of an add/add_batch operation."""

    def __init__(
        self,
        entities: list[dict[str, str]],
        relationships: list[dict[str, str]],
        executed: int,
        errors: list[str],
    ) -> None:
        self.entities = entities
        self.relationships = relationships
        self.executed = executed
        self.errors = errors
        self.ok = len(errors) == 0

    def __repr__(self) -> str:
        return (
            f"AddResult(entities={len(self.entities)}, "
            f"relationships={len(self.relationships)}, "
            f"executed={self.executed}, errors={len(self.errors)})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ok": self.ok,
            "entities": self.entities,
            "relationships": self.relationships,
            "executed": self.executed,
            "errors": self.errors,
        }
