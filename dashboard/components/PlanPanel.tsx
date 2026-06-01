import { ArrowRight, Warning, CheckCircle } from "@phosphor-icons/react/dist/ssr";
import type { Evidence } from "@/lib/evidence";
import styles from "./PlanPanel.module.css";

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "neutral";
}) {
  return (
    <div className={styles.metric} data-tone={tone ?? "neutral"}>
      <span className={styles.metricValue}>{value}</span>
      <span className={styles.metricLabel}>{label}</span>
    </div>
  );
}

function EvidenceColumn({
  title,
  evidence,
  variant,
}: {
  title: string;
  evidence: Evidence | null;
  variant: "before" | "after";
}) {
  if (!evidence) {
    return (
      <div className={styles.column} data-variant={variant}>
        <header className={styles.colHead}>
          <span className={styles.colTitle}>{title}</span>
          <span className={styles.pendingTag}>pending verify</span>
        </header>
        <div className={styles.placeholder}>
          Observed plan appears here after the fix is applied and re-measured.
        </div>
      </div>
    );
  }

  const m = evidence.metrics;
  return (
    <div className={styles.column} data-variant={variant}>
      <header className={styles.colHead}>
        <span className={styles.colTitle}>{title}</span>
        {m.has_blocking_sort === true ? (
          <span className={styles.badBadge}>
            <Warning weight="fill" size={14} /> blocking sort
          </span>
        ) : (
          <span className={styles.goodBadge}>
            <CheckCircle weight="fill" size={14} /> no sort
          </span>
        )}
      </header>

      <div className={styles.stageChain}>
        {m.stages.map((s, i) => (
          <span key={i} className={styles.stageNode} data-stage={s}>
            {s}
            {i < m.stages.length - 1 && <ArrowRight size={12} className={styles.stageArrow} />}
          </span>
        ))}
      </div>

      <div className={styles.metrics}>
        <Metric
          label="keys examined"
          value={m.total_keys_examined.toLocaleString()}
          tone={m.has_blocking_sort === true ? "bad" : "good"}
        />
        <Metric label="docs examined" value={m.docs_examined.toLocaleString()} />
        <Metric label="returned" value={m.docs_returned.toLocaleString()} />
        <Metric label="millis" value={m.millis.toFixed(0)} />
      </div>
    </div>
  );
}

export function PlanPanel({
  before,
  after,
}: {
  before: Evidence;
  after: Evidence | null;
}) {
  return (
    <section className={styles.panel}>
      <h2 className={styles.heading}>Predicted vs Observed</h2>
      <div className={styles.grid}>
        <EvidenceColumn title="Before — serving index" evidence={before} variant="before" />
        <EvidenceColumn title="After — recommended index" evidence={after} variant="after" />
      </div>
    </section>
  );
}
