# Safety Boundary Decisions

This log records governance changes that were **deliberately deferred** because they
would alter a frozen contract or extend an agent's reach beyond its sanctioned
boundary. Each entry states what was proposed, why it was held back, the residual
risk of holding back, and the safe interim that shipped instead.

## The boundary rule

The system is built on a strict separation of authority:

- **Agents recommend.** Reasoning and oversight agents inspect, diagnose, and
  challenge. They are read-only and hold no mutation authority.
- **Deterministic code decides.** Validation and the controller make the
  accept/reject call from evidence, not from agent prose.
- **Humans approve.** No index is applied until a human approves the specific
  evidence hash.
- **Verification proves.** `VERIFIED` is established only by re-measuring after the
  change; it is never asserted by an agent and never derived in the client.

`EvidencePack v1` is the **frozen contract** that carries this guarantee end to end.
It is mirrored across the Python schema (`controller/schemas.py`), the published JSON
Schema (`contracts/`), and the dashboard's TypeScript types (`dashboard/lib/evidence.ts`).
Changing any field of the pack is a **hard-stop** that requires explicit approval —
it cannot be done as a side effect of a feature. The items below were each blocked on
that rule.

---

## 2026-06-07 — Deferred: policy-check records

**Context.** The Agent Oversight layer presents a Security Agent role that reviews
permissions, scope, policy fit, and index risk
(`dashboard/components/OversightView.tsx`). There is no schema for the outcome of such
a check: no `PolicyCheckEvent` structure exists, and no policy records are carried in
`EvidencePack` or written to the ledger. The role is therefore **presentational** —
it describes a capability the data model does not yet record.

**Proposed change.** Introduce a `PolicyCheckEvent` structure (policy id, decision,
rationale, evidence references), or add a policy annotation to the existing
`agent_trace` entries, so a policy review produces a durable, auditable record.

**Why deferred.** Both flavors modify `EvidencePack v1`. A new `PolicyCheckEvent`
would add a field to the pack, and an `agent_trace` annotation would change
`AgentTraceEvent` (`controller/schemas.py`), which is itself part of the frozen pack.
Either path is a frozen-contract change and thus a hard-stop without explicit
approval. Policy records also raise an upstream question — what produces the
decision — that must respect the boundary rule (deterministic code decides; an agent
may annotate but must not be the source of truth).

**Risk.** Until this lands, there is no machine-readable trail proving a policy review
occurred or what it concluded. Operators cannot audit policy outcomes per run, and the
Security Agent role's described checks have no recorded result. This is a transparency
gap, not a safety gap: no policy record means no policy enforcement is claimed, and
the deterministic gate and human approval still stand between a recommendation and any
mutation.

**Safe interim taken.** The oversight view shows an **honest empty state** rather than
fabricated policy outcomes. The component is explicitly documented as a system-map and
evidence-display representation with no backend agent execution, and it renders
"No oversight findings recorded for this run." when no findings are present
(`dashboard/components/OversightView.tsx`). The UI never implies a policy check ran
when no record exists.

---

## 2026-06-07 — Deferred: decision approver and timestamp on the Decision record

**Context.** The dashboard's TypeScript `Decision` type anticipates optional
`approved_by` and `approved_at` fields (`dashboard/lib/evidence.ts`). The Python
`Decision` model carries only `action`, `evidence_hash`, and `phase` — it has neither
`approved_by` nor `approved_at` (`controller/schemas.py`). The contract and the
producer are out of step on who approved a decision and when.

**Proposed change.** Add `approved_by` and `approved_at` to the Python `Decision`
model so the producer emits the approver identity and approval time that the consumer
already expects.

**Why deferred.** `Decision` is part of `EvidencePack v1`. Adding fields to it changes
the frozen contract and is a hard-stop without explicit approval, even though the
TypeScript side already tolerates the fields as optional.

**Risk.** The `Decision` record alone does not name the approver, so any consumer that
reads only the decision sees an unattributed approval. The audit trail must source
attribution elsewhere. Note also that the interim covers the approver **only**:
`ApprovalGate` has no timestamp field (`controller/schemas.py`), so the `approved_at`
half that the TypeScript contract anticipates has **no interim source** and currently
renders as unavailable.

**Safe interim taken.** The audit page derives the approver from the approval gate
rather than the decision, with no schema change: it reads
`gate?.approver ?? decision.approved_by ?? "—"`
(`dashboard/app/audit/page.tsx`). `ApprovalGate.approver` is already part of the
frozen pack and is required to be present on approved, verified, and rejected packs by
the pack validators, so attribution is sound for decided runs. Approval time is shown
as unavailable until the deferred change lands.

---

## 2026-06-07 — Deferred: optional read-only inspection tools (low priority)

**Context.** A set of optional read-only tools was scoped for the oversight/inspection
layer: `plan_diff_inspector`, `index_metadata_reader`, `history_lookup`, and
`policy_reader`. None are required for the current diagnose → approve → verify loop.

**Proposed change.** Add these read-only tools so agents can inspect plan diffs, index
metadata, prior runs, and policy data while staying within read-only bounds.

**Why deferred.** Held as **low priority** — the current loop is complete without them,
so they do not justify contract or surface-area changes now. One of them,
`history_lookup`, also crosses a boundary worth its own review: it would require giving
agents **read access to the ledger**, which is the system's audit record. Expanding what
agents can read is a boundary decision, not a convenience, and must be evaluated
separately rather than bundled in.

**Risk.** Deferring these costs nothing operationally — the loop functions without
them. The only standing item is `history_lookup`: granting agents ledger read access
widens their reach into the audit record, so it must be assessed on its own (least
privilege, what is exposed, and whether read access can leak into influence over a
decision) before it is considered.

**Safe interim taken.** None of the four tools are exposed. Agents remain read-only
within their existing inputs, and the ledger stays outside agent reach until the
`history_lookup` access question is evaluated on its own merits.
