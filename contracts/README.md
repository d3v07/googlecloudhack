# Contracts — the dashboard boundary

`evidence_pack.schema.json` is the **only** interface the dashboard (#10) depends on.

## Rule

The dashboard consumes `EvidencePack` JSON — via this schema and the read endpoint (#18) — and **nothing else**. It must not import `controller/`, `agents/`, or any backend module. The backend can change freely as long as the `v1` schema holds (additive-only after freeze).

## Files

- `evidence_pack.schema.json` — JSON Schema (draft 2020-12), generated from the `EvidencePack` pydantic model.
- `examples/evidence_pack.example.json` — a representative `DIAGNOSED` pack (the ESR B→C scenario) to build against before live data exists.

## EvidencePack shape (v1)

`version`, `run_id`, `namespace`, `status` (`diagnosed` / `approved` / `verified` / `rejected`), `before` (Evidence), `after` (Evidence | null), `finding`, `recommendation` (ordered `[field, direction]` index keys), `decision` (null until approved), `phase_log`, `agent_trace`, `approval_gate`, `evidence_hash`, `created_at`.

`evidence_hash` binds `before` + `recommendation` together — it pins *what gets applied given what evidence*, which is what a human approval signs off on. When `decision` is present its `evidence_hash` must equal the pack's.

`approval_gate` is the dashboard-visible control plane: `/run` opens it before
diagnosis, moves it to `pending_approval` with the required hash, and the decision
route closes it as rejected or verified. `agent_trace` must start with the
`approval_gate/gate` event, then record split Agent Engine role events
(`component`: `diagnose_agent`, `candidate_agent`, `rationale_agent`) plus the
actual Agent Engine `resource`,
deterministic validation, human approval, apply, and verify.

## Regenerate

After changing the `EvidencePack` model:

```bash
uv run python contracts/_generate.py
```

The contract test fails if the committed schema drifts from the model.
