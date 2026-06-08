import {
  Brain,
  CheckCircle,
  ClockCounterClockwise,
  Database,
  MagnifyingGlass,
  ShieldCheck,
  Warning,
  XCircle,
} from "@phosphor-icons/react/dist/ssr";
import {
  formatMemoryScore,
  memoryHitSummary,
  memoryHitTitle,
  normalizeSiftMemory,
  type SiftMemoryResult,
} from "@/lib/siftMemory";
import styles from "./SiftMemoryPanel.module.css";

function StateIcon({ state }: { state: ReturnType<typeof normalizeSiftMemory>["state"] }) {
  if (state === "configured_with_results") return <CheckCircle weight="fill" size={16} />;
  if (state === "configured_no_results") return <MagnifyingGlass size={16} />;
  if (state === "failed") return <XCircle weight="fill" size={16} />;
  return <Warning size={16} />;
}

export function SiftMemoryPanel({ memory }: { memory?: SiftMemoryResult | null }) {
  const view = normalizeSiftMemory(memory);
  const detail = view.error ?? memory?.message?.trim() ?? null;
  const visibleHits = view.hits.slice(0, 4);
  const hiddenCount = view.hits.length - visibleHits.length;

  return (
    <section className={styles.panel} data-state={view.state} aria-label="Sift Memory">
      <div className={styles.header}>
        <div className={styles.identity}>
          <span className={styles.iconWrap}>
            <Brain weight="fill" size={22} />
          </span>
          <div>
            <p className={styles.eyebrow}>DBRE-only retrieval context</p>
            <h2>Sift Memory</h2>
          </div>
        </div>
        <span className={styles.state}>
          <StateIcon state={view.state} />
          {view.label}
        </span>
      </div>

      <div className={styles.boundary}>
        <ShieldCheck weight="fill" size={16} />
        <span>
          Read-only retrieval context only. The deterministic controller still selects, applies,
          and verifies.
        </span>
      </div>

      <div className={styles.metaGrid}>
        <div className={styles.metaItem}>
          <MagnifyingGlass size={15} />
          <span>Retrieval query</span>
          <code>{view.query ?? "not attached"}</code>
        </div>
        <div className={styles.metaItem}>
          <Database size={15} />
          <span>Memory namespace</span>
          <code>{view.namespace ?? "default"}</code>
        </div>
        <div className={styles.metaItem}>
          <ClockCounterClockwise size={15} />
          <span>Retrieved</span>
          <code>{view.retrievedAt ?? "not recorded"}</code>
        </div>
      </div>

      <p className={styles.summary}>{view.summary}</p>
      {detail && <p className={styles.detail}>{detail}</p>}

      {visibleHits.length > 0 && (
        <ol className={styles.results} aria-label="Sift Memory results">
          {visibleHits.map((hit, index) => {
            const score = formatMemoryScore(hit.score);
            return (
              <li className={styles.result} key={hit.id ?? `${index}-${memoryHitTitle(hit, index)}`}>
                <div className={styles.resultHead}>
                  <span className={styles.resultTitle}>{memoryHitTitle(hit, index)}</span>
                  <span className={styles.resultMeta}>
                    {score && <code>score {score}</code>}
                    <code>{hit.source}</code>
                  </span>
                </div>
                <p>{memoryHitSummary(hit)}</p>
                {hit.tags.length > 0 && (
                  <div className={styles.tags}>
                    {hit.tags.map((tag) => (
                      <code key={tag}>{tag}</code>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {hiddenCount > 0 && <p className={styles.more}>+{hiddenCount} more memory results</p>}
    </section>
  );
}
