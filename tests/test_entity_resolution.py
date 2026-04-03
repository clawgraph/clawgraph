"""Tests for entity resolution and deduplication (F21)."""

from unittest.mock import MagicMock, patch

from clawgraph.db import GraphDB, _normalize_name
from clawgraph.memory import Memory

# ---------------------------------------------------------------------------
# normalize_name unit tests
# ---------------------------------------------------------------------------

class TestNormalizeName:
    """Tests for the _normalize_name utility."""

    def test_lowercase(self) -> None:
        assert _normalize_name("John Smith") == "john smith"

    def test_strip_whitespace(self) -> None:
        assert _normalize_name("  John Smith  ") == "john smith"

    def test_collapse_internal_whitespace(self) -> None:
        assert _normalize_name("John   Smith") == "john smith"

    def test_tabs_and_newlines(self) -> None:
        assert _normalize_name("John\tSmith\n") == "john smith"

    def test_unicode_normalization(self) -> None:
        # NFC normalization: composed vs decomposed forms
        composed = "\u00e9"  # é (single code point)
        decomposed = "e\u0301"  # e + combining acute accent
        assert _normalize_name(composed) == _normalize_name(decomposed)

    def test_empty_string(self) -> None:
        assert _normalize_name("") == ""

    def test_already_normalized(self) -> None:
        assert _normalize_name("john smith") == "john smith"

    def test_mixed_case(self) -> None:
        assert _normalize_name("jOhN sMiTh") == "john smith"


# ---------------------------------------------------------------------------
# GraphDB entity resolution helpers
# ---------------------------------------------------------------------------

