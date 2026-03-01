"""Database layer — Kùzu embedded graph database wrapper."""

from __future__ import annotations

import os
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
            result = self._conn.execute(cypher, parameters or {})
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
        """
        self.create_node_table("Entity", {"name": "STRING", "label": "STRING"})
        self.create_rel_table("Relates", "Entity", "Entity", {"type": "STRING"})

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

    def close(self) -> None:
        """Close the database connection."""
        # Kùzu handles cleanup on garbage collection
        pass


class DatabaseError(Exception):
    """Raised when a database operation fails."""
