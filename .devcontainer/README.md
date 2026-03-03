# DevContainer Test Bed

This directory provides a containerized environment for testing ClawGraph with AI agents (like OpenClaw).

## Quick Start

### Unit Tests (no API key needed)

```bash
docker compose -f .devcontainer/docker-compose.test.yml run test-bed
```

### Integration Tests (requires OPENAI_API_KEY)

```bash
export OPENAI_API_KEY=sk-...
docker compose -f .devcontainer/docker-compose.test.yml run integration-test
```

### VS Code Dev Container

1. Open this repo in VS Code
2. Install the "Dev Containers" extension
3. Press `Ctrl+Shift+P` → "Dev Containers: Reopen in Container"
4. The container will install Python 3.11, Node.js 20, ClawGraph, and OpenClaw

## OpenClaw Skill Testing

The `skills/clawgraph/SKILL.md` can be tested with OpenClaw:

```bash
# Inside the devcontainer
openclaw --skill-dir /workspace/skills
```

Then ask the agent to use its ClawGraph memory skill to store and recall information.

## CI Integration

To run these tests in GitHub Actions, add to your workflow:

```yaml
- name: Container integration tests
  run: |
    docker compose -f .devcontainer/docker-compose.test.yml run test-bed
```

For integration tests that call real LLMs, use GitHub Secrets:

```yaml
- name: Integration tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    docker compose -f .devcontainer/docker-compose.test.yml run integration-test
```
