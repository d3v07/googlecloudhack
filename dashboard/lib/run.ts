/**
 * "Ask the agent" trigger (#37).
 *
 * Kicks off a live diagnosis by POSTing to the same-origin /api/run proxy (which
 * holds RUN_API_TOKEN server-side and forwards to the read API's gated /run).
 * The backend /run is synchronous — it returns the full EvidencePack (status
 * "diagnosed") — so no polling is needed; just show a spinner while it runs.
 */

import type { EvidencePack } from "./evidence";

export interface RunResult {
  ok: boolean;
  pack?: EvidencePack;
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

    const pack = (await res.json()) as EvidencePack;
    return { ok: true, pack };
  } catch {
    return { ok: false, error: "network", message: "Run API unreachable." };
  }
}
