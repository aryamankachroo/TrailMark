"use client";

import * as React from "react";
import { FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ReportGeneratorPanel } from "@/components/reports/ReportGeneratorPanel";

export default function ReportsPage() {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="px-8 py-6">
      <header className="mb-5">
        <h1 className="font-display text-xl tracking-wide text-gold">Examination Reports</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Regulation-formatted evidence packages generated from the immutable record.
        </p>
      </header>
      <div className="panel max-w-2xl p-6">
        <div className="flex items-start gap-4">
          <FileText className="mt-0.5 h-5 w-5 shrink-0 text-gold" />
          <div className="flex-1">
            <h2 className="text-sm text-ink">SEC Rule 17a-4 — Recordkeeping Attestation</h2>
            <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">
              Certifies WORM storage configuration, entry counts by risk tier, chain
              integrity verification results, and sample entries for the reporting
              period — signed by the TrailMark platform key and formatted as an
              examination response.
            </p>
            <Button className="mt-4" onClick={() => setOpen(true)}>
              Generate Report
            </Button>
          </div>
        </div>
      </div>
      <ReportGeneratorPanel open={open} onOpenChange={setOpen} />
    </div>
  );
}
