/**
 * Server-component session accessor. Reads the httpOnly cookie via next/headers and verifies
 * it with the edge-safe helper. Use in server components / route handlers (Node runtime).
 */

import { cookies } from "next/headers";

import { SESSION_COOKIE, verifyToken, type Session } from "./session";

export async function getSession(): Promise<Session | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return token ? verifyToken(token) : null;
}

/** The raw token, for server-side proxies that forward it as a bearer to the read API. */
export async function getSessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}
