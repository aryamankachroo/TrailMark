"use client";

import * as React from "react";

import { ApiError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

const REPORT_TYPES = [
  { value: "sec-17a4", label: "SEC Rule 17a-4 — Immutable Recordkeeping Attestation" },
];

export function ReportGeneratorPanel({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [reportType, setReportType] = React.useState("sec-17a4");
  const [periodFrom, setPeriodFrom] = React.useState("");
  const [periodTo, setPeriodTo] = React.useState("");
  const [generating, setGenerating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function generate() {
    if (!periodFrom || !periodTo) {
      setError("A reporting period is required.");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const resp = await fetch(`/api/v1/reports/${reportType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          period_from: new Date(periodFrom).toISOString(),
          period_to: new Date(`${periodTo}T23:59:59.999Z`).toISOString(),
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        throw new ApiError(
          resp.status,
          body?.error?.code ?? "error",
          body?.error?.message ?? `Report generation failed (${resp.status})`,
        );
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `trailmark-${reportType}-${periodFrom}-to-${periodTo}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      onOpenChange(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setError("The report engine ships in an upcoming phase of the build.");
      } else {
        setError(e instanceof Error ? e.message : "Report generation failed.");
      }
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Generate Examination Report</DialogTitle>
        <DialogDescription>
          Regulation-formatted evidence produced directly from the immutable record,
          with cryptographic attestation by the TrailMark platform key.
        </DialogDescription>

        <div className="mt-4 space-y-3">
          <div>
            <div className="docket-label mb-1.5">Report Type</div>
            <Select
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="w-full"
            >
              {REPORT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="docket-label mb-1.5">Period From</div>
              <Input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
            </div>
            <div>
              <div className="docket-label mb-1.5">Period To</div>
              <Input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
            </div>
          </div>
        </div>

        {error && <p className="mt-3 text-sm text-verdict-red">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={generating}>
            Cancel
          </Button>
          <Button variant="primary" onClick={generate} disabled={generating}>
            {generating ? "Generating…" : "Generate PDF"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
