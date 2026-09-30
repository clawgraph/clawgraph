"""Database layer — Kùzu embedded graph database wrapper."""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kuzu

from clawgraph.cypher import validate_cypher

_REL_MATCH = (
    "MATCH (a:Entity {name: $source})-[r:Relates {type: $type}]->"
    "(b:Entity {name: $target}) "
)
_REL_COUNT = _REL_MATCH + "RETURN count(r) AS count"
_REL_DELETE = _REL_MATCH + "DELETE r"
_ENTITY_MERGE = (
    "MERGE (e:Entity {name: $name}) SET e.label = $label, e.updated_at = $now"
)
_ENTITY_TIMESTAMP = (
    "MATCH (e:Entity {name: $name}) "
    "WHERE e.created_at IS NULL OR e.created_at = '' SET e.created_at = $now"
)
_ENDPOINT_COUNT = "MATCH (e:Entity) WHERE e.name IN $names RETURN count(e) AS count"
_REL_MERGE = (
    "MATCH (a:Entity {name: $source}), (b:Entity {name: $target}) "
    "MERGE (a)-[r:Relates {type: $type}]->(b) RETURN count(r) AS count"
)
_REL_TIMESTAMP = (
    _REL_MATCH + "WHERE r.created_at IS NULL OR r.created_at = '' SET r.created_at = $now"
)


