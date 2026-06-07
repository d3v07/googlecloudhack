/**
 * Server-only write proxy for POST /run (#37).
 *
 * The read API gates /run behind a shared secret (backend #58). That secret must
 * never reach the browser, so the dashboard calls THIS same-origin route, which
 * holds the token in server-only env (RUN_API_TOKEN) and forwards to the read API
 * with the X-API-Token header.
 *
 * When the backend is NOT configured, this route does NOT 503 — it returns a
 * locally-generated DIAGNOSED EvidencePack (the simulation fixture) with a
 * `simulated: true` flag, so the demo still works. The token is never involved
 * on that path. The simulation is read-only: it never applies anything.
 *
 * Env (server-only — never NEXT_PUBLIC_*):
 *   API_URL          base URL of the read API
 *   RUN_API_TOKEN    shared secret for the gated write endpoints
 */

import { NextResponse } from "next/server";

import { FIXTURE_SIMULATION } from "@/lib/fixtures";

export const runtime = "nodejs";

function apiBase(): string | null {
  const raw = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL)?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

export async function POST(req: Request) {
  const base = apiBase();
  const token = process.env.RUN_API_TOKEN;
  if (!base || !token) {
    // No backend: return a locally-generated DIAGNOSED pack, flagged simulated.
    // Shape mirrors the configured passthrough (a bare EvidencePack) plus the
    // sibling `simulated` flag; the token is never touched on this path.
    return NextResponse.json({ ...FIXTURE_SIMULATION, simulated: true }, { status: 200 });
  }

  // Body is optional ({} or {"run_id":"..."}); forward whatever the client sent.
  const body = await req.text().catch(() => "{}");

  try {
    const upstream = await fetch(`${base}/run`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-token": token },
      body: body || "{}",
    });
    // Pass through status + body verbatim so the client sees the real result.
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: "upstream_unreachable", message: "Run API unreachable." },
      { status: 502 },
    );
  }
}
