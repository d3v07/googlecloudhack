"use client";

import { useState } from "react";
import { Play, Lightning, Warning, CheckCircle, Database } from "@phosphor-icons/react/dist/ssr";

import styles from "./WorkloadConsole.module.css";

const STORES = ["Austin", "Denver", "London", "New York", "San Diego", "Seattle"];
const METHODS = ["In store", "Online", "Phone"];
const SORT_FIELDS = [
  { value: "", label: "No sort" },
  { value: "saleDate", label: "saleDate" },
  { value: "customer.age", label: "customer.age" },
];
const NAMESPACE = "sample_supplies.sales_agent_demo";

interface Preset {
  key: string;
  label: string;
  intent: string;
}

interface CapturedSignal {
  is_slow: boolean;
  severity: string;
  ratio: number;
  blocking_sort: boolean;
  collscan: boolean;
}

interface CapturedMetrics {
  docs_examined: number;
  docs_returned: number;
  total_keys_examined: number;
  millis: number;
  stages: string[];
  has_blocking_sort: boolean;
}

interface RunResult {
  captured: {
    captured_id: string;
    preset: string | null;
    user: { display_name: string };
    query: { filter: Record<string, unknown>; sort: [string, number][]; limit: number };
    metrics: CapturedMetrics;
    signal: CapturedSignal;
  };
  preview: { storeLocation: string; saleDate: string; age: number; purchaseMethod: string }[];
}

export function WorkloadConsole({
  displayName,
  presets,
}: {
  displayName: string;
  presets: Preset[];
}) {
  const [store, setStore] = useState("");
  const [method, setMethod] = useState("");
  const [ageMin, setAgeMin] = useState("");
  const [ageMax, setAgeMax] = useState("");
  const [sortField, setSortField] = useState("saleDate");
  const [sortDir, setSortDir] = useState(-1);
  const [limit, setLimit] = useState(20);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);

  async function runQuery(payload: Record<string, unknown>) {
    setError(null);
    setRunning(true);
    setResult(null);
    try {
      const res = await fetch("/api/workload/query", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(typeof data?.detail === "string" ? data.detail : "Query failed.");
      } else {
        setResult(data as RunResult);
      }
    } catch {
      setError("Network error — please try again.");
    } finally {
      setRunning(false);
    }
  }

  function runBuilder() {
    runQuery({
      store_location: store || undefined,
      purchase_method: method || undefined,
      age_min: ageMin === "" ? undefined : Number(ageMin),
      age_max: ageMax === "" ? undefined : Number(ageMax),
      sort_field: sortField || undefined,
      sort_dir: sortDir,
      limit,
    });
  }

  const signal = result?.captured.signal;
  const metrics = result?.captured.metrics;

  return (
    <main className={styles.wrap}>
      <header className={styles.head}>
        <div>
          <h1 className={styles.title}>Workload Console</h1>
          <p className={styles.sub}>
            <Database size={14} weight="fill" /> {NAMESPACE} · queries run live and are attributed
            to <strong>{displayName}</strong>
          </p>
        </div>
      </header>

      <section className={styles.panel} aria-labelledby="presets-h">
        <h2 id="presets-h" className={styles.panelTitle}>
          <Lightning size={16} weight="fill" /> Quick workloads
        </h2>
        <div className={styles.presetGrid}>
          {presets.map((p) => (
            <button
              key={p.key}
              className={styles.preset}
              data-intent={p.intent}
              disabled={running}
              onClick={() => runQuery({ preset: p.key })}
            >
              <span className={styles.presetDot} data-intent={p.intent} aria-hidden />
              {p.label}
            </button>
          ))}
          {presets.length === 0 && (
            <p className={styles.empty}>No presets available (backend unreachable).</p>
          )}
        </div>
      </section>

      <section className={styles.panel} aria-labelledby="builder-h">
        <h2 id="builder-h" className={styles.panelTitle}>
          Build a query
        </h2>
        <div className={styles.form}>
          <label className={styles.field}>
            <span>storeLocation</span>
            <select value={store} onChange={(e) => setStore(e.target.value)}>
              <option value="">— any —</option>
              {STORES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span>purchaseMethod</span>
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="">— any —</option>
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span>customer.age ≥</span>
            <input
              type="number"
              min={16}
              max={75}
              value={ageMin}
              placeholder="min"
              onChange={(e) => setAgeMin(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span>customer.age ≤</span>
            <input
              type="number"
              min={16}
              max={75}
              value={ageMax}
              placeholder="max"
              onChange={(e) => setAgeMax(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span>sort field</span>
            <select value={sortField} onChange={(e) => setSortField(e.target.value)}>
              {SORT_FIELDS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span>sort direction</span>
            <select
              value={sortDir}
              disabled={!sortField}
              onChange={(e) => setSortDir(Number(e.target.value))}
            >
              <option value={-1}>descending</option>
              <option value={1}>ascending</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>limit</span>
            <input
              type="number"
              min={1}
              max={200}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            />
          </label>
          <button className={styles.run} disabled={running} onClick={runBuilder}>
            <Play size={16} weight="fill" />
            {running ? "Running…" : "Run query"}
          </button>
        </div>
      </section>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {result && signal && metrics && (
        <section className={styles.result} aria-live="polite">
          <div className={styles.verdict} data-severity={signal.severity}>
            {signal.blocking_sort || signal.collscan ? (
              <Warning size={20} weight="fill" />
            ) : (
              <CheckCircle size={20} weight="fill" />
            )}
            <div>
              <strong>
                {signal.blocking_sort
                  ? "Blocking in-memory SORT"
                  : signal.collscan
                    ? "Full collection scan"
                    : "Served in index order"}
              </strong>
              <span className={styles.verdictSub}>
                {signal.is_slow ? "slow" : "healthy"} · examined{" "}
                {metrics.docs_examined.toLocaleString()} docs to return {metrics.docs_returned} (
                {signal.ratio.toLocaleString(undefined, { maximumFractionDigits: 0 })}×) ·{" "}
                {metrics.millis.toFixed(0)} ms
              </span>
            </div>
          </div>

          <div className={styles.metrics}>
            <Metric label="docs examined" value={metrics.docs_examined.toLocaleString()} />
            <Metric label="docs returned" value={String(metrics.docs_returned)} />
            <Metric label="keys examined" value={metrics.total_keys_examined.toLocaleString()} />
            <div className={styles.stages}>
              {metrics.stages.map((s, i) => (
                <span key={`${s}-${i}`} className={styles.stage} data-sort={s === "SORT"}>
                  {s}
                </span>
              ))}
            </div>
          </div>

          <p className={styles.attribution}>
            Captured to the DBRE slow-query queue, attributed to{" "}
            <strong>{result.captured.user.display_name}</strong>.
          </p>

          {result.preview.length > 0 && (
            <table className={styles.preview}>
              <thead>
                <tr>
                  <th>storeLocation</th>
                  <th>customer.age</th>
                  <th>saleDate</th>
                  <th>purchaseMethod</th>
                </tr>
              </thead>
              <tbody>
                {result.preview.map((row, i) => (
                  <tr key={i}>
                    <td>{row.storeLocation}</td>
                    <td>{row.age}</td>
                    <td>{row.saleDate?.slice(0, 10)}</td>
                    <td>{row.purchaseMethod}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metric}>
      <span className={styles.metricValue}>{value}</span>
      <span className={styles.metricLabel}>{label}</span>
    </div>
  );
}
