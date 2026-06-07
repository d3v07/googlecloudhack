import {
  ChartLineUp,
  ListMagnifyingGlass,
  PencilSimple,
  CalendarDots,
  ArrowRight,
  Lock,
} from "@phosphor-icons/react/dist/ssr";
import styles from "./intake.module.css";

// Layer 2: Intake + API Gateway. Explains how runs ENTER the system and how the
// dashboard talks to the FastAPI Cloud Run API — without expanding the API
// contract. Sources that aren't wired to live ingestion are labelled honestly as
// "planned intake path"; only the preset /run path is live today.

const SOURCES = [
  {
    icon: ChartLineUp,
    name: "Atlas Performance Advisor",
    desc: "Recommended slow-query candidates",
    status: "planned" as const,
  },
  {
    icon: ListMagnifyingGlass,
    name: "Profiler / Slow Query Logs",
    desc: "Observed real workload behavior",
    status: "planned" as const,
  },
  {
    icon: PencilSimple,
    name: "Manual Query Paste",
    desc: "Operator-driven investigation",
    status: "planned" as const,
  },
  {
    icon: CalendarDots,
    name: "Scheduled Scan",
    desc: "Periodic automated intake",
    status: "planned" as const,
  },
];

const ROUTES = [
  { method: "GET", path: "/packs", desc: "list available EvidencePacks" },
  { method: "POST", path: "/run", desc: "create a gated read-only run" },
  { method: "POST", path: "/packs/:id/decision", desc: "record decision for a pack" },
];

export default function IntakePage() {
  return (
    <main className={styles.main}>
      <header className={styles.head}>
        <h1 className={styles.title}>Intake &amp; API Gateway</h1>
        <p className={styles.sub}>
          How runs enter the system and how the dashboard talks to the FastAPI Cloud Run API. The
          dashboard never expands the API contract — it consumes EvidencePack v1 over the existing
          routes only.
        </p>
      </header>

      {/* 1. Intake sources */}
      <section className={styles.section}>
        <h2 className={styles.sectionHeading}>Intake sources</h2>
        <div className={styles.sourceGrid}>
          {SOURCES.map(({ icon: Icon, name, desc, status }) => (
            <div key={name} className={styles.sourceCard}>
              <div className={styles.sourceTop}>
                <Icon size={20} className={styles.sourceIcon} />
                <span className={styles.plannedTag}>
                  {status === "planned" ? "planned intake path" : "available intake path"}
                </span>
              </div>
              <span className={styles.sourceName}>{name}</span>
              <span className={styles.sourceDesc}>{desc}</span>
            </div>
          ))}
        </div>
      </section>

      {/* flow: sources -> intake service -> gateway */}
      <section className={styles.section}>
        <h2 className={styles.sectionHeading}>Run Intake Service</h2>
        <div className={styles.flowRow}>
          <div className={styles.flowBox}>
            <span className={styles.flowTitle}>Run Intake API</span>
            <ul className={styles.flowList}>
              <li>creates gated read-only runs</li>
              <li>normalizes query metadata</li>
              <li>creates run record</li>
              <li>binds pending approval gate</li>
              <li>writes initial ledger event</li>
            </ul>
          </div>
          <ArrowRight size={22} className={styles.flowArrow} />
          <div className={styles.flowBox}>
            <span className={styles.flowTitle}>FastAPI Cloud Run API</span>
            <ul className={styles.routeList}>
              {ROUTES.map((r) => (
                <li key={r.path} className={styles.route}>
                  <span className={styles.method} data-method={r.method}>
                    {r.method}
                  </span>
                  <code className={styles.routePath}>{r.path}</code>
                  <span className={styles.routeDesc}>{r.desc}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* exact required wording */}
      <section className={styles.wordingBlock}>
        <Lock size={18} className={styles.wordingIcon} />
        <p className={styles.wording}>
          <code>/run</code> creates a gated read-only run. Mutation remains impossible until the
          operator approves a matching EvidencePack hash.
        </p>
      </section>

      {/* run state after intake */}
      <section className={styles.section}>
        <h2 className={styles.sectionHeading}>Run state after intake</h2>
        <div className={styles.stateGrid}>
          <StateRow k="State" v="PENDING_APPROVAL" tone="amber" />
          <StateRow k="Mode" v="READ-ONLY" tone="green" />
          <StateRow k="Mutations" v="BLOCKED" tone="red" />
          <StateRow k="Approval Gate" v="UNMATCHED until matching evidence hash approval exists" tone="neutral" />
        </div>
      </section>

      {/* downstream handoff */}
      <section className={styles.section}>
        <h2 className={styles.sectionHeading}>Downstream handoff</h2>
        <div className={styles.handoff}>
          <span className={styles.handoffItem}>
            <code>run_id</code>
          </span>
          <span className={styles.handoffItem}>intake context</span>
          <span className={styles.handoffItem}>source metadata</span>
          <span className={styles.handoffItem}>pending state</span>
        </div>
      </section>
    </main>
  );
}

function StateRow({
  k,
  v,
  tone,
}: {
  k: string;
  v: string;
  tone: "amber" | "green" | "red" | "neutral";
}) {
  return (
    <div className={styles.stateRow}>
      <span className={styles.stateKey}>{k}</span>
      <span className={styles.stateVal} data-tone={tone}>
        {v}
      </span>
    </div>
  );
}
