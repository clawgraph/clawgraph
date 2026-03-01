# ClawGraph

> Graph-based memory abstraction layer for AI agents.

**Official site**: [clawgraph.ai](https://clawgraph.ai)

> ⚠️ This is the only official ClawGraph project. It lives at `clawgraph.ai` and this GitHub repository.

## What It Does

ClawGraph is a CLI tool that uses an LLM to convert natural language into Cypher queries, managing persistent memory in a local embedded graph database ([Kùzu](https://kuzudb.com/)).

- **Natural language in, graph memory out** — no Cypher knowledge required
- **Embedded database** — no servers, no Docker, just a local file
- **Automatic ontology** — the LLM infers and maintains your graph schema
- **Agent-friendly** — JSON output mode for programmatic consumption
- **Provider-agnostic** — works with any LLM via LiteLLM

## Installation

```bash
pip install clawgraph
```

## Usage

```bash
# Store a fact
clawgraph add "John works at Acme Corp as a senior engineer"

# Query the graph
clawgraph query "Where does John work?"

# View the ontology
clawgraph ontology

# Export the graph
clawgraph export graph.json

# JSON output for agents
clawgraph query "Who works at Acme?" --output json

# Configure the LLM
clawgraph config llm.model gpt-4
```

## Architecture

```
User/Agent → CLI → LLM (generates Cypher) → Kùzu (embedded graph DB)
```

| Component | Library |
|-----------|---------|
| CLI | [Typer](https://typer.tiangolo.com/) |
| LLM | [LiteLLM](https://docs.litellm.ai/) |
| Graph DB | [Kùzu](https://kuzudb.com/) (embedded) |
| Output | [Rich](https://rich.readthedocs.io/) |

## Configuration

Config lives at `~/.clawgraph/config.yaml`:

```yaml
llm:
  model: gpt-4
  temperature: 0.0
db:
  path: ~/.clawgraph/data
output:
  format: human
```

Set your API key:

```bash
export OPENAI_API_KEY=sk-...
# or
export ANTHROPIC_API_KEY=sk-ant-...
```

## Development

```bash
git clone https://github.com/clawgraph/clawgraph.git
cd clawgraph
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
