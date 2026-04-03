# Agent Instructions

## Project

ClawGraph is a Python CLI tool that uses LLMs to generate Cypher queries
and stores graph-based memory in an embedded Kùzu database.

## Architecture

- `src/clawgraph/cli.py` — CLI entry point using Typer
- `src/clawgraph/llm.py` — LLM calls via OpenAI SDK
- `src/clawgraph/cypher.py` — Cypher generation and validation
- `src/clawgraph/ontology.py` — Schema/ontology tracking
- `src/clawgraph/db.py` — Kùzu database wrapper
- `src/clawgraph/config.py` — Config loading from ~/.clawgraph/config.yaml

## Rules

- All code goes in `src/clawgraph/`
- All tests go in `tests/`
- Use type hints everywhere
- Use `rich` for terminal output
- JSON output via `--output json` flag on all commands
- Never hardcode API keys — use env vars or config
- Cypher must be validated before execution (use `cypher.py`)
- Handle LLM errors gracefully — never crash on bad LLM output
- Idempotent operations — adding the same fact twice should not duplicate
- Use MERGE instead of CREATE in Cypher to prevent duplicates

## Dependencies

- `typer` — CLI framework
- `kuzu` — Embedded graph database
- `openai` — OpenAI SDK (supports any OpenAI-compatible endpoint)
- `pyyaml` — Config file parsing
- `rich` — Terminal formatting

Do not add new dependencies without justification.

## Testing

- Use `pytest`
- Mock LLM calls in tests — never make real API calls in CI
- Test Cypher validation with known good/bad inputs
- Use `tmp_path` fixture for tests that touch the filesystem
- Run tests with: `pytest`

## TDD Workflow (Red → Green → Refactor)

All feature work and bug fixes **must** follow the red/green/refactor cycle:

1. **Red** — Write a failing test first. The test defines the expected behavior
   before any implementation exists. Run `pytest` and confirm the test fails
   with the expected assertion error.
2. **Green** — Write the minimum code to make the test pass. Do not add
   anything beyond what the test requires. Run `pytest` and confirm green.
3. **Refactor** — Clean up the implementation (and the test if needed) while
   keeping all tests green. No behavior changes in this step.

### Agent TDD Rules

- **Never write implementation without a failing test first.** If a test
  doesn't exist for the behavior you're changing, write one before touching
  production code.
- **One test at a time.** Don't batch-write multiple tests before going green.
  Write one failing test → make it pass → repeat.
- **Run the full suite after each green step** (`pytest`) to catch regressions.
- **Bug fixes start with a regression test** that reproduces the bug (red),
  then fix the code (green).
- **Commit at green.** Every commit should have a passing test suite. Never
  commit red.
- **Test names describe behavior, not implementation.** Use
  `test_merge_idempotent` not `test_merge_function`. Tests are living
  documentation.
- **Keep tests fast.** Use `:memory:` databases, mocks for LLM calls, and
  `tmp_path` for filesystem work. The full suite should run in seconds.

## Style

- Python 3.10+
- Follow PEP 8
- Use `ruff` for linting
- Use `mypy` for type checking
- Docstrings on all public functions (Google style)
- Keep functions small and focused

## Commit Messages

- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`
- Keep subject line under 72 characters

## Key Design Decisions

- **Kùzu** over Neo4j — embedded, no server required, native Cypher
- **OpenAI SDK** — direct, minimal deps, supports any OpenAI-compatible endpoint via base_url
- **Typer** over Click — less boilerplate, type-hint driven
- **YAML** config over TOML — more human-readable for simple config
- **Ontology persisted to JSON** — simple, portable, human-editable
