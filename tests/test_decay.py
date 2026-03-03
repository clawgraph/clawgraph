"""Tests for memory decay and garbage collection."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from clawgraph.db import GraphDB
from clawgraph.memory import Memory


class TestAccessTracking:
    """Tests for Entity access_count and last_accessed tracking."""

    def test_entity_has_access_columns(self) -> None:
        """New entities should have access_count and last_accessed columns."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute(
            "MERGE (e:Entity {name: 'Alice'}) SET e.label = 'Person'"
        )
        results = db.execute(
            "MATCH (e:Entity) RETURN e.name, e.access_count, e.last_accessed"
        )
        assert len(results) == 1
        assert results[0]["e.access_count"] == 0
        assert results[0]["e.last_accessed"] == ""

    def test_migration_adds_access_columns(self) -> None:
        """Migration should add access columns to existing DBs."""
        db = GraphDB(db_path=":memory:")
        # Create schema without access columns (simulate old DB)
        db.create_node_table(
            "Entity", {"name": "STRING", "label": "STRING"}
        )
        # Running ensure_base_schema should migrate
        db._migrate_timestamps()
        db.execute(
            "MERGE (e:Entity {name: 'Bob'}) SET e.label = 'Person'"
        )
        results = db.execute(
            "MATCH (e:Entity) RETURN e.access_count, e.last_accessed"
        )
        assert len(results) == 1
        assert results[0]["e.access_count"] == 0

    @patch("clawgraph.llm.litellm")
    def test_query_increments_access_count(self, mock_litellm: MagicMock) -> None:
        """mem.query() should increment access_count for returned entities."""
        add_resp = '{"entities": [{"name": "John", "label": "Person"}], "relationships": []}'
        query_resp = "MATCH (e:Entity) RETURN e.name, e.label"

        mock_litellm.completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=add_resp))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=query_resp))]),
        ]

        mem = Memory(db_path=":memory:")
        mem.add("John is a person")
        mem.query("List all people")

        results = mem._db.execute(
            "MATCH (e:Entity) RETURN e.access_count, e.last_accessed"
        )
        assert results[0]["e.access_count"] == 1
        assert results[0]["e.last_accessed"] != ""

    @patch("clawgraph.llm.litellm")
    def test_multiple_queries_increment_count(self, mock_litellm: MagicMock) -> None:
        """Multiple queries should increment access_count multiple times."""
        add_resp = '{"entities": [{"name": "Alice", "label": "Person"}], "relationships": []}'
        query_resp = "MATCH (e:Entity) RETURN e.name"

        mock_litellm.completion.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=add_resp))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=query_resp))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=query_resp))]),
        ]

        mem = Memory(db_path=":memory:")
        mem.add("Alice is a person")
        mem.query("Who is Alice?")
        mem.query("Who is Alice?")

        results = mem._db.execute(
            "MATCH (e:Entity) RETURN e.access_count"
        )
        assert results[0]["e.access_count"] == 2


