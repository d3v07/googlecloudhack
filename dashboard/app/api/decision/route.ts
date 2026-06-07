/**
 * Server-only write proxy for POST /packs/{run_id}/decision (#37, retrofit of #26).
 *
 * Same rationale as the /run proxy: the read API gates /decision behind the shared
 * secret (backend #58), so the dashboard posts here (same-origin, no token in the
 * browser) and this route forwards with X-API-Token.
 *
 * Request body: { runId: string, payload: { decision, evidence_hash, approver?, note? } }
 */

import { NextResponse } from "next/server";

import { getSessionToken } from "@/lib/auth";

export const runtime = "nodejs";

function apiBase(): string | null {
  const raw = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL)?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

export async function POST(req: Request) {
  const base = apiBase();
  const token = process.env.RUN_API_TOKEN;
  if (!base || !token) {
    return NextResponse.json(
      { error: "no_api", message: "Decision API not configured (API_URL / RUN_API_TOKEN unset)." },
      { status: 503 },
    );
  }

  let runId: string;
  let payload: unknown;
  try {
    const parsed = (await req.json()) as { runId?: string; payload?: unknown };
    if (!parsed.runId || !parsed.payload) throw new Error("missing runId/payload");
    runId = parsed.runId;
    payload = parsed.payload;
  } catch {
    return NextResponse.json(
      { error: "bad_request", message: "Expected { runId, payload }." },
      { status: 400 },
    );
  }

  const sessionToken = await getSessionToken();
  try {
    const upstream = await fetch(`${base}/packs/${encodeURIComponent(runId)}/decision`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-token": token,
        ...(sessionToken ? { authorization: `Bearer ${sessionToken}` } : {}),
      },
      body: JSON.stringify(payload),
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: "upstream_unreachable", message: "Decision API unreachable." },
      { status: 502 },
    );
  }
}
