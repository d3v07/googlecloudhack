"use client";

import { useState } from "react";
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

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <>
      {/* mobile top bar with hamburger */}
      <div className={styles.mobileBar}>
        <div className={styles.mobileBrand}>
          <Database weight="fill" size={20} className={styles.brandIcon} />
          <span className={styles.brandName}>DBRE Console</span>
        </div>
        <button
          className={styles.hamburger}
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Close navigation" : "Open navigation"}
          aria-expanded={open}
        >
          {open ? <X size={22} /> : <List size={22} />}
        </button>
      </div>

      <aside className={styles.sidebar} data-open={open}>
        <div className={styles.brand}>
          <Database weight="fill" size={22} className={styles.brandIcon} />
          <div className={styles.brandText}>
            <span className={styles.brandName}>DBRE Console</span>
            <span className={styles.brandTag}>operator control plane</span>
          </div>
        </div>

        <nav className={styles.nav}>
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={styles.link}
              data-active={isActive(href)}
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
