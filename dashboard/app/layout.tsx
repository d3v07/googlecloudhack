import type { Metadata } from "next";
import { JetBrains_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { SidebarNav } from "@/components/SidebarNav";
import { getSession } from "@/lib/auth";
import layout from "./layout.module.css";

// Non-default typography (see globals.css rationale).
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DBRE Console — Evidence-Driven Agent",
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
