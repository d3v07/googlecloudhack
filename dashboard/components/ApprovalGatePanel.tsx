"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CircleNotch,
  Fingerprint,
  LockKey,
  ShieldCheck,
  Warning,
  XCircle,
} from "@phosphor-icons/react/dist/ssr";
import type { ApprovalGateState, EvidencePack } from "@/lib/evidence";
import { isVerificationFailed, shortHash } from "@/lib/evidence";
import { submitDecision, type DecisionKind } from "@/lib/approval";
import styles from "./ApprovalGatePanel.module.css";

function fallbackGateState(pack: EvidencePack): ApprovalGateState {
  if (pack.status === "verified") return "verified";
  if (pack.status === "rejected") return "rejected";
  if (pack.status === "approved") return "approved";
  return "pending_approval";
}

function stateLabel(state: ApprovalGateState): string {
  switch (state) {
    case "collecting_evidence":
      return "Collecting evidence";
    case "pending_approval":
      return "Pending approval";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "verified":
      return "Verified";
  }
}

export function ApprovalGatePanel({
  pack,
  running,
  onPackUpdate,
}: {
  pack: EvidencePack;
  running: boolean;
  onPackUpdate: (pack: EvidencePack) => void;
}) {
  const [busy, setBusy] = useState<DecisionKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBusy(null);
    setError(null);
  }, [pack.run_id, pack.evidence_hash]);

  const gate = pack.approval_gate;
  const gateState = running ? "collecting_evidence" : gate?.state ?? fallbackGateState(pack);
  const pending = !running && gateState === "pending_approval" && pack.status === "diagnosed";
  const hash = gate?.required_hash ?? pack.evidence_hash;
  const approvedHash = gate?.approved_hash;
  const mutationBlocked = running || !gate?.mutation_allowed;
  const legacy = !gate;
  const verificationFailed = isVerificationFailed(pack);

  const statusText = useMemo(() => {
    if (legacy) return "Legacy pack: re-run to open a first-class approval gate.";
    if (running)
      return "/run creates a gated read-only run. Mutation remains impossible until the operator approves a matching EvidencePack hash.";
    if (pending) return "Human approval is required before the controller can apply an index.";
    if (verificationFailed)
      return "Index applied, but verification did not pass — the blocking sort remains. See the trace.";
    if (gateState === "verified") return "Approved mutation was applied and verified.";
    if (gateState === "rejected") return "The gate is closed without mutation.";
    return "The gate has closed for this evidence pack.";
  }, [gateState, legacy, pending, running, verificationFailed]);

  async function decide(decision: DecisionKind) {
    setBusy(decision);
    setError(null);
    const res = await submitDecision({ runId: pack.run_id, decision, evidenceHash: hash });
    setBusy(null);

    if (res.ok && res.pack) {
      onPackUpdate(res.pack);
      return;
    }
    if (res.ok) {
      setError("Decision API did not return the updated EvidencePack.");
      return;
    }
    setError(res.message ?? "Could not record the decision.");
  }

  return (
    <section className={styles.panel} aria-label="Human approval gate">
      <div className={styles.identity}>
        <div className={styles.iconWrap}>
          <ShieldCheck weight="fill" size={24} />
        </div>
        <div>
          <p className={styles.eyebrow}>Human Operator / Judge</p>
          <h2>Approval Gate</h2>
        </div>
      </div>

      <div className={styles.statusBlock}>
        <span className={styles.state} data-state={gateState}>
          {stateLabel(gateState)}
        </span>
        <span className={styles.lock} data-open={!mutationBlocked}>
          <LockKey size={15} weight="fill" />
          {mutationBlocked ? "mutation blocked" : "mutation unlocked"}
        </span>
        <p>{statusText}</p>
      </div>

      <div className={styles.hashBlock}>
        <Fingerprint size={16} />
        <span>full evidence hash</span>
        <code title={approvedHash ?? hash}>{approvedHash ?? hash}</code>
      </div>

      <div className={styles.actions}>
        {error && (
          <span className={styles.error}>
            <Warning weight="fill" size={14} /> {error}
          </span>
        )}
        {/* short hash preview sits next to the CTA so the operator sees exactly
            which hash they are signing */}
        <span className={styles.ctaHash}>
          <Fingerprint size={13} />
          {shortHash(hash)}
        </span>
        <button
          className={styles.reject}
          disabled={!pending || busy !== null}
          onClick={() => decide("reject")}
        >
          {busy === "reject" ? <CircleNotch size={16} className={styles.spin} /> : <XCircle size={16} />}
          Reject
        </button>
        <button
          className={styles.approve}
          disabled={!pending || busy !== null}
          onClick={() => decide("approve")}
        >
          {busy === "approve" ? (
            <CircleNotch size={18} className={styles.spin} />
          ) : (
            <ShieldCheck weight="fill" size={18} />
          )}
          Approve this evidence hash
        </button>
      </div>

      {/* Safety authority — who is allowed to do what (Layer 1 AC, exact lines). */}
      <div className={styles.safety}>
        <p className={styles.safetyTitle}>Safety authority</p>
        <ul className={styles.safetyList}>
          <li>
            <span>Agent recommendation</span> read-only
          </li>
          <li>
            <span>Winner selection</span> deterministic Python
          </li>
          <li>
            <span>Approval</span> hash-bound human decision
          </li>
          <li>
            <span>Mutation</span> backend-only after approval
          </li>
          <li>
            <span>Verification</span> re-explain after apply
          </li>
        </ul>
      </div>
    </section>
  );
}
