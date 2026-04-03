# Contributing to ClawGraph

Thank you for your interest in contributing to ClawGraph! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/clawgraph/clawgraph.git
cd clawgraph

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_db.py

# Run with coverage
pytest --cov=clawgraph
```

All tests must pass before submitting a PR. Tests that call the LLM are mocked — no API key is needed to run the test suite.

## Code Style

We use **ruff** for linting and **mypy** for type checking:

```bash
# Lint
ruff check src/ tests/

# Auto-fix lint issues
ruff check --fix src/ tests/

# Type check
mypy src/clawgraph/
```

### Style Guidelines

- **Python 3.10+** — use modern type hints (`str | None` instead of `Optional[str]`)
- **PEP 8** — enforced by ruff
- **Google-style docstrings** on all public functions
- **Type hints** on all function signatures
- **Line length** — 88 characters (configured in `pyproject.toml`)
- Keep functions small and focused

## Pull Request Process

1. **Create a branch** from `main` with a descriptive name (e.g., `feat/stats-command`, `fix/query-error`)
2. **Make your changes** — keep PRs focused on a single concern
3. **Add tests** for new functionality
4. **Ensure all checks pass:**
   ```bash
   ruff check src/ tests/
   mypy src/clawgraph/
   pytest
   ```
5. **Open a PR** against `main` with a clear description of what changed and why
6. **Address review feedback** — we aim for a quick turnaround

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add stats command
fix: handle empty database in query
docs: update README with new CLI examples
test: add tests for clear command
chore: update ruff to 0.9.10
```

- **feat:** — new feature
- **fix:** — bug fix
- **docs:** — documentation only
- **test:** — adding or updating tests
- **chore:** — maintenance (deps, CI, config)

Keep the subject line under 72 characters.

## Project Structure

```
src/clawgraph/
├── cli.py       # CLI entry point (Typer)
├── db.py        # Kùzu database wrapper
├── llm.py       # LLM integration (OpenAI SDK)
├── cypher.py    # Cypher generation and validation
├── ontology.py  # Schema/ontology tracking
├── config.py    # Config loading (~/.clawgraph/config.yaml)
└── memory.py    # High-level Memory API

tests/
├── test_cli.py
├── test_db.py
├── test_llm.py
├── test_cypher.py
├── test_ontology.py
├── test_config.py
└── test_memory.py
```

## Key Design Decisions

- **Kùzu** over Neo4j — embedded, no server required
- **OpenAI SDK** — direct, minimal deps, supports any OpenAI-compatible endpoint
- **Typer** over Click — less boilerplate, type-hint driven
- **MERGE over CREATE** — all Cypher uses MERGE for idempotency
- **Generic schema** — Entity/Relates tables rather than per-type tables

## Reporting Issues

Open an issue on [GitHub Issues](https://github.com/clawgraph/clawgraph/issues) with:

- A clear description of the problem or feature request
- Steps to reproduce (for bugs)
- Expected vs actual behavior
- Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).
