"use client";

import * as React from "react";

import { ApiError, createPolicyVersion } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export function PolicyUploadModal({
  open,
  onOpenChange,
  onCreated,
  defaultPolicyId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
  defaultPolicyId?: string;
}) {
  const [policyId, setPolicyId] = React.useState("");
  const [name, setName] = React.useState("");
  const [effectiveAt, setEffectiveAt] = React.useState("");
  const [content, setContent] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setPolicyId(defaultPolicyId ?? "");
      setName("");
      setEffectiveAt("");
      setContent("");
      setError(null);
    }
  }, [open, defaultPolicyId]);

  async function submit() {
    if (!policyId.trim() || !content.trim()) {
      setError("A policy identifier and policy content are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createPolicyVersion({
        policy_id: policyId.trim(),
        name: name.trim() || null,
        content,
        effective_at: effectiveAt
          ? new Date(effectiveAt).toISOString()
          : undefined,
      });
      onCreated();
      onOpenChange(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setError(
          "This exact policy content is already on the record. A new version must differ.",
        );
      } else {
        setError(e instanceof Error ? e.message : "Policy registration failed.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Register Policy Version</DialogTitle>
        <DialogDescription>
          A registered version is content-hashed and preserved in WORM storage. It becomes
          the version in force from its effective time until superseded — the basis for SEC
          206(4)-7 replay.
        </DialogDescription>

        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="docket-label mb-1.5">Policy Identifier</div>
              <Input
                value={policyId}
                onChange={(e) => setPolicyId(e.target.value)}
                placeholder="wsp_trade_supervision"
                disabled={Boolean(defaultPolicyId)}
              />
            </div>
            <div>
              <div className="docket-label mb-1.5">Effective From (optional)</div>
              <Input
                type="datetime-local"
                value={effectiveAt}
                onChange={(e) => setEffectiveAt(e.target.value)}
              />
            </div>
          </div>
          <div>
            <div className="docket-label mb-1.5">Display Name (optional)</div>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Written Supervisory Procedures — Trade Surveillance"
            />
          </div>
          <div>
            <div className="docket-label mb-1.5">Policy Content</div>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Full policy text as adopted…"
              className="min-h-[200px] font-mono text-[12px]"
            />
          </div>
        </div>

        {error && <p className="mt-3 text-sm text-verdict-red">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} disabled={submitting}>
            {submitting ? "Registering…" : "Register Version"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
