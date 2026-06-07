/**
 * Data layer for the dashboard (#25).
 *
 * Fetches an EvidencePack from the read API (#18, deployed at #31) and falls
 * back to the committed example pack when no API is configured or it is
 * unreachable — so the dashboard always renders something, and auto-upgrades to
 * live data the moment `API_URL` points at a real endpoint.
 *
 * Contract boundary unchanged: this module only ever produces `EvidencePack`
 * JSON; it never imports controller/ or agents/.
 */

import type { EvidencePack } from "./evidence";
import examplePack from "./example_pack.json";
import { FIXTURES } from "./fixtures";

/**
 * Where a rendered pack came from (dashboard-internal — NOT part of EvidencePack
 * v1): `live` from the read API, `fallback` from a committed visual-state
 * fixture, `simulation` from a locally-generated demo run when no backend is
 * configured. `simulation` must never be presented as `live`.
 */
export type PackSource = "live" | "fallback" | "simulation";

export interface PackResult {
  pack: EvidencePack;
  source: PackSource;
  /** Set when we fell back; explains why (shown subtly in the UI footer). */
  notice?: string;
}

const EXAMPLE = examplePack as unknown as EvidencePack;

/** The configured read API base, or null when unset. */
export function apiBaseUrl(): string | null {
  // loadPack runs server-side (the page is server-rendered), so prefer the runtime
  // API_URL — NEXT_PUBLIC_API_URL is inlined at build time and would be undefined in a
  // container built before env is set. NEXT_PUBLIC stays as a build-time/static fallback.
  const raw = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL)?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

/**
 * Resolve which run to show: explicit arg > PACK_ID (runtime) > NEXT_PUBLIC_PACK_ID
 * (build-time) > the live demo pack. The fallback to the bundled example happens in
 * loadPack only when no API is configured or the fetch fails.
 */
export function resolveRunId(explicit?: string): string {
  return (
    explicit?.trim() ||
    process.env.PACK_ID?.trim() ||
    process.env.NEXT_PUBLIC_PACK_ID?.trim() ||
    "demo-001"
  );
}

export interface PackListResult {
  packs: EvidencePack[];
  source: PackSource;
  notice?: string;
}

/**
 * List all packs via the existing GET /packs route (read-only — no new endpoint).
 * Never throws: on any failure it falls back to the single bundled example so
 * Overview/History always render something honest.
 */
export async function loadPacks(): Promise<PackListResult> {
  const base = apiBaseUrl();
  if (!base) {
    return {
      packs: FIXTURES,
      source: "fallback",
      notice:
        "No API configured (API_URL unset) — showing local fixtures for every operator state (not live data).",
    };
  }
  try {
    const res = await fetch(`${base}/packs`, {
      cache: "no-store",
      headers: { accept: "application/json" },
    });
    if (!res.ok) {
      return {
        packs: [EXAMPLE],
        source: "fallback",
        notice: `Read API returned ${res.status} — showing the bundled example.`,
      };
    }
    const packs = (await res.json()) as EvidencePack[];
    if (!Array.isArray(packs) || packs.length === 0) {
      return { packs: [], source: "live" };
    }
    return { packs, source: "live" };
  } catch {
    return {
      packs: [EXAMPLE],
      source: "fallback",
      notice: "Read API unreachable — showing the bundled example pack.",
    };
  }
}

/**
 * Load a pack. Never throws — on any failure it returns the example pack with a
 * `fallback` source and a human-readable notice, so the page can always render.
 */
export async function loadPack(runId?: string): Promise<PackResult> {
  const base = apiBaseUrl();
  const id = resolveRunId(runId);

  if (!base) {
    const fixture = FIXTURES.find((p) => p.run_id === id);
    // A resolved "sim-"-prefixed fixture is a locally-generated demo run: label
    // it "simulation" (never "live"/"fallback") so the operator can't mistake it.
    if (fixture && fixture.run_id.startsWith("sim-")) {
      return {
        pack: fixture,
        source: "simulation",
        notice: "Local simulation — generated on the dashboard, not a live run.",
      };
    }
    return {
      pack: fixture ?? EXAMPLE,
      source: "fallback",
      notice: fixture
        ? `No API configured (API_URL unset) — showing local fixture "${id}" (not live data).`
        : "No API configured (API_URL unset) — showing the bundled example pack.",
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
