# DevContainer Test Bed

This directory provides a containerized environment for testing ClawGraph with AI agents (OpenClaw).

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Docker Compose                                 │
│                                                 │
│  ┌───────────────────────┐                      │
│  │  openclaw-gateway     │ ← port 18789         │
│  │  (OpenClaw agent)     │   WebChat + Control  │
│  │  + ClawGraph skill    │   UI in browser      │
│  └──────────┬────────────┘                      │
│             │ shared network                    │
│  ┌──────────▼────────────┐                      │
│  │  openclaw-test        │                      │
│  │  (CLI test runner)    │                      │
│  │  openclaw agent --msg │                      │
│  │  clawgraph export     │ ← inspect results    │
│  └───────────────────────┘                      │
└─────────────────────────────────────────────────┘
```

## Prerequisites

- Docker + Docker Compose v2
- `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) env var set

## Quick Start

### 1. Unit Tests (no API key needed)

```bash
docker compose -f .devcontainer/docker-compose.test.yml run test-bed
```

### 2. ClawGraph CLI Integration Tests (requires API key)

```bash
export OPENAI_API_KEY=sk-...
docker compose -f .devcontainer/docker-compose.test.yml run integration-test
```

### 3. Full OpenClaw Agent Test (the interesting one)

Start the OpenClaw gateway with the ClawGraph skill loaded:

```bash
export OPENAI_API_KEY=sk-...
docker compose -f .devcontainer/docker-compose.test.yml up openclaw-gateway
```

The gateway prints a token URL. Open `http://127.0.0.1:18789/` in your browser
to access the **WebChat UI** — you can chat with the agent directly and ask it
to use ClawGraph.

In a **second terminal**, run the automated test:

```bash
docker compose -f .devcontainer/docker-compose.test.yml run openclaw-test
```

This sends messages to the agent via CLI, then inspects ClawGraph directly.

## How to Communicate with the Agent

### Option A: WebChat UI (interactive, easiest)

1. Start the gateway: `docker compose ... up openclaw-gateway`
2. Open `http://127.0.0.1:18789/` in your browser
3. Paste the gateway token (printed in terminal) into Settings
4. Chat naturally: "Remember that Alice works at Google"
5. Then: "What do you know about Alice?"

### Option B: CLI one-shot (scriptable, for CI)

```bash
# Send a single message and get the agent's response on stdout
docker compose -f .devcontainer/docker-compose.test.yml run openclaw-test \
  bash -c 'openclaw agent --message "Store: Bob is a designer at Netflix"'
```

### Option C: Inspect ClawGraph directly (verification)

After the agent has stored facts, check the graph:

```bash
# From the gateway container
docker compose -f .devcontainer/docker-compose.test.yml exec openclaw-gateway \
  clawgraph export --output json

# Or query
docker compose -f .devcontainer/docker-compose.test.yml exec openclaw-gateway \
  clawgraph query "Who works where?" --output json
```

## VS Code Dev Container

1. Open this repo in VS Code
2. Install the "Dev Containers" extension
3. Press `Ctrl+Shift+P` → "Dev Containers: Reopen in Container"
4. The container installs Python 3.11, Node.js 22, ClawGraph, and OpenClaw
5. Port 18789 is forwarded automatically
6. Run `openclaw onboard` inside the container to set up the agent

## OpenClaw Skill Location

The ClawGraph skill is at `skills/clawgraph/SKILL.md`. The docker-compose
copies it to `~/.openclaw/workspace/skills/clawgraph/SKILL.md` inside the
container so OpenClaw auto-discovers it.

## CI Integration

Unit tests (no secrets needed):

```yaml
- name: Container unit tests
  run: |
    docker compose -f .devcontainer/docker-compose.test.yml run test-bed
```

Integration tests with real LLM calls (use GitHub Secrets):

```yaml
- name: Integration tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    docker compose -f .devcontainer/docker-compose.test.yml run integration-test
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "pairing required" | Run `openclaw devices list` then `openclaw devices approve <id>` |
| Gateway won't start | Check `OPENAI_API_KEY` is set; run `openclaw doctor` |
| Port 18789 in use | Stop other OpenClaw instances or change port in compose |
| Node version error | Ensure image has Node ≥22 (check `node --version`) |
