# Automated PyPI Publishing via Trusted Publishers

ClawGraph uses GitHub Actions with PyPI Trusted Publishers (OIDC) to
automatically publish new versions to PyPI when a GitHub Release is created.
No API keys or tokens are needed.

## How It Works

1. A maintainer creates a **GitHub Release** with a tag like `v0.1.2`.
2. The `publish.yml` workflow triggers automatically.
3. GitHub Actions builds the package and uploads it to PyPI using OIDC
   (OpenID Connect) — no secrets required.

## Setup (One-Time)

### 1. Configure Trusted Publisher on PyPI

### 3. Verify the Workflow File

The workflow lives at `.github/workflows/publish.yml`. It:

- Triggers on `release` events (type `published`)
- Builds the package with `python -m build`
- Publishes via `pypa/gh-action-pypi-publish` using OIDC (no token)

## Release Flow

```
1. Bump version in pyproject.toml and src/clawgraph/__init__.py
2. Merge to main via PR
3. Create a GitHub Release:
   - Tag: v<version>  (e.g. v0.1.2)
   - Target: main
   - Title: v<version>
   - Auto-generate release notes or write manually
4. publish.yml runs automatically → package appears on PyPI
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `403 Forbidden` on upload | Trusted Publisher not configured or environment name mismatch — verify PyPI settings match exactly |
| Workflow doesn't trigger | Ensure the release type is `published` and the workflow file is on the default branch |
| Build fails | Run `python -m build` locally to reproduce |
| Wrong version uploaded | Check that `pyproject.toml` and `__init__.py` versions match the release tag |

## Removing the Old Manual Flow

Once Trusted Publishing is verified working:

1. Revoke any PyPI API tokens at <https://pypi.org/manage/account/>
2. Remove any `PYPI_TOKEN` secrets from GitHub repo settings
3. Stop using `twine upload` locally
