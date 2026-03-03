---
name: clawgraph
description: Graph-based memory using ClawGraph — store, query, and recall structured knowledge across sessions
version: 0.1.0
requires:
  bins:
    - python3
    - pip
  env:
    - OPENAI_API_KEY
tags:
  - memory
  - knowledge-graph
  - persistence
---

# ClawGraph Memory Skill

You have access to **ClawGraph**, a graph-based memory system that lets you store facts as entities and relationships in a persistent knowledge graph. Use it to remember information across conversations.

## Installation

```bash
pip install clawgraph
```

## When to Use This Skill

- When the user tells you something worth remembering (names, preferences, projects, relationships)
- When you need to recall previously stored information
- When the user asks "do you remember..." or "what do you know about..."
- When building up knowledge about a project, team, or domain over time

## How to Store Facts

Use the ClawGraph Python API to add facts as natural language statements:

```python
from clawgraph.memory import Memory

mem = Memory()

# Single fact
mem.add("Alice is a software engineer at Acme Corp")

# Multiple facts at once (faster — one LLM call)
mem.add_batch([
    "Bob manages the design team",
    "Alice and Bob are working on Project Atlas",
    "Project Atlas launches in Q3 2026",
])
```

Each fact is automatically decomposed into entities and relationships, then stored using MERGE (idempotent — safe to add the same fact multiple times).

## How to Query Memory

Ask natural language questions to retrieve stored knowledge:

```python
results = mem.query("Who works at Acme Corp?")
# Returns: [{"e.name": "Alice", "e.label": "Person", ...}]

results = mem.query("What projects is Alice working on?")
```

## How to List Everything

```python
# All entities
mem.entities()

# All relationships  
mem.relationships()

# Full export (entities + relationships + ontology)
mem.export()
```

## Configuration

ClawGraph uses `~/.clawgraph/config.yaml` for defaults, or you can pass config directly:

```python
mem = Memory(config={
    "llm": {"model": "gpt-4o-mini"},
    "db": {"path": "~/.clawgraph/data"},
})
```

The LLM model can be any provider supported by LiteLLM (OpenAI, Anthropic, Ollama, etc.).

## Persistence

The graph database persists to disk automatically at `~/.clawgraph/data`. Data survives restarts.

### Snapshots

```python
# Save a backup
mem.save_snapshot("memory-backup.tar.gz")

# Restore from backup
restored = Memory.from_snapshot("memory-backup.tar.gz", "/path/to/restore")
```

### Seed Facts on Startup

```python
mem = Memory(init_facts=[
    "The user's name is Alice",
    "Alice prefers Python over JavaScript",
])
```

`init_facts` uses MERGE, so it's safe to call on every startup — duplicates are ignored.

## Best Practices

1. **Store facts as clear, simple statements** — "Alice works at Acme" not "I think maybe Alice might work at Acme"
2. **Use add_batch for multiple facts** — it's significantly faster than calling add() in a loop
3. **Query before adding** — check if information already exists to avoid confusion
4. **Use init_facts for baseline knowledge** — things the agent should always know
5. **Export periodically** — use `mem.export()` to inspect what's stored

## Environment Variables

- `OPENAI_API_KEY` — Required for default model (gpt-4o-mini)
- `ANTHROPIC_API_KEY` — For Claude models
- `CLAWGRAPH_MODEL` — Override default model via env var

## CLI Usage

ClawGraph also has a CLI for interactive use:

```bash
clawgraph add "Alice is an engineer at Acme"
clawgraph query "Who works at Acme?"
clawgraph ontology show
clawgraph export
```
