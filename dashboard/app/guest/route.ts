/**
 * One-click guest entry for judging. Logs in server-side with the read-only demo account
 * (GUEST_USER/GUEST_PASS env), stores the issued token in the httpOnly session cookie, and
 * redirects to that role's home. The token never reaches the browser. Returns 503 if the
 * guest account is not configured so the link fails closed rather than leaking a login form.
 */

import { NextResponse } from "next/server";

import { SESSION_COOKIE, roleHome, type Role } from "@/lib/session";

export const runtime = "nodejs";

function apiBase(): string | null {
  const raw = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL)?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

export async function GET(req: Request) {
  const base = apiBase();
  const username = process.env.GUEST_USER?.trim();
  const password = process.env.GUEST_PASS;
  if (!base || !username || !password) {
    return NextResponse.json({ error: "guest_unconfigured" }, { status: 503 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    return NextResponse.json({ error: "upstream_unreachable" }, { status: 502 });
  }

  if (!upstream.ok) {
    return NextResponse.json({ error: "guest_login_failed" }, { status: 502 });
  }

  const data = (await upstream.json()) as { token: string; role: Role };
  // Behind Cloud Run, req.url is the internal 0.0.0.0:8080 address — build the redirect from
  // the forwarded host so the browser navigates to the public origin, not the container.
  const proto = req.headers.get("x-forwarded-proto") ?? "https";
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  const dest = host
    ? new URL(roleHome(data.role), `${proto}://${host}`)
    : new URL(roleHome(data.role), req.url);
  const res = NextResponse.redirect(dest);
  res.cookies.set(SESSION_COOKIE, data.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 12 * 60 * 60,
  });
  return res;
}
