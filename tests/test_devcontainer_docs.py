"""Regression tests for the Docker/OpenClaw walkthrough files."""

from pathlib import Path


def test_openclaw_gateway_service_uses_bootstrap_script() -> None:
    compose_path = Path(".devcontainer/docker-compose.test.yml")

    compose_text = compose_path.read_text(encoding="utf-8")

    assert "/workspace/.devcontainer/start-openclaw-gateway.sh" in compose_text


def test_openclaw_test_service_selects_a_session_for_agent_calls() -> None:
    compose_path = Path(".devcontainer/docker-compose.test.yml")

    compose_text = compose_path.read_text(encoding="utf-8")

    assert "openclaw agent" in compose_text
    assert "--to +15555550123" in compose_text
    assert "--message" in compose_text


def test_openclaw_test_service_sets_supported_thinking_level() -> None:
    compose_path = Path(".devcontainer/docker-compose.test.yml")

    compose_text = compose_path.read_text(encoding="utf-8")

    assert "--thinking minimal" in compose_text


def test_openclaw_test_service_uses_explicit_memory_control_prompts() -> None:
    compose_path = Path(".devcontainer/docker-compose.test.yml")

    compose_text = compose_path.read_text(encoding="utf-8")

    assert "Use your ClawGraph memory skill to store exactly these facts:" in compose_text
    assert "clawgraph export --output json" in compose_text
    assert "Use your ClawGraph memory skill to query:" not in compose_text
    assert "Hi, I'm Alice." not in compose_text


def test_devcontainer_readme_marks_natural_auto_storage_as_experimental() -> None:
    readme_path = Path(".devcontainer/README.md")

    readme_text = readme_path.read_text(encoding="utf-8")

    assert "Natural agent-decided storage is still experimental" in readme_text
    assert "For deterministic validation, use an explicit ClawGraph instruction" in readme_text


def test_devcontainer_readme_ci_unit_test_snippet_uses_test_bed() -> None:
    readme_path = Path(".devcontainer/README.md")

    readme_text = readme_path.read_text(encoding="utf-8")
    ci_unit_block = readme_text.split("Unit tests (no secrets needed):", 1)[1].split(
        "Integration tests with real LLM calls", 1
    )[0]

    assert "docker compose -f .devcontainer/docker-compose.test.yml run test-bed" in ci_unit_block
    assert "openclaw agent" not in ci_unit_block


def test_gateway_bootstrap_uses_requested_model_split() -> None:
    bootstrap_path = Path(".devcontainer/start-openclaw-gateway.sh")

    bootstrap_text = bootstrap_path.read_text(encoding="utf-8")

    assert '"primary": "openai/gpt-5.4"' in bootstrap_text
    assert 'model: gpt-5.4-mini' in bootstrap_text


def test_gateway_bootstrap_seeds_workspace_memory_policy() -> None:
    bootstrap_path = Path(".devcontainer/start-openclaw-gateway.sh")

    bootstrap_text = bootstrap_path.read_text(encoding="utf-8")

    assert '/root/.openclaw/workspace/MEMORY.md' in bootstrap_text
    assert '/root/.openclaw/workspace/USER.md' in bootstrap_text
    assert 'ClawGraph is the durable memory system for this workspace' in bootstrap_text
    assert 'Always use the clawgraph skill immediately when the user shares durable facts worth remembering' in bootstrap_text
    assert 'Never rely on chat context or markdown memory files as a substitute for ClawGraph' in bootstrap_text
    assert 'Do not claim you stored or remembered durable facts unless you actually used ClawGraph successfully' in bootstrap_text


def test_clawgraph_skill_requires_high_confidence_fact_storage() -> None:
    skill_path = Path("skills/clawgraph/SKILL.md")

    skill_text = skill_path.read_text(encoding="utf-8")

    assert "Automatically store explicit durable user facts" in skill_text
    assert "do not infer or upgrade weak signals" in skill_text
    assert "Only store facts that are explicitly stated by the user" in skill_text
    assert "Do not infer, upgrade, or invent facts" in skill_text
    assert "Proactively store durable user facts without waiting for an explicit memory command" in skill_text
    assert "Preserve the user's phrasing when possible" in skill_text
    assert "OpenAI-compatible APIs today" in skill_text
    assert "LiteLLM" not in skill_text


def test_main_readme_includes_verified_openclaw_walkthrough() -> None:
    readme_path = Path("README.md")

    readme_text = readme_path.read_text(encoding="utf-8")

    assert "## OpenClaw Walkthrough" in readme_text
    assert "docker compose -p ocwalk -f .devcontainer/docker-compose.test.yml up -d openclaw-gateway" in readme_text
    assert "Hi, I'm Alice. I work at Google, I'm learning Rust" in readme_text
    assert "What do you know about me so far?" in readme_text
    assert "OpenClaw runs on `gpt-5.4`" in readme_text
    assert "ClawGraph extraction uses `gpt-5.4-mini`" in readme_text
    assert "Natural OpenClaw auto-storage is still experimental" in readme_text


def test_main_readme_has_generic_architecture_view() -> None:
    readme_path = Path("README.md")

    readme_text = readme_path.read_text(encoding="utf-8")

    assert "Apps / Agents / Workflows" in readme_text
    assert "CLI / Python API / OpenClaw skill" in readme_text
    assert "OpenAI-compatible LLM" in readme_text
    assert "Local Kuzu DB" in readme_text
