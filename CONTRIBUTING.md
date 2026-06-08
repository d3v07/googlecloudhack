# Contributing

Thanks for your interest in the Evidence-Driven DBRE Agent.

## Development setup

```bash
uv sync --dev
cp .env.example .env          # fill MongoDB + (prod) Vertex values
cd dashboard && npm install
```

## Workflow

- **Every change starts as an issue**, then a branch (`feat/…`, `fix/…`, `docs/…`), then a PR.
  No direct commits to `main`.
- **Tests must pass before a PR merges**, and code review is required on every PR.
- Commits reference issues where applicable: `feat: description (Closes #N)`.

## Checks (run before opening a PR)

```bash
uv run ruff format --check . && uv run ruff check .   # Python format + lint
uv run pytest -q                                       # unit + contract (live tests auto-skip with no DB)
cd dashboard && npm run lint && npm run build          # dashboard typecheck + build
```

## Conventions

- Python: PEP 8, type annotations, `ruff` (line length 100). TypeScript: immutable updates,
  complete effect dependency arrays.
- **`EvidencePack` v1 is frozen** (`contracts/`) — additive-only, and only with explicit review.
- **Agents stay read-only.** Mutation happens only in the deterministic controller, after a
  hash-bound human approval.
- **No secrets in code** — `.env` locally, Secret Manager in production. Never commit `.env` or keys.

## Tests

- Unit + contract tests run offline. Live integration tests are gated on a MongoDB connection
  string and skip without one.
- New behavior needs a test; security-critical code (auth) is held to 100% coverage.
