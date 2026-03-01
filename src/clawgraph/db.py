"""Database layer — Kùzu embedded graph database wrapper."""

from __future__ import annotations

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
        """
        if db_path is None:
            db_path = Path.home() / ".clawgraph" / "data"
        self._db_path = Path(db_path)
        self._db_path.mkdir(parents=True, exist_ok=True)
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

    def has_node_table(self, label: str) -> bool:
        """Check if a node table exists."""
        try:
            result = self._conn.execute(
                "CALL show_tables() RETURN name WHERE name = $name",
                {"name": label},
            )
            return result.has_next()
        except Exception:
            return False

    def close(self) -> None:
        """Close the database connection."""
        # Kùzu handles cleanup on garbage collection
        pass


class DatabaseError(Exception):
    """Raised when a database operation fails."""
