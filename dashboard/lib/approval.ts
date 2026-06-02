/**
 * Approval submission layer (#26, retrofitted in #37).
 *
 * The read API's /decision endpoint is token-gated (backend #58), and the token
 * must never reach the browser. So this client posts to the SAME-ORIGIN proxy
 * route (`/api/decision`, server-only) which holds RUN_API_TOKEN and forwards
 * upstream. The request/response shape the operator's browser sees is unchanged.
 */

import type { EvidencePack, PackStatus } from "./evidence";

export type DecisionKind = "approve" | "reject";

export interface DecisionResult {
  ok: boolean;
  /** Resulting status if the server reported one (approved / rejected). */
  status?: PackStatus;
  /** Full updated pack if the server returned it (preferred per the contract). */
  pack?: EvidencePack;
  /** Populated when ok === false. */
  error?: "no_api" | "stale_evidence_hash" | "not_found" | "network" | "server";
  message?: string;
}

/**
 * Submit an approve/reject decision keyed to the evidence hash the operator saw.
 * Posts to the same-origin /api/decision proxy. Never throws — returns a
 * DecisionResult the UI can render directly.
 */
export async function submitDecision(args: {
  runId: string;
  decision: DecisionKind;
  evidenceHash: string;
  approver?: string;
  note?: string;
}): Promise<DecisionResult> {
  try {
    const res = await fetch("/api/decision", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({
        runId: args.runId,
        payload: {
          decision: args.decision,
          evidence_hash: args.evidenceHash,
          approver: args.approver ?? "dashboard-operator",
          ...(args.note ? { note: args.note } : {}),
        },
      }),
    });

    if (res.status === 503) {
      // Proxy reports the write API isn't configured (e.g. local dev w/o token).
      return {
        ok: false,
        error: "no_api",
        message: "No approval API configured.",
      };
    }
    if (res.status === 409) {
      return {
        ok: false,
        error: "stale_evidence_hash",
        message: "The evidence changed since you reviewed it — please re-review.",
      };
    }
    if (res.status === 404) {
      return { ok: false, error: "not_found", message: "Run not found." };
    }
    if (!res.ok) {
      return { ok: false, error: "server", message: `Approval API returned ${res.status}.` };
    }

    // Preferred: server returns the updated pack. Fall back to a status field.
    const body = (await res.json().catch(() => ({}))) as Partial<EvidencePack> & {
      status?: PackStatus;
    };
    const status: PackStatus =
      body.status ?? (args.decision === "approve" ? "approved" : "rejected");
    return {
      ok: true,
      status,
      pack: body.version ? (body as EvidencePack) : undefined,
    };
  } catch {
    return { ok: false, error: "network", message: "Approval API unreachable." };
  }
}
