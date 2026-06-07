/**
 * Edge-safe session helpers: verify the HS256 token the read API issued at login and map it
 * to a typed Session. No `next/headers` import here so middleware (edge runtime) can use it.
 * SESSION_SECRET is read server-side only and never reaches the browser bundle.
 */

import { jwtVerify } from "jose";

export const SESSION_COOKIE = "gcrah_session";

export type Role = "user" | "dbre";

export interface Session {
  username: string;
  displayName: string;
  role: Role;
}

function secretKey(): Uint8Array {
  const secret = process.env.SESSION_SECRET;
  if (!secret) throw new Error("SESSION_SECRET is not configured");
  return new TextEncoder().encode(secret);
}

/** Verify + decode a session token. Returns null on any tampering, expiry, or misconfig. */
export async function verifyToken(token: string): Promise<Session | null> {
  try {
    const { payload } = await jwtVerify(token, secretKey(), { algorithms: ["HS256"] });
    const role = payload.role;
    if ((role !== "user" && role !== "dbre") || typeof payload.sub !== "string") return null;
    const displayName = typeof payload.name === "string" ? payload.name : payload.sub;
    return { username: payload.sub, displayName, role };
  } catch {
    return null;
  }
}

export function roleHome(role: Role): string {
  return role === "user" ? "/console" : "/dbre";
}

/** The user-persona workload area (everything else is DBRE-only). */
export function isUserArea(pathname: string): boolean {
  return pathname === "/console" || pathname.startsWith("/console/");
}
