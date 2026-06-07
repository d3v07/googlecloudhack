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
  afterState,
}: {
  title: string;
  evidence: Evidence | null;
  variant: "before" | "after";
  // only meaningful for the after column when its evidence is absent
  afterState?: "pending" | "failed";
}) {
  if (!evidence) {
    const failed = afterState === "failed";
    return (
      <div className={styles.column} data-variant={variant}>
        <header className={styles.colHead}>
          <span className={styles.colTitle}>{title}</span>
          <span className={failed ? styles.badBadge : styles.pendingTag}>
            {failed ? (
              <>
                <Warning weight="fill" size={14} /> verification failed
              </>
            ) : (
              "pending verification"
            )}
          </span>
        </header>
        {/* explicit explain-plan diff label for the after side (Layer 1 AC) */}
        <p className={styles.diffLabel} data-tone={failed ? "bad" : "neutral"}>
          {failed
            ? "After: verification failed, see trace"
            : "After: pending verification"}
        </p>
        <div className={styles.placeholder}>
          {failed
            ? "The apply ran but re-explain did not confirm the fix. Check the trace."
            : "Observed plan appears here after the fix is applied and re-measured."}
        </div>
      </div>
    );
  }

  const m = evidence.metrics;
  const sorted = m.has_blocking_sort === true;
  // The explicit explain-plan diff sentence (Layer 1 AC).
  const diffLine =
    variant === "before"
      ? sorted
        ? "Before: SORT present / high docs examined"
        : "Before: index-backed query"
      : sorted
        ? "After: SORT still present, see trace"
        : "After: SORT removed / index-backed query";
  return (
    <div className={styles.column} data-variant={variant}>
      <header className={styles.colHead}>
        <span className={styles.colTitle}>{title}</span>
        {sorted ? (
          <span className={styles.badBadge}>
            <Warning weight="fill" size={14} /> blocking sort
          </span>
        ) : (
          <span className={styles.goodBadge}>
            <CheckCircle weight="fill" size={14} /> no sort
          </span>
        )}
      </header>

      <p className={styles.diffLabel} data-tone={sorted ? "bad" : "good"}>
        {diffLine}
      </p>

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
  verificationFailed = false,
}: {
  before: Evidence;
  after: Evidence | null;
  verificationFailed?: boolean;
}) {
  return (
    <section className={styles.panel}>
      <h2 className={styles.heading}>Before / After explain-plan diff</h2>
      <div className={styles.grid}>
        <EvidenceColumn title="Before — serving index" evidence={before} variant="before" />
        <EvidenceColumn
          title="After — recommended index"
          evidence={after}
          variant="after"
          afterState={verificationFailed ? "failed" : "pending"}
        />
      </div>
    </section>
  );
}
