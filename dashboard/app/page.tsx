import Link from "next/link";
import {
  SquaresFour,
  Clock,
  CheckCircle,
  WarningOctagon,
  ArrowRight,
  WifiHigh,
  WifiSlash,
} from "@phosphor-icons/react/dist/ssr";
import { loadPacks } from "@/lib/api";
import { displayStatus, shortHash } from "@/lib/evidence";
import { StatusPill } from "@/components/StatusPill";
import styles from "./overview.module.css";

export const dynamic = "force-dynamic";

// Overview (Layer 1): the landing page — fleet status at a glance + the run list.
// Reads the existing GET /packs (no new endpoint); falls back to the bundled
// example when no API is configured.
export default async function OverviewPage() {
  const { packs, source, notice } = await loadPacks();

  const counts = packs.reduce(
    (acc, p) => {
      const { key } = displayStatus(p);
      if (key === "pending-approval") acc.pending += 1;
      else if (key === "verified") acc.verified += 1;
      else if (key === "verification-failed" || key === "rejected") acc.attention += 1;
      return acc;
    },
    { pending: 0, verified: 0, attention: 0 },
  );

  return (
    <main className={styles.main}>
      <header className={styles.head}>
        <div className={styles.titleRow}>
          <SquaresFour weight="fill" size={22} className={styles.titleIcon} />
          <h1 className={styles.title}>Overview</h1>
          <span className={styles.source} data-source={source} title={notice ?? "Live read API"}>
            {source === "live" ? <WifiHigh size={13} /> : <WifiSlash size={13} />}
            {source}
          </span>
        </div>
        <p className={styles.sub}>
          Evidence-driven index runs. Every fix is gated behind a hash-bound human approval;
          mutation happens backend-only after approval.
        </p>
      </header>

      <section className={styles.stats}>
        <StatCard icon={<SquaresFour size={18} />} label="Total runs" value={packs.length} tone="neutral" />
        <StatCard icon={<Clock size={18} />} label="Pending approval" value={counts.pending} tone="amber" />
        <StatCard icon={<CheckCircle size={18} />} label="Verified" value={counts.verified} tone="green" />
        <StatCard
          icon={<WarningOctagon size={18} />}
          label="Needs attention"
          value={counts.attention}
          tone="red"
        />
      </section>

      <section className={styles.listSection}>
        <h2 className={styles.listHeading}>Runs</h2>
        {packs.length === 0 ? (
          <div className={styles.empty}>
            No runs recorded yet. Trigger one from{" "}
            <Link href="/run-review" className={styles.emptyLink}>
              Run Review
            </Link>
            .
          </div>
        ) : (
          <ul className={styles.runList}>
            {packs.map((p) => {
              const ds = displayStatus(p);
              return (
                <li key={p.run_id} className={styles.runItem}>
                  <Link href={`/runs/${encodeURIComponent(p.run_id)}`} className={styles.runLink}>
                    <div className={styles.runMain}>
                      <span className={styles.runId}>{p.run_id}</span>
                      <span className={styles.runNs}>{p.namespace}</span>
                    </div>
                    <div className={styles.runMeta}>
                      <code className={styles.runHash}>{shortHash(p.evidence_hash)}</code>
                      <StatusPill status={ds.key} label={ds.label} />
                      <ArrowRight size={15} className={styles.runArrow} />
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </main>
  );
}

function StatCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: "neutral" | "amber" | "green" | "red";
}) {
  return (
    <div className={styles.stat} data-tone={tone}>
      <span className={styles.statIcon}>{icon}</span>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}
