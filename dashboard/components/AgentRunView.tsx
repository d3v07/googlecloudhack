"use client";

import { useState } from "react";
import {
  MagnifyingGlass,
  GitBranch,
  WifiHigh,
  WifiSlash,
  Flask,
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
import styles from "@/app/run-review.module.css";

/**
 * Run review for a DBRE-selected diagnosis. The run is produced from the slow-query queue (the
 * "Diagnose" action runs POST /run on the captured query); this view renders the resulting pack
 * and the approval gate. Approving applies + verifies the index server-side — the dashboard
 * never asserts a verified result on the client.
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
  const source = initialSource;
  const notice = initialNotice;
  const ds = displayStatus(pack);
  const verificationFailed = isVerificationFailed(pack);

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
            {source === "live" ? (
              <WifiHigh size={13} />
            ) : source === "simulation" ? (
              <Flask size={13} weight="fill" />
            ) : (
              <WifiSlash size={13} />
            )}
            {source === "simulation" ? "simulation" : source}
          </span>
        </div>
      </header>

      <ApprovalGatePanel pack={pack} running={false} onPackUpdate={setPack} />

      <StageIndicator status={pack.status} running={false} />
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
