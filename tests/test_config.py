"""Tests for configuration management."""

from pathlib import Path
from unittest.mock import patch

from clawgraph.config import _deep_merge, load_config


class TestLoadConfig:
    """Tests for load_config."""

    def test_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent" / "config.yaml"
        with patch("clawgraph.config.get_config_path", return_value=fake_path):
            config = load_config()
        assert config["llm"]["model"] == "gpt-5.4-mini"
        assert config["llm"]["temperature"] == 0.0
        assert config["output"]["format"] == "human"

    def test_returns_independent_default_copy(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent" / "config.yaml"
        with patch("clawgraph.config.get_config_path", return_value=fake_path):
            first = load_config()
            first["llm"]["model"] = "mutated"
            second = load_config()

        assert second["llm"]["model"] == "gpt-5.4-mini"


class TestDeepMerge:
    """Tests for _deep_merge."""

    def test_simple_override(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        assert _deep_merge(base, override) == {"a": 1, "b": 3}

    def test_nested_merge(self) -> None:
        base = {"llm": {"model": "gpt-4", "temperature": 0.0}}
        override = {"llm": {"model": "claude-3"}}
        result = _deep_merge(base, override)
        assert result["llm"]["model"] == "claude-3"
        assert result["llm"]["temperature"] == 0.0

    def test_adds_new_keys(self) -> None:
        base = {"a": 1}
        override = {"b": 2}
        assert _deep_merge(base, override) == {"a": 1, "b": 2}
