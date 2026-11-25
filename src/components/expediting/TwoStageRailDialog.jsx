import React, { useState } from "react";
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogFooter 
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ShieldCheck, CheckCircle2, Clock, ShieldAlert, ArrowRight } from "lucide-react";
import { toast } from "sonner";

export default function TwoStageRailDialog({ open, onOpenChange, po, item, userRole, onSuccess }) {
  const [stage, setStage] = useState("stage1"); // 'stage1' (Inspector) or 'stage2' (Expeditor)
  const [techRemarks, setTechRemarks] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [recoveryImpact, setRecoveryImpact] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isInspectorOrQC = userRole?.includes("inspector") || userRole?.includes("qc");
  const isExpeditorOrMgr = userRole?.includes("expeditor") || userRole?.includes("admin");

  const handleStage1TechnicalClose = async () => {
    if (!techRemarks.trim()) {
      toast.error("Inspector technical rework verification remarks are mandatory.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/v1/rail/technical-close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          po: po || "2820-2025-74259-A",
          item_id: item?.id || item?.no || "NCR-01",
          inspector: "Inspector / QC Lead",
          remarks: techRemarks,
          evidence_url: evidenceUrl,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Technical closeout failed");

      toast.success("Stage 1 Technical Closeout completed! Handed off to Expeditor for Stage 2.");
      if (onSuccess) onSuccess(data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.message || "Error submitting technical closeout");
    } finally {
      setSubmitting(false);
    }
  };

  const handleStage2ScheduleClose = async () => {
    if (!recoveryImpact.trim()) {
      toast.error("Expeditor schedule recovery impact statement is mandatory.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/v1/rail/schedule-close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          po: po || "2820-2025-74259-A",
          item_id: item?.id || item?.no || "NCR-01",
          expeditor: "Package Expeditor",
          recovery_impact: recoveryImpact,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Schedule closeout failed");

      toast.success("Stage 2 Schedule Closeout confirmed! RAIL item is now fully Closed.");
      if (onSuccess) onSuccess(data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.message || "Error submitting schedule closeout");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base md:text-lg font-bold text-gray-900">
            <ShieldAlert className="w-5 h-5 text-indigo-600" />
            <span>Two-Stage Verification — RAIL Quality Closeout</span>
          </DialogTitle>
        </DialogHeader>

        {/* Workflow Progression Stepper */}
        <div className="flex items-center justify-between p-3 bg-gray-50 rounded-xl border border-gray-200">
          <div className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
              item?.technical_status === "APPROVED" 
                ? "bg-emerald-600 text-white" 
                : stage === "stage1" ? "bg-indigo-600 text-white" : "bg-gray-200 text-gray-600"
            }`}>
              1
            </div>
            <div>
              <p className="text-xs font-bold text-gray-900">Stage 1: Technical Sign-off</p>
              <p className="text-[10px] text-gray-500">Inspector confirms rework / NDT</p>
            </div>
          </div>

          <ArrowRight className="w-4 h-4 text-gray-400" />

          <div className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
              item?.commercial_status === "CLOSED" 
                ? "bg-emerald-600 text-white" 
                : stage === "stage2" ? "bg-indigo-600 text-white" : "bg-gray-200 text-gray-600"
            }`}>
              2
            </div>
            <div>
              <p className="text-xs font-bold text-gray-900">Stage 2: Schedule Closeout</p>
              <p className="text-[10px] text-gray-500">Expeditor verifies float &amp; delivery</p>
            </div>
          </div>
        </div>

        {/* Tab Toggle for testing both stages */}
        <div className="flex gap-2 border-b border-gray-200 pb-2">
          <button
            type="button"
            onClick={() => setStage("stage1")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              stage === "stage1"
                ? "bg-indigo-600 text-white shadow-xs"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            Stage 1: Inspector Technical Approval
          </button>
          <button
            type="button"
            onClick={() => setStage("stage2")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              stage === "stage2"
                ? "bg-indigo-600 text-white shadow-xs"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            Stage 2: Expeditor Schedule Closeout
          </button>
        </div>

        {stage === "stage1" ? (
          <div className="space-y-3">
            <div className="bg-blue-50/70 p-3 rounded-xl border border-blue-100 text-xs text-blue-900">
              <p className="font-semibold mb-1">Inspector Quality Verification Gate</p>
              <p className="text-blue-800/80">
                Verify physical rework, re-inspection findings, and test reports. Approving this stage transitions the item to <strong>Pending Expeditor Verification</strong>.
              </p>
            </div>

            <div>
              <Label className="text-xs font-semibold">Inspector Findings &amp; Technical Closeout Remarks *</Label>
              <Textarea
                rows={3}
                value={techRemarks}
                onChange={(e) => setTechRemarks(e.target.value)}
                placeholder="Describe physical rework verification, test certificate references, and dimensional sign-off..."
                className="text-xs mt-1"
              />
            </div>

            <div>
              <Label className="text-xs font-semibold">Evidence / Photo Attachment URL (Optional)</Label>
              <Input
                value={evidenceUrl}
                onChange={(e) => setEvidenceUrl(e.target.value)}
                placeholder="https://... or /uploads/ncr_rework_proof.pdf"
                className="text-xs mt-1 font-mono"
              />
            </div>

            <Button
              onClick={handleStage1TechnicalClose}
              disabled={submitting}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold h-9"
            >
              {submitting ? "Signing Off..." : "Approve Technical Stage 1 & Hand Off to Expeditor"}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="bg-emerald-50/70 p-3 rounded-xl border border-emerald-100 text-xs text-emerald-900">
              <p className="font-semibold mb-1">Expeditor Schedule Recovery Gate</p>
              <p className="text-emerald-800/80">
                Confirm whether the resolved defect caused a manufacturing schedule delay, consumed float, or requires a revised shipping lot.
              </p>
            </div>

            <div>
              <Label className="text-xs font-semibold">Schedule Recovery Impact Statement *</Label>
              <Textarea
                rows={3}
                value={recoveryImpact}
                onChange={(e) => setRecoveryImpact(e.target.value)}
                placeholder="e.g. Rework completed within 3 days; absorbed by 5-day float. Contractual delivery lot remains unimpacted."
                className="text-xs mt-1"
              />
            </div>

            <Button
              onClick={handleStage2ScheduleClose}
              disabled={submitting}
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold h-9"
            >
              {submitting ? "Confirming..." : "Confirm Stage 2 Schedule Recovery & Fully Close Action"}
            </Button>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

