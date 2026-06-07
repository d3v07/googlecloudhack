"use client";

import { useState } from "react";
import {
  MagnifyingGlass,
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
import { StatusPill } from "@/components/StatusPill";
import { TracePanel } from "@/components/TracePanel";
import type { EvidencePack } from "@/lib/evidence";
import { displayStatus, isVerificationFailed } from "@/lib/evidence";
import type { PackSource } from "@/lib/api";
import { askTheAgent } from "@/lib/run";
import styles from "@/app/run-review.module.css";

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
  const ds = displayStatus(pack);
  const verificationFailed = isVerificationFailed(pack);

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
          <MagnifyingGlass weight="fill" size={20} className={styles.brandIcon} />
          <h1 className={styles.brandName}>Run Review</h1>
        </div>
        <div className={styles.runMeta}>
          <GitBranch size={14} />
          <code>{pack.run_id}</code>
          <span className={styles.dot}>·</span>
          <code>{pack.namespace}</code>
          <StatusPill status={ds.key} label={ds.label} />
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
        <PlanPanel
          before={pack.before}
          after={pack.after}
          verificationFailed={verificationFailed}
        />
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
