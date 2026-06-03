# googlecloudhack — Evidence-Driven DBRE Agent

A Gemini-powered MongoDB performance engineer: detects slow queries, proposes ESR-correct
indexes from real `explain` evidence, gates `apply` behind human approval, verifies the
result, and ships a hashed evidence pack plus an internal event ledger for every fix.

> **Status:** Day-5 — live Cloud Run demo with Agent Engine native diagnosis tools,
> deterministic validation, human-gated apply/verify, and Evidence Ledger collections.

## Architecture

Five demo stages (Detect → Diagnose → Test → Approve → Verify) over a deterministic
three-phase safety engine (DIAGNOSE → APPROVE → VERIFY).

Current production path:

```text
Dashboard -> FastAPI Cloud Run (opens approval gate) -> Agent Engine native tools
          -> deterministic controller validates + emits DIAGNOSED EvidencePack
          -> /packs/{id}/decision hash-bound approval ticket
          -> apply + verify
```

Agent Engine performs read-only Mongo diagnosis/rationale with Python-native tools.
Deterministic Python remains the safety authority: it recomputes the ESR winner, evidence
hash, phase transitions, index apply, and verification. `/run` opens the approval gate
before diagnosis and remains read-only; `/packs/{run_id}/decision` is the only path that
can issue the one-time approval ticket required for mutation.

The dashboard reads only `EvidencePack` JSON, including `approval_gate` state and
`agent_trace` proof that the gate opened before Agent Engine participation. Internally,
MongoDB persists ledger collections for `slow_queries`, `candidates`, `experiments`,
`decisions`, `evidence_packs`, `approvals`, `applications`, and `verifications`.

## Quickstart

```bash
uv sync --dev
cp .env.example .env   # fill GCP + MongoDB values
uv run pytest -q
```

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
