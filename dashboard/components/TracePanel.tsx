import {
  Brain,
  CheckCircle,
  Database,
  Fingerprint,
  Warning,
  XCircle,
} from "@phosphor-icons/react/dist/ssr";
import type { AgentTraceEvent } from "@/lib/evidence";
import styles from "./TracePanel.module.css";

const LEGEND = "Production model: 3 read-only agent roles / 4 read-only diagnosis tools.";

// The 4 read-only diagnosis tools, in diagnosis-flow order (matches the trace
// event order: explain → compare → diagnose → rationalize). Do NOT rename.
const DIAGNOSIS_TOOLS = [
  "explain_slow_query",
  "compare_candidate_indexes",
  "diagnose_candidate",
  "rationalize_recommendation",
] as const;

// The 3 read-only agent roles, keyed by the stage that names them. The Diagnose
// Agent owns two stages (detect + diagnose) — that is why there are 3 roles but
// 4 tools.
const ROLE_BY_STAGE: Partial<Record<AgentTraceEvent["stage"], string>> = {
  detect: "Diagnose Agent",
  diagnose: "Diagnose Agent",
  candidate: "Candidate Agent",
  rationale: "Rationale Agent",
};

const ROLE_ORDER = ["Diagnose Agent", "Candidate Agent", "Rationale Agent"] as const;

function actorLabel(actor: AgentTraceEvent["actor"]): string {
  switch (actor) {
    case "approval_gate":
      return "Approval Gate";
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

function StatusIcon({ status }: { status: AgentTraceEvent["status"] }) {
  if (status === "ok") return <CheckCircle weight="fill" size={16} />;
  if (status === "failed") return <XCircle weight="fill" size={16} />;
  return <Warning size={16} />;
}

/**
 * One trace row. The meta column is rendered per the lens it appears under:
 *   - "tool": lead with the tool name (the Tool Calls lens).
 *   - "plain": stage + actor + any chips (Controller / Human lenses).
 * The Roles lens renders its own role-grouped rows and never uses this.
 */
function TraceRow({ event, variant }: { event: AgentTraceEvent; variant: "tool" | "plain" }) {
  return (
    <li className={styles.traceItem} data-failed={event.status === "failed" ? "" : undefined}>
      <span className={styles.traceState} data-status={event.status}>
        <StatusIcon status={event.status} />
      </span>
      <span className={styles.traceMeta}>
        {variant === "tool" ? (
          <>
            {event.tool && <code className={styles.tool}>{event.tool}</code>}
            <span className={styles.stage}>{stageLabel(event.stage)}</span>
          </>
        ) : (
          <>
            <span className={styles.stage}>{stageLabel(event.stage)}</span>
            <span className={styles.actor}>{actorLabel(event.actor)}</span>
            {event.tool && <code className={styles.tool}>{event.tool}</code>}
          </>
        )}
      </span>
      <span className={styles.traceSummary}>{event.summary}</span>
      {event.ledger_ref && <code className={styles.ledgerRef}>{event.ledger_ref}</code>}
    </li>
  );
}

function TraceSection({
  title,
  caption,
  children,
}: {
  title: string;
  caption: string;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionHead}>
        <span className={styles.sectionTitle}>{title}</span>
        <span className={styles.sectionCaption}>{caption}</span>
      </div>
      {children}
    </div>
  );
}

function rowKey(event: AgentTraceEvent, index: number): string {
  return `${index}-${event.stage}-${event.actor}-${event.tool ?? "event"}`;
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
  // Drift banner is for overridden drift only. A failed verify surfaces as its
  // own red row, not as a "drift was overridden" success message.
  const hasDrift = trace.some((event) => event.status === "drift");

  // §1 Roles — group the agent_engine events under the 3 named roles, so the
  // section visibly reads as 3 roles (the Diagnose Agent's two events nest).
  const roleGroups = ROLE_ORDER.map((role) => ({
    role,
    events: agentEvents.filter((event) => ROLE_BY_STAGE[event.stage] === role),
  })).filter((group) => group.events.length > 0);

  // §2 Tool Calls — only events whose tool is one of the exact 4 diagnosis tools.
  const toolEvents = DIAGNOSIS_TOOLS.flatMap((tool) =>
    trace.filter((event) => event.tool === tool),
  );

  // §3 Deterministic Safety / Controller.
  const controllerEvents = trace.filter((event) => event.actor === "deterministic_controller");

  // §4 Human / Approval Gate.
  const gateEvents = trace.filter(
    (event) => event.actor === "human" || event.actor === "approval_gate",
  );

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

      <p className={styles.legend}>{LEGEND}</p>

      {trace.length === 0 ? (
        <div className={styles.emptyTrace}>
          <Warning size={16} /> No trace events recorded in this pack.
        </div>
      ) : (
        <div className={styles.sections}>
          {roleGroups.length > 0 && (
            <TraceSection title="Roles" caption="3 read-only agent roles">
              <div className={styles.roleGroups}>
                {roleGroups.map((group) => (
                  <div className={styles.roleGroup} key={group.role}>
                    <span className={styles.roleName}>{group.role}</span>
                    <ol className={styles.traceList} aria-label={`${group.role} trace`}>
                      {group.events.map((event, index) => (
                        <TraceRow key={rowKey(event, index)} event={event} variant="plain" />
                      ))}
                    </ol>
                  </div>
                ))}
              </div>
            </TraceSection>
          )}

          {toolEvents.length > 0 && (
            <TraceSection title="Tool Calls" caption="4 read-only diagnosis tools">
              <ol className={styles.traceList} aria-label="Tool calls">
                {toolEvents.map((event, index) => (
                  <TraceRow key={rowKey(event, index)} event={event} variant="tool" />
                ))}
              </ol>
            </TraceSection>
          )}

          {controllerEvents.length > 0 && (
            <TraceSection
              title="Deterministic Safety / Controller"
              caption="validation, apply, verify"
            >
              <ol className={styles.traceList} aria-label="Deterministic safety and controller trace">
                {controllerEvents.map((event, index) => (
                  <TraceRow key={rowKey(event, index)} event={event} variant="plain" />
                ))}
              </ol>
            </TraceSection>
          )}

          {gateEvents.length > 0 && (
            <TraceSection title="Human / Approval Gate" caption="gate and approval decisions">
              <ol className={styles.traceList} aria-label="Human and approval gate trace">
                {gateEvents.map((event, index) => (
                  <TraceRow key={rowKey(event, index)} event={event} variant="plain" />
                ))}
              </ol>
            </TraceSection>
          )}
        </div>
      )}

      {hasDrift && <div className={styles.drift}>Deterministic validation overrode drift.</div>}
    </section>
  );
}
