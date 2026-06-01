/**
 * Data layer for the dashboard (#25).
 *
 * Fetches an EvidencePack from the read API (#18, deployed at #31) and falls
 * back to the committed example pack when no API is configured or it is
 * unreachable — so the dashboard always renders something, and auto-upgrades to
 * live data the moment `NEXT_PUBLIC_API_URL` points at a real endpoint.
 *
 * Contract boundary unchanged: this module only ever produces `EvidencePack`
 * JSON; it never imports controller/ or agents/.
 */

import type { EvidencePack } from "./evidence";
import examplePack from "./example_pack.json";

export type PackSource = "live" | "fallback";

export interface PackResult {
  pack: EvidencePack;
  source: PackSource;
  /** Set when we fell back; explains why (shown subtly in the UI footer). */
  notice?: string;
}

const EXAMPLE = examplePack as unknown as EvidencePack;

/** The configured read API base, or null when unset. */
export function apiBaseUrl(): string | null {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

/**
 * Resolve which run to show: explicit arg > NEXT_PUBLIC_PACK_ID env > the
 * example pack's own run_id (so the fallback is self-consistent).
 */
export function resolveRunId(explicit?: string): string {
  return explicit?.trim() || process.env.NEXT_PUBLIC_PACK_ID?.trim() || EXAMPLE.run_id;
}

/**
 * Load a pack. Never throws — on any failure it returns the example pack with a
 * `fallback` source and a human-readable notice, so the page can always render.
 */
export async function loadPack(runId?: string): Promise<PackResult> {
  const base = apiBaseUrl();
  const id = resolveRunId(runId);

  if (!base) {
    return {
      pack: EXAMPLE,
      source: "fallback",
      notice: "No API configured (NEXT_PUBLIC_API_URL unset) — showing the bundled example pack.",
    };
  }

  const url = `${base}/packs/${encodeURIComponent(id)}`;
  try {
    // no-store: the pack changes as the run progresses; always read fresh.
    const res = await fetch(url, {
      cache: "no-store",
      headers: { accept: "application/json" },
    });

    if (res.status === 404) {
      return {
        pack: EXAMPLE,
        source: "fallback",
        notice: `No pack found for run "${id}" (404) — showing the bundled example.`,
      };
    }
    if (!res.ok) {
      return {
        pack: EXAMPLE,
        source: "fallback",
        notice: `Read API returned ${res.status} — showing the bundled example.`,
      };
    }

    const pack = (await res.json()) as EvidencePack;
    return { pack, source: "live" };
  } catch {
    return {
      pack: EXAMPLE,
      source: "fallback",
      notice: "Read API unreachable — showing the bundled example pack.",
    };
  }
}