class TestFindEntityByNormalizedName:
    """Tests for GraphDB.find_entity_by_normalized_name."""

    def test_finds_exact_match(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'John Smith'}) SET e.label = 'Person'")

        result = db.find_entity_by_normalized_name("john smith")
        assert result is not None
        assert result["e.name"] == "John Smith"

    def test_finds_case_variant(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'John Smith'}) SET e.label = 'Person'")

        # Searching for lowercase normalized form should find it
        result = db.find_entity_by_normalized_name("john smith")
        assert result is not None
        assert result["e.name"] == "John Smith"

    def test_returns_none_when_not_found(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        result = db.find_entity_by_normalized_name("nobody")
        assert result is None

    def test_returns_none_no_table(self) -> None:
        db = GraphDB(db_path=":memory:")
        result = db.find_entity_by_normalized_name("anything")
        assert result is None


class TestUpdateEntityAliases:
    """Tests for GraphDB.update_entity_aliases."""

    def test_sets_aliases(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'John Smith'}) SET e.label = 'Person'")

        db.update_entity_aliases("John Smith", "john smith|JOHN SMITH")
        rows = db.execute("MATCH (e:Entity {name: 'John Smith'}) RETURN e.aliases")
        assert rows[0]["e.aliases"] == "john smith|JOHN SMITH"

    def test_overwrites_existing_aliases(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        db.update_entity_aliases("Alice", "alice")
        db.update_entity_aliases("Alice", "alice|ALICE")
        rows = db.execute("MATCH (e:Entity {name: 'Alice'}) RETURN e.aliases")
        assert rows[0]["e.aliases"] == "alice|ALICE"


class TestAliasesColumn:
    """Tests for the aliases column in Entity table."""

    def test_new_db_has_aliases_column(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Test'}) SET e.label = 'Thing'")
        rows = db.execute("MATCH (e:Entity) RETURN e.aliases")
        assert len(rows) == 1
        # Default value may be None or empty string depending on how the entity was created
        assert rows[0]["e.aliases"] in (None, "")

    def test_get_all_entities_includes_aliases(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'")
        db.update_entity_aliases("Alice", "alice|Al")
        entities = db.get_all_entities()
        assert len(entities) == 1
        assert "e.aliases" in entities[0]
        assert entities[0]["e.aliases"] == "alice|Al"

    def test_migration_adds_aliases(self) -> None:
        """Simulate an existing DB that lacks aliases column."""
        db = GraphDB(db_path=":memory:")
        # Create old-style schema without aliases
        db.create_node_table(
            "Entity",
            {"name": "STRING", "label": "STRING",
             "created_at": "STRING", "updated_at": "STRING"},
        )
        db.create_rel_table(
            "Relates", "Entity", "Entity",
            {"type": "STRING", "created_at": "STRING"},
        )
        db.execute("MERGE (e:Entity {name: 'Old'}) SET e.label = 'Thing'")

        # Running ensure_base_schema should add aliases via migration
        db.ensure_base_schema()

        rows = db.execute("MATCH (e:Entity) RETURN e.name, e.aliases")
        assert len(rows) == 1
        assert rows[0]["e.name"] == "Old"
        # Migration default
        assert rows[0]["e.aliases"] == ""


# ---------------------------------------------------------------------------
# Memory-level entity resolution (mocked LLM)
# ---------------------------------------------------------------------------

def _mock_llm(json_resp: str) -> MagicMock:
    """Create a mock LLM client that returns *json_resp*."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


class TestEntityResolutionCaseInsensitive:
    """Core acceptance tests: same entity with different casing → single node."""

    @patch("clawgraph.llm._get_client")
    def test_case_variant_produces_single_entity(
        self, mock_get_client: MagicMock
    ) -> None:
        """'John Smith' then 'john smith' → one entity."""
        # First call: LLM returns "John Smith"
        resp1 = '{"entities": [{"name": "John Smith", "label": "Person"}, {"name": "Acme", "label": "Organization"}], "relationships": [{"from": "John Smith", "to": "Acme", "type": "WORKS_AT"}]}'
        # Second call: LLM returns "john smith"
        resp2 = '{"entities": [{"name": "john smith", "label": "Person"}, {"name": "NYC", "label": "Place"}], "relationships": [{"from": "john smith", "to": "NYC", "type": "LIVES_IN"}]}'

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp1))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp2))]),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("John Smith works at Acme")
        mem.add("john smith lives in NYC")

        entities = mem.entities()
        person_entities = [e for e in entities if e["e.label"] == "Person"]
        assert len(person_entities) == 1
        assert person_entities[0]["e.name"] == "John Smith"

    @patch("clawgraph.llm._get_client")
    def test_alias_recorded_on_resolution(
        self, mock_get_client: MagicMock
    ) -> None:
        """When a case variant resolves, the variant is stored as alias."""
        resp1 = '{"entities": [{"name": "John Smith", "label": "Person"}], "relationships": []}'
        resp2 = '{"entities": [{"name": "john smith", "label": "Person"}], "relationships": []}'

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp1))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp2))]),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("John Smith is a person")
        mem.add("john smith is a person")

        entities = mem.entities()
        assert len(entities) == 1
        aliases = entities[0]["e.aliases"]
        assert "john smith" in aliases

    @patch("clawgraph.llm._get_client")
    def test_whitespace_variant_produces_single_entity(
        self, mock_get_client: MagicMock
    ) -> None:
        """'John  Smith' (extra space) resolves to 'John Smith'."""
        resp1 = '{"entities": [{"name": "John Smith", "label": "Person"}], "relationships": []}'
        resp2 = '{"entities": [{"name": "John  Smith", "label": "Person"}], "relationships": []}'

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp1))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp2))]),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("John Smith is here")
        mem.add("John  Smith is here")

        entities = mem.entities()
        person_entities = [e for e in entities if e["e.label"] == "Person"]
        assert len(person_entities) == 1
        assert person_entities[0]["e.name"] == "John Smith"


class TestEntityResolutionRelationships:
    """Relationships correctly point to canonical entity after resolution."""

    @patch("clawgraph.llm._get_client")
    def test_relationships_use_canonical_name(
        self, mock_get_client: MagicMock
    ) -> None:
        resp1 = '{"entities": [{"name": "John Smith", "label": "Person"}, {"name": "Acme", "label": "Organization"}], "relationships": [{"from": "John Smith", "to": "Acme", "type": "WORKS_AT"}]}'
        resp2 = '{"entities": [{"name": "john smith", "label": "Person"}, {"name": "NYC", "label": "Place"}], "relationships": [{"from": "john smith", "to": "NYC", "type": "LIVES_IN"}]}'

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp1))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp2))]),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("John Smith works at Acme")
        mem.add("john smith lives in NYC")

        rels = mem.relationships()
        assert len(rels) == 2
        # Both rels should reference canonical "John Smith"
        rel_froms = {r["a.name"] for r in rels}
        assert rel_froms == {"John Smith"}


class TestEntityResolutionIdempotent:
    """Adding the same fact twice must not duplicate entities."""

    @patch("clawgraph.llm._get_client")
    def test_identical_add_is_idempotent(
        self, mock_get_client: MagicMock
    ) -> None:
        resp = '{"entities": [{"name": "John Smith", "label": "Person"}], "relationships": []}'
        mock_get_client.return_value = _mock_llm(resp)

        mem = Memory(db_path=":memory:")
        mem.add("John Smith is a person")
        mem.add("John Smith is a person")

        assert len(mem.entities()) == 1

    @patch("clawgraph.llm._get_client")
    def test_case_variant_add_is_idempotent(
        self, mock_get_client: MagicMock
    ) -> None:
        resp1 = '{"entities": [{"name": "John Smith", "label": "Person"}], "relationships": []}'
        resp2 = '{"entities": [{"name": "JOHN SMITH", "label": "Person"}], "relationships": []}'

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp1))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp2))]),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("John Smith is a person")
        mem.add("JOHN SMITH is a person")

        assert len(mem.entities()) == 1


class TestEntityResolutionBatch:
    """Entity resolution also works inside add_batch."""

    @patch("clawgraph.llm._get_client")
    def test_batch_deduplication(
        self, mock_get_client: MagicMock
    ) -> None:
        """Batch LLM response with same entity twice (different case)."""
        resp = '{"entities": [{"name": "John Smith", "label": "Person"}, {"name": "john smith", "label": "Person"}], "relationships": []}'
        mock_get_client.return_value = _mock_llm(resp)

        mem = Memory(db_path=":memory:")
        result = mem.add_batch(["John Smith exists", "john smith exists"])

        entities = mem.entities()
        assert len(entities) == 1
        assert entities[0]["e.name"] == "John Smith"
        assert result.ok


class TestEntitiesReturnAliases:
    """mem.entities() returns canonical names with aliases."""

    @patch("clawgraph.llm._get_client")
    def test_entities_includes_aliases_key(
        self, mock_get_client: MagicMock
    ) -> None:
        resp = '{"entities": [{"name": "Alice", "label": "Person"}], "relationships": []}'
        mock_get_client.return_value = _mock_llm(resp)

        mem = Memory(db_path=":memory:")
        mem.add("Alice is a person")

        entities = mem.entities()
        assert len(entities) == 1
        assert "e.aliases" in entities[0]

    @patch("clawgraph.llm._get_client")
    def test_entities_aliases_populated_after_resolution(
        self, mock_get_client: MagicMock
    ) -> None:
        resp1 = '{"entities": [{"name": "Alice", "label": "Person"}], "relationships": []}'
        resp2 = '{"entities": [{"name": "alice", "label": "Person"}], "relationships": []}'
        resp3 = '{"entities": [{"name": "ALICE", "label": "Person"}], "relationships": []}'

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp1))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp2))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=resp3))]),
        ]
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        mem.add("Alice is a person")
        mem.add("alice is a person")
        mem.add("ALICE is a person")

        entities = mem.entities()
        assert len(entities) == 1
        aliases_str = entities[0]["e.aliases"]
        alias_set = {a for a in aliases_str.split("|") if a}
        assert "alice" in alias_set
        assert "ALICE" in alias_set


class TestNoRegressionExistingBehavior:
    """Verify existing add/query behavior is not broken."""

    @patch("clawgraph.llm._get_client")
    def test_add_single_fact_still_works(self, mock_get_client: MagicMock) -> None:
        json_resp = '{"entities": [{"name": "John", "label": "Person"}, {"name": "Acme", "label": "Organization"}], "relationships": [{"from": "John", "to": "Acme", "type": "WORKS_AT"}]}'
        mock_get_client.return_value = _mock_llm(json_resp)

        mem = Memory(db_path=":memory:")
        result = mem.add("John works at Acme")
        assert result.ok
        assert len(result.entities) == 2
        assert len(result.relationships) == 1

    @patch("clawgraph.llm._get_client")
    def test_query_still_works(self, mock_get_client: MagicMock) -> None:
        add_resp = '{"entities": [{"name": "John", "label": "Person"}], "relationships": []}'
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

    @patch("clawgraph.llm._get_client")
    def test_export_includes_aliases(self, mock_get_client: MagicMock) -> None:
        resp = '{"entities": [{"name": "X", "label": "Thing"}], "relationships": []}'
        mock_get_client.return_value = _mock_llm(resp)

        mem = Memory(db_path=":memory:")
        mem.add("X is a thing")
        export = mem.export()
        assert "entities" in export
        assert "relationships" in export
        assert "ontology" in export
        # Entities should include aliases field
        assert "e.aliases" in export["entities"][0]
