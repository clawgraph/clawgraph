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

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from clawgraph.cypher import sanitize_cypher, validate_cypher
from clawgraph.db import GraphDB
from clawgraph.llm import (
    LLMError,
    build_merge_cypher_groups,
    generate_cypher,
    infer_ontology,
    infer_ontology_batch,
    select_relationships_for_retraction,
    select_relevant_entities,
)
from clawgraph.ontology import Ontology


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

        return self._db.execute(cypher)

    def recall(self, context: str, max_tokens: int = 2000, hops: int = 2) -> str:
        """Recall relevant existing facts as an agent-friendly text block.

        Counts one UTF-8 byte per token, including separators: a deliberately
        conservative, Unicode-aware approximation, not a model tokenizer.
        Graph values are JSON-quoted with ASCII escapes and must be treated
        as untrusted data. Only complete facts are kept; lower-ranked trailing
        facts are removed when the next fact would exceed the budget.
        The LLM sees at most 200 names/labels (16,000 JSON characters), locally
        prioritized by context word overlap. Large graphs can omit semantic
        matches outside this shortlist; no unrelated facts are substituted.

        Args:
            context: Natural language context used to rank existing entities.
            max_tokens: Approximate output token budget.
            hops: Neighborhood traversal distance, one or two.

        Returns:
            Quoted, escaped fact lines in relevance order.

        Raises:
            ValueError: If context, max_tokens, or hops has an invalid value/type.
            LLMError: If entity selection fails or returns malformed data.
        """
        if not isinstance(context, str):
            raise ValueError("context must be a string")
        if type(max_tokens) is not int or max_tokens < 0:
            raise ValueError("max_tokens must be a nonnegative integer")
        if type(hops) is not int or hops not in (1, 2):
            raise ValueError("hops must be an integer of 1 or 2")
        if not context.strip() or max_tokens == 0:
            return ""
        candidates = self._recall_candidates(context)
        if not candidates:
            return ""
        names = select_relevant_entities(context, candidates, model=self._model)
        facts: dict[str, None] = {}
        for name in names:
            neighborhood = self._db.get_neighborhood(name, hops=hops)
            for entity in neighborhood["entities"]:
                facts[
                    f'- Entity {json.dumps(entity["name"])} '
                    f'(label {json.dumps(entity["label"])}).'
                ] = None
            for rel in neighborhood["relationships"]:
                facts[
                    f'- {json.dumps(rel["from"])} --{json.dumps(rel["type"])}'
                    f'--> {json.dumps(rel["to"])}.'
                ] = None
        kept: list[str] = []
        used = 0
        for fact in facts:
            cost = len(fact.encode("utf-8")) + bool(kept)
            if used + cost > max_tokens:
                break
            kept.append(fact)
            used += cost
        return "\n".join(kept)

    def _recall_candidates(self, context: str) -> list[dict[str, Any]]:
        """Bound graph data sent to the model with a stable local shortlist."""
        words = set(re.findall(r"\w+", context.casefold()))

        def priority(row: dict[str, Any]) -> tuple[int, str]:
            text = f'{row["e.name"]} {row["e.label"]}'.casefold()
            overlap = len(words.intersection(re.findall(r"\w+", text)))
            return -overlap, str(row["e.name"])

        candidates: list[dict[str, Any]] = []
        size = 2
        for row in sorted(self.entities(), key=priority):
            candidate = {"name": row["e.name"], "label": row["e.label"]}
            cost = len(json.dumps(candidate)) + (2 if candidates else 0)
            if size + cost > 16000:
                continue
            candidates.append(candidate)
            size += cost
            if len(candidates) == 200:
                break
        return candidates

    def entities(self) -> list[dict[str, Any]]:
        """Get all entities in the graph."""
        return self._db.get_all_entities()

    def delete_entity(self, name: str) -> bool:
        """Delete an exact entity, cascading all its relationships.

        Args:
            name: Nonempty exact entity name; requires caller authorization.

        Returns:
            Whether an entity was deleted. Repeated deletion is a no-op.

        Raises:
            ValueError: If name is invalid.
            DatabaseError: If deletion fails and is rolled back.
            OSError: If separate ontology JSON persistence fails after commit.
        """
        deleted = self._db.delete_entity(name)
        if deleted:
            self._synchronize_ontology()
        return deleted

    def _synchronize_ontology(self) -> None:
        """Refresh ontology only after a successful database commit."""
        self._ontology.synchronize(self.entities(), self.relationships())

    def retract(self, statement: str) -> int:
        """Retract exact stored relationships while preserving endpoint entities.

        Sends at most 200 relationship triples (16,000 JSON characters) to
        the LLM, prioritizing lexical overlap. Matches outside this bounded
        shortlist may be missed; ambiguous or unmatched input is a no-op.

        Args:
            statement: Natural-language fact to retract; requires authorization.

        Returns:
            Number of matching edges removed atomically.

        Raises:
            ValueError: If statement is not a nonempty string.
            LLMError: If relationship selection fails.
            DatabaseError: If any deletion fails; all deletions are rolled back.
            OSError: If separate ontology persistence fails after graph commit.
        """
        selected = self._select_retractions(statement)
        removed = self._db.delete_relationships(selected)
        if removed:
            self._synchronize_ontology()
        return removed

    def _select_retractions(self, statement: str) -> list[dict[str, str]]:
        """Select only existing relationships, never model-generated queries."""
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("statement must be a nonempty string")
        rows = [
            {"from": row["a.name"], "to": row["b.name"], "type": row["r.type"]}
            for row in self.relationships()
            if all(isinstance(row[key], str) and row[key].strip()
                   for key in ("a.name", "b.name", "r.type"))
        ]
        words = set(re.findall(r"\w+", statement.casefold()))

        def priority(rel: dict[str, str]) -> tuple[int, str, str, str]:
            text = " ".join(rel.values()).casefold()
            return (
                -len(words.intersection(re.findall(r"\w+", text))),
                rel["from"], rel["to"], rel["type"],
            )

        candidates: list[dict[str, str]] = []
        size = 2
        for rel in sorted(rows, key=priority):
            cost = len(json.dumps(rel)) + (2 if candidates else 0)
            if size + cost > 16000:
                continue
            candidates.append(rel)
            size += cost
            if len(candidates) == 200:
                break
        if not candidates:
            return []
        return select_relationships_for_retraction(
            statement, candidates, model=self._model,
        )

    def update(self, old: str, new: str) -> AddResult:
        """Correct an existing fact in one atomic graph transaction.

        Old-fact selection uses the same bounded shortlist as retract().
        Replacement extraction must contain at least one relationship; each
        endpoint must already exist or be present in the extracted entities.
        Selection and full validation finish before mutation. Existing endpoint
        entities and creation timestamps for retained facts are preserved.
        Ontology JSON is synchronized separately after the graph commit.

        Args:
            old: Fact whose existing relationship triples should be replaced.
            new: Replacement fact; requires caller authorization.

        Returns:
            AddResult counting replacement entity and relationship groups.

        Raises:
            ValueError: If old/new is empty or the old fact cannot be found.
            LLMError: If selection or extraction fails before mutation.
            DatabaseError: If any write fails; the old fact remains intact.
            OSError: If separate ontology persistence fails after graph commit.
        """
        for text, field in ((old, "old"), (new, "new")):
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{field} must be a nonempty string")
        selected = self._select_retractions(old)
        if not selected:
            raise ValueError("No matching old fact found; nothing was changed")
        try:
            inferred = infer_ontology(
                new, existing_ontology=self._ontology.to_context_string(), model=self._model,
            )
        except (AttributeError, IndexError, KeyError, TypeError, ValueError, RecursionError) as exc:
            raise LLMError("Invalid replacement extraction response") from exc
        entities, relationships = self._validated_replacement(inferred)
        self._db.replace_relationships(selected, entities, relationships)
        self._synchronize_ontology()
        return AddResult(
            entities=entities, relationships=relationships,
            executed=len(entities) + len(relationships), errors=[],
        )

    def _validated_replacement(
        self, inferred: object,
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Validate the complete replacement before issuing any writes."""
        if not isinstance(inferred, dict) or set(inferred) != {"entities", "relationships"}:
            raise LLMError("Invalid replacement: expected entities and relationships")
        entities = self._replacement_records(inferred["entities"], ("name", "label"))
        relationships = self._replacement_records(inferred["relationships"], ("from", "to", "type"))
        if not relationships:
            raise LLMError("Replacement must contain at least one relationship")
        by_name: dict[str, dict[str, str]] = {}
        for entity in entities:
            if (
                self._ontology.allowed_labels is not None
                and entity["label"] not in self._ontology.allowed_labels
            ):
                raise LLMError("Replacement entity label is not allowed")
            name = entity["name"]
            if name in by_name and by_name[name] != entity:
                raise LLMError("Replacement contains conflicting labels for one entity")
            by_name[name] = entity
        known = {row["e.name"] for row in self.entities()} | set(by_name)
        for rel in relationships:
            if (
                self._ontology.allowed_relationship_types is not None
                and rel["type"] not in self._ontology.allowed_relationship_types
            ):
                raise LLMError("Replacement relationship type is not allowed")
            if rel["from"] not in known or rel["to"] not in known:
                raise LLMError("Replacement relationship refers to a missing endpoint")
        unique = {(rel["from"], rel["to"], rel["type"]): rel for rel in relationships}
        return list(by_name.values()), list(unique.values())

    @staticmethod
    def _replacement_records(value: object, fields: tuple[str, ...]) -> list[dict[str, str]]:
        """Require exact record shapes and nonempty string values."""
        if not isinstance(value, list):
            raise LLMError("Replacement entities and relationships must be lists")
        result: list[dict[str, str]] = []
        for row in value:
            if (
                not isinstance(row, dict) or set(row) != set(fields)
                or any(not isinstance(item, str) or not item.strip() for item in row.values())
            ):
                raise LLMError("Invalid replacement record")
            result.append({field: row[field] for field in fields})
        return result

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
        cypher_groups = build_merge_cypher_groups(entities, relationships)

        executed = 0
        errors: list[str] = []

        for group in cypher_groups:
            if self._execute_cypher_group(group, errors):
                executed += 1

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
            executed=executed,
            errors=errors,
        )

    def _execute_cypher_group(self, lines: list[str], errors: list[str]) -> bool:
        """Execute a logical write composed of one or more Cypher statements."""
        if not lines:
            return False

        clean_lines: list[str] = []
        for line in lines:
            clean = sanitize_cypher(line)
            validation = validate_cypher(clean)

            if not validation:
                errors.append(f"Validation failed: {clean} — {validation.errors}")
                return False

            clean_lines.append(clean)

        conn = self._db.connection

        try:
            conn.execute("BEGIN TRANSACTION")
        except Exception as e:
            errors.append(f"DB error: {e}")
            return False

        try:
            for clean in clean_lines:
                conn.execute(clean)
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass

            errors.append(f"DB error: {e}")
            return False

        return True

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
            "entities": deepcopy(self.entities),
            "relationships": deepcopy(self.relationships),
            "executed": self.executed,
            "errors": list(self.errors),
        }
