import type { Metadata } from "next";
import { JetBrains_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { SidebarNav } from "@/components/SidebarNav";
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
    "Operator console for the Evidence-Driven DBRE agent: review the evidence pack and approve the index fix.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${mono.variable} ${sans.variable}`}>
      <body>
        <div className={layout.shell}>
          <SidebarNav />
          <div className={layout.content}>{children}</div>
        </div>
      </body>
    </html>
  );
}
