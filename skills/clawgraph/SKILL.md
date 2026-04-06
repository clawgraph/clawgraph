---
name: clawgraph
description: Automatically store explicit durable user facts and recall them later; do not infer or upgrade weak signals
homepage: https://github.com/clawgraph/clawgraph
version: 0.1.3
metadata: {"openclaw": {"emoji": "🧠", "requires": {"bins": ["clawgraph"], "env": ["OPENAI_API_KEY"]}, "primaryEnv": "OPENAI_API_KEY", "install": [{"id": "uv", "kind": "uv", "package": "clawgraph==0.1.3", "label": "Install ClawGraph (uv)", "bins": ["clawgraph"]}]}}
tags:
  - memory
  - knowledge-graph
  - persistence
---

# ClawGraph Memory Skill

You have access to **ClawGraph**, a graph-based memory CLI that stores facts as entities and relationships in a persistent knowledge graph. Use it to remember information across conversations.

## When to Use

- User tells you something worth remembering (names, preferences, projects, relationships)
- You need to recall previously stored information
- User asks "do you remember..." or "what do you know about..."
- Building up knowledge about a project, team, or domain over time

## Storage Guardrails

- Proactively store durable user facts without waiting for an explicit memory command when the user shares information that is likely to matter later.
- Only store facts that are explicitly stated by the user or already confirmed in the current session.
- Preserve the user's phrasing when possible, and preserve the user's meaning closely when storing facts; prefer the exact claim they made over a stronger paraphrase.
- Do not infer, upgrade, or invent facts. For example, "I'm learning Rust" does not mean "I am a Rust developer," and "I'm planning a demo" is not an occupation.
- If a detail is ambiguous, speculative, or feels too weak to persist, do not store it.
- When several explicit facts appear in one message, store only the durable facts that are likely to matter later.

## Automatic Decision Rule

When the user naturally shares stable personal, project, team, or preference information, assume you should store it in ClawGraph even if they did not say "remember this." Good candidates include names, employers, roles, long-term goals, durable preferences, important relationships, and active projects.

Do not store fleeting conversational filler, jokes, weak guesses, or details that are only implied.

## Store Facts (CLI)

```bash
# Single fact
clawgraph add "Alice is a senior engineer at Acme Corp" --output json

# Multiple facts at once (one LLM call — much faster)
clawgraph add-batch "Bob manages the design team" "Alice and Bob work on Project Atlas" --output json
```

Each fact is automatically decomposed into entities and relationships using MERGE (idempotent — safe to add the same fact twice).

## Query Memory (CLI)

```bash
# Natural language question — returns matching results
clawgraph query "Who works at Acme Corp?" --output json

# Inspect the full graph
clawgraph export --output json
```

## Common Patterns

```bash
# Store, then verify
clawgraph add "Carol is the CTO of Acme Corp" --output json
clawgraph query "Who is the CTO of Acme Corp?" --output json

# Batch store related facts
clawgraph add-batch \
  "Project Atlas launches Q3 2026" \
  "Alice leads Project Atlas" \
  "Atlas uses a graph database backend" \
  --output json

# Show what's stored
clawgraph export --output json

# View the ontology (schema)
clawgraph ontology --output json
```

## Python API (for complex workflows)

When you need programmatic control, use the Python API:

```python
from clawgraph.memory import Memory

mem = Memory()
mem.add("Alice works at Acme Corp")
results = mem.query("Who works at Acme Corp?")
print(results)
mem.add_batch(["Bob is a designer", "Bob works at Acme Corp"])
```

## Key Details

- **Persistence**: Data stored at `~/.clawgraph/data` — survives restarts
- **Idempotent**: Uses MERGE — adding the same fact twice won't create duplicates
- **JSON output**: Always use `--output json` for structured, parseable results
- **Config**: `~/.clawgraph/config.yaml` for defaults (model, db path)
- **Models**: OpenAI-compatible APIs today via the OpenAI SDK. The current default model path is `gpt-5.4-mini` for ClawGraph extraction.
- **Env vars**: `OPENAI_API_KEY` is required. `OPENAI_BASE_URL` is optional for other OpenAI-compatible endpoints.
