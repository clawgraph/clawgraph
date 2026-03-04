"""Ontology management — tracks node labels, relationship types, and properties."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


class Ontology:
    """Manages the graph schema / ontology.

    Tracks known node labels, relationship types, and their properties.
    Feeds this context into LLM prompts for consistent Cypher generation.

    Can be seeded with allowed labels and relationship types to constrain
    what the LLM extracts. This is useful for domain-specific applications.

    Example::

        ontology = Ontology(
            allowed_labels=["Person", "Company", "Skill"],
            allowed_relationship_types=["WORKS_AT", "HAS_SKILL", "MANAGES"],
        )
    """

    def __init__(
        self,
        config_dir: str | Path | None = None,
        allowed_labels: list[str] | None = None,
        allowed_relationship_types: list[str] | None = None,
    ) -> None:
        """Initialize the ontology manager.

        Args:
            config_dir: Directory for ontology storage.
                        Defaults to ~/.clawgraph.
            allowed_labels: If set, constrain entity extraction to only
                            these labels (e.g., ["Person", "Company"]).
            allowed_relationship_types: If set, constrain relationship
                            extraction to only these types (e.g., ["WORKS_AT"]).
        """
        if config_dir is None:
            config_dir = Path.home() / ".clawgraph"
        self._config_dir = Path(config_dir)
        self._ontology_path = self._config_dir / "ontology.json"
        self._allowed_labels = allowed_labels
        self._allowed_relationship_types = allowed_relationship_types
        self._schema: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        """Load ontology from disk."""
        if self._ontology_path.exists():
            with open(self._ontology_path) as f:
                return cast(dict[str, Any], json.load(f))
        return {"nodes": {}, "relationships": {}}

    def _save(self) -> None:
        """Persist ontology to disk."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._ontology_path, "w") as f:
            json.dump(self._schema, f, indent=2)

    @property
    def nodes(self) -> dict[str, dict[str, str]]:
        """Get all node labels and their properties."""
        return cast(dict[str, dict[str, str]], self._schema.get("nodes", {}))

    @property
    def relationships(self) -> dict[str, dict[str, Any]]:
        """Get all relationship types and their properties."""
        return cast(dict[str, dict[str, Any]], self._schema.get("relationships", {}))

    def add_node_label(self, label: str, properties: dict[str, str] | None = None) -> None:
        """Register a node label with optional properties.

        Args:
            label: The node label (e.g., 'Person', 'Organization').
            properties: Dict of property_name -> type_string.
        """
        if label not in self._schema["nodes"]:
            self._schema["nodes"][label] = {}
        if properties:
            self._schema["nodes"][label].update(properties)
        self._save()

    def add_relationship_type(
        self,
        rel_type: str,
        from_label: str,
        to_label: str,
        properties: dict[str, str] | None = None,
    ) -> None:
        """Register a relationship type.

        Args:
            rel_type: The relationship type (e.g., 'WORKS_AT').
            from_label: Source node label.
            to_label: Target node label.
            properties: Dict of property_name -> type_string.
        """
        self._schema["relationships"][rel_type] = {
            "from": from_label,
            "to": to_label,
            "properties": properties or {},
        }
        self._save()

    @property
    def allowed_labels(self) -> list[str] | None:
        """Get allowed entity labels, if constrained."""
        return self._allowed_labels

    @property
    def allowed_relationship_types(self) -> list[str] | None:
        """Get allowed relationship types, if constrained."""
        return self._allowed_relationship_types

    def to_context_string(self) -> str:
        """Serialize the ontology into a string for LLM context.

        Includes constraints if allowed_labels or allowed_relationship_types
        were set.

        Returns:
            Human-readable ontology description for LLM prompts.
        """
        lines: list[str] = []

        # Constraints section
        if self._allowed_labels:
            lines.append(f"ALLOWED entity labels (use ONLY these): {', '.join(self._allowed_labels)}")
        if self._allowed_relationship_types:
            lines.append(f"ALLOWED relationship types (use ONLY these): {', '.join(self._allowed_relationship_types)}")

        if not self._schema["nodes"] and not self._schema["relationships"] and not lines:
            return "No ontology defined yet."

        if self._schema["nodes"]:
            lines.append("Node labels:")
            for label, props in self._schema["nodes"].items():
                prop_str = ", ".join(f"{k}: {v}" for k, v in props.items())
                lines.append(f"  - {label}({prop_str})" if prop_str else f"  - {label}")

        if self._schema["relationships"]:
            lines.append("Relationship types:")
            for rel_type, info in self._schema["relationships"].items():
                lines.append(f"  - (:{info['from']})-[:{rel_type}]->(:{info['to']})")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Return the ontology as a dictionary."""
        result = self._schema.copy()
        if self._allowed_labels:
            result["allowed_labels"] = self._allowed_labels
        if self._allowed_relationship_types:
            result["allowed_relationship_types"] = self._allowed_relationship_types
        return result

    def clear(self) -> None:
        """Clear the ontology."""
        self._schema = {"nodes": {}, "relationships": {}}
        self._save()
