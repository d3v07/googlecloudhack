import Link from "next/link";
import {
  CheckCircle,
  XCircle,
  SealCheck,
  ListChecks,
  Scroll,
} from "@phosphor-icons/react/dist/ssr";
import { loadPack } from "@/lib/api";
import { displayStatus, shortHash } from "@/lib/evidence";
import { StatusPill } from "@/components/StatusPill";
import styles from "./audit.module.css";

export const dynamic = "force-dynamic";

// Audit & Compliance (Layer 1): approvals, verification trail, trace items, and
// policy events. Policy events are not part of EvidencePack v1, so that section
// shows an honest empty state.
export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ run_id?: string }>;
}) {
  const { run_id } = await searchParams;
  const { pack, source } = await loadPack(run_id);
  const ds = displayStatus(pack);

  const decision = pack.decision;
  const gate = pack.approval_gate;
  const trace = pack.agent_trace ?? [];
  const verified = ds.key === "verified";
  const verificationFailed = ds.key === "verification-failed";

  return (
    <main className={styles.main}>
      <header className={styles.head}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>Audit &amp; Compliance</h1>
          <StatusPill status={ds.key} label={ds.label} />
        </div>
        <p className={styles.sub}>
          Approval and verification trail for run <code>{pack.run_id}</code>.{" "}
          <Link href={`/runs/${encodeURIComponent(pack.run_id)}`} className={styles.link}>
            Open in Run Review
          </Link>
          .
          {source === "fallback" && (
            <span className={styles.notice}> Showing the bundled example pack.</span>
          )}
        </p>
      </header>

      {/* approvals */}
      <Section icon={<ListChecks />} title="Approvals">
        {decision ? (
          <div className={styles.row}>
            <span className={styles.ok}>
              <CheckCircle /> Decision recorded
            </span>
            {/* approver is carried on the approval gate; the decision record often omits it */}
            <Field k="approver" v={String(gate?.approver ?? decision.approved_by ?? "—")} />
            <Field k="approved at" v={String(decision.approved_at ?? "—")} />
            <Field k="bound hash" v={shortHash(decision.evidence_hash)} mono />
          </div>
        ) : gate ? (
          <p className={styles.empty}>
            Gate state: {gate.state}. No approval decision recorded yet for this run.
          </p>
        ) : (
          <p className={styles.empty}>No approval recorded for this run.</p>
        )}
      </Section>

      {/* verification trail */}
      <Section icon={<SealCheck />} title="Verification trail">
        {verified ? (
          <span className={styles.ok}>
            <CheckCircle /> Re-explain after apply confirmed the fix (SORT removed).
          </span>
        ) : verificationFailed ? (
          <span className={styles.bad}>
            <XCircle /> Apply ran but re-explain did not confirm the fix — see trace.
          </span>
        ) : (
          <p className={styles.empty}>
            Not yet verified. Verification runs after a hash-bound approval applies the index.
          </p>
        )}
      </Section>

      {/* trace items */}
      <Section icon={<Scroll />} title="Trace">
        {trace.length === 0 ? (
          <p className={styles.empty}>No trace events recorded for this run.</p>
        ) : (
          <ul className={styles.trace}>
            {trace.map((t, i) => (
              <li key={i} className={styles.traceItem} data-status={t.status}>
                <span className={styles.traceStage}>{t.stage}</span>
                <span className={styles.traceActor}>{t.actor.replace(/_/g, " ")}</span>
                <span className={styles.traceSummary}>{t.summary}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* policy events — not in EvidencePack v1 */}
      <Section icon={<ListChecks />} title="Policy events">
        <p className={styles.empty}>No policy events recorded for this run.</p>
      </Section>
    </main>
  );
}

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionHead}>
        <span className={styles.sectionIcon}>{icon}</span>
        {title}
      </h2>
      <div className={styles.sectionBody}>{children}</div>
    </section>
  );
}

function Field({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <span className={styles.field}>
      <span className={styles.fieldKey}>{k}</span>
      <span className={mono ? styles.fieldValMono : styles.fieldVal}>{v}</span>
    </span>
  );
}
