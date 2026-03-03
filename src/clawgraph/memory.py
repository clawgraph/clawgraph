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
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

logger = logging.getLogger(__name__)


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

        return self._execute_inferred(entities, relationships)

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

        return self._execute_inferred(entities, relationships)

    def query(self, question: str) -> list[dict[str, Any]]:
        """Query graph memory with natural language.

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

        # Increment access counts for returned entities
        self._increment_access_counts(results)

        return results

    def prune(
        self,
        max_age_days: int | None = None,
        min_access_count: int | None = None,
    ) -> list[str]:
        """Remove stale or rarely-accessed entities.

        Args:
            max_age_days: Remove entities not accessed for this many days.
                          Uses last_accessed timestamp (falls back to
                          created_at if never accessed).
            min_access_count: Remove entities with access_count below
                              this threshold.

        Returns:
            List of entity names that were removed.
        """
        if max_age_days is None and min_access_count is None:
            return []

        if not self._db.has_node_table("Entity"):
            return []

        removed: list[str] = []

        if max_age_days is not None:
            removed.extend(self._prune_by_age(max_age_days))

        if min_access_count is not None:
            removed.extend(self._prune_by_access_count(min_access_count))

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for name in removed:
            if name not in seen:
                seen.add(name)
                unique.append(name)

        for name in unique:
            logger.info("Pruned entity: %s", name)

        return unique

    def _prune_by_age(self, max_age_days: int) -> list[str]:
        """Remove entities not accessed within max_age_days."""
        rows = self._db.execute(
            "MATCH (e:Entity) RETURN e.name, e.last_accessed, e.created_at"
        )
        to_remove: list[str] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            last = row.get("e.last_accessed") or row.get("e.created_at") or ""
            if not last:
                to_remove.append(row["e.name"])
                continue
            try:
                ts = datetime.fromisoformat(last)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (now - ts).days
                if age >= max_age_days:
                    to_remove.append(row["e.name"])
            except (ValueError, TypeError):
                to_remove.append(row["e.name"])

        for name in to_remove:
            self._db.execute(
                "MATCH (e:Entity {name: $name}) DETACH DELETE e",
                {"name": name},
            )
        return to_remove

    def _prune_by_access_count(self, min_access_count: int) -> list[str]:
        """Remove entities with access_count below the threshold."""
        rows = self._db.execute(
            "MATCH (e:Entity) WHERE COALESCE(e.access_count, 0) < $min "
            "RETURN e.name",
            {"min": min_access_count},
        )
        names = [row["e.name"] for row in rows]
        for name in names:
            self._db.execute(
                "MATCH (e:Entity {name: $name}) DETACH DELETE e",
                {"name": name},
            )
        return names

    def _increment_access_counts(self, results: list[dict[str, Any]]) -> None:
        """Increment access_count and update last_accessed for entities in results."""
        if not self._db.has_node_table("Entity"):
            return

        entity_names: set[str] = set()
        for row in results:
            for key, value in row.items():
                if key.startswith("e.name") or key.endswith(".name"):
                    if isinstance(value, str):
                        entity_names.add(value)

        now = GraphDB.now_iso()
        for name in entity_names:
            try:
                self._db.execute(
                    "MATCH (e:Entity {name: $name}) "
                    "SET e.access_count = COALESCE(e.access_count, 0) + 1, "
                    "e.last_accessed = $now",
                    {"name": name, "now": now},
                )
            except Exception:
                pass  # Entity may not exist or column missing

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
