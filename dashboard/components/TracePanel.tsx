import { Brain, CheckCircle, Database, Fingerprint, Warning } from "@phosphor-icons/react/dist/ssr";
import type { AgentTraceEvent } from "@/lib/evidence";
import styles from "./TracePanel.module.css";

function actorLabel(actor: AgentTraceEvent["actor"]): string {
  switch (actor) {
    case "agent_engine":
      return "Agent Engine";
    case "deterministic_controller":
      return "Controller";
    case "human":
      return "Human";
  }
}

function stageLabel(stage: AgentTraceEvent["stage"]): string {
  return stage.charAt(0).toUpperCase() + stage.slice(1);
}

export function TracePanel({
  trace,
  evidenceHash,
  ledgerPersisted,
}: {
  trace: AgentTraceEvent[];
  evidenceHash: string;
  ledgerPersisted: boolean;
}) {
  const agentEvents = trace.filter((event) => event.actor === "agent_engine");
  const hasDrift = trace.some((event) => event.status === "drift" || event.status === "failed");

  return (
    <section className={styles.panel}>
      <div className={styles.summaryGrid}>
        <div className={styles.summaryItem}>
          <Fingerprint size={18} className={styles.hashIcon} />
          <span className={styles.summaryLabel}>Evidence hash</span>
          <code className={styles.hash}>{evidenceHash.slice(0, 16)}…</code>
        </div>
        <div className={styles.summaryItem}>
          <Brain size={18} className={styles.agentIcon} />
          <span className={styles.summaryLabel}>Agent Engine</span>
          <span className={styles.summaryValue}>
            {agentEvents.length > 0 ? `${agentEvents.length} tool events` : "not recorded"}
          </span>
        </div>
        <div className={styles.summaryItem}>
          <Database size={18} className={styles.ledgerIcon} />
          <span className={styles.summaryLabel}>Ledger</span>
          <span className={styles.summaryValue}>{ledgerPersisted ? "persisted" : "example"}</span>
        </div>
      </div>

      <ol className={styles.traceList} aria-label="Agent and controller trace">
        {trace.length === 0 ? (
          <li className={styles.emptyTrace}>
            <Warning size={16} /> No trace events recorded in this pack.
          </li>
        ) : (
          trace.map((event, index) => (
            <li key={`${event.stage}-${event.actor}-${event.tool ?? index}`} className={styles.traceItem}>
              <span className={styles.traceState} data-status={event.status}>
                {event.status === "ok" ? <CheckCircle weight="fill" size={16} /> : <Warning size={16} />}
              </span>
              <span className={styles.traceMeta}>
                <span className={styles.stage}>{stageLabel(event.stage)}</span>
                <span className={styles.actor}>{actorLabel(event.actor)}</span>
                {event.tool && <code className={styles.tool}>{event.tool}</code>}
              </span>
              <span className={styles.traceSummary}>{event.summary}</span>
            </li>
          ))
        )}
      </ol>

      {hasDrift && <div className={styles.drift}>Deterministic validation overrode drift.</div>}
    </section>
  );
}
