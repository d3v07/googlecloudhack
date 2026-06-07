/**
 * Server-only proxy for the DBRE "Diagnose" action. Forwards a captured_query_id to the read
 * API's POST /run with BOTH the write token (RUN_API_TOKEN, server-only) and the DBRE session
 * bearer (from the httpOnly cookie). The backend loads the captured query and runs the existing
 * diagnose pipeline on it. Returns the DIAGNOSED pack (with its run_id).
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
  const apiToken = process.env.RUN_API_TOKEN;
  if (!base || !apiToken) {
    return NextResponse.json({ error: "diagnose_unconfigured" }, { status: 503 });
  }
  const sessionToken = await getSessionToken();
  if (!sessionToken) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  let capturedId: string;
  try {
    const parsed = (await req.json()) as { captured_query_id?: string };
    if (!parsed.captured_query_id) throw new Error("missing captured_query_id");
    capturedId = parsed.captured_query_id;
  } catch {
    return NextResponse.json(
      { error: "bad_request", message: "Expected { captured_query_id }." },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(`${base}/run`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-token": apiToken,
        authorization: `Bearer ${sessionToken}`,
      },
      body: JSON.stringify({ captured_query_id: capturedId }),
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unreachable" }, { status: 502 });
  }
}
