# Evidence-Driven DBRE Agent

Two personas, one MongoDB performance loop:

- **Users** run real query workloads against a live Atlas collection from a guided console. Each
  query's real `explain` evidence is captured and attributed to whoever ran it.
- A **DBRE** triages the *actual* slowest captured queries — ranked by explain evidence (blocking
  sort, collection scan, over-scan ratio), not wall-clock — diagnoses one, and approves an
  ESR-correct index fix. The controller applies it behind a hash-bound human gate, then verifies it.

There is no hardcoded demo query: the queries the DBRE fixes are the ones users really ran.

## Flow

```text
USER  ─ login ─> Workload Console ─ guided query ─> read API ─ explain ─> Atlas
                                                       └─ capture (attributed) ─> query_log
DBRE  ─ login ─> Slow-Query Queue (ranked by evidence)
                   └─ Diagnose ─> deterministic ESR diagnosis ─> DIAGNOSED EvidencePack
                        └─ hash-bound Approve ─> apply index + re-explain ─> VERIFIED
```

## Architecture

- **Dashboard** — Next.js (App Router). Seeded role-based login backed by an httpOnly session
  cookie; the user persona is confined to the workload console, the DBRE to the triage + review
  planes. The read API is the security authority — it re-verifies the session bearer on every data
  call, and the approver identity always comes from the verified session, never the browser.
- **Read API** — FastAPI on Cloud Run. Guided, validated, read-only workload queries; evidence
  capture; the evidence-ranked queue; and the DIAGNOSE → (human APPROVE) → VERIFY remediation flow.
  Index mutation happens only after a matching hash-bound approval.
- **Diagnosis** — a pure, deterministic ESR analyzer derives the correct index key order
  (Equality → Sort → Range) from each query's own structure. In production three read-only Vertex AI
  Agent Engine roles narrate the diagnosis; locally the controller runs deterministically.
- **State** — MongoDB Atlas. `dbre_state` holds `users`, `query_log`, `evidence_packs`, and the
  internal ledger collections; the demo workload runs against `sample_supplies.sales_agent_demo`.

The dashboard reads only `EvidencePack` v1 JSON; that contract is frozen in `contracts/`.

## Quickstart

```bash
uv sync --dev
cp .env.example .env     # fill MongoDB + (prod) Vertex values; set SESSION_SECRET + RUN_API_TOKEN

# one-time data + accounts (against your Atlas cluster)
uv run python seed/seed_demo_fixture.py seed   # 300k demo docs
uv run python seed/seed_workload.py verify     # baseline indexes + prove the trap presets
uv run python seed/seed_users.py               # Dev Trivedi, Aakash Singh, DBRE — prints passwords once

uv run pytest -q                                # unit + contract (live integration auto-skips with no conn)
```

Run the full stack locally (deterministic controller, no Vertex needed):

```bash
SS=$(openssl rand -hex 32); RT=$(openssl rand -hex 16)
# read API (reads Atlas via MDB_MCP_CONNECTION_STRING from .env)
SESSION_SECRET=$SS RUN_API_TOKEN=$RT uv run uvicorn api.server:app --port 8000
# dashboard — SAME SESSION_SECRET + RUN_API_TOKEN, API_URL -> the read API
cd dashboard && npm install && \
  API_URL=http://127.0.0.1:8000 SESSION_SECRET=$SS RUN_API_TOKEN=$RT npm run dev
```

Re-run `seed/seed_workload.py reset` between demos — an approved fix removes the trap for a whole
store/method class.

## Safety

- Agents and tools are read-only; only the deterministic controller mutates, and only after a
  matching hash-bound approval.
- The approver identity comes from the verified DBRE session — never from the browser.
- Secrets live in `.env` (local) / Secret Manager (prod); none are committed.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
