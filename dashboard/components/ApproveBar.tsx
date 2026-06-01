"use client";

import { useState } from "react";
import { ShieldCheck, Fingerprint } from "@phosphor-icons/react/dist/ssr";
import type { PackStatus } from "@/lib/evidence";
import styles from "./ApproveBar.module.css";

/**
 * Approve action. In this scaffold the button is intentionally inert (Day 3+
 * wires it to POST an approval keyed to evidence_hash). The hash is shown
 * because it is exactly what a human approval signs off on.
 */
export function ApproveBar({
  evidenceHash,
  status,
}: {
  evidenceHash: string;
  status: PackStatus;
}) {
  const [clicked, setClicked] = useState(false);
  const pending = status === "diagnosed";

  return (
    <section className={styles.bar}>
      <div className={styles.hashWrap}>
        <Fingerprint size={16} className={styles.hashIcon} />
        <span className={styles.hashLabel}>evidence hash</span>
        <code className={styles.hash}>{evidenceHash}</code>
      </div>

      <button
        className={styles.approve}
        disabled={!pending || clicked}
        onClick={() => setClicked(true)}
        title={pending ? "Approve the recommended index" : "Nothing pending approval"}
      >
        <ShieldCheck weight="fill" size={18} />
        {clicked ? "Approval recorded (scaffold)" : pending ? "Approve fix" : "No action pending"}
      </button>
    </section>
  );
}
