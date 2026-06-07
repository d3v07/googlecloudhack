import { Eye, ClipboardText, ShieldWarning, Prohibit, Target } from "@phosphor-icons/react/dist/ssr";
import styles from "./OversightView.module.css";

// Layer 4: Agent Oversight. New read-only oversight roles — they inspect and
// challenge, they never execute. This is the dashboard/system-map representation
// + evidence display hooks only (no backend agent execution here). Real oversight
// outputs aren't present in EvidencePack v1 yet, so an honest empty state shows.

const AGENTS = [
  {
    icon: Eye,
    name: "Main Orchestrator Agent",
    purpose: "oversees agent workflow, completeness, and consistency; no mutation authority",
    inputs: ["run context", "plan", "tasks", "evidence", "agent outputs"],
    checks: ["workflow completeness", "agent sequencing", "consistency"],
    outputs: ["gaps identified", "routing recommendations", "clarifications"],
  },
  {
    icon: ClipboardText,
    name: "Reviewer Agent",
    purpose: "reviews evidence quality, missing fields, and reasoning consistency",
    inputs: ["evidence items", "rationale", "citations", "field requirements"],
    checks: ["field completeness", "data quality", "reasoning alignment"],
    outputs: ["missing fields", "quality findings", "improvement suggestions"],
  },
  {
    icon: ShieldWarning,
    name: "Security Agent",
    purpose: "reviews permissions, scope, policy fit, and index risk",
    inputs: ["requested actions", "roles", "scopes", "policies", "index selection"],
    checks: ["permissions", "policy alignment", "index risk and exposure"],
    outputs: ["risk flags", "policy deviations", "safer alternatives"],
  },
];

const CONSTRAINTS = [
  "read-only",
  "no credentials exposure",
  "no mutation authority",
  "suggestions must be validated downstream",
];

const CATCHES = [
  "incomplete evidence",
  "inconsistent reasoning",
  "risky index choice",
  "out-of-policy action",
];

export function OversightView({ hasFindings = false }: { hasFindings?: boolean }) {
  return (
    <section className={styles.wrap} id="oversight">
      <header className={styles.head}>
        <h2 className={styles.heading}>Agent Oversight Layer</h2>
        <span className={styles.ro}>read-only guardrails &amp; quality</span>
      </header>
      <p className={styles.note}>
        Oversight agents inspect and challenge the reasoning agents. They never execute and hold no
        mutation authority — every suggestion is validated downstream.
      </p>

      <div className={styles.agentGrid}>
        {AGENTS.map(({ icon: Icon, name, purpose, inputs, checks, outputs }) => (
          <div key={name} className={styles.agentCard}>
            <div className={styles.agentTop}>
              <Icon size={18} className={styles.agentIcon} />
              <span className={styles.agentName}>{name}</span>
            </div>
            <p className={styles.purpose}>{purpose}</p>
            <Facet label="Inputs" items={inputs} />
            <Facet label="Checks performed" items={checks} />
            <Facet label="Outputs" items={outputs} />
          </div>
        ))}
      </div>

      <div className={styles.panels}>
        <div className={styles.panel}>
          <div className={styles.panelHead}>
            <Prohibit size={15} className={styles.constraintIcon} />
            <span>Oversight-only constraints</span>
          </div>
          <ul className={styles.panelList}>
            {CONSTRAINTS.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
        <div className={styles.panel}>
          <div className={styles.panelHead}>
            <Target size={15} className={styles.catchIcon} />
            <span>What this layer catches</span>
          </div>
          <ul className={styles.panelList}>
            {CATCHES.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className={styles.flowPanels}>
        <div className={styles.flowPanel}>
          <span className={styles.flowTitle}>Downstream → Specialist Reasoning Agents (read-only)</span>
          <ul className={styles.flowList}>
            <li>observes agent plans, outputs, and intermediate artifacts</li>
            <li>may request clarifications or re-checks</li>
          </ul>
        </div>
        <div className={styles.flowPanel}>
          <span className={styles.flowTitle}>Sideways → Control Plane / Policy Data (read-only)</span>
          <ul className={styles.flowList}>
            <li>policies</li>
            <li>approvals</li>
            <li>execution guardrails</li>
            <li>verification rules</li>
            <li>historical signals</li>
          </ul>
        </div>
      </div>

      {!hasFindings && (
        <p className={styles.empty}>No oversight findings recorded for this run.</p>
      )}
    </section>
  );
}

function Facet({ label, items }: { label: string; items: string[] }) {
  return (
    <div className={styles.facet}>
      <span className={styles.facetLabel}>{label}</span>
      <div className={styles.chips}>
        {items.map((i) => (
          <span key={i} className={styles.chip}>
            {i}
          </span>
        ))}
      </div>
    </div>
  );
}
