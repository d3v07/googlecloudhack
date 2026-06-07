"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Gauge, Stethoscope, Warning } from "@phosphor-icons/react/dist/ssr";

import styles from "./SlowQueryQueue.module.css";

export interface SlowQuery {
  captured_id: string;
  namespace: string;
  preset: string | null;
  user: { username: string; display_name: string };
  query: {
    filter: Record<string, { $gte?: number; $lte?: number } | string>;
    sort: [string, number][];
    limit: number;
  };
  metrics: {
    docs_examined: number;
    docs_returned: number;
    total_keys_examined: number;
    millis: number;
    stages: string[];
    has_blocking_sort: boolean;
  };
  signal: {
    severity: string;
    ratio: number;
    blocking_sort: boolean;
    collscan: boolean;
    score: number;
  };
  captured_at: string;
}

function summarize(q: SlowQuery): string {
  const f = q.query.filter;
  const parts: string[] = [];
  if (typeof f.storeLocation === "string") parts.push(`store=${f.storeLocation}`);
  if (typeof f.purchaseMethod === "string") parts.push(`method=${f.purchaseMethod}`);
  const age = f["customer.age"];
  if (age && typeof age === "object") parts.push(`age ${age.$gte ?? ""}–${age.$lte ?? ""}`);
  const sort = q.query.sort?.[0];
  if (sort) parts.push(`sort ${sort[0]} ${sort[1] === -1 ? "↓" : "↑"}`);
  return parts.join(" · ") || "full scan";
}

export function SlowQueryQueue({ rows, error }: { rows: SlowQuery[]; error: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function diagnose(capturedId: string) {
    setActionError(null);
    setBusy(capturedId);
    try {
      const res = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ captured_query_id: capturedId }),
      });
      const data = await res.json();
      if (!res.ok) {
        setActionError(typeof data?.detail === "string" ? data.detail : "Diagnosis failed.");
        setBusy(null);
        return;
      }
      router.push(`/runs/${encodeURIComponent(data.run_id)}`);
    } catch {
      setActionError("Network error — please try again.");
      setBusy(null);
    }
  }

  return (
    <main className={styles.wrap}>
      <header className={styles.head}>
        <h1 className={styles.title}>
          <Gauge size={22} weight="fill" /> Slow-Query Queue
        </h1>
        <p className={styles.sub}>
          Captured user workloads ranked by explain evidence — blocking sort, collection scan, and
          over-scan ratio, not wall-clock. Pick one to diagnose.
        </p>
      </header>

      {error && (
        <p className={styles.notice} role="status">
          {error}
        </p>
      )}
      {actionError && (
        <p className={styles.error} role="alert">
          {actionError}
        </p>
      )}

      {rows.length === 0 && !error ? (
        <p className={styles.empty}>
          No slow queries captured yet — run workloads from a user&apos;s console to populate the
          queue.
        </p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>sev</th>
                <th>query</th>
                <th>signal</th>
                <th>over-scan</th>
                <th>keys</th>
                <th>caused by</th>
                <th aria-label="action" />
              </tr>
            </thead>
            <tbody>
              {rows.map((q) => (
                <tr key={q.captured_id}>
                  <td>
                    <span className={styles.sev} data-severity={q.signal.severity}>
                      {q.signal.severity}
                    </span>
                  </td>
                  <td className={styles.queryCell}>
                    <span className={styles.querySummary}>{summarize(q)}</span>
                    {q.preset && <span className={styles.preset}>{q.preset}</span>}
                  </td>
                  <td>
                    <div className={styles.signals}>
                      {q.signal.blocking_sort && (
                        <span className={styles.flag} data-kind="sort">
                          <Warning size={12} weight="fill" /> blocking SORT
                        </span>
                      )}
                      {q.signal.collscan && (
                        <span className={styles.flag} data-kind="scan">
                          COLLSCAN
                        </span>
                      )}
                    </div>
                  </td>
                  <td className={styles.mono}>
                    {q.metrics.docs_examined.toLocaleString()}/{q.metrics.docs_returned} (
                    {q.signal.ratio.toLocaleString(undefined, { maximumFractionDigits: 0 })}×)
                  </td>
                  <td className={styles.mono}>{q.metrics.total_keys_examined.toLocaleString()}</td>
                  <td>{q.user.display_name}</td>
                  <td>
                    <button
                      className={styles.diagnose}
                      disabled={busy !== null}
                      onClick={() => diagnose(q.captured_id)}
                    >
                      <Stethoscope size={15} weight="bold" />
                      {busy === q.captured_id ? "Diagnosing…" : "Diagnose"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
