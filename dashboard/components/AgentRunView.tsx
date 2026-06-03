"use client";

import { useState } from "react";
import {
  Database,
  GitBranch,
  WifiHigh,
  WifiSlash,
  Sparkle,
  CircleNotch,
} from "@phosphor-icons/react/dist/ssr";
import { StageIndicator } from "@/components/StageIndicator";
import { PlanPanel } from "@/components/PlanPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { ApprovalGatePanel } from "@/components/ApprovalGatePanel";
import { TracePanel } from "@/components/TracePanel";
import type { EvidencePack } from "@/lib/evidence";
import type { PackSource } from "@/lib/api";
import { askTheAgent } from "@/lib/run";
import styles from "@/app/page.module.css";

/**
 * The interactive run view (#37). Seeded with the server-loaded pack; the "Ask
 * the agent" button triggers a live diagnosis (POST /api/run) and swaps the
 * rendered pack for the freshly-produced one. The 5-stage
 * indicator shows a running state while the agent works.
 */
export function AgentRunView({
  initialPack,
  initialSource,
  initialNotice,
}: {
  initialPack: EvidencePack;
  initialSource: PackSource;
  initialNotice?: string;
}) {
  const [pack, setPack] = useState<EvidencePack>(initialPack);
  const [source, setSource] = useState<PackSource>(initialSource);
  const [notice, setNotice] = useState<string | undefined>(initialNotice);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const statusLabel =
    pack.status === "diagnosed"
      ? "pending approval"
      : pack.status === "verified"
        ? "verified"
        : pack.status;

  async function onAsk() {
    setRunning(true);
    setError(null);
    const res = await askTheAgent();
    setRunning(false);
    if (res.ok && res.pack) {
      setPack(res.pack);
      setSource("live");
      setNotice(undefined);
    } else {
      setError(res.message ?? "Could not run the agent.");
    }
  }

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
            {statusLabel}
          </span>
          <span className={styles.source} data-source={source} title={notice ?? "Live read API"}>
            {source === "live" ? <WifiHigh size={13} /> : <WifiSlash size={13} />}
            {source}
          </span>
        </div>
      </header>

      <ApprovalGatePanel pack={pack} running={running} onPackUpdate={setPack} />

      <div className={styles.askBar}>
        <button className={styles.askButton} onClick={onAsk} disabled={running}>
          {running ? (
            <CircleNotch size={18} className={styles.spin} />
          ) : (
            <Sparkle weight="fill" size={18} />
          )}
          {running ? "Agent diagnosing…" : "Ask the agent to diagnose"}
        </button>
        <span className={styles.askHint}>
          {running
            ? "Running the live Agent Engine diagnosis over the Denver/ESR fixture…"
            : "Triggers a diagnosis run and renders the resulting evidence pack."}
        </span>
        {error && <span className={styles.askError}>{error}</span>}
      </div>

      <StageIndicator status={pack.status} running={running} />
      <TracePanel
        trace={pack.agent_trace ?? []}
        evidenceHash={pack.evidence_hash}
        ledgerPersisted={source === "live"}
      />

      <div className={styles.grid}>
        <PlanPanel before={pack.before} after={pack.after} />
        <EvidencePanel finding={pack.finding} recommendation={pack.recommendation} />
      </div>

      <footer className={styles.footer}>
        EvidencePack <code>{pack.version}</code>
        {source === "live"
          ? " · live from the read API · ledger persisted"
          : ` · ${notice ?? "showing the bundled example"}`}
      </footer>
    </main>
  );
}
