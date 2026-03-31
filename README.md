# ClawGraph

> Graph-based memory abstraction layer for AI agents.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![Tests](https://github.com/clawgraph/clawgraph/actions/workflows/test.yml/badge.svg)](https://github.com/clawgraph/clawgraph/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/clawgraph.svg)](https://pypi.org/project/clawgraph/)

**Official site**: [clawgraph.ai](https://clawgraph.ai)

## What It Does

ClawGraph converts natural language into graph memory. Tell it facts, it stores them in a local embedded graph database ([Kùzu](https://kuzudb.com/)). Ask it questions, it queries the graph and returns results.

- **Natural language in, graph memory out** — no Cypher knowledge required
- **Embedded database** — no servers, no Docker, just a local file
- **Automatic ontology** — the LLM infers and maintains your graph schema
- **Python API** — `from clawgraph import Memory` for use in agentic loops
- **Batch mode** — process multiple facts in a single LLM call
- **Provider-agnostic** — works with any LLM via LiteLLM (OpenAI, Anthropic, etc.)
- **Idempotent** — adding the same fact twice won't create duplicates

## Installation

```bash
pip install clawgraph
```

## Quick Start

### CLI

```bash
# Store facts
clawgraph add "John works at Acme Corp as a software engineer"
clawgraph add "Alice is a data scientist at Google"
clawgraph add "John and Alice are friends"

# Query the graph
clawgraph query "Where does John work?"
# ┏━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┓
# ┃ a.name ┃ r.type   ┃ b.name    ┃
# ┡━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━┩
# │ John   │ WORKS_AT │ Acme Corp │
# └────────┴──────────┴───────────┘

# Batch add (one LLM call for multiple facts)
clawgraph add-batch "Bob is a designer" "Bob works at Netflix"

# View the ontology
clawgraph ontology

# Export the graph as JSON
clawgraph export
clawgraph export graph.json

# JSON output for agents
clawgraph query "Who works at Acme?" --output json

# Configure
clawgraph config llm.model gpt-4o-mini
clawgraph config                         # show all config
```

### Python API (for agentic loops)

```python
from clawgraph import Memory

mem = Memory()

# Add facts
mem.add("John works at Acme Corp")
mem.add("Alice is a data scientist at Google")

# Batch add — multiple facts, one LLM call
mem.add_batch([
    "Bob is a designer at Netflix",
    "Carol manages engineering at Acme",
    "Bob and Carol are married",
])

# Query
results = mem.query("Who works where?")
# [{"a.name": "John", "r.type": "WORKS_AT", "b.name": "Acme Corp"}, ...]

# Direct access
mem.entities()        # all entities
mem.relationships()   # all relationships
mem.export()          # full graph + ontology as dict
```

For agents, initialize `Memory()` once and reuse it — the DB connection and ontology are kept warm across calls.

### Custom Ontology (constrained extraction)

By default ClawGraph lets the LLM choose entity labels and relationship types freely. For domain-specific applications, you can constrain extraction to a fixed schema:

```python
from clawgraph import Memory

# Only extract these entity types and relationships
mem = Memory(
    allowed_labels=["Person", "Company", "Skill"],
    allowed_relationship_types=["WORKS_AT", "HAS_SKILL", "MANAGES"],
)

mem.add("Alice is a Python developer at Acme Corp")
# Entities: Alice (Person), Python (Skill), Acme Corp (Company)
# Relationships: Alice -WORKS_AT-> Acme Corp, Alice -HAS_SKILL-> Python
```

You can also pass a fully configured `Ontology` object:

```python
from clawgraph.ontology import Ontology
from clawgraph import Memory

ont = Ontology(
    allowed_labels=["Patient", "Doctor", "Condition"],
    allowed_relationship_types=["TREATS", "DIAGNOSED_WITH", "REFERRED_BY"],
)
mem = Memory(ontology=ont)
```

Constraints are injected into the LLM prompt, so the model will only produce entities and relationships matching your schema.

### Hybrid Retrieval (Vector Fallback)

When a Cypher query returns empty results (e.g. due to a name mismatch), ClawGraph can fall back to vector similarity search over entity names and automatically traverse the graph neighbourhood of matching entities.

```bash
# Install with vector support
pip install clawgraph[vectors]
```

```python
from clawgraph import Memory

mem = Memory(enable_vectors=True)

# Store facts — entity names are also embedded as vectors
mem.add("Alice works at Acme Corp")
mem.add("Bob manages the engineering team at Acme Corp")

# Exact Cypher match works as normal
mem.query("Who works at Acme Corp?")

# Fuzzy match — "ACME project" doesn't exist in the graph, but
# vector similarity finds "Acme Corp" and returns its neighbourhood
mem.query("Tell me about the ACME project")
```

**How it works:**

1. `query()` first tries the LLM-generated Cypher query (primary path)
2. If Cypher returns no results and vectors are enabled, it embeds the question using `text-embedding-3-small`
3. Cosine similarity search finds the closest entity names in the vector index
4. For each match, it traverses 1-2 hops in the graph to collect related context

**Notes:**

- `enable_vectors=False` (default) — works exactly as before with no extra dependencies
- Requires `numpy` — installed via `pip install clawgraph[vectors]`
- If `enable_vectors=True` is set without numpy installed, a clear `ImportError` is raised
- Vector index persists to disk alongside the Kùzu database

## Architecture

```
User/Agent → LLM (extracts entities) → Cypher (MERGE) → Kùzu (embedded graph DB)
```

ClawGraph uses a **generic schema** — all entities are stored as `Entity(name, label)` nodes and all relationships use `Relates(type)` edges. This means the LLM doesn't need to generate table DDL, just extract structured data.

| Component | Library | Why |
|-----------|---------|-----|
| CLI | [Typer](https://typer.tiangolo.com/) | Type-hint driven, minimal boilerplate |
| LLM | [LiteLLM](https://docs.litellm.ai/) | Any provider via one interface |
| Graph DB | [Kùzu](https://kuzudb.com/) | Embedded, no server, native Cypher |
| Output | [Rich](https://rich.readthedocs.io/) | Tables, panels, colors |

## Configuration

Config lives at `~/.clawgraph/config.yaml`:

```yaml
llm:
  model: gpt-4o-mini
  temperature: 0.0
db:
  path: ~/.clawgraph/data
output:
  format: human
```

### API Key Setup

ClawGraph needs an API key from your LLM provider. There are three ways to provide it (in priority order):

**1. Project `.env` file (recommended)**

Create a `.env` file in your working directory:

```bash
OPENAI_API_KEY=sk-proj-...
```

ClawGraph auto-loads `.env` from the current directory. This file takes precedence over system environment variables.

**2. Environment variable**

```bash
# OpenAI
export OPENAI_API_KEY=sk-proj-...

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# Azure OpenAI
export AZURE_API_KEY=...
export AZURE_API_BASE=https://your-resource.openai.azure.com/
```

**3. Config file**

You can set the model (but not the key) via config:

```bash
clawgraph config llm.model gpt-4o-mini
```

### Recommended Models

| Model | Speed | Cost | Best for |
|-------|-------|------|----------|
| **`gpt-4o-mini`** | ~1s | ~$0.15/1M tokens | **Default.** Best balance of speed and accuracy for entity extraction. Recommended for agentic loops. |
| `gpt-4o` | ~2-3s | ~$2.50/1M tokens | Higher accuracy on complex or ambiguous statements. |
| `claude-3-5-haiku-latest` | ~1s | ~$0.25/1M tokens | Fast Anthropic alternative. |
| `claude-sonnet-4-20250514` | ~2s | ~$3/1M tokens | Best Anthropic accuracy. |

For agentic loops where you're calling `add()` frequently, **`gpt-4o-mini` is recommended** — it's fast enough for real-time use and accurate enough for entity extraction.

Override per-call with `--model`:

```bash
clawgraph add "complex statement" --model gpt-4o
```

Or via the Python API:

```python
mem = Memory(model="gpt-4o-mini")  # set once
```

Data is stored at `~/.clawgraph/data` (Kùzu DB) and `~/.clawgraph/ontology.json`.

## Development

```bash
git clone https://github.com/clawgraph/clawgraph.git
cd clawgraph
python -m venv .venv
.venv/Scripts/activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
