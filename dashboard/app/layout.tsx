import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { SidebarNav } from "@/components/SidebarNav";
import { getSession } from "@/lib/auth";
import layout from "./layout.module.css";

// Slate kit typography: Geist + Geist Mono — single-family discipline (see globals.css).
const sans = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sift — Evidence-Driven DBRE",
  description:
    "Operator console for the Evidence-Driven DBRE agent: run workloads, triage slow queries, and approve the index fix.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getSession();
  return (
    <html lang="en" className={`${mono.variable} ${sans.variable}`}>
      <body>
        {session ? (
          <div className={layout.shell}>
            <SidebarNav session={session} />
            <div className={layout.content}>{children}</div>
          </div>
        ) : (
          <div className={layout.bare}>{children}</div>
        )}
      </body>
    </html>
  );
}
