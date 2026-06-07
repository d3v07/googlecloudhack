import { getSessionToken } from "@/lib/auth";
import { SlowQueryQueue, type SlowQuery } from "@/components/SlowQueryQueue";

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

export default async function DbreQueuePage() {
  const { rows, error } = await loadSlowQueries();
  return <SlowQueryQueue rows={rows} error={error} />;
}
