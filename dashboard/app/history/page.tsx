import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { loadPacks } from "@/lib/api";
import { displayStatus, shortHash, formatIndexSpec } from "@/lib/evidence";
import { StatusPill } from "@/components/StatusPill";
import styles from "./history.module.css";

export const dynamic = "force-dynamic";

// History & Compare (Layer 1): past runs + outcomes, derived from the existing
// GET /packs (no new endpoint). A compact comparison table of run → status →
// recommended index → outcome.
export default async function HistoryPage() {
  const { packs, source, notice } = await loadPacks();

  // group by outcome for the summary band
  const byOutcome = packs.reduce<Record<string, number>>((acc, p) => {
    const { label } = displayStatus(p);
    acc[label] = (acc[label] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <main className={styles.main}>
      <header className={styles.head}>
        <h1 className={styles.title}>History &amp; Compare</h1>
        <p className={styles.sub}>
          Past runs and their outcomes, derived from the read API. Compare what each run recommended
          and whether it verified.
          {source === "fallback" && <span className={styles.notice}> {notice}</span>}
        </p>
      </header>

      {Object.keys(byOutcome).length > 0 && (
        <div className={styles.summary}>
          {Object.entries(byOutcome).map(([label, n]) => (
            <span key={label} className={styles.summaryItem}>
              <strong>{n}</strong> {label}
            </span>
          ))}
        </div>
      )}

      {packs.length === 0 ? (
        <div className={styles.empty}>No run history yet.</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th className={styles.hideSm}>Recommended index</th>
                <th className={styles.hideSm}>Hash</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {packs.map((p) => {
                const ds = displayStatus(p);
                return (
                  <tr key={p.run_id}>
                    <td>
                      <span className={styles.runId}>{p.run_id}</span>
                    </td>
                    <td>
                      <StatusPill status={ds.key} label={ds.label} />
                    </td>
                    <td className={styles.hideSm}>
                      <code className={styles.idx}>{formatIndexSpec(p.recommendation.index_spec)}</code>
                    </td>
                    <td className={styles.hideSm}>
                      <code className={styles.hash}>{shortHash(p.evidence_hash)}</code>
                    </td>
                    <td className={styles.actionCell}>
                      <Link
                        href={`/runs/${encodeURIComponent(p.run_id)}`}
                        className={styles.review}
                      >
                        Review <ArrowRight size={13} />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
