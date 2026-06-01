import { Database, GitBranch } from "@phosphor-icons/react/dist/ssr";
import { StageIndicator } from "@/components/StageIndicator";
import { PlanPanel } from "@/components/PlanPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { ApproveBar } from "@/components/ApproveBar";
import type { EvidencePack } from "@/lib/evidence";
import packData from "@/lib/example_pack.json";
import styles from "./page.module.css";

// Static for now: the committed example pack (the ESR B->C scenario). Day 3+
// swaps this for the live read endpoint (#18). The contract is identical.
const pack = packData as unknown as EvidencePack;

export default function AgentRunPage() {
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
        </div>
      </header>

      <StageIndicator status={pack.status} />

      <div className={styles.grid}>
        <PlanPanel before={pack.before} after={pack.after} />
        <EvidencePanel finding={pack.finding} recommendation={pack.recommendation} />
      </div>

      <ApproveBar evidenceHash={pack.evidence_hash} status={pack.status} />

      <footer className={styles.footer}>
        EvidencePack <code>{pack.version}</code> · rendered statically from the committed
        example · live data arrives via the read endpoint (#18)
      </footer>
    </main>
  );
}
