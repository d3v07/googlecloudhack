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
import { SiftMemoryPanel } from "@/components/SiftMemoryPanel";
import { Tour, type TourStep } from "@/components/Tour";
import type { EvidencePack } from "@/lib/evidence";
import { displayStatus, isVerificationFailed } from "@/lib/evidence";
import type { PackSource } from "@/lib/api";
import type { SiftMemoryResult } from "@/lib/siftMemory";
import styles from "@/app/run-review.module.css";

const RUNREVIEW_TOUR: TourStep[] = [
  {
    title: "Reviewing one diagnosis",
    body: "This is the EvidencePack for a single captured query. The agent has recommended a fix — but nothing has touched the database yet. The decision is yours.",
  },
  {
    title: "The approval gate",
    body: "Status is PENDING APPROVAL · MUTATION BLOCKED. The full evidence hash binds your approval to exactly this evidence — approve a different pack and the hash won't match, so a stale fix can't slip through.",
  },
  {
    title: "Why it's safe",
    body: "Safety Authority spells out the trust model: agents are read-only and only recommend, deterministic Python picks the winner, you approve, mutation is backend-only after that, then it re-explains to verify. The agent never writes to the database.",
  },
  {
    title: "The evidence",
    body: "Scroll down for the HIGH finding (the blocking SORT), the ESR index recommendation, and the before/after explain-plan diff. The 'after' side fills in once it's verified.",
  },
  {
    title: "Approve → apply → verify",
    body: "Click 'Approve this evidence hash': the backend creates the recommended index and re-explains — the SORT disappears and docs-examined collapses, and the run flips to VERIFIED. 'Reject' records your decision and changes nothing.",
  },
];

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
  initialMemory,
}: {
  initialPack: EvidencePack;
  initialSource: PackSource;
  initialNotice?: string;
  initialMemory?: SiftMemoryResult | null;
}) {
  const [pack, setPack] = useState<EvidencePack>(initialPack);
  const source = initialSource;
  const notice = initialNotice;
  const ds = displayStatus(pack);
  const verificationFailed = isVerificationFailed(pack);

  return (
    <main className={styles.main}>
      <Tour id="runreview" title="Run review" steps={RUNREVIEW_TOUR} />
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
      <SiftMemoryPanel memory={initialMemory} />

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
