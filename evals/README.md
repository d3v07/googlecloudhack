# Agent eval harness (#38)

Grades the DBRE agent's diagnosis quality on the #9 ESR fixture and emits a
scorecard. Proves the agent actually works — not just "it ran once" — and gives
the demo/Devpost a concrete quality scorecard.

## What it grades

| Check | Layer | Asserts |
|-------|-------|---------|
| `esr_correct` | all | recommends ESR index **C** `{storeLocation:1, saleDate:-1, customer.age:1}`, **not** the obvious-but-wrong **B** |
| `phase_gate` | deterministic | a write tool (`create-index`/`drop-index`) is blocked in diagnose/approve, allowed only in verify |
| `narrative_grounded` | demo-pack | the **real Gemini narrative** cites the blocking sort and invents **no** numbers (catches hallucination) |
| `live_run` + `latency_recorded` | live | the deployed agent answers `POST /run` and the round-trip is timed |
| `agent_engine_path` | diagram-live | `/run` records Agent Engine participation in the DIAGNOSE phase log |
| `no_mutation_before_approval` | diagram-live | target indexes are unchanged immediately after `/run` |
| `ledger_records_exist` | diagram-live | all diagram ledger collections have a deterministic record for the run |
| `approval_verifies_esr_fix` | diagram-live | approval preserves the hash and verifies the ESR key reduction |
| `no_extra_indexes` | diagram-live | no scratch or generated indexes are left behind |

## Run

```bash
# deterministic only — no creds, CI-safe
uv run python -m evals.run_eval

# + grade the pre-seeded demo-001 pack's real Gemini narrative (read-only)
uv run python -m evals.run_eval --demo-pack

# + trigger and grade a live agent run (needs RUN_API_TOKEN + API_URL)
set -a && source dashboard/.env.local && set +a
uv run python -m evals.run_eval --demo-pack --live

# + run the full diagram-conformance gate (also needs Mongo connection string)
uv run --with python-dotenv python -m dotenv run -- \
  uv run python -m evals.run_eval --demo-pack --diagram-live
```

Outputs `evals/scorecard.json` + `evals/scorecard.md` (latest committed run:
**PASS** across deterministic, demo-pack, live, and diagram-live gates).

## Layers, and why

- **Deterministic** (always, CI-safe): the ESR logic and the phase gate are pure
  Python — no model, no network. These can't flake.
- **demo-pack** (read-only HTTP): grades the pre-seeded `demo-001` pack, the one
  pack that carries a real Gemini narrative — this is where anti-hallucination
  meets actual model output.
- **live** (needs the write token): triggers the Agent Engine-backed `/run` path
  and grades the returned pack. `/run` packs are deterministic-only (no narrative),
  so `narrative_grounded` is correctly skipped there — the demo-pack layer covers
  narrative grounding instead.
- **diagram-live** (needs the write token + Mongo connection): exercises the
  shipped architecture end to end: Agent Engine participation, no mutation before
  approval, event ledger persistence, hash-bound approval, verified ESR fix, and
  clean target indexes.

CI runs only the deterministic unit tests (`tests/unit/test_evals.py`); the live
test is `skipif`-gated on `RUN_API_TOKEN` + `API_URL`.
