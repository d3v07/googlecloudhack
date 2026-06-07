/**
 * "Ask the agent" trigger (#37).
 *
 * Kicks off a live diagnosis by POSTing to the same-origin /api/run proxy (which
 * holds RUN_API_TOKEN server-side and forwards to the read API's gated /run).
 * The backend /run is synchronous — it returns the full EvidencePack (status
 * "diagnosed") — so no polling is needed; just show a spinner while it runs.
 *
 * When no backend is configured the proxy returns a locally-generated pack with
 * `simulated: true` (HTTP 200). We surface that flag so the UI can label the run
 * a SIMULATION instead of claiming it is live.
 */

import type { EvidencePack } from "./evidence";

export interface RunResult {
  ok: boolean;
  pack?: EvidencePack;
  /** True when the proxy returned a locally-generated (non-live) pack. */
  simulated?: boolean;
  error?: "no_api" | "server" | "network";
  message?: string;
}

/** Trigger the preset Denver/ESR demo run. Never throws. */
export async function askTheAgent(): Promise<RunResult> {
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: "{}",
    });

    if (res.status === 503) {
      return { ok: false, error: "no_api", message: "No run API configured." };
    }
    if (!res.ok) {
      return { ok: false, error: "server", message: `Run API returned ${res.status}.` };
    }

    // The proxy returns a bare EvidencePack; the no-backend path adds a sibling
    // `simulated: true`. Read the flag, then treat the rest as the pack.
    const body = (await res.json()) as EvidencePack & { simulated?: boolean };
    const simulated = body.simulated === true;
    return { ok: true, pack: body, simulated };
  } catch {
    return { ok: false, error: "network", message: "Run API unreachable." };
  }
}
