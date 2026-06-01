/**
 * Approval submission layer (#26).
 *
 * Isolates the approval API call so the exact endpoint + request shape live in
 * ONE place — see APPROVAL_CONTRACT.md, the proposal sent to #29 (@d3v07). When
 * that shape is finalized, only this file changes; the UI does not.
 *
 * Client-side (the ApproveBar is a client component), so it reads the public
 * NEXT_PUBLIC_API_URL — the same base used by lib/api.ts for reads.
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

function apiBase(): string | null {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

/**
 * Submit an approve/reject decision keyed to the evidence hash the operator saw.
 * Never throws — returns a DecisionResult the UI can render directly.
 */
export async function submitDecision(args: {
  runId: string;
  decision: DecisionKind;
  evidenceHash: string;
  approver?: string;
  note?: string;
}): Promise<DecisionResult> {
  const base = apiBase();
  if (!base) {
    // No API yet (fallback mode): report cleanly so the UI can show a
    // "demo only" state rather than pretend it persisted.
    return {
      ok: false,
      error: "no_api",
      message: "No approval API configured (NEXT_PUBLIC_API_URL unset).",
    };
  }

  const url = `${base}/packs/${encodeURIComponent(args.runId)}/decision`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({
        decision: args.decision,
        evidence_hash: args.evidenceHash,
        approver: args.approver ?? "dashboard-operator",
        ...(args.note ? { note: args.note } : {}),
      }),
    });

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
