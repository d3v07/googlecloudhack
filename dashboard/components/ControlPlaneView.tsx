import {
  Gear,
  ShieldCheckered,
  UserCheck,
  Lock,
  MagnifyingGlassPlus,
  Heartbeat,
  ArrowRight,
} from "@phosphor-icons/react/dist/ssr";
import type { EvidencePack } from "@/lib/evidence";
import { currentStateIndex, displayStatus } from "@/lib/evidence";
import styles from "./ControlPlaneView.module.css";

// Layer 3: deterministic Control Plane. Six service cards + the run state machine
// + failure handling. Built from existing EvidencePack v1 fields only — no
// backend contract changes. Current state is highlighted when derivable.

const SERVICES = [
  {
    icon: Gear,
    name: "Run Orchestrator",
    desc: "orchestrates phases and state, tracks run lifecycle",
    responsibilities: [
      "orchestrates phase flow and tasks",
      "maintains run state and transitions",
      "tracks lifecycle and metadata",
    ],
  },
  {
    icon: ShieldCheckered,
    name: "Policy / Phase Gates",
    desc: "enforce policy and phase transitions",
    responsibilities: [
      "evaluates policies and rules",
      "enforces phase entry/exit conditions",
      "blocks or routes based on policy",
    ],
  },
  {
    icon: UserCheck,
    name: "Approval Service",
    desc: "human approvals and delegation",
    responsibilities: [
      "manages human approvals",
      "records approver decisions and time",
      "validates matching evidence hash",
    ],
  },
  {
    icon: Lock,
    name: "Execution Guard",
    desc: "backend-only safety guardrails",
    responsibilities: [
      "enforces backend-only execution",
      "validates safety rules and scopes",
      "blocks unsafe or out-of-policy requests",
    ],
  },
  {
    icon: MagnifyingGlassPlus,
    name: "Verification Engine",
    desc: "re-explain and verify results",
    responsibilities: [
      "re-explains results independently",
      "verifies outcomes and assertions",
      "produces verification status and proof",
    ],
  },
  {
    icon: Heartbeat,
    name: "Health Monitor",
    desc: "watches run status, agent completion, and failures",
    responsibilities: [
      "monitors run progress and health",
      "detects failures and anomalies",
      "surfaces alerts and escalations",
    ],
  },
];

const STATE_MACHINE = [
  "Intake",
  "Diagnose",
  "Candidate Review",
  "Approval Pending",
  "Apply",
  "Verify",
  "Closed",
] as const;

const FAILURES = [
  "Invalid proposal",
  "Approval mismatch",
  "Verification failure",
  "Agent timeout",
] as const;

export function ControlPlaneView({ pack }: { pack: EvidencePack | null }) {
  const current = currentStateIndex(pack);
  const failedVerify = pack ? displayStatus(pack).key === "verification-failed" : false;

  return (
    <section className={styles.wrap} id="control-plane">
      <header className={styles.head}>
        <h2 className={styles.heading}>Control Plane</h2>
        <span className={styles.det}>deterministic orchestration &amp; state</span>
      </header>
      <p className={styles.note}>
        This layer is deterministic. It coordinates policy, timing, approvals, and state for every
        run.
      </p>

      <div className={styles.cardGrid}>
        {SERVICES.map(({ icon: Icon, name, desc, responsibilities }) => (
          <div key={name} className={styles.card}>
            <div className={styles.cardTop}>
              <Icon size={18} className={styles.cardIcon} />
              <span className={styles.cardName}>{name}</span>
            </div>
            <p className={styles.cardDesc}>{desc}</p>
            <ul className={styles.respList}>
              {responsibilities.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <h3 className={styles.subHeading}>Run state machine</h3>
      {current === null && (
        <p className={styles.honest}>
          Current run state not derivable — showing the product lifecycle. Actual run status is shown
          per run in Run Review.
        </p>
      )}
      <ol className={styles.states}>
        {STATE_MACHINE.map((s, i) => (
          <li
            key={s}
            className={styles.stateNode}
            data-current={i === current}
            data-done={current !== null && i < current}
          >
            <span className={styles.stateName}>{s}</span>
            {i < STATE_MACHINE.length - 1 && (
              <ArrowRight size={13} className={styles.stateArrow} />
            )}
          </li>
        ))}
      </ol>

      <h3 className={styles.subHeading}>Failure handling</h3>
      <div className={styles.failures}>
        {FAILURES.map((f) => {
          const active = failedVerify && f === "Verification failure";
          return (
            <span key={f} className={styles.failure} data-active={active}>
              {f}
              {active && <em className={styles.failTag}>seen in this run</em>}
            </span>
          );
        })}
      </div>
    </section>
  );
}
