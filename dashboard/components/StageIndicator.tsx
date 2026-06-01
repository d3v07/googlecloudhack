import { CheckCircle, CircleNotch, Circle, XCircle } from "@phosphor-icons/react/dist/ssr";
import { STAGES, type PackStatus, activeStageIndex } from "@/lib/evidence";
import styles from "./StageIndicator.module.css";

/**
 * The five operator-facing stages: Detect -> Diagnose -> Test -> Approve -> Verify.
 * Completed stages show a check; the active stage pulses; a rejected pack marks
 * the Approve stage with an X.
 */
export function StageIndicator({ status }: { status: PackStatus }) {
  const active = activeStageIndex(status);

  return (
    <ol className={styles.track} aria-label="Pipeline stages">
      {STAGES.map((stage, i) => {
        const done = i < active;
        const isActive = i === active;
        const rejectedHere = status === "rejected" && stage === "Approve";

        let state: "done" | "active" | "pending" | "rejected" = "pending";
        if (rejectedHere) state = "rejected";
        else if (done) state = "done";
        else if (isActive) state = "active";

        return (
          <li key={stage} className={styles.step} data-state={state}>
            <span className={styles.icon}>
              {state === "done" && <CheckCircle weight="fill" size={20} />}
              {state === "active" && <CircleNotch weight="bold" size={20} className={styles.spin} />}
              {state === "pending" && <Circle size={20} />}
              {state === "rejected" && <XCircle weight="fill" size={20} />}
            </span>
            <span className={styles.label}>{stage}</span>
            {i < STAGES.length - 1 && <span className={styles.connector} aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}
