# Contributing to ClawGraph

Thanks for your interest in contributing to ClawGraph! Here's how to get started.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:

   ```bash
   git clone https://github.com/<your-username>/clawgraph.git
   cd clawgraph
   ```

3. **Create a branch** for your change:

   ```bash
   git checkout -b feat/my-feature
   ```

4. **Install** dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # macOS/Linux
   # .venv\Scripts\activate   # Windows
   pip install -e ".[dev]"
   ```

## Development Workflow

1. Make your changes in `src/clawgraph/`.
2. Add or update tests in `tests/`.
3. Run checks:

   ```bash
   ruff check src/ tests/
   mypy src/clawgraph/ --ignore-missing-imports
   pytest
   ```

4. **Commit** using [conventional commits](https://www.conventionalcommits.org/):

   ```
   feat: add new feature
   fix: correct a bug
   docs: update documentation
   test: add or fix tests
   chore: maintenance tasks
   ```

5. **Push** your branch and open a **Pull Request** against `main`.

## Code Style

- Python 3.10+
- Follow PEP 8 (enforced by `ruff`)
- Type hints on all functions
- Google-style docstrings on public functions
- Keep functions small and focused

## Testing

- Use `pytest` with `tmp_path` for filesystem tests.
- Mock LLM calls — never make real API calls in tests.
- Use `GraphDB(db_path=":memory:")` for database tests.

## Reporting Issues

Open an issue on GitHub with:

- A clear description of the problem or suggestion.
- Steps to reproduce (if applicable).
- Expected vs. actual behavior.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
