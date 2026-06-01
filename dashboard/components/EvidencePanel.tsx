import { Warning, Lightbulb } from "@phosphor-icons/react/dist/ssr";
import type { Finding, Recommendation } from "@/lib/evidence";
import { formatIndexSpec } from "@/lib/evidence";
import styles from "./EvidencePanel.module.css";

export function EvidencePanel({
  finding,
  recommendation,
}: {
  finding: Finding;
  recommendation: Recommendation;
}) {
  return (
    <section className={styles.panel}>
      <div className={styles.block}>
        <header className={styles.head}>
          <Warning weight="fill" size={16} className={styles.findingIcon} />
          <span className={styles.title}>Finding</span>
          <span className={styles.severity} data-sev={finding.severity}>
            {finding.severity}
          </span>
        </header>
        <p className={styles.body}>{finding.problem}</p>
        {finding.evidence_refs.length > 0 && (
          <div className={styles.refs}>
            {finding.evidence_refs.map((r) => (
              <code key={r} className={styles.ref}>
                {r}
              </code>
            ))}
          </div>
        )}
      </div>

      <div className={styles.divider} />

      <div className={styles.block}>
        <header className={styles.head}>
          <Lightbulb weight="fill" size={16} className={styles.recIcon} />
          <span className={styles.title}>Recommendation</span>
        </header>
        <code className={styles.indexSpec}>
          createIndex({formatIndexSpec(recommendation.index_spec)})
        </code>
        <p className={styles.body}>{recommendation.rationale}</p>
      </div>
    </section>
  );
}
