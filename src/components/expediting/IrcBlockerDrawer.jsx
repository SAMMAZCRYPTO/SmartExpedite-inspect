import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { 
  ShieldAlert, 
  AlertTriangle, 
  Clock, 
  CheckCircle2, 
  FileCheck2, 
  RefreshCw, 
  ExternalLink,
  Info
} from "lucide-react";
import { toast } from "sonner";
import { useProject } from "@/components/context/ProjectContext";

export default function IrcBlockerDrawer({ open, onOpenChange, onSelectPo }) {
  const { selectedProjectId } = useProject();
  const [loading, setLoading] = useState(false);
  const [blockers, setBlockers] = useState([]);

  const fetchBlockers = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/v1/executive/irc-blockers?project_id=${encodeURIComponent(selectedProjectId || "all")}`
      );
      const json = await res.json();
      if (json.ok) {
        setBlockers(json.blockers || []);
      } else {
        setBlockers([]);
      }
    } catch (e) {
      console.error("Failed to fetch IRC blockers", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setBlockers([]);
    if (open) {
      fetchBlockers();
    }
  }, [open, selectedProjectId]);

  const getSeverityStyle = (sev) => {
    switch (sev) {
      case "CRITICAL":
        return "bg-rose-50 text-rose-700 border-rose-200";
      case "HIGH":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "MEDIUM":
        return "bg-blue-50 text-blue-700 border-blue-200";
      default:
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col p-6 overflow-hidden">
        <DialogHeader className="pb-3 border-b border-gray-100 shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600">
                <ShieldAlert className="w-4 h-4" />
              </div>
              <div>
                <DialogTitle className="text-base font-bold text-gray-900">
                  Real-Time IRC Release Blocker Diagnostics
                </DialogTitle>
                <DialogDescription className="text-xs text-gray-500">
                  Live diagnostic view of completed inspections awaiting statutory release certificates.
                </DialogDescription>
              </div>
            </div>
            <Button
              variant="outline"
              size="xs"
              onClick={fetchBlockers}
              disabled={loading}
              className="text-xs h-7"
            >
              <RefreshCw className={`w-3 h-3 mr-1 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-3 space-y-3">
          {loading ? (
            <div className="py-12 text-center text-gray-500 text-xs">
              Evaluating quality gates and finding statuses across all active orders...
            </div>
          ) : blockers.length === 0 ? (
            <div className="py-12 text-center text-gray-500 text-xs flex flex-col items-center">
              <CheckCircle2 className="w-8 h-8 text-emerald-500 mb-2" />
              <p className="font-semibold text-gray-700">No Blocked Inspection Releases</p>
              <p className="text-gray-400">All completed inspections have either been released or have clean gates.</p>
            </div>
          ) : (
            blockers.map((b, idx) => (
              <div
                key={idx}
                className="p-3.5 rounded-xl border border-gray-200/90 bg-white hover:border-gray-300 transition-all shadow-xs space-y-2"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-xs text-gray-900">
                        PO #{b.po}
                      </span>
                      <span className="text-gray-400 text-xs">•</span>
                      <span className="text-xs font-semibold text-gray-600">
                        {b.supplier}
                      </span>
                      <span className="text-gray-400 text-xs">•</span>
                      <span className="text-[11px] font-mono text-gray-500">
                        {b.notification_number}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 pt-0.5">
                      <span
                        className={`inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-md border ${getSeverityStyle(
                          b.severity
                        )}`}
                      >
                        {b.status_badge}
                      </span>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <Badge variant="outline" className="text-[11px] font-semibold text-gray-600 bg-gray-50">
                      <Clock className="w-3 h-3 mr-1 text-gray-500" />
                      {b.sla_timer}
                    </Badge>
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-gray-50/80 border border-gray-100 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5 text-gray-700">
                    <Info className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                    <span><b>Required Next Step:</b> {b.action_required}</span>
                  </div>

                  {onSelectPo && (
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => {
                        onSelectPo(b.po);
                        onOpenChange(false);
                      }}
                      className="text-xs text-indigo-600 hover:text-indigo-700 h-6 px-2 font-medium"
                    >
                      View PO <ExternalLink className="w-3 h-3 ml-1" />
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

