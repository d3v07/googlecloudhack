# googlecloudhack — Evidence-Driven DBRE Agent

A Gemini-powered MongoDB performance engineer: detects slow queries, proposes ESR-correct
indexes from real `explain` evidence, gates `apply` behind human approval, verifies the
result, and ships a hashed evidence pack plus an internal event ledger for every fix.

> **Status:** Day-5 — live Cloud Run demo with split Agent Engine diagnosis roles,
> deterministic validation, human-gated apply/verify, and Evidence Ledger collections.

## Architecture

Five demo stages (Detect → Diagnose → Test → Approve → Verify) over a deterministic
three-phase safety engine (DIAGNOSE → APPROVE → VERIFY).

Current production path:

```text
Dashboard -> FastAPI Cloud Run (creates gated read-only run)
          -> Diagnose Agent Engine -> Candidate Agent Engine -> Rationale Agent Engine
          -> deterministic controller validates + emits DIAGNOSED EvidencePack
          -> /packs/{id}/decision hash-bound approval ticket
          -> apply + verify
```

The three Agent Engine resources perform read-only Mongo diagnosis, candidate testing,
and rationale generation with Python-native tools.
Deterministic Python remains the safety authority: it recomputes the ESR winner, evidence
hash, phase transitions, index apply, and verification. `/run` creates a gated read-only
run. Mutation remains impossible until the operator approves a matching EvidencePack hash;
`/packs/{run_id}/decision` is the only path that can issue the one-time internal apply
action required for mutation.

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
