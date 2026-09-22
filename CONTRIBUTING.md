# Contributing to OwnVitals

OwnVitals is a single-user public beta that processes sensitive health data.
Small, focused changes that improve reliability, privacy, documentation,
localization, and the supported beta workflow are welcome.

## Before opening a change

- Search existing issues and keep each pull request focused on one concern.
- Do not add features outside the current [beta scope](docs/release-scope.md)
  without discussing the scope first.
- Never attach real health exports, reports, database files, tokens, logs,
  photos, or identifying screenshots. Use synthetic fixtures and examples.
- Report security problems privately as described in [SECURITY.md](SECURITY.md).

## Development setup

Use Python 3.12 and install the editable development environment:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

On Windows, replace `.venv/bin/python` with
`.\.venv\Scripts\python.exe`.

Before submitting a pull request, run:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/python -m pip_audit --skip-editable
```

## Expectations

- Add or update tests for changed behavior.
- Keep English and Russian user-facing strings in sync.
- Preserve compatibility with the documented SQLite data and configuration
  unless the change includes a safe migration.
- Update the README or privacy/security documentation when behavior or data
  flow changes.
- Avoid adding telemetry, remote services, or new data sharing by default.

By contributing, you agree that your contribution is licensed under the MIT
License included with the project.
