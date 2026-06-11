import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, verifyToken, roleHome, isUserArea } from "@/lib/session";

/**
 * Page-level gate. Unauthenticated visitors go to /login; a user persona is confined to the
 * workload console and the DBRE persona to everything else. The read API re-verifies the
 * bearer on every data call, so this is UX routing — the backend stays the security authority.
 */
export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const session = token ? await verifyToken(token) : null;

  if (pathname === "/guest") {
    return NextResponse.next();
  }

  if (pathname === "/login") {
    return session
      ? NextResponse.redirect(new URL(roleHome(session.role), req.url))
      : NextResponse.next();
  }

  if (!session) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  if (session.role === "user" && !isUserArea(pathname)) {
    return NextResponse.redirect(new URL("/console", req.url));
  }
  if (session.role === "dbre" && isUserArea(pathname)) {
    return NextResponse.redirect(new URL("/dbre", req.url));
  }
  return NextResponse.next();
}

export const config = {
  // Run on every page; skip API routes, Next internals, and static files.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
