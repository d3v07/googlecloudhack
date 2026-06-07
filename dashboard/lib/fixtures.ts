/**
 * Visual-state fixtures for the dashboard's fallback path ONLY.
 *
 * Live data is happy-path, so the `verification-failed` and `rejected` states
 * never appear against the live read API. These fixtures let the no-API
 * fallback render every operator-facing state honestly. They are built by
 * spreading the bundled example pack (the real EvidencePack v1 shape, with a
 * valid evidence_hash and approval_gate) and overriding only the fields that
 * differ — so they inherit the exact contract and auto-pick-up copy fixes.
 *
 * NOT live data. `loadPacks`/`loadPack` tag these `source: "fallback"`.
 */

import type {
  AgentTraceEvent,
  ApprovalGate,
  Decision,
  Evidence,
  EvidencePack,
} from "./evidence";
import examplePack from "./example_pack.json";

const BASE = examplePack as unknown as EvidencePack;

const APPROVER = "dashboard-operator";
const APPROVED_AT = "2026-06-01T00:05:00Z";

/** A clean after-plan: blocking sort removed (verification passes). */
const CLEAN_AFTER: Evidence = {
  explain_plan: {
    inputStage: { indexName: "esr_right_C", stage: "IXSCAN" },
    stage: "FETCH",
  },
  metrics: {
    docs_examined: 20,
    docs_returned: 20,
    has_blocking_sort: false,
    millis: 2.0,
    stages: ["FETCH", "IXSCAN"],
    total_keys_examined: 20,
  },
  query: BASE.before.query,
};

/** A still-broken after-plan: blocking sort persists (verification fails). */
const FAILED_AFTER: Evidence = {
  explain_plan: BASE.before.explain_plan,
  metrics: { ...BASE.before.metrics, has_blocking_sort: true },
  query: BASE.before.query,
};

function gate(state: ApprovalGate["state"], overrides: Partial<ApprovalGate> = {}): ApprovalGate {
  return { ...BASE.approval_gate!, state, ...overrides };
}

function decision(): Decision {
  return {
    evidence_hash: BASE.evidence_hash,
    approved_by: APPROVER,
    approved_at: APPROVED_AT,
  };
}

const APPROVE_EVENT: AgentTraceEvent = {
  stage: "approve",
  actor: "human",
  status: "ok",
  summary: `Approved by ${APPROVER}.`,
  component: null,
  resource: null,
  tool: null,
  ledger_ref: "approvals/example-esr-001:approve:approval",
};

const APPLY_EVENT: AgentTraceEvent = {
  stage: "apply",
  actor: "deterministic_controller",
  status: "ok",
  summary: "Applied approved index esr_right_C.",
  component: null,
  resource: null,
  tool: "apply_index",
  ledger_ref: "applications/example-esr-001:approve:application",
};

const VERIFY_OK_EVENT: AgentTraceEvent = {
  stage: "verify",
  actor: "deterministic_controller",
  status: "ok",
  summary: "Verified ESR fix.",
  component: null,
  resource: null,
  tool: "explain",
  ledger_ref: "verifications/example-esr-001:verify:verification",
};

const VERIFY_FAILED_EVENT: AgentTraceEvent = {
  stage: "verify",
  actor: "deterministic_controller",
  status: "failed",
  summary: "Verification still has a blocking sort.",
  component: null,
  resource: null,
  tool: "explain",
  ledger_ref: "verifications/example-esr-001:verify:verification",
};

const REJECT_EVENT: AgentTraceEvent = {
  stage: "approve",
  actor: "human",
  status: "ok",
  summary: `Rejected by ${APPROVER}.`,
  component: null,
  resource: null,
  tool: null,
  ledger_ref: "approvals/example-esr-001:approve:rejection",
};

const GATE_REJECTED_EVENT: AgentTraceEvent = {
  stage: "gate",
  actor: "approval_gate",
  status: "ok",
  summary: "Approval gate closed as rejected.",
  component: null,
  resource: null,
  tool: "approval_gate",
  ledger_ref: "approvals/example-esr-001:approve:rejection",
};

/** status diagnosed, after null — pending approval. */
export const FIXTURE_PENDING: EvidencePack = {
  ...BASE,
  run_id: "fixture-pending",
};

/**
 * Local simulation pack (run_id prefix "sim-"). Served by /api/run and resolved
 * by loadPack ONLY when no backend is configured, so the demo still shows a
 * full DIAGNOSED evidence pack. Labeled "simulation" (never "live") everywhere
 * it surfaces; it is read-only and never applies anything.
 */
export const FIXTURE_SIMULATION: EvidencePack = {
  ...BASE,
  run_id: "sim-001",
};

/** status approved, after null — applied, verification pending (defensive). */
export const FIXTURE_APPLYING: EvidencePack = {
  ...BASE,
  run_id: "fixture-applying",
  status: "approved",
  after: null,
  decision: decision(),
  agent_trace: [...BASE.agent_trace, APPROVE_EVENT, APPLY_EVENT],
  approval_gate: gate("approved", {
    approved_hash: BASE.evidence_hash,
    approver: APPROVER,
  }),
};

/** status approved, after present with blocking sort + failed VERIFY event. */
export const FIXTURE_VERIFICATION_FAILED: EvidencePack = {
  ...BASE,
  run_id: "fixture-verification-failed",
  status: "approved",
  after: FAILED_AFTER,
  decision: decision(),
  agent_trace: [...BASE.agent_trace, APPROVE_EVENT, APPLY_EVENT, VERIFY_FAILED_EVENT],
  approval_gate: gate("approved", {
    approved_hash: BASE.evidence_hash,
    approver: APPROVER,
  }),
};

/**
 * status rejected — no mutation, no after-evidence. The decision records the
 * evidence hash + reject action (no approver): the backend `reject_pack` keeps
 * the approver on the gate/ledger, not the decision.
 */
export const FIXTURE_REJECTED: EvidencePack = {
  ...BASE,
  run_id: "fixture-rejected",
  status: "rejected",
  after: null,
  decision: { evidence_hash: BASE.evidence_hash, action: "reject" },
  agent_trace: [...BASE.agent_trace, REJECT_EVENT, GATE_REJECTED_EVENT],
  approval_gate: gate("rejected", {
    approver: APPROVER,
  }),
};

/** status verified, after present with the blocking sort removed. */
export const FIXTURE_VERIFIED: EvidencePack = {
  ...BASE,
  run_id: "fixture-verified",
  status: "verified",
  after: CLEAN_AFTER,
  decision: decision(),
  agent_trace: [...BASE.agent_trace, APPROVE_EVENT, APPLY_EVENT, VERIFY_OK_EVENT],
  approval_gate: gate("verified", {
    approved_hash: BASE.evidence_hash,
    approver: APPROVER,
  }),
};

/** All visual-state fixtures, in pipeline order (simulation pack last). */
export const FIXTURES: EvidencePack[] = [
  FIXTURE_PENDING,
  FIXTURE_APPLYING,
  FIXTURE_VERIFICATION_FAILED,
  FIXTURE_REJECTED,
  FIXTURE_VERIFIED,
  FIXTURE_SIMULATION,
];
