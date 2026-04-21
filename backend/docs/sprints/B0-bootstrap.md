# B0 — Bootstrap

**Status:** ✅ Complete

## Purpose
Initialise the `swiss-legal-api` project: package manager, Python version pin, tooling config, and dependency manifest.

## Files Created
| File | Purpose |
|---|---|
| `.python-version` | Pins Python 3.12 for uv |
| `pyproject.toml` | Project metadata, runtime + dev deps, pytest/mypy config |
| `.env.example` | Secret names for local dev |
| `.gitignore` | Excludes `.venv`, `__pycache__`, `.env`, `openapi.json`, build artefacts |
| `README.md` | Project overview |
| `ruff.toml` | Line-length 100, py312 target, lint rule set E/F/I/UP/B/SIM/RUF |

## Key Decisions
- **uv** chosen as package manager (deterministic, fast)
- `src/` layout with `hatchling` build backend
- `pytest-asyncio` mode set to `auto` globally in `pyproject.toml`
- `mypy --strict` enforced project-wide

## Acceptance Criteria — All Met
- `uv --version` prints ✅
- `python --version` prints 3.12.x ✅
- `import fastapi, pydantic, anthropic, qdrant_client` prints `ok` ✅
- Exactly six root files created ✅
