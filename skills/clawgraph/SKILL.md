---
name: clawgraph
description: Graph-based memory — store, query, and recall structured knowledge across sessions
version: 0.1.1
metadata: {"openclaw": {"requires": {"bins": ["clawgraph"], "env": ["OPENAI_API_KEY"]}, "primaryEnv": "OPENAI_API_KEY", "install": [{"id": "pip", "kind": "node", "label": "Install ClawGraph (pip)", "bins": ["clawgraph"]}]}}
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
- **Models**: Any LiteLLM-supported provider (OpenAI, Anthropic, Ollama, etc.)
- **Env vars**: `OPENAI_API_KEY` (required), `CLAWGRAPH_MODEL` (optional override)
