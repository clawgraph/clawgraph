"""ClawGraph — Graph-based memory abstraction layer for AI agents."""

from typing import Any

__version__ = "0.1.2"


def __getattr__(name: str) -> Any:
    """Lazy import Memory to avoid heavy imports on package load."""
    if name == "Memory":
        from clawgraph.memory import Memory
        return Memory
    raise AttributeError(f"module 'clawgraph' has no attribute {name!r}")