class TestPruneByAge:
    """Tests for mem.prune(max_age_days=...)."""

    def test_prune_old_entities(self) -> None:
        """Entities not accessed for N+ days should be removed."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        db.execute(
            "MERGE (e:Entity {name: 'OldNode'}) "
            f"SET e.label = 'Thing', e.last_accessed = '{old_ts}'"
        )
        recent_ts = datetime.now(timezone.utc).isoformat()
        db.execute(
            "MERGE (e:Entity {name: 'NewNode'}) "
            f"SET e.label = 'Thing', e.last_accessed = '{recent_ts}'"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        removed = mem.prune(max_age_days=30)
        assert "OldNode" in removed
        assert "NewNode" not in removed

        remaining = db.get_all_entities()
        names = [e["e.name"] for e in remaining]
        assert "OldNode" not in names
        assert "NewNode" in names

    def test_prune_uses_created_at_fallback(self) -> None:
        """When last_accessed is empty, fall back to created_at."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        old_ts = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        db.execute(
            "MERGE (e:Entity {name: 'FallbackNode'}) "
            f"SET e.label = 'Thing', e.created_at = '{old_ts}'"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        removed = mem.prune(max_age_days=30)
        assert "FallbackNode" in removed

    def test_prune_empty_timestamp_removed(self) -> None:
        """Entities with no timestamps at all should be pruned."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        db.execute(
            "MERGE (e:Entity {name: 'NoTimestamp'}) SET e.label = 'Thing'"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        removed = mem.prune(max_age_days=30)
        assert "NoTimestamp" in removed


class TestPruneByAccessCount:
    """Tests for mem.prune(min_access_count=...)."""

    def test_prune_rarely_accessed(self) -> None:
        """Entities with access_count below threshold should be removed."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        db.execute(
            "MERGE (e:Entity {name: 'Popular'}) "
            "SET e.label = 'Thing', e.access_count = 10"
        )
        db.execute(
            "MERGE (e:Entity {name: 'Rare'}) "
            "SET e.label = 'Thing', e.access_count = 1"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        removed = mem.prune(min_access_count=2)
        assert "Rare" in removed
        assert "Popular" not in removed

        remaining = db.get_all_entities()
        names = [e["e.name"] for e in remaining]
        assert "Rare" not in names
        assert "Popular" in names

    def test_prune_zero_access_count(self) -> None:
        """Default access_count=0 entities should be pruned with min_access_count=1."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        db.execute(
            "MERGE (e:Entity {name: 'Fresh'}) SET e.label = 'Thing'"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        removed = mem.prune(min_access_count=1)
        assert "Fresh" in removed


class TestPruneCombined:
    """Tests for prune with both criteria."""

    def test_prune_no_args_noop(self) -> None:
        """prune() with no args should be a no-op."""
        mem = Memory(db_path=":memory:")
        removed = mem.prune()
        assert removed == []

    def test_prune_both_criteria(self) -> None:
        """Prune by both age and access count."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        now_ts = datetime.now(timezone.utc).isoformat()

        # Old with low access => removed by both criteria
        db.execute(
            "MERGE (e:Entity {name: 'OldRare'}) "
            f"SET e.label = 'Thing', e.last_accessed = '{old_ts}', e.access_count = 0"
        )
        # Old with high access => removed by age
        db.execute(
            "MERGE (e:Entity {name: 'OldPopular'}) "
            f"SET e.label = 'Thing', e.last_accessed = '{old_ts}', e.access_count = 10"
        )
        # Recent with low access => removed by access count
        db.execute(
            "MERGE (e:Entity {name: 'NewRare'}) "
            f"SET e.label = 'Thing', e.last_accessed = '{now_ts}', e.access_count = 0"
        )
        # Recent with high access => kept
        db.execute(
            "MERGE (e:Entity {name: 'NewPopular'}) "
            f"SET e.label = 'Thing', e.last_accessed = '{now_ts}', e.access_count = 10"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        removed = mem.prune(max_age_days=30, min_access_count=2)
        assert "OldRare" in removed
        assert "OldPopular" in removed
        assert "NewRare" in removed
        assert "NewPopular" not in removed

    def test_prune_deduplicates_results(self) -> None:
        """Entity removed by both criteria should appear once in result."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        db.execute(
            "MERGE (e:Entity {name: 'Both'}) "
            f"SET e.label = 'Thing', e.last_accessed = '{old_ts}', e.access_count = 0"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        removed = mem.prune(max_age_days=30, min_access_count=1)
        assert removed.count("Both") == 1


class TestPruneLogging:
    """Tests for prune logging."""

    def test_prune_logs_removed_entities(self, caplog: object) -> None:
        """Pruning should log which entities are removed."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute(
            "MERGE (e:Entity {name: 'ToRemove'}) "
            "SET e.label = 'Thing', e.access_count = 0"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        with patch("clawgraph.memory.logger") as mock_logger:
            mem.prune(min_access_count=1)
            mock_logger.info.assert_called_with("Pruned entity: %s", "ToRemove")


class TestPruneRelationships:
    """Tests that pruning detach-deletes relationships too."""

    def test_prune_removes_relationships(self) -> None:
        """DETACH DELETE should remove entity and its relationships."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()

        db.execute(
            "MERGE (e:Entity {name: 'A'}) SET e.label = 'Thing', e.access_count = 0"
        )
        db.execute(
            "MERGE (e:Entity {name: 'B'}) SET e.label = 'Thing', e.access_count = 10"
        )
        db.execute(
            "MATCH (a:Entity {name: 'A'}), (b:Entity {name: 'B'}) "
            "MERGE (a)-[r:Relates {type: 'LINKED'}]->(b)"
        )

        mem = Memory.__new__(Memory)
        mem._db = db
        mem._ontology = MagicMock()
        mem._model = None

        mem.prune(min_access_count=1)

        rels = db.get_all_relationships()
        assert len(rels) == 0
