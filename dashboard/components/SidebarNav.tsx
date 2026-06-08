"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  SquaresFour,
  MagnifyingGlass,
  TreeStructure,
  ClockCounterClockwise,
  ShieldCheck,
  Gauge,
  Terminal,
  SignOut,
  List,
  X,
} from "@phosphor-icons/react/dist/ssr";
import { Logo } from "@/components/Logo";
import type { Session } from "@/lib/session";
import styles from "./SidebarNav.module.css";

const DBRE_NAV = [
  { href: "/dbre", label: "Slow-Query Queue", icon: Gauge },
  { href: "/", label: "Overview", icon: SquaresFour },
  { href: "/run-review", label: "Run Review", icon: MagnifyingGlass },
  { href: "/system-map", label: "System Map", icon: TreeStructure },
  { href: "/history", label: "History & Compare", icon: ClockCounterClockwise },
  { href: "/audit", label: "Audit & Compliance", icon: ShieldCheck },
] as const;

const USER_NAV = [{ href: "/console", label: "Workload Console", icon: Terminal }] as const;

export function SidebarNav({ session }: { session: Session }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const hamburgerRef = useRef<HTMLButtonElement>(null);
  const firstLinkRef = useRef<HTMLAnchorElement>(null);
  const wasOpen = useRef(false);

  const nav = session.role === "dbre" ? DBRE_NAV : USER_NAV;

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    // /runs/<id> is the canonical run view; keep "Run Review" active there too.
    if (href === "/run-review")
      return pathname.startsWith("/run-review") || pathname.startsWith("/runs");
    return pathname.startsWith(href);
  }

  // Move focus into the drawer on open and back to the hamburger on close —
  // only on a real transition, never on the initial (closed) mount.
  useEffect(() => {
    if (open && !wasOpen.current) {
      firstLinkRef.current?.focus();
    } else if (!open && wasOpen.current) {
      hamburgerRef.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  // Escape closes the drawer.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <>
      {/* mobile top bar with hamburger */}
      <div className={styles.mobileBar}>
        <div className={styles.mobileBrand}>
          <Logo size={20} />
          <span className={styles.brandName}>Sift</span>
        </div>
        <button
          ref={hamburgerRef}
          className={styles.hamburger}
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Close navigation" : "Open navigation"}
          aria-controls="sidebar-nav"
          aria-expanded={open}
        >
          {open ? <X size={22} /> : <List size={22} />}
        </button>
      </div>

      <aside id="sidebar-nav" className={styles.sidebar} data-open={open}>
        <div className={styles.brand}>
          <Logo size={22} />
          <div className={styles.brandText}>
            <span className={styles.brandName}>Sift</span>
            <span className={styles.brandTag}>
              {session.role === "dbre" ? "operator control plane" : "workload console"}
            </span>
          </div>
        </div>

        <nav className={styles.nav}>
          {nav.map(({ href, label, icon: Icon }, i) => (
            <Link
              key={href}
              ref={i === 0 ? firstLinkRef : undefined}
              href={href}
              className={styles.link}
              data-active={isActive(href)}
              aria-current={isActive(href) ? "page" : undefined}
              onClick={() => setOpen(false)}
            >
              <Icon size={18} weight={isActive(href) ? "fill" : "regular"} />
              {label}
            </Link>
          ))}
        </nav>

        <div className={styles.identity}>
          <div className={styles.identityText}>
            <span className={styles.identityName}>{session.displayName}</span>
            <span className={styles.roleBadge} data-role={session.role}>
              {session.role === "dbre" ? "DBRE" : "user"}
            </span>
          </div>
          <button className={styles.logout} onClick={logout} aria-label="Sign out">
            <SignOut size={16} />
            Sign out
          </button>
        </div>

        <div className={styles.footer}>
          <span className={styles.footerLine}>Evidence-Driven DBRE Agent</span>
          <span className={styles.footerDim}>reads EvidencePack v1 · mutation backend-only</span>
        </div>
      </aside>

      {open && <div className={styles.scrim} onClick={() => setOpen(false)} aria-hidden />}
    </>
  );
}
