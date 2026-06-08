import { apiBaseUrl } from "@/lib/api";
import { getSessionToken } from "@/lib/auth";
import type { SiftMemoryResult } from "@/lib/siftMemory";

export async function loadSiftMemory(runId: string): Promise<SiftMemoryResult | null> {
  const base = apiBaseUrl();
  const token = await getSessionToken();
  if (!base || !token) return null;
  try {
    const res = await fetch(`${base}/packs/${encodeURIComponent(runId)}/memory`, {
      headers: { accept: "application/json", authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as SiftMemoryResult;
  } catch {
    return null;
  }
}
