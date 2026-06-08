export type SiftMemoryStatus = "unconfigured" | "ok" | "empty" | "fallback" | "failed";

export interface SiftMemoryGuidance {
  id: string;
  title: string;
  summary: string;
  reason: string;
  source: "voyage" | "local";
  score: number;
  tags: string[];
}

export interface SiftMemoryResult {
  configured: boolean;
  run_id: string;
  status: SiftMemoryStatus;
  mutation_authority: boolean;
  guidance: SiftMemoryGuidance[];
  models: { embed: string; rerank: string };
  query?: string | null;
  namespace?: string | null;
  retrieved_at?: string | null;
  message?: string | null;
}

export type SiftMemoryViewState =
  | "configured_with_results"
  | "configured_no_results"
  | "not_configured"
  | "failed";

export interface SiftMemoryViewModel {
  state: SiftMemoryViewState;
  label: string;
  summary: string;
  query: string | null;
  hits: SiftMemoryGuidance[];
  error: string | null;
  namespace: string | null;
  retrievedAt: string | null;
}

function cleanHits(results: SiftMemoryGuidance[] | undefined): SiftMemoryGuidance[] {
  if (!Array.isArray(results)) return [];
  return results.filter((hit) => hit && typeof hit === "object");
}

export function normalizeSiftMemory(
  memory: SiftMemoryResult | null | undefined,
): SiftMemoryViewModel {
  const base = {
    query: memory?.query?.trim() || null,
    hits: cleanHits(memory?.guidance),
    error: memory?.message?.trim() || null,
    namespace: memory?.namespace?.trim() || null,
    retrievedAt: memory?.retrieved_at?.trim() || null,
  };

  if (memory?.status === "failed") {
    return {
      ...base,
      state: "failed",
      label: "Failed",
      summary: "Memory retrieval failed before context could be attached to this run.",
    };
  }

  if (!memory || memory.status === "unconfigured" || memory.configured === false) {
    return {
      ...base,
      hits: [],
      state: "not_configured",
      label: "Not configured",
      summary: "No Sift Memory retrieval context is attached to this EvidencePack yet.",
    };
  }

  if (base.hits.length === 0) {
    return {
      ...base,
      state: "configured_no_results",
      label: "Configured · no results",
      summary: "Sift Memory retrieval ran and returned no matching context for this query.",
    };
  }

  return {
    ...base,
    state: "configured_with_results",
    label: `${base.hits.length} result${base.hits.length === 1 ? "" : "s"}`,
    summary: "Sift Memory retrieved read-only context for this run.",
  };
}

export function memoryHitTitle(hit: SiftMemoryGuidance, index: number): string {
  return hit.title?.trim() || hit.id?.trim() || `Memory result ${index + 1}`;
}

export function memoryHitSummary(hit: SiftMemoryGuidance): string {
  return hit.summary?.trim() || hit.reason?.trim() || "No summary provided.";
}

export function formatMemoryScore(score: number | undefined): string | null {
  if (typeof score !== "number" || Number.isNaN(score)) return null;
  if (score > 1) return score.toFixed(1);
  return score.toFixed(2);
}
