import type { DisplayStatus } from "@/lib/evidence";
import styles from "./StatusPill.module.css";

/**
 * Consistent status pill across every page. The five states (pending-approval,
 * approved, verified, rejected, verification-failed) are visually distinct —
 * an acceptance criterion: they must not look identical.
 */
export function StatusPill({ status, label }: { status: DisplayStatus; label: string }) {
  return (
    <span className={styles.pill} data-status={status}>
      {label}
    </span>
  );
}
