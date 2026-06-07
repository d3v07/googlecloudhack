import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { loadPack } from "@/lib/api";
import { ControlPlaneView } from "@/components/ControlPlaneView";
import { OversightView } from "@/components/OversightView";
import styles from "./system-map.module.css";

// System Map (Layer 1) + Control Plane (Layer 3) + Agent Oversight (Layer 4) as
// one scrolling page. Hand-built CSS architecture map (no diagram lib) so it
// matches the console and reflows on mobile. Pulls one pack so Control Plane can
// highlight the current run state honestly.
export default async function SystemMapPage() {
  const { pack, source } = await loadPack();
  const livePack = source === "live" ? pack : null;

  return (
    <main className={styles.main}>
      <header className={styles.head}>
        <h1 className={styles.title}>System Map</h1>
        <p className={styles.sub}>
          Where each part sits, how a run flows through the deterministic control plane, and the
          read-only oversight layer that watches it. Intake is detailed on the{" "}
          <Link href="/intake" className={styles.inlineLink}>
            Intake &amp; API Gateway
          </Link>{" "}
          page.
        </p>
      </header>

      {/* architecture map */}
      <section className={styles.mapWrap}>
        <div className={styles.tier}>
          <Box tone="amber" title="Next.js Dashboard" sub="operator console (Cloud Run)" />
        </div>
        <Down />
        <div className={styles.tier}>
          <Box tone="cyan" title="FastAPI Cloud Run API" sub="/packs · /run · /packs/:id/decision" />
        </div>
        <Down />
        <div className={styles.tierRow}>
          <Box tone="green" title="Deterministic Controller" sub="winner selection · phase gates" />
          <Box tone="cyan" title="Agent Engine Roles" sub="diagnose · candidate · rationale (read-only)" />
          <Box tone="neutral" title="Evidence Ledger" sub="EvidencePack + event collections" />
        </div>
        <Down />
        <div className={styles.tierRow}>
          <Box tone="green" title="MongoDB target" sub="sample_supplies.sales_agent_demo" />
          <Box tone="neutral" title="Secret Manager" sub="connection string · API token" />
          <Box tone="neutral" title="Policy / Verification" sub="re-explain after apply" />
        </div>
      </section>

      <div className={styles.divider} />
      <ControlPlaneView pack={livePack} />

      <div className={styles.divider} />
      <OversightView hasFindings={false} />
    </main>
  );
}

function Box({
  title,
  sub,
  tone,
}: {
  title: string;
  sub: string;
  tone: "amber" | "cyan" | "green" | "neutral";
}) {
  return (
    <div className={styles.box} data-tone={tone}>
      <span className={styles.boxTitle}>{title}</span>
      <span className={styles.boxSub}>{sub}</span>
    </div>
  );
}

function Down() {
  return (
    <div className={styles.down} aria-hidden>
      <ArrowRight size={18} className={styles.downIcon} />
    </div>
  );
}
