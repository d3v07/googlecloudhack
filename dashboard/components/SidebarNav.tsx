"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Database,
  SquaresFour,
  MagnifyingGlass,
  TreeStructure,
  ClockCounterClockwise,
  ShieldCheck,
  List,
  X,
} from "@phosphor-icons/react/dist/ssr";
import styles from "./SidebarNav.module.css";

const NAV = [
  { href: "/", label: "Overview", icon: SquaresFour },
  { href: "/run-review", label: "Run Review", icon: MagnifyingGlass },
  { href: "/system-map", label: "System Map", icon: TreeStructure },
  { href: "/history", label: "History & Compare", icon: ClockCounterClockwise },
  { href: "/audit", label: "Audit & Compliance", icon: ShieldCheck },
] as const;

export function SidebarNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const hamburgerRef = useRef<HTMLButtonElement>(null);
  const firstLinkRef = useRef<HTMLAnchorElement>(null);
  const wasOpen = useRef(false);

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    // /runs/<id> is the canonical run view; keep "Run Review" active there too.
    if (href === "/run-review") return pathname.startsWith("/run-review") || pathname.startsWith("/runs");
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

  return (
    <>
      {/* mobile top bar with hamburger */}
      <div className={styles.mobileBar}>
        <div className={styles.mobileBrand}>
          <Database weight="fill" size={20} className={styles.brandIcon} />
          <span className={styles.brandName}>DBRE Console</span>
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
          <Database weight="fill" size={22} className={styles.brandIcon} />
          <div className={styles.brandText}>
            <span className={styles.brandName}>DBRE Console</span>
            <span className={styles.brandTag}>operator control plane</span>
          </div>
        </div>

        <nav className={styles.nav}>
          {NAV.map(({ href, label, icon: Icon }, i) => (
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

        <div className={styles.footer}>
          <span className={styles.footerLine}>Evidence-Driven DBRE Agent</span>
          <span className={styles.footerDim}>reads EvidencePack v1 · mutation backend-only</span>
        </div>
      </aside>

      {open && <div className={styles.scrim} onClick={() => setOpen(false)} aria-hidden />}
    </>
  );
}
