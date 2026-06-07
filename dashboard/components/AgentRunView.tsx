"use client";

import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  MagnifyingGlass,
  GitBranch,
  WifiHigh,
  WifiSlash,
  Flask,
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
 * the agent" button triggers a diagnosis (POST /api/run) and navigates to
 * /runs/<run_id> for the freshly-produced run, so the destination's loader
 * supplies the durable source (live vs simulation) — we never assert "live" on
 * the client. The 5-stage indicator shows a running state while it works.
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
  const router = useRouter();
  const pathname = usePathname();
  const [pack, setPack] = useState<EvidencePack>(initialPack);
  // source/notice are fixed for this rendered run: "Ask" navigates to a fresh
  // run rather than mutating in place, and approving a pack never changes its
  // source. setPack still drives in-place approval updates from the gate panel.
  const source = initialSource;
  const notice = initialNotice;
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ds = displayStatus(pack);
  const verificationFailed = isVerificationFailed(pack);

  async function onAsk() {
    setRunning(true);
    setError(null);
    const res = await askTheAgent();
    if (res.ok && res.pack) {
      // Navigate to the produced run; loadPack on that page resolves the honest
      // source (live from the read API, or simulation when no backend is set).
      const target = `/runs/${encodeURIComponent(res.pack.run_id)}`;
      if (pathname === target) {
        // Same run id (e.g. re-running the simulation while already here): a push
        // is a no-op and would never clear the spinner — refresh in place instead.
        router.refresh();
        setRunning(false);
      } else {
        router.push(target);
      }
      return;
    }
    setRunning(false);
    setError(res.message ?? "Could not run the agent.");
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

      <ApprovalGatePanel pack={pack} running={running} onPackUpdate={setPack} />

      <div className={styles.askBar}>
        <button className={styles.askButton} onClick={onAsk} disabled={running}>
          {running ? (
            <CircleNotch size={18} className={styles.spin} />
          ) : (
            <Sparkle weight="fill" size={18} />
          )}
          {running ? "Diagnosis running…" : "Ask the agent to diagnose"}
        </button>
        <span className={styles.askHint}>
          {running
            ? "Diagnosis running over the Denver/ESR query…"
            : "Triggers a diagnosis run and opens the resulting evidence pack."}
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
