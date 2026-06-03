"use client";

import { useEffect, useState } from "react";
import {
  ShieldCheck,
  XCircle,
  Fingerprint,
  CircleNotch,
  Warning,
} from "@phosphor-icons/react/dist/ssr";
import type { PackStatus } from "@/lib/evidence";
import { submitDecision, type DecisionKind } from "@/lib/approval";
import styles from "./ApproveBar.module.css";

/**
 * Approve / reject the recommended index, keyed to evidence_hash.
 *
 * The hash is what the operator signs off on (it binds before + recommendation),
 * so it is sent with the decision. The actual request shape lives in
 * lib/approval.ts (see APPROVAL_CONTRACT.md). If the approval API is missing,
 * the UI shows an error and does not fake a persisted decision.
 */
export function ApproveBar({
  runId,
  evidenceHash,
  status,
}: {
  runId: string;
  evidenceHash: string;
  status: PackStatus;
}) {
  // Local status lets the bar reflect the outcome without a full reload.
  const [localStatus, setLocalStatus] = useState<PackStatus>(status);
  const [busy, setBusy] = useState<DecisionKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLocalStatus(status);
    setBusy(null);
    setError(null);
  }, [runId, evidenceHash, status]);

  const pending = localStatus === "diagnosed";
  const settled =
    localStatus === "approved" || localStatus === "verified" || localStatus === "rejected";
  const success = localStatus === "approved" || localStatus === "verified";

  async function decide(decision: DecisionKind) {
    setBusy(decision);
    setError(null);
    const res = await submitDecision({ runId, decision, evidenceHash });
    setBusy(null);

    if (res.ok) {
      setLocalStatus(res.status ?? (decision === "approve" ? "approved" : "rejected"));
      return;
    }
    setError(res.message ?? "Could not record the decision.");
  }

  return (
    <section className={styles.bar}>
      <div className={styles.hashWrap}>
        <Fingerprint size={16} className={styles.hashIcon} />
        <span className={styles.hashLabel}>evidence hash</span>
        <code className={styles.hash}>{evidenceHash}</code>
      </div>

      <div className={styles.actions}>
        {error && (
          <span className={styles.error}>
            <Warning weight="fill" size={14} /> {error}
          </span>
        )}

        {settled ? (
          <span className={styles.settled} data-decision={success ? "approved" : "rejected"}>
            {success ? (
              <ShieldCheck weight="fill" size={18} />
            ) : (
              <XCircle weight="fill" size={18} />
            )}
            {localStatus === "verified"
              ? "Fix verified"
              : localStatus === "approved"
                ? "Fix approved"
                : "Fix rejected"}
          </span>
        ) : (
          <>
            <button
              className={styles.reject}
              disabled={!pending || busy !== null}
              onClick={() => decide("reject")}
            >
              {busy === "reject" ? (
                <CircleNotch size={16} className={styles.spin} />
              ) : (
                <XCircle size={16} />
              )}
              Reject
            </button>
            <button
              className={styles.approve}
              disabled={!pending || busy !== null}
              onClick={() => decide("approve")}
              title={pending ? "Approve the recommended index" : "Nothing pending approval"}
            >
              {busy === "approve" ? (
                <CircleNotch size={18} className={styles.spin} />
              ) : (
                <ShieldCheck weight="fill" size={18} />
              )}
              {pending ? "Approve fix" : "No action pending"}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
