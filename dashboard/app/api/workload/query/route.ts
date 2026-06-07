/**
 * Server-only proxy for running a guided workload query. Reads the httpOnly session cookie and
 * forwards it to the read API as a bearer — the token never touches the browser. The backend
 * enforces the `user` role and attributes the capture to the authenticated identity.
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
  if (!base) {
    return NextResponse.json({ error: "workload_unconfigured" }, { status: 503 });
  }
  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  const body = await req.text().catch(() => "{}");
  try {
    const upstream = await fetch(`${base}/workload/query`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: body || "{}",
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unreachable" }, { status: 502 });
  }
}
