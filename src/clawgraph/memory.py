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

from copy import deepcopy
from pathlib import Path
from typing import Any

from clawgraph.cypher import sanitize_cypher, validate_cypher
from clawgraph.db import GraphDB
from clawgraph.llm import (
    LLMError,
    build_merge_cypher_groups,
    generate_cypher,
    identify_relevant_entities,
    infer_ontology,
    infer_ontology_batch,
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

    def recall(self, context: str, max_tokens: int = 2000) -> str:
        """Recall relevant knowledge for context injection into agent prompts.

        This is the primary API for agent integration. Instead of writing
        Cypher queries, agents describe what they're working on and get
        back a pre-formatted block of relevant knowledge.

        Flow:
            1. Get all entity names from the graph
            2. Ask the LLM which entities are relevant to the context
            3. For each relevant entity, traverse 1-2 hops in the graph
            4. Serialize the subgraph as natural language
            5. Trim to the token budget

        Args:
            context: Description of what the agent is working on
                (e.g., "user is asking about deployment").
            max_tokens: Approximate token budget for the output.
                Uses the heuristic of 4 characters ≈ 1 token.

        Returns:
            Natural language summary of relevant knowledge, suitable for
            system prompt injection. Returns empty string if nothing
            relevant is found or the graph is empty.
        """
        if not context or not context.strip():
            return ""

        # Step 1: Get all entity names
        all_entities = self._db.get_all_entities()
        if not all_entities:
            return ""

        entity_names = [e["e.name"] for e in all_entities]

        # Step 2: Identify relevant entities via LLM
        relevant_names = identify_relevant_entities(
            context, entity_names, model=self._model
        )

        if not relevant_names:
            return ""

        # Step 3: Traverse neighborhood for each relevant entity
        # Collect unique facts as (source, rel_type, target) tuples
        seen_facts: set[tuple[str, str, str]] = set()
        facts: list[tuple[str, str, str, str, str]] = []
        entity_labels: dict[str, str] = {}

        for name in relevant_names:
            neighborhood = self._db.get_neighborhood(name, hops=2)
            center = neighborhood.get("entity")
            if center:
                entity_labels[center["e.name"]] = center.get("e.label", "")

            for ent in neighborhood.get("entities", []):
                entity_labels[ent["e.name"]] = ent.get("e.label", "")

            for rel in neighborhood.get("relationships", []):
                fact_key = (rel["a.name"], rel["r.type"], rel["b.name"])
                if fact_key not in seen_facts:
                    seen_facts.add(fact_key)
                    a_label = entity_labels.get(rel["a.name"], "")
                    b_label = entity_labels.get(rel["b.name"], "")
                    facts.append(
                        (rel["a.name"], a_label, rel["r.type"], rel["b.name"], b_label)
                    )

        if not facts:
            return ""

        # Step 4: Serialize as natural language
        # Order: facts about entities in relevance order first
        lines = _serialize_facts(facts, relevant_names)

        # Step 5: Trim to token budget (4 chars ≈ 1 token)
        max_chars = max_tokens * 4
        header = "Known facts:\n"
        result_lines: list[str] = []
        current_chars = len(header)

        for line in lines:
            line_chars = len(line) + 1  # +1 for newline
            if current_chars + line_chars > max_chars:
                break
            result_lines.append(line)
            current_chars += line_chars

        if not result_lines:
            return ""

        return header + "\n".join(result_lines)

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


def _serialize_facts(
    facts: list[tuple[str, str, str, str, str]],
    relevance_order: list[str],
) -> list[str]:
    """Serialize relationship facts as natural language lines.

    Facts involving entities earlier in ``relevance_order`` appear first.
    Each fact is rendered as:
        ``- {source} ({label}) {rel_type} {target} ({label})``

    Args:
        facts: List of (source_name, source_label, rel_type, target_name,
               target_label) tuples.
        relevance_order: Entity names ordered by relevance (most relevant
                         first). Used for sorting output.

    Returns:
        List of formatted fact strings (without the "Known facts:" header).
    """
    # Build a relevance rank map for sorting
    rank: dict[str, int] = {name: i for i, name in enumerate(relevance_order)}
    high = len(relevance_order)

    def _sort_key(fact: tuple[str, str, str, str, str]) -> int:
        # Prefer facts that mention higher-ranked entities
        return min(rank.get(fact[0], high), rank.get(fact[3], high))

    sorted_facts = sorted(facts, key=_sort_key)

    lines: list[str] = []
    for src_name, src_label, rel_type, tgt_name, tgt_label in sorted_facts:
        # Format relationship type: WORKS_AT -> works at
        readable_rel = rel_type.replace("_", " ").lower()
        src_part = f"{src_name} ({src_label})" if src_label else src_name
        tgt_part = f"{tgt_name} ({tgt_label})" if tgt_label else tgt_name
        lines.append(f"- {src_part} {readable_rel} {tgt_part}")

    return lines


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
