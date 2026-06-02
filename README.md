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
Dashboard -> FastAPI Cloud Run -> Agent Engine native tools -> deterministic controller
          -> DIAGNOSED EvidencePack -> human approval -> apply + verify
```

Agent Engine performs read-only Mongo diagnosis/rationale with Python-native tools.
Deterministic Python remains the safety authority: it recomputes the ESR winner, evidence
hash, phase transitions, index apply, and verification. `/run` is read-only;
`/packs/{run_id}/decision` is the only mutation path.

The dashboard reads only `EvidencePack` JSON, including `agent_trace` proof of Agent Engine
tool participation. Internally, MongoDB persists ledger collections for `slow_queries`,
`candidates`, `experiments`, `decisions`, `evidence_packs`, `approvals`, `applications`, and
`verifications`.

## Quickstart

```bash
uv sync --dev
cp .env.example .env   # fill GCP + MongoDB values
uv run pytest -q
```

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
