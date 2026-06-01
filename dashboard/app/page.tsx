import { Database, GitBranch, WifiHigh, WifiSlash } from "@phosphor-icons/react/dist/ssr";
import { StageIndicator } from "@/components/StageIndicator";
import { PlanPanel } from "@/components/PlanPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { ApproveBar } from "@/components/ApproveBar";
import { loadPack } from "@/lib/api";
import styles from "./page.module.css";

// Async server component: reads a pack from the live read API (#18/#31), falling
// back to the committed example when no API is configured or it is unreachable.
// `run_id` comes from the ?run_id= query param (or NEXT_PUBLIC_PACK_ID env).
export default async function AgentRunPage({
  searchParams,
}: {
  searchParams: Promise<{ run_id?: string }>;
}) {
  const { run_id } = await searchParams;
  const { pack, source, notice } = await loadPack(run_id);

  return (
    <main className={styles.main}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <Database weight="fill" size={22} className={styles.brandIcon} />
          <span className={styles.brandName}>DBRE Console</span>
          <span className={styles.brandTag}>evidence-driven index review</span>
        </div>
        <div className={styles.runMeta}>
          <GitBranch size={14} />
          <code>{pack.run_id}</code>
          <span className={styles.dot}>·</span>
          <code>{pack.namespace}</code>
          <span className={styles.status} data-status={pack.status}>
            {pack.status}
          </span>
          <span className={styles.source} data-source={source} title={notice ?? "Live read API"}>
            {source === "live" ? <WifiHigh size={13} /> : <WifiSlash size={13} />}
            {source}
          </span>
        </div>
      </header>

      <StageIndicator status={pack.status} />

      <div className={styles.grid}>
        <PlanPanel before={pack.before} after={pack.after} />
        <EvidencePanel finding={pack.finding} recommendation={pack.recommendation} />
      </div>

      <ApproveBar evidenceHash={pack.evidence_hash} status={pack.status} />

      <footer className={styles.footer}>
        EvidencePack <code>{pack.version}</code>
        {source === "live"
          ? " · live from the read API"
          : ` · ${notice ?? "showing the bundled example"}`}
      </footer>
    </main>
  );
}
