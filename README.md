# Evidence-Driven DBRE Agent

> A safe MongoDB index-remediation control plane. It turns a slow query into a
> measured, human-approved index fix — and never lets automation touch the
> database on its own.

A Gemini-powered MongoDB performance engineer: it detects a blocking-sort slow query,
proposes the **ESR-correct** index from real `explain` evidence, gates the `apply`
behind a **hash-bound human approval**, verifies the fix by re-measuring, and records a
signed `EvidencePack` plus an internal event ledger for every run.

**Live demo:** https://gcrah-dashboard-2vbnam7yma-uc.a.run.app

---

## The core rule

```
Agents recommend.            read-only reasoning — never decide, apply, or verify
Deterministic code decides.  ESR winner · evidence hash · phase gates
Humans approve.              a specific evidence hash, before any mutation
Verification proves.         re-explain — VERIFIED only on measured improvement
```

This separation of authority is the whole point: an agent can be wrong, and nothing
breaks — deterministic code and a human stand between any recommendation and the database.

## Architecture

```
Operator dashboard (Next.js)
      │   reads EvidencePack JSON only
      ▼
FastAPI on Cloud Run          reads public · writes token-gated (Secret Manager)
      │
      ├─ Diagnose / Candidate / Rationale roles   (Vertex AI Agent Engine, read-only)
      │     read-only Mongo tools:
      │       explain_slow_query · diagnose_candidate
      │       compare_candidate_indexes · rationalize_recommendation
      ▼
Deterministic Python controller   ESR winner · evidence hash · phase gates · apply · verify
      │
      ▼
MongoDB Atlas (target)  +  Evidence Ledger
   slow_queries · candidates · experiments · decisions
   evidence_packs · approvals · applications · verifications
```

Five operator stages (**Detect → Diagnose → Test → Approve → Verify**) sit over a
deterministic three-phase safety engine (**DIAGNOSE → APPROVE → VERIFY**).

`POST /run` creates a **gated, read-only run**; mutation is impossible until the operator
approves a matching `EvidencePack` hash. `POST /packs/{run_id}/decision` is the only path
that can issue the one-time apply.

## Golden path

```
slow query → explain → diagnose the blocking sort → compare candidate indexes
  → deterministic ESR winner → EvidencePack (bound evidence hash)
  → human approves that exact hash → backend applies the index
  → re-explain verification → ledger trace
```

A run is **VERIFIED** only when *all* hold (deterministic, backend-side):

1. the blocking `SORT` is gone in the after-plan,
2. the recommended index is evidenced in the winning/hinted plan,
3. at least one metric improves (docs examined, keys examined, or millis),
4. the result is written to the trace/ledger.

Otherwise the run stays **APPROVED** (applied-but-not-verified) with the failure recorded.
The frontend never marks a run VERIFIED.

## Quick start

**Dashboard (Next.js):**

```bash
cd dashboard
npm install
npm run dev          # http://localhost:7777  (set PORT as needed)
```

With no API configured, the dashboard runs in a clearly-labeled **simulation** mode
(read-only, never shown as live). Point it at a live backend with `API_URL`.

**Backend + tests (Python, uv):**

```bash
uv sync --dev
cp .env.example .env     # fill Google Cloud project + MongoDB values
uv run pytest -q
```

## Dashboard routes

| Route | Purpose |
|---|---|
| `/` | overview — fleet status + run list |
| `/runs/[run_id]` | single-run review — approval gate, before/after explain diff, trace |
| `/run-review?run_id=…` | legacy alias for the run view |
| `/system-map` | architecture + control-plane + oversight map |
| `/history` | run history & compare |
| `/audit` | approval / verification / policy audit trail |
| `/intake` | intake + API gateway |

## API

| Method · Route | Auth | Purpose |
|---|---|---|
| `GET /packs` | public | list EvidencePacks |
| `GET /packs/{run_id}` | public | fetch one EvidencePack |
| `POST /run` | token | create a gated, read-only DIAGNOSED run |
| `POST /packs/{run_id}/decision` | token | hash-bound approve / reject |

The dashboard reaches the write endpoints only through its own **same-origin server
proxy** — the token stays server-side (Secret Manager) and never reaches the client bundle.

## Safety boundaries

- No `EvidencePack v1` schema changes, tool renames, or new API routes without approval.
- Agents and tools are **read-only**; no credentials in the frontend.
- Mutation is **backend-only**, after a matching hash-bound human approval.
- The frontend never marks a run `VERIFIED`.

See [`docs/safety-boundary-decisions.md`](docs/safety-boundary-decisions.md) for deferred
governance decisions, and [`PROJECT_PROMPT.md`](PROJECT_PROMPT.md) for the durable brief.

## Tech stack

Next.js · FastAPI · Vertex AI Agent Engine (Gemini) · MongoDB Atlas · Google Cloud Run ·
Secret Manager · `uv` + pytest · vitest.

## Status

- **Layers 1–4** — multipage operator console, intake, control-plane + oversight map, and hash-bound approval UI (shipped, PR #99).
- **Layers 5–8** — three-check verification rail + tests, live-run navigation + labeled simulation fallback, gate-sourced audit trail, governance record (shipped, PR #100).
- Deployed on Cloud Run (dashboard + read API). The dashboard runs under a dedicated,
  least-privilege service account with a Secret-Manager-sourced token.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
