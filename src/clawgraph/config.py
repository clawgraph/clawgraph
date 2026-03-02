"""Configuration management for ClawGraph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG: dict[str, Any] = {
    "llm": {
        "model": "gpt-4o-mini",
        "temperature": 0.0,
    },
    "db": {
        "path": str(Path.home() / ".clawgraph" / "data"),
    },
    "output": {
        "format": "human",
    },
}


def get_config_path() -> Path:
    """Get the path to the config file."""
    return Path.home() / ".clawgraph" / "config.yaml"


def load_config() -> dict[str, Any]:
    """Load configuration from ~/.clawgraph/config.yaml.

    Returns:
        Merged config dict (defaults + user overrides).
    """
    config = _DEFAULT_CONFIG.copy()
    config_path = get_config_path()

    if config_path.exists():
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        config = _deep_merge(config, user_config)

    return config


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to ~/.clawgraph/config.yaml.

    Args:
        config: Configuration dictionary to save.
    """
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_config_value(key: str) -> Any:
    """Get a config value by dot-separated key.

    Args:
        key: Dot-separated key (e.g., 'llm.model').

    Returns:
        The config value, or None if not found.
    """
    config = load_config()
    parts = key.split(".")
    current: Any = config
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def set_config_value(key: str, value: str) -> None:
    """Set a config value by dot-separated key.

    Args:
        key: Dot-separated key (e.g., 'llm.model').
        value: Value to set (stored as string).
    """
    config = load_config()
    parts = key.split(".")
    current = config
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    save_config(config)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
