/**
 * Server-only login proxy. Forwards credentials to the read API's /auth/login, and on success
 * stores the issued token in an httpOnly cookie — the token never reaches the browser JS. The
 * JSON returned to the client carries only role/identity, never the token.
 */

import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/session";

export const runtime = "nodejs";

function apiBase(): string | null {
  const raw = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL)?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

export async function POST(req: Request) {
  const base = apiBase();
  if (!base) {
    return NextResponse.json({ error: "auth_unconfigured" }, { status: 503 });
  }

  const body = await req.text().catch(() => "{}");
  let upstream: Response;
  try {
    upstream = await fetch(`${base}/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body || "{}",
    });
  } catch {
    return NextResponse.json({ error: "upstream_unreachable" }, { status: 502 });
  }

  if (!upstream.ok) {
    // Pass through 401/422/503 without leaking internal detail.
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  }

  const data = (await upstream.json()) as {
    token: string;
    role: string;
    username: string;
    display_name: string;
  };

  const res = NextResponse.json({
    role: data.role,
    username: data.username,
    display_name: data.display_name,
  });
  res.cookies.set(SESSION_COOKIE, data.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 12 * 60 * 60,
  });
  return res;
}
