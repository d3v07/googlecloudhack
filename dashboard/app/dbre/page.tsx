import { getSessionToken } from "@/lib/auth";
import { SlowQueryQueue, type SlowQuery } from "@/components/SlowQueryQueue";
import { Tour, type TourStep } from "@/components/Tour";

async function loadSlowQueries(): Promise<{ rows: SlowQuery[]; error: string | null }> {
  const base = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL)?.trim();
  const token = await getSessionToken();
  if (!base || !token) return { rows: [], error: "Backend not configured." };
  try {
    const res = await fetch(`${base.replace(/\/+$/, "")}/workload/slow-queries`, {
      headers: { authorization: `Bearer ${token}`, accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) return { rows: [], error: `Read API returned ${res.status}.` };
    return { rows: (await res.json()) as SlowQuery[], error: null };
  } catch {
    return { rows: [], error: "Read API unreachable." };
  }
}

const DBRE_TOUR: TourStep[] = [
  {
    title: "The slow-query queue",
    body: "These are the actual slowest queries your users ran, ranked by explain evidence — blocking sort, collection scan, over-scan ratio — not noisy wall-clock time.",
  },
  {
    title: "Diagnose the worst one",
    body: "Click Diagnose on a row. Sift derives the ESR-correct index from the query's own equality/sort/range shape and opens an EvidencePack — no mutation yet.",
  },
  {
    title: "Review, then approve",
    body: "Check the finding and the evidence hash, then approve. The approval is bound to that exact hash: the agent only recommends — you decide what gets applied.",
  },
  {
    title: "Verification proves it",
    body: "On approve, the backend applies the index and re-explains: the blocking SORT is gone and docs-examined collapses. The pack moves to VERIFIED.",
  },
];

export default async function DbreQueuePage() {
  const { rows, error } = await loadSlowQueries();
  return (
    <>
      <SlowQueryQueue rows={rows} error={error} />
      <Tour id="dbre" title="DBRE triage" steps={DBRE_TOUR} />
    </>
  );
}
