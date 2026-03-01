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