class GraphDB:
    """Wrapper around Kùzu embedded graph database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize the graph database.

        Args:
            db_path: Path to the database directory.
                     Defaults to ~/.clawgraph/data.
                     Use ':memory:' for in-memory database.
        """
        if db_path is None:
            from clawgraph.config import load_config
            config = load_config()
            db_path = config.get("db", {}).get("path", str(Path.home() / ".clawgraph" / "data"))

        self._db_path = db_path
        if str(db_path) != ":memory:":
            # Only create the parent dir — Kùzu creates the DB dir itself
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        db_instance = kuzu.Database(str(self._db_path))
        self._db: kuzu.Database | None = db_instance
        self._conn: kuzu.Connection | None = kuzu.Connection(db_instance)

    @property
    def connection(self) -> kuzu.Connection:
        """Get the active database connection."""
        return self._require_open()

    def _require_open(self) -> kuzu.Connection:
        """Return the active connection or raise if the database is closed."""
        if self._db is None or self._conn is None:
            raise DatabaseError("Database is closed")
        return self._conn

    def execute(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as a list of dicts.

        Args:
            cypher: The Cypher query to execute.
            parameters: Optional query parameters.

        Returns:
            List of result rows as dictionaries.
        """
        try:
            raw_result = self._require_open().execute(cypher, parameters or {})
            # kuzu.Connection.execute() returns QueryResult | list[QueryResult]
            result = raw_result if not isinstance(raw_result, list) else raw_result[0]
            rows: list[dict[str, Any]] = []
            while result.has_next():
                row = result.get_next()
                rows.append(dict(zip(result.get_column_names(), row)))
            return rows
        except Exception as e:
            raise DatabaseError(f"Cypher execution failed: {e}") from e

    def get_tables(self) -> list[dict[str, Any]]:
        """Get all tables in the database."""
        return self.execute("CALL show_tables() RETURN *")

    def has_node_table(self, label: str) -> bool:
        """Check if a node table exists."""
        tables = self.get_tables()
        return any(t.get("name") == label and t.get("type") == "NODE" for t in tables)

    def has_rel_table(self, name: str) -> bool:
        """Check if a relationship table exists."""
        tables = self.get_tables()
        return any(t.get("name") == name and t.get("type") == "REL" for t in tables)

    def create_node_table(self, label: str, properties: dict[str, str]) -> None:
        """Create a node table if it doesn't exist.

        Args:
            label: The node table name (e.g., 'Person').
            properties: Dict of property_name -> Kùzu type (e.g., {'name': 'STRING'}).
                        First property is used as PRIMARY KEY.
        """
        if self.has_node_table(label):
            return

        if not properties:
            properties = {"name": "STRING"}

        pk = next(iter(properties))
        props = ", ".join(f"{k} {v}" for k, v in properties.items())
        cypher = f"CREATE NODE TABLE {label}({props}, PRIMARY KEY({pk}))"
        self.execute(cypher)

    def create_rel_table(self, name: str, from_label: str, to_label: str, properties: dict[str, str] | None = None) -> None:
        """Create a relationship table if it doesn't exist.

        Args:
            name: The relationship table name (e.g., 'WORKS_AT').
            from_label: Source node table.
            to_label: Target node table.
            properties: Optional properties on the relationship.
        """
        if self.has_rel_table(name):
            return

        props = ""
        if properties:
            props = ", " + ", ".join(f"{k} {v}" for k, v in properties.items())
        cypher = f"CREATE REL TABLE {name}(FROM {from_label} TO {to_label}{props})"
        self.execute(cypher)

    def ensure_base_schema(self) -> None:
        """Ensure the base Entity/Relates schema exists.

        Creates a generic Entity node table and Relates rel table
        that can be used for any graph memory storage.
        Includes created_at/updated_at timestamps on entities and
        created_at on relationships.
        """
        self.create_node_table(
            "Entity",
            {"name": "STRING", "label": "STRING",
             "created_at": "STRING", "updated_at": "STRING"},
        )
        self.create_rel_table(
            "Relates", "Entity", "Entity",
            {"type": "STRING", "created_at": "STRING"},
        )
        # Migrate existing DBs: add timestamp columns if missing
        self._migrate_timestamps()

    def get_all_entities(self) -> list[dict[str, Any]]:
        """Get all entities in the graph."""
        if not self.has_node_table("Entity"):
            return []
        return self.execute("MATCH (e:Entity) RETURN e.name, e.label")

    def get_all_relationships(self) -> list[dict[str, Any]]:
        """Get all relationships in the graph."""
        if not self.has_rel_table("Relates"):
            return []
        return self.execute(
            "MATCH (a:Entity)-[r:Relates]->(b:Entity) RETURN a.name, r.type, b.name"
        )

    def get_neighborhood(
        self, entity: str, hops: int = 2,
    ) -> dict[str, list[dict[str, Any]]]:
        """Get a breadth-first neighborhood, preserving edge direction.

        Args:
            entity: Exact existing entity name.
            hops: Maximum undirected traversal distance (one or two).

        Returns:
            Entities with name/label and relationships with from/type/to.
            The seed is included even when isolated. Facts are deduplicated.

        Raises:
            ValueError: If entity is not a string or hops is not one or two.
        """
        if not isinstance(entity, str):
            raise ValueError("entity must be a string")
        if type(hops) is not int or hops not in (1, 2):
            raise ValueError("hops must be an integer of 1 or 2")
        seeds = self._validated_read(
            "MATCH (e:Entity {name: $name}) RETURN e.name AS name, e.label AS label",
            {"name": entity},
        )
        entities = {row["name"]: row for row in seeds}
        relationships: dict[tuple[str, str, str], dict[str, Any]] = {}
        frontier = list(entities)
        for _ in range(hops):
            if not frontier:
                break
            rows = self._validated_read(
                "MATCH (a:Entity)-[r:Relates]->(b:Entity) "
                "WHERE a.name IN $names OR b.name IN $names "
                "RETURN a.name AS source, a.label AS source_label, "
                "r.type AS type, b.name AS target, b.label AS target_label "
                "ORDER BY source, type, target",
                {"names": frontier},
            )
            next_frontier: list[str] = []
            for row in rows:
                key = (row["source"], row["type"], row["target"])
                relationships[key] = {
                    "from": key[0], "type": key[1], "to": key[2],
                }
                for side in ("source", "target"):
                    name = row[side]
                    if name not in entities:
                        entities[name] = {"name": name, "label": row[f"{side}_label"]}
                        next_frontier.append(name)
            frontier = sorted(next_frontier)
        return {
            "entities": list(entities.values()),
            "relationships": list(relationships.values()),
        }

    def delete_entity(self, name: str) -> bool:
        """Delete an exact entity and all incoming/outgoing relationships.

        Args:
            name: Exact entity name.

        Returns:
            Whether an entity was removed; missing entities are a no-op.

        Raises:
            ValueError: If name is not a nonempty string.
            DatabaseError: If the transaction fails.
        """
        self._require_text(name, "name")
        count = "MATCH (e:Entity {name: $name}) RETURN count(e) AS count"
        delete = "MATCH (e:Entity {name: $name}) DETACH DELETE e"
        with self._mutation_transaction([count, delete]):
            found = bool(self.execute(count, {"name": name})[0]["count"])
            if found:
                self.execute(delete, {"name": name})
        return found

    def delete_relationship(self, source: str, target: str, rel_type: str) -> bool:
        """Delete only the exact directed relationship triple.

        Args:
            source: Exact source entity name.
            target: Exact target entity name.
            rel_type: Exact relationship type.

        Returns:
            Whether any matching relationship was removed; endpoints remain.

        Raises:
            ValueError: If an argument is not a nonempty string.
            DatabaseError: If the transaction fails.
        """
        return bool(self.delete_relationships([
            {"from": source, "to": target, "type": rel_type},
        ]))

    def delete_relationships(self, relationships: list[dict[str, str]]) -> int:
        """Delete exact triples in one all-or-nothing transaction.

        Args:
            relationships: Relationships with from, to, and type strings.

        Returns:
            Number of matching edges removed, leaving all endpoints intact.

        Raises:
            ValueError: If a triple contains an empty or non-string value.
            DatabaseError: If the transaction fails and is rolled back.
        """
        for rel in relationships:
            for field in ("from", "to", "type"):
                self._require_text(rel[field], field)
        if not relationships:
            return 0
        with self._mutation_transaction([_REL_COUNT, _REL_DELETE]):
            return self._delete_relationships_in_transaction(relationships)

    def _delete_relationships_in_transaction(
        self, relationships: list[dict[str, str]],
    ) -> int:
        """Remove selected edges inside an existing transaction."""
        removed = 0
        for rel in relationships:
            parameters = {"source": rel["from"], "target": rel["to"], "type": rel["type"]}
            count = int(self.execute(_REL_COUNT, parameters)[0]["count"])
            if count:
                self.execute(_REL_DELETE, parameters)
                removed += count
        return removed

    def replace_relationships(
        self, removals: list[dict[str, str]], entities: list[dict[str, str]],
        relationships: list[dict[str, str]],
    ) -> None:
        """Atomically remove selected edges and merge a validated replacement.

        Args:
            removals: Exact old relationship triples.
            entities: Replacement entities with name and label.
            relationships: Replacement triples with from, to, and type.

        Raises:
            ValueError: If a selected old relationship no longer exists.
            DatabaseError: If any write fails; all changes are rolled back.
        """
        now = self.now_iso()
        replacement_keys = {(rel["from"], rel["to"], rel["type"]) for rel in relationships}
        with self._mutation_transaction([
            _REL_COUNT, _REL_DELETE, _ENTITY_MERGE, _ENTITY_TIMESTAMP,
            _ENDPOINT_COUNT, _REL_MERGE, _REL_TIMESTAMP,
        ]):
            for rel in removals:
                parameters = {"source": rel["from"], "target": rel["to"], "type": rel["type"]}
                if not self.execute(_REL_COUNT, parameters)[0]["count"]:
                    raise ValueError("Selected old fact no longer exists; nothing was changed")
            self._delete_relationships_in_transaction([
                rel for rel in removals
                if (rel["from"], rel["to"], rel["type"]) not in replacement_keys
            ])
            for entity in entities:
                parameters = {"name": entity["name"], "label": entity["label"], "now": now}
                self.execute(_ENTITY_MERGE, parameters)
                self.execute(_ENTITY_TIMESTAMP, {"name": entity["name"], "now": now})
            endpoints = sorted({rel[field] for rel in relationships for field in ("from", "to")})
            if self.execute(_ENDPOINT_COUNT, {"names": endpoints})[0]["count"] != len(endpoints):
                raise DatabaseError("Replacement relationship endpoint no longer exists")
            for rel in relationships:
                parameters = {
                    "source": rel["from"], "target": rel["to"],
                    "type": rel["type"],
                }
                if not self.execute(_REL_MERGE, parameters)[0]["count"]:
                    raise DatabaseError("Replacement relationship endpoint no longer exists")
                self.execute(_REL_TIMESTAMP, {**parameters, "now": now})

    @staticmethod
    def _require_text(value: str, field: str) -> None:
        """Reject empty/non-string mutation identifiers without normalizing data."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a nonempty string")

    @contextmanager
    def _mutation_transaction(self, statements: list[str]) -> Iterator[None]:
        """Validate all fixed queries before starting an atomic mutation."""
        for statement in statements:
            validation = validate_cypher(statement)
            if not validation:
                raise DatabaseError(f"Invalid mutation query: {validation.errors}")
        self.execute("BEGIN TRANSACTION")
        try:
            yield
            self.execute("COMMIT")
        except Exception as exc:
            try:
                self.execute("ROLLBACK")
            except DatabaseError:
                pass
            if isinstance(exc, ValueError):
                raise
            raise DatabaseError(f"Graph mutation failed: {exc}") from exc

    def _validated_read(
        self, cypher: str, parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Validate fixed read queries before executing bound parameters."""
        validation = validate_cypher(cypher)
        if not validation:
            raise DatabaseError(f"Invalid read query: {validation.errors}")
        return self.execute(cypher, parameters)

    def close(self) -> None:
        """Close the database connection and release file locks."""
        self._conn = None
        self._db = None

    @property
    def db_path(self) -> str:
        """Get the database path."""
        return str(self._db_path)

    def save_snapshot(self, output_path: str | Path) -> Path:
        """Save a snapshot of the database as a .tar.gz archive.

        Temporarily closes the DB connection to release file locks
        (required on Windows), creates the archive, then reconnects.

        Args:
            output_path: Path for the output archive. If it doesn't
                         end in .tar.gz, the extension is appended.

        Returns:
            The Path to the created archive.

        Raises:
            DatabaseError: If the DB is in-memory or the snapshot fails.
        """
        if str(self._db_path) == ":memory:":
            raise DatabaseError("Cannot snapshot an in-memory database")

        output = Path(output_path)
        if not output.name.endswith(".tar.gz"):
            output = output.with_suffix(".tar.gz")

        output.parent.mkdir(parents=True, exist_ok=True)
        db_dir = Path(self._db_path)
        self._require_open()

        # Close connection and DB to release file locks
        self._conn = None
        self._db = None

        try:
            with tarfile.open(str(output), "w:gz") as tar:
                for item in db_dir.rglob("*"):
                    # Skip lock files to avoid issues on restore
                    if item.name.startswith(".") and "lock" in item.name.lower():
                        continue
                    arcname = str(Path(db_dir.name) / item.relative_to(db_dir))
                    tar.add(str(item), arcname=arcname)
                # Add the directory entry itself
                tar.add(str(db_dir), arcname=db_dir.name, recursive=False)
        finally:
            # Reconnect regardless of success/failure
            db_instance = kuzu.Database(str(self._db_path))
            self._db = db_instance
            self._conn = kuzu.Connection(db_instance)

        return output

    @classmethod
    def load_snapshot(cls, archive_path: str | Path, target_dir: str | Path) -> GraphDB:
        """Restore a database from a .tar.gz snapshot.

        Args:
            archive_path: Path to the .tar.gz archive.
            target_dir: Directory to extract the DB into.

        Returns:
            A new GraphDB instance pointing at the restored database.

        Raises:
            DatabaseError: If extraction fails.
        """
        archive = Path(archive_path)
        target = Path(target_dir)

        if not archive.exists():
            raise DatabaseError(f"Snapshot not found: {archive}")

        target.mkdir(parents=True, exist_ok=True)

        try:
            with tarfile.open(str(archive), "r:gz") as tar:
                # Get the top-level directory name from the archive
                members = tar.getnames()
                if not members:
                    raise DatabaseError("Empty snapshot archive")
                top_dir = members[0].split("/")[0]
                tar.extractall(str(target))
        except tarfile.TarError as e:
            raise DatabaseError(f"Failed to extract snapshot: {e}") from e

        db_path = target / top_dir
        return cls(db_path=str(db_path))

    def _migrate_timestamps(self) -> None:
        """Add timestamp columns to existing tables that lack them.

        This is a no-op for new databases. For databases created before
        timestamps were added, it attempts to ALTER TABLE to add the
        columns. Failures are silently ignored (column may already exist).
        """
        migrations = [
            "ALTER TABLE Entity ADD created_at STRING DEFAULT ''",
            "ALTER TABLE Entity ADD updated_at STRING DEFAULT ''",
            "ALTER TABLE Relates ADD created_at STRING DEFAULT ''",
        ]
        conn = self._require_open()
        for stmt in migrations:
            try:
                conn.execute(stmt)
            except Exception:
                pass  # Column likely already exists

    @staticmethod
    def now_iso() -> str:
        """Get current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()


class DatabaseError(Exception):
    """Raised when a database operation fails."""
