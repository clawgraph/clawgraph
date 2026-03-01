"""ClawGraph — Graph-based memory abstraction layer for AI agents."""

__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy import Memory to avoid heavy imports on package load."""
    if name == "Memory":
        from clawgraph.memory import Memory
        return Memory
    raise AttributeError(f"module 'clawgraph' has no attribute {name!r}")
