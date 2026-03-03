# Agent Memory Upgrade Guide

Instructions for AI agents to adopt ClawGraph as their persistent memory backend.

## Overview

ClawGraph replaces flat-file or in-context memory with a **graph database**. Instead of appending to markdown files or stuffing context windows, you store facts as entities and relationships that can be queried with natural language.

**Before**: Agent remembers nothing between sessions, or uses brittle text files.
**After**: Agent has a persistent, queryable knowledge graph that survives restarts.

## Quick Start (3 Steps)

### Step 1: Install

```bash
pip install clawgraph
```

### Step 2: Initialize Memory in Your Agent Loop

```python
from clawgraph.memory import Memory

# Initialize once at agent startup
mem = Memory(
    init_facts=[
        # Seed with baseline knowledge the agent should always have
        "This agent assists with software development",
        "The user prefers Python and TypeScript",
    ],
    config={
        "llm": {"model": "gpt-4o-mini"},  # or any LiteLLM-supported model
    },
)
```

### Step 3: Store and Recall During Conversations

```python
# When the user shares information worth remembering
mem.add("The user's name is Alice")
mem.add("Alice is working on Project Phoenix")

# When you need to recall something
results = mem.query("What project is the user working on?")
# → [{"e.name": "Project Phoenix", ...}]

# Batch mode for multiple facts (1 LLM call, much faster)
mem.add_batch([
    "Project Phoenix uses React and FastAPI",
    "The deadline is March 2026",
    "Bob is the project manager",
])
```

## Integration Patterns

### Pattern 1: Session Bootstrap

Load all known context at the start of each session:

```python
mem = Memory()

# Get everything the agent knows
export = mem.export()
entities = export["entities"]
relationships = export["relationships"]

# Build a context summary for the system prompt
context_lines = []
for e in entities:
    context_lines.append(f"- {e['e.name']} ({e['e.label']})")
for r in relationships:
    context_lines.append(f"- {r['a.name']} --{r['r.type']}--> {r['b.name']}")

system_context = "Known facts:\n" + "\n".join(context_lines)
```

### Pattern 2: Selective Recall

Query only what's relevant to the current conversation:

```python
# User asks about a project
results = mem.query("What do we know about Project Phoenix?")

# User asks about a person
results = mem.query("Who is Bob and what does he do?")

# User asks about relationships
results = mem.query("Who works with Alice?")
```

### Pattern 3: Continuous Learning

Store new information as conversations happen:

```python
def process_user_message(message: str) -> None:
    # Check if the message contains storable facts
    # (use your own heuristic or LLM classification)
    if contains_factual_info(message):
        mem.add(message)

    # Query memory for relevant context
    context = mem.query(f"What do I know that's relevant to: {message}")
    
    # Use context in your response generation
    ...
```

### Pattern 4: Ontology Constraints

Restrict what the agent can store to specific entity types:

```python
mem = Memory(
    allowed_labels=["Person", "Project", "Technology", "Company"],
    allowed_relationship_types=["WORKS_AT", "WORKS_ON", "USES", "MANAGES", "KNOWS"],
)
```

This prevents the graph from becoming noisy with irrelevant entity types.

### Pattern 5: Snapshots for Safety

Back up memory before risky operations:

```python
# Before a large import or migration
mem.save_snapshot("pre-migration-backup.tar.gz")

# If something goes wrong, restore
mem = Memory.from_snapshot("pre-migration-backup.tar.gz", "/path/to/db")
```

## What Gets Stored

ClawGraph uses a generic schema:

| Table | Columns |
|-------|---------|
| **Entity** | `name` (PK), `label`, `created_at`, `updated_at` |
| **Relates** | `type`, `created_at`, from Entity → to Entity |

Example: "Alice works at Acme" becomes:
- Entity: `{name: "Alice", label: "Person"}`
- Entity: `{name: "Acme", label: "Organization"}`
- Relates: `Alice --WORKS_AT--> Acme`

## Configuration Reference

### Config File (`~/.clawgraph/config.yaml`)

```yaml
llm:
  model: gpt-4o-mini
  temperature: 0.0

db:
  path: ~/.clawgraph/data
```

### Programmatic Config

```python
mem = Memory(config={
    "llm": {"model": "gpt-4o-mini", "temperature": 0.0},
    "db": {"path": "/custom/path/to/db"},
})
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI API access |
| `ANTHROPIC_API_KEY` | Anthropic API access |

Any LiteLLM-supported provider works — see [LiteLLM docs](https://docs.litellm.ai/docs/providers).

## Decision Heuristics: When to Store vs. Ignore

**STORE** when the user:
- Shares personal info (name, role, preferences)
- Describes project details (tech stack, deadlines, team)
- Establishes relationships ("Alice manages Bob")
- States preferences ("I prefer tabs over spaces")
- Provides domain knowledge worth recalling later

**IGNORE** when:
- The user is asking a one-off question
- The information is ephemeral (weather, time)
- The statement is an instruction, not a fact
- The information is already stored (check with `mem.query()` first)

## Migration from Other Memory Systems

### From Markdown Files

```python
import pathlib

mem = Memory()

# Read existing memory files
memory_dir = pathlib.Path("~/.agent/memory").expanduser()
for md_file in memory_dir.glob("*.md"):
    content = md_file.read_text()
    # Split into individual facts (one per line or paragraph)
    facts = [line.strip() for line in content.splitlines() if line.strip()]
    mem.add_batch(facts)
```

### From JSON/SQLite

```python
import json

mem = Memory()

with open("memory.json") as f:
    data = json.load(f)

facts = [item["content"] for item in data["memories"]]
mem.add_batch(facts)
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `LLMError` on add | Check API key env vars are set |
| Duplicate entities | Expected — MERGE is idempotent, duplicates are harmless |
| Slow batch operations | Reduce batch size or use a faster model |
| DB locked on Windows | Call `mem.close()` before snapshots |
| Empty query results | Check `mem.entities()` to verify data exists |
