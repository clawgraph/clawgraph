"""Tests for tiered model configuration and integration."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clawgraph.config import load_config
from clawgraph.llm import LLMError, _call_integration_model
from clawgraph.memory import Memory


class TestTieredConfig:
    """Tests for integration_model config key support."""

    def test_default_config_has_integration_model(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent" / "config.yaml"
        with patch("clawgraph.config.get_config_path", return_value=fake_path):
            config = load_config()
        assert config["llm"]["integration_model"] == "gpt-4o"

    def test_default_config_preserves_model(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent" / "config.yaml"
        with patch("clawgraph.config.get_config_path", return_value=fake_path):
            config = load_config()
        assert config["llm"]["model"] == "gpt-4o-mini"

    def test_user_config_overrides_integration_model(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("llm:\n  integration_model: claude-3-5-sonnet-20241022\n")
        with patch("clawgraph.config.get_config_path", return_value=config_file):
            config = load_config()
        assert config["llm"]["integration_model"] == "claude-3-5-sonnet-20241022"
        # Tier 1 model should still be the default
        assert config["llm"]["model"] == "gpt-4o-mini"


class TestCallIntegrationModel:
    """Tests for _call_integration_model() helper."""

    @patch("clawgraph.llm.litellm")
    def test_uses_integration_model_from_config(self, mock_litellm: MagicMock, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("llm:\n  integration_model: gpt-4o\n")

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="integration result"))
        ]
        mock_litellm.completion.return_value = mock_response

        with patch("clawgraph.config.get_config_path", return_value=config_file):
            result = _call_integration_model(
                messages=[{"role": "user", "content": "hello"}]
            )

        assert result == "integration result"
        call_kwargs = mock_litellm.completion.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o"

    @patch("clawgraph.llm.litellm")
    def test_explicit_model_overrides_config(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="response"))
        ]
        mock_litellm.completion.return_value = mock_response

        _call_integration_model(
            messages=[{"role": "user", "content": "hello"}],
            model="claude-3-opus-20240229",
        )

        call_kwargs = mock_litellm.completion.call_args
        assert call_kwargs.kwargs["model"] == "claude-3-opus-20240229"

    def test_raises_when_no_integration_model_configured(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        # Explicitly unset integration_model
        config_file.write_text("llm:\n  integration_model:\n")

        with patch("clawgraph.config.get_config_path", return_value=config_file):
            with pytest.raises(LLMError, match="integration_model is not configured"):
                _call_integration_model(
                    messages=[{"role": "user", "content": "hello"}]
                )

    @patch("clawgraph.llm.litellm")
    def test_raises_on_llm_api_error(self, mock_litellm: MagicMock) -> None:
        mock_litellm.completion.side_effect = Exception("API unavailable")

        with pytest.raises(LLMError, match="Integration model call failed"):
            _call_integration_model(
                messages=[{"role": "user", "content": "hello"}],
                model="gpt-4o",
            )

    @patch("clawgraph.llm.litellm")
    def test_raises_on_empty_response(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=None))]
        mock_litellm.completion.return_value = mock_response

        with pytest.raises(LLMError, match="Integration model returned empty response"):
            _call_integration_model(
                messages=[{"role": "user", "content": "hello"}],
                model="gpt-4o",
            )

    @patch("clawgraph.llm.litellm")
    def test_strips_whitespace_from_response(self, mock_litellm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="  trimmed  "))
        ]
        mock_litellm.completion.return_value = mock_response

        result = _call_integration_model(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-4o",
        )
        assert result == "trimmed"


class TestMemoryIntegrationModel:
    """Tests for integration_model param on Memory.__init__()."""

    def test_explicit_integration_model_param(self) -> None:
        mem = Memory(db_path=":memory:", integration_model="gpt-4o")
        assert mem._integration_model == "gpt-4o"

    def test_config_dict_sets_integration_model(self) -> None:
        mem = Memory(
            db_path=":memory:",
            config={"llm": {"integration_model": "gpt-4o"}},
        )
        assert mem._integration_model == "gpt-4o"

    def test_explicit_param_overrides_config_dict(self) -> None:
        mem = Memory(
            db_path=":memory:",
            integration_model="claude-3-opus-20240229",
            config={"llm": {"integration_model": "gpt-4o"}},
        )
        assert mem._integration_model == "claude-3-opus-20240229"

    def test_no_integration_model_defaults_to_none(self) -> None:
        # Pass empty config to avoid reading ~/.clawgraph/config.yaml
        mem = Memory(db_path=":memory:", config={})
        assert mem._integration_model is None

    def test_tier1_model_unaffected_by_integration_model(self) -> None:
        mem = Memory(
            db_path=":memory:",
            model="gpt-4o-mini",
            integration_model="gpt-4o",
        )
        assert mem._model == "gpt-4o-mini"
        assert mem._integration_model == "gpt-4o"


class TestMemoryIntegrate:
    """Tests for Memory.integrate() stub method."""

    def test_integrate_warns_when_no_model(self, caplog: pytest.LogCaptureFixture) -> None:
        mem = Memory(db_path=":memory:", config={})
        assert mem._integration_model is None

        with caplog.at_level(logging.WARNING):
            mem.integrate()

        assert "integration_model is not configured" in caplog.text

    def test_integrate_returns_none_when_no_model(self) -> None:
        mem = Memory(db_path=":memory:", config={})
        result = mem.integrate()
        assert result is None

    def test_integrate_logs_info_when_model_set(self, caplog: pytest.LogCaptureFixture) -> None:
        mem = Memory(
            db_path=":memory:",
            integration_model="gpt-4o",
        )
        with caplog.at_level(logging.INFO):
            mem.integrate()

        assert "no integration tasks pending" in caplog.text

    def test_integrate_returns_none_when_model_set(self) -> None:
        mem = Memory(db_path=":memory:", integration_model="gpt-4o")
        result = mem.integrate()
        assert result is None

    @patch("clawgraph.llm.litellm")
    def test_add_does_not_call_integration_model(self, mock_litellm: MagicMock) -> None:
        """Tier 2 model must never be called on the add() hot path."""
        json_resp = '{"entities": [{"name": "Alice", "label": "Person"}], "relationships": []}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json_resp))]
        mock_litellm.completion.return_value = mock_response

        mem = Memory(
            db_path=":memory:",
            model="gpt-4o-mini",
            integration_model="gpt-4o",
        )
        mem.add("Alice is a person")

        # Only 1 LLM call (Tier 1 for infer_ontology), no Tier 2 call
        assert mock_litellm.completion.call_count == 1
        call_kwargs = mock_litellm.completion.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o-mini"
