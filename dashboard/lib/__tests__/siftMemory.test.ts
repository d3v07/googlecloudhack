import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  formatMemoryScore,
  memoryHitSummary,
  memoryHitTitle,
  normalizeSiftMemory,
} from "@/lib/siftMemory";
import type { SiftMemoryGuidance, SiftMemoryResult } from "@/lib/siftMemory";

const baseMemory = {
  run_id: "run-1",
  mutation_authority: false,
  models: { embed: "voyage-4-lite", rerank: "rerank-2.5-lite" },
};

describe("normalizeSiftMemory", () => {
  it("maps missing memory data to the not configured state", () => {
    expect(normalizeSiftMemory(undefined)).toMatchObject({
      state: "not_configured",
      label: "Not configured",
      hits: [],
    });
  });

  it("maps explicit not_configured memory data", () => {
    const memory: SiftMemoryResult = {
      ...baseMemory,
      status: "unconfigured",
      configured: false,
      guidance: [],
    };
    expect(normalizeSiftMemory(memory)).toMatchObject({
      state: "not_configured",
      query: null,
      hits: [],
    });
  });

  it("maps configured memory with no results", () => {
    const memory: SiftMemoryResult = {
      ...baseMemory,
      status: "empty",
      configured: true,
      query: "blocking sort customer age",
      guidance: [],
    };
    expect(normalizeSiftMemory(memory)).toMatchObject({
      state: "configured_no_results",
      label: "Configured · no results",
      query: "blocking sort customer age",
      hits: [],
    });
  });

  it("maps configured memory with results", () => {
    const memory: SiftMemoryResult = {
      ...baseMemory,
      status: "ok",
      configured: true,
      guidance: [
        {
          id: "mem-1",
          title: "ESR order",
          summary: "Equality, Sort, Range ordering.",
          reason: "Same blocking SORT.",
          source: "voyage",
          score: 0.92,
          tags: ["ESR"],
        },
        {
          id: "mem-2",
          title: "Rejected order",
          summary: "Prior candidate rejected because range came before sort.",
          reason: "Same shape.",
          source: "voyage",
          score: 0.75,
          tags: [],
        },
      ],
      namespace: "dbre",
      retrieved_at: "2026-06-08T14:00:00Z",
    };
    const result = normalizeSiftMemory(memory);
    expect(result).toMatchObject({
      state: "configured_with_results",
      label: "2 results",
      namespace: "dbre",
      retrievedAt: "2026-06-08T14:00:00Z",
    });
    expect(result.hits).toHaveLength(2);
  });

  it("maps failed memory retrieval", () => {
    const memory: SiftMemoryResult = {
      ...baseMemory,
      status: "failed",
      configured: true,
      guidance: [],
      message: "vector store unavailable",
    };
    expect(normalizeSiftMemory(memory)).toMatchObject({
      state: "failed",
      label: "Failed",
      error: "vector store unavailable",
    });
  });
});

describe("memory result formatting", () => {
  it("uses stable fallbacks for title and summary", () => {
    const hit = {
      id: "abc",
      title: "",
      summary: "",
      reason: "Same query shape.",
      source: "local",
      score: 0.1,
      tags: [],
    } satisfies SiftMemoryGuidance;
    expect(memoryHitTitle(hit, 0)).toBe("abc");
    expect(memoryHitSummary(hit)).toBe("Same query shape.");
  });

  it("formats normalized and raw scores", () => {
    expect(formatMemoryScore(0.847)).toBe("0.85");
    expect(formatMemoryScore(12.345)).toBe("12.3");
    expect(formatMemoryScore(undefined)).toBeNull();
  });
});

describe("voyage key never reaches the client", () => {
  // The client-shipped memory modules must never reference the Voyage key.
  // The key is read server-side only (read API), never NEXT_PUBLIC_* or browser-bound.
  const clientFiles = ["../siftMemory.ts", "../../components/SiftMemoryPanel.tsx"];
  for (const rel of clientFiles) {
    it(`${rel} references no Voyage API key`, () => {
      const src = readFileSync(new URL(rel, import.meta.url), "utf8");
      expect(src).not.toMatch(/VOYAGE_API_KEY/);
      expect(src).not.toMatch(/NEXT_PUBLIC_VOYAGE/);
    });
  }
});
