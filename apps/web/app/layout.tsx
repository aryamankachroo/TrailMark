import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "TrailMark — Immutable Recordkeeping for AI Agents",
  description:
    "Compliance-grade audit trail platform. WORM recordkeeping, chain of custody, and supervisory attestation for AI agents in financial services.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
