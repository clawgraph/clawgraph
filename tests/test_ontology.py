"""Tests for ontology management."""

import json
from pathlib import Path

from clawgraph.ontology import Ontology


class TestOntology:
    """Tests for the Ontology class."""

    def test_starts_empty(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        assert ontology.nodes == {}
        assert ontology.relationships == {}

    def test_add_node_label(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        ontology.add_node_label("Person", {"name": "STRING", "age": "INT64"})
        assert "Person" in ontology.nodes
        assert ontology.nodes["Person"]["name"] == "STRING"

    def test_add_relationship(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        ontology.add_relationship_type("WORKS_AT", "Person", "Organization")
        assert "WORKS_AT" in ontology.relationships
        assert ontology.relationships["WORKS_AT"]["from"] == "Person"

    def test_persists_to_disk(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        ontology.add_node_label("Person", {"name": "STRING"})

        # Reload from disk
        ontology2 = Ontology(config_dir=tmp_path)
        assert "Person" in ontology2.nodes

    def test_to_context_string_empty(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        assert ontology.to_context_string() == "No ontology defined yet."

    def test_to_context_string_with_data(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        ontology.add_node_label("Person", {"name": "STRING"})
        ontology.add_relationship_type("KNOWS", "Person", "Person")
        context = ontology.to_context_string()
        assert "Person" in context
        assert "KNOWS" in context

    def test_clear(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        ontology.add_node_label("Person")
        ontology.clear()
        assert ontology.nodes == {}


class TestOntologyConstraints:
    """Tests for allowed_labels and allowed_relationship_types constraints."""

    def test_allowed_labels_default_none(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        assert ontology.allowed_labels is None

    def test_allowed_relationship_types_default_none(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        assert ontology.allowed_relationship_types is None

    def test_set_allowed_labels(self, tmp_path: Path) -> None:
        ontology = Ontology(
            config_dir=tmp_path,
            allowed_labels=["Person", "Company"],
        )
        assert ontology.allowed_labels == ["Person", "Company"]

    def test_set_allowed_relationship_types(self, tmp_path: Path) -> None:
        ontology = Ontology(
            config_dir=tmp_path,
            allowed_relationship_types=["WORKS_AT", "KNOWS"],
        )
        assert ontology.allowed_relationship_types == ["WORKS_AT", "KNOWS"]

    def test_context_string_includes_allowed_labels(self, tmp_path: Path) -> None:
        ontology = Ontology(
            config_dir=tmp_path,
            allowed_labels=["Person", "Company"],
        )
        ctx = ontology.to_context_string()
        assert "ALLOWED entity labels (use ONLY these): Person, Company" in ctx

    def test_context_string_includes_allowed_rels(self, tmp_path: Path) -> None:
        ontology = Ontology(
            config_dir=tmp_path,
            allowed_relationship_types=["WORKS_AT", "MANAGES"],
        )
        ctx = ontology.to_context_string()
        assert "ALLOWED relationship types (use ONLY these): WORKS_AT, MANAGES" in ctx

    def test_context_string_constraints_only(self, tmp_path: Path) -> None:
        """Constraints alone should produce a context string (not 'No ontology')."""
        ontology = Ontology(
            config_dir=tmp_path,
            allowed_labels=["Person"],
        )
        ctx = ontology.to_context_string()
        assert ctx != "No ontology defined yet."
        assert "Person" in ctx

    def test_context_string_constraints_with_data(self, tmp_path: Path) -> None:
        ontology = Ontology(
            config_dir=tmp_path,
            allowed_labels=["Person", "Skill"],
            allowed_relationship_types=["HAS_SKILL"],
        )
        ontology.add_node_label("Person", {"name": "STRING"})
        ctx = ontology.to_context_string()
        assert "ALLOWED entity labels" in ctx
        assert "ALLOWED relationship types" in ctx
        assert "Node labels:" in ctx

    def test_to_dict_includes_constraints(self, tmp_path: Path) -> None:
        ontology = Ontology(
            config_dir=tmp_path,
            allowed_labels=["Person"],
            allowed_relationship_types=["KNOWS"],
        )
        d = ontology.to_dict()
        assert d["allowed_labels"] == ["Person"]
        assert d["allowed_relationship_types"] == ["KNOWS"]

    def test_to_dict_omits_constraints_when_none(self, tmp_path: Path) -> None:
        ontology = Ontology(config_dir=tmp_path)
        d = ontology.to_dict()
        assert "allowed_labels" not in d
        assert "allowed_relationship_types" not in d
