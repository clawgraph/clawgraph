"""Database layer — Kùzu embedded graph database wrapper."""

from __future__ import annotations

import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kuzu


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
        self._db = kuzu.Database(str(self._db_path))
        self._conn = kuzu.Connection(self._db)

    @property
    def connection(self) -> kuzu.Connection:
        """Get the active database connection."""
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
            raw_result = self._conn.execute(cypher, parameters or {})
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
            {"type": "STRING", "created_at": "STRING",
             "source_agent": "STRING", "source_session": "STRING",
             "source_input": "STRING"},
        )
        # Migrate existing DBs: add missing columns
        self._migrate_schema()

    def get_all_entities(self) -> list[dict[str, Any]]:
        """Get all entities in the graph."""
        if not self.has_node_table("Entity"):
            return []
        return self.execute("MATCH (e:Entity) RETURN e.name, e.label")

    def get_all_relationships(self) -> list[dict[str, Any]]:
        """Get all relationships in the graph, including provenance metadata."""
        if not self.has_rel_table("Relates"):
            return []
        return self.execute(
            "MATCH (a:Entity)-[r:Relates]->(b:Entity) "
            "RETURN a.name, r.type, b.name, "
            "r.source_agent, r.source_session, r.source_input"
        )

    def close(self) -> None:
        """Close the database connection and release file locks."""
        if hasattr(self, "_conn"):
            del self._conn
        if hasattr(self, "_db"):
            del self._db

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

        # Close connection and DB to release file locks
        del self._conn
        del self._db

        try:
            with tarfile.open(str(output), "w:gz") as tar:
                for item in db_dir.rglob("*"):
                    # Skip lock files to avoid issues on restore
                    if item.name.startswith(".") and "lock" in item.name.lower():
                        continue
                    arcname = str(db_dir.name / item.relative_to(db_dir))
                    tar.add(str(item), arcname=arcname)
                # Add the directory entry itself
                tar.add(str(db_dir), arcname=db_dir.name, recursive=False)
        finally:
            # Reconnect regardless of success/failure
            self._db = kuzu.Database(str(self._db_path))
            self._conn = kuzu.Connection(self._db)

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

    def _migrate_schema(self) -> None:
        """Add missing columns to existing tables.

        This is a no-op for new databases. For databases created before
        new columns were added, it attempts to ALTER TABLE to add them.
        Failures are silently ignored (column may already exist).
        """
        migrations = [
            "ALTER TABLE Entity ADD created_at STRING DEFAULT ''",
            "ALTER TABLE Entity ADD updated_at STRING DEFAULT ''",
            "ALTER TABLE Relates ADD created_at STRING DEFAULT ''",
            "ALTER TABLE Relates ADD source_agent STRING DEFAULT ''",
            "ALTER TABLE Relates ADD source_session STRING DEFAULT ''",
            "ALTER TABLE Relates ADD source_input STRING DEFAULT ''",
        ]
        for stmt in migrations:
            try:
                self._conn.execute(stmt)
            except Exception:
                pass  # Column likely already exists

    @staticmethod
    def now_iso() -> str:
        """Get current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()


class DatabaseError(Exception):
    """Raised when a database operation fails."""
