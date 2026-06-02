/**
 * EvidencePack v1 — the ONLY contract the dashboard depends on.
 *
 * Mirrors `contracts/evidence_pack.schema.json`. Per `contracts/README.md`, the
 * dashboard consumes EvidencePack JSON (this shape + the future #18 read
 * endpoint) and nothing else — it must not import controller/ or agents/.
 */

export type IndexKey = [field: string, direction: number];

export interface ExplainMetrics {
  docs_examined: number;
  docs_returned: number;
  has_blocking_sort?: boolean;
  millis: number;
  stages: string[];
  total_keys_examined: number;
}

export interface Query {
  filter: Record<string, unknown>;
  limit: number;
  sort: IndexKey[];
}

export interface Evidence {
  explain_plan: Record<string, unknown>;
  metrics: ExplainMetrics;
  query: Query;
}

export interface Finding {
  evidence_refs: string[];
  problem: string;
  severity: "low" | "medium" | "high" | "critical";
}

export interface Recommendation {
  index_spec: IndexKey[];
  rationale: string;
}

export interface Decision {
  evidence_hash: string;
  approved_by?: string;
  approved_at?: string;
  [k: string]: unknown;
}

export type PackStatus = "diagnosed" | "approved" | "verified" | "rejected";
export type AgentTraceStage =
  | "detect"
  | "diagnose"
  | "candidate"
  | "rationale"
  | "approve"
  | "apply"
  | "verify";
export type AgentTraceActor = "agent_engine" | "deterministic_controller" | "human";
export type AgentTraceStatus = "ok" | "drift" | "failed";

export interface AgentTraceEvent {
  stage: AgentTraceStage;
  actor: AgentTraceActor;
  status: AgentTraceStatus;
  summary: string;
  tool: string | null;
  ledger_ref: string | null;
}

export interface EvidencePack {
  version: string;
  run_id: string;
  namespace: string;
  status: PackStatus;
  before: Evidence;
  after: Evidence | null;
  finding: Finding;
  recommendation: Recommendation;
  decision: Decision | null;
  phase_log: unknown[];
  agent_trace: AgentTraceEvent[];
  evidence_hash: string;
  created_at: string;
}

/** The five operator-facing stages, in order. */
export const STAGES = ["Detect", "Diagnose", "Test", "Approve", "Verify"] as const;
export type Stage = (typeof STAGES)[number];

/**
 * Map a pack's backend status to how far the 5-stage pipeline has progressed.
 * `diagnosed` means Detect+Diagnose+Test are done and we're waiting at Approve.
 */
export function activeStageIndex(status: PackStatus): number {
  switch (status) {
    case "diagnosed":
      return 3; // waiting at Approve
    case "approved":
      return 4; // moving into Verify
    case "verified":
      return 5; // all done
    case "rejected":
      return 3; // stopped at Approve
  }
}

/** Render ordered index keys as `{ field: dir, ... }`. */
export function formatIndexSpec(spec: IndexKey[]): string {
  return "{ " + spec.map(([f, d]) => `${f}: ${d}`).join(", ") + " }";
}
