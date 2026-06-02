# Architecture — Evidence-Driven DBRE Agent

A Gemini-powered MongoDB performance engineer. It detects a slow query, diagnoses
the root cause from real `explain` evidence, proposes the correct ESR index,
gates the apply behind human approval, verifies the result, and ships a
**hashed evidence pack** plus an internal event ledger for every fix.

Five operator-facing **stages** sit over a three-phase safety **engine**
(Diagnose → Approve → Verify), itself the core of the original seven-phase
plan-and-execute design.

## System diagram

```mermaid
flowchart TB
    subgraph user["Operator"]
        DASH["Next.js Dashboard<br/>(Cloud Run)"]
    end

    subgraph gcp["Google Cloud"]
        API["Controller API<br/>FastAPI on Cloud Run"]
        AE["Agent Engine + ADK<br/>native diagnosis tools + rationale"]
        SM["Secret Manager"]
    end

    subgraph core["Deterministic controller"]
        EXPLAIN["explain.py<br/>stage + counter extraction"]
        DECIDE["diagnosis.py<br/>ESR winner selection"]
        PACK["pack.py<br/>EvidencePack + SHA-256 hash"]
        GATE["phases.py<br/>phase-gated transitions"]
        ORCH["orchestrator.py<br/>diagnose → approve → verify"]
    end

    subgraph data["MongoDB Atlas"]
        TARGET[("target cluster<br/>sales_agent_demo")]
        STATE[("agent-state cluster<br/>Evidence Ledger")]
        LEDGER["slow_queries<br/>candidates<br/>experiments<br/>decisions<br/>evidence_packs<br/>approvals<br/>applications<br/>verifications"]
    end

    DASH -- "GET /packs/:id" --> API
    DASH -- "POST /run" --> API
    DASH -- "POST /packs/:id/decision" --> API
    API -- "/run asks for native read-only diagnosis" --> AE
    AE -- "explain + candidate + rationale tool trace" --> API
    API --> ORCH
    AE --> EXPLAIN --> TARGET
    ORCH --> DECIDE --> PACK
    GATE -. enforces .-> ORCH
    ORCH -- "diagnosis/application/verification events" --> LEDGER --> STATE
    PACK -- "EvidencePack aggregate" --> STATE
    API -- "approved apply only" --> TARGET
    API -- reads creds --> SM

    PACK -- "EvidencePack JSON (contract)" --> API
```

## The five stages → three-phase engine

| Stage (UI) | Engine phase | What happens | Who does it |
|------------|-------------|--------------|-------------|
| **Detect** | (pre) | Slow query surfaced from the fixture / logs | Agent Engine native tool |
| **Diagnose** | `DIAGNOSE` | Read `explain`, extract stages + counters, identify the blocking-sort root cause | Agent Engine native tools, deterministic code validates |
| **Test** | `DIAGNOSE` | Compare B vs C and propose index **C** (correct ESR) from measured evidence | Agent Engine native tools, deterministic code recomputes |
| **Approve** | `APPROVE` | Human reviews the evidence pack and approves/rejects, keyed to `evidence_hash` | **human gate** |
| **Verify** | `VERIFY` | Apply the approved index, re-`explain`, confirm the sort is gone | deterministic |

## Why this is an agent, not a chat loop

Three things make it a real plan-and-execute system (and the reason we run on
**Agent Engine + ADK**, not the no-code console):

1. **Phase-gated tools** (`controller/phases.py`) — a write/apply tool cannot be
   called outside the `VERIFY` phase; transitions are asserted, illegal jumps
   raise.
2. **Human-in-loop pause** — the controller blocks at `APPROVE` until a decision
   arrives carrying the matching `evidence_hash`. The API returns `409` if the
   hash is stale (the evidence changed under the operator).
3. **Gemini never decides or applies** — Agent Engine can gather read-only evidence,
   propose, and explain, but the *winner selection*, the *hash*, the *apply*, and the
   *verification* are deterministic Python.

## The contract boundary

The dashboard depends on **one thing only**: `EvidencePack` JSON
(`contracts/evidence_pack.schema.json`). It never imports `controller/`,
`agents/`, or any backend module — it reads packs from the API and POSTs
decisions back. Backend internals can change freely behind the frozen `v1`
schema.

`EvidencePack.agent_trace` is the visible architecture proof: Agent Engine tool events,
deterministic validation, human approval, apply, and verify are recorded without exposing
raw ledger collections to the dashboard.

The internal Evidence Ledger is richer than the dashboard contract. MongoDB
stores event collections for `slow_queries`, `candidates`, `experiments`,
`decisions`, `approvals`, `applications`, and `verifications`, plus the
`evidence_packs` aggregate the dashboard reads.
