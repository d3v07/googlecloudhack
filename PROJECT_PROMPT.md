# PROJECT_PROMPT.md

Durable project brief. Read this first before any new work. It describes what the
product is, what has shipped, and the safety boundaries that must never be crossed.

## 1. Product Summary

**Evidence-Driven DBRE Agent** — a safe MongoDB index-remediation control plane. It
turns a slow query into a measured, human-approved index fix, and never lets
automation mutate the database on its own.

Path:

```
operator dashboard -> FastAPI API -> deterministic controller
  -> read-only reasoning agent roles + read-only diagnosis tools
  -> MongoDB target + evidence ledger
```

Every fix is gated behind a hash-bound human approval; mutation happens backend-only,
after approval, and is then proven by re-measurement.

## 2. Core Rule

```
Agents recommend.
Deterministic code decides.
Humans approve.
Verification proves.
```

This separation of authority **is** the product. It must hold end to end.

## 3. Current Shipped Architecture

- Multipage **Next.js** operator dashboard (server-rendered; reads EvidencePack JSON only).
- **FastAPI** API on **Cloud Run** — reads are public; write/mutation endpoints are token-gated.
- **EvidencePack v1** is the single contract between backend and frontend; the dashboard depends on nothing else.
- **3 read-only reasoning agent roles** (Diagnose, Candidate, Rationale) — they inspect and recommend; they never select the winner, apply an index, or mark a run verified.
- **4 read-only diagnosis tools** — they capture evidence only; none mutates the database or sees raw credentials.
- **Deterministic Python** owns winner selection (ESR), evidence-hash binding, approval enforcement, index apply, and verification.
- **Secret Manager** holds the write token (no plaintext in service config); the database connection string is also Secret-Manager-sourced.
- The dashboard runs under a **dedicated service account** with least-privilege access to only the run-token secret.

## 4. Dashboard Routes

- `/` — overview: fleet status + run list
- `/runs/[run_id]` — canonical single-run review (approval gate, before/after explain diff, trace)
- `/run-review?run_id=...` — legacy alias for the run view
- `/system-map` — architecture + control-plane + oversight map
- `/history` — run history & compare
- `/audit` — approval / verification / policy audit trail
- `/intake` — intake + API gateway (static, informational)

## 5. API Contract (existing routes only)

- `GET /packs` — list EvidencePacks
- `GET /packs/{run_id}` — fetch one EvidencePack
- `POST /run` — create a gated, read-only DIAGNOSED run (token-gated)
- `POST /packs/{run_id}/decision` — submit a hash-bound approve/reject decision (token-gated)

No other routes. The dashboard reaches the write endpoints only through its own
same-origin server proxy (`/api/run`, `/api/decision`), which holds the token
server-side and never exposes it to the client.

## 6. Safety Boundaries (do not cross without explicit approval)

- No EvidencePack v1 schema changes without approval.
- No tool renames without approval.
- No new API routes without approval.
- No credentials in the frontend / client bundle.
- Agents and tools are read-only.
- The frontend never marks a run VERIFIED.
- Mutation is backend-only, and only after a matching, hash-bound human approval.

## 7. Golden Path

```
slow query
  -> explain
  -> diagnose (extract the blocking-sort root cause)
  -> compare candidate indexes
  -> deterministic ESR winner
  -> EvidencePack with bound evidence hash
  -> human approval of that exact hash
  -> backend applies the index
  -> re-explain verification
  -> ledger trace recorded
```

## 8. Verification Criteria

A run is **VERIFIED** only when ALL hold (deterministic, backend-side):

- the blocking SORT is gone in the after-plan,
- the selected/recommended index is evidenced in the winning or hinted plan,
- at least one cost metric improves (docs examined, keys examined, or millis),
- the verification result is written to the trace / ledger.

If any check fails, the run stays **APPROVED** (applied-but-not-verified), the VERIFY
trace event is marked failed, and the ledger records the failure. VERIFIED is never
inferred by the client.

## 9. Local Run / Demo

**Dashboard (local):**

```
cd dashboard
npm install
npm run dev          # or: npm run build && npm start   (listens on $PORT, e.g. 7777)
```

**API env (server-side only — values intentionally omitted):**

- `API_URL` — base URL of the read API; drives server-side data loading + the proxy
- `NEXT_PUBLIC_API_URL` — build-time fallback base URL
- `RUN_API_TOKEN` — write-endpoint token; **server-only**, sourced from Secret Manager in production, never in the client bundle

**Simulation fallback:** when no API/token is configured, "Ask the agent" returns a
clearly-labeled local **SIMULATION** run (a read-only DIAGNOSED pack) and navigates to
its run page. It is never shown as live and never mutates anything.

**Live smoke checklist (deployed):**

- `/`, `/system-map`, `/runs/<id>` load
- "Ask the agent" triggers a real run, then navigates to `/runs/{new_run_id}`
- `GET /packs` includes the new run
- the approval gate shows pending and hash-bound (`required_hash == evidence_hash`)
- no token in the client bundle / page source

**Deploy & rollback (concept, no secrets):** the dashboard is a Cloud Run service
built from `dashboard/Dockerfile` via a source build. Each deploy creates a new
immutable revision; the previously-serving revision is retained and is the one-step
rollback target (re-route 100% of traffic back to it). The token and connection
string live in Secret Manager and are referenced by the service, never inlined.

## 10. Current Status

- **Layers 1–4** shipped via **PR #99** — multipage operator console, intake, control-plane + oversight map, hash-bound approval UI.
- **Layers 5–8** shipped via **PR #100** — three-check verification rail + lock-in tests, live-run navigation + labeled simulation fallback, gate-sourced audit approver, and a deferred-governance record.
- **PR #101** — documentation wording aligned with the shipped console (open at time of writing).
- Production was deployed once from combined `main` after #99 + #100 (dashboard revision `gcrah-dashboard-00007-ncf`; prior revision `gcrah-dashboard-00006-8fz` retained as the rollback target).
- The post-deploy smoke test created a single **read-only DIAGNOSED** run (`run-94dd1850`) at pending-approval — **no mutation occurred**.
- Deferred and recorded in `docs/safety-boundary-decisions.md`: policy-check records and `Decision.approved_by/at` (both EvidencePack v1 changes), plus optional read-only inspection tools.
