import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { 
  AlertTriangle, 
  FileWarning, 
  TrendingDown, 
  ShieldAlert, 
  Clock, 
  ChevronRight,
  ExternalLink,
  X
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useProject } from "@/components/context/ProjectContext";

export default function ExecutiveRiskRibbon({ onSelectPo }) {
  const { selectedProjectId } = useProject();
  const [activeRiskCategory, setActiveRiskCategory] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ["executive-risk-summary", selectedProjectId || "all"],
    queryFn: async () => {
      const res = await fetch(
        `/api/v1/executive/risk-summary?project_id=${encodeURIComponent(selectedProjectId || "all")}`
      );
      if (!res.ok) throw new Error("Failed to load risk summary");
      return res.json();
    },
    refetchInterval: 15000,
  });

  const counts = data?.counts || {
    overdue_docs: 0,
    missing_itp: 0,
    fab_variance: 0,
    escalated_rail: 0,
    ld_risks: 0,
    total_alerts: 0,
  };

  const alerts = data?.alerts || {};

  const riskTiles = [
    {
      id: "missing_itp",
      label: "Missing Code 1/2 ITP",
      sub: "Milestones lacking approved inspection plan",
      count: counts.missing_itp,
      icon: FileWarning,
      color: "border-red-200 bg-red-50/80 hover:bg-red-100 text-red-900",
      badgeColor: "bg-red-600 text-white",
      dot: "bg-red-500",
    },
    {
      id: "fab_variance",
      label: "Fabrication Variance (>10%)",
      sub: "Shop progress slip (Vendor vs Field Expeditor)",
      count: counts.fab_variance,
      icon: TrendingDown,
      color: "border-amber-200 bg-amber-50/80 hover:bg-amber-100 text-amber-900",
      badgeColor: "bg-amber-600 text-white",
      dot: "bg-amber-500",
    },
    {
      id: "overdue_docs",
      label: "Overdue EDMS Reviews",
      sub: "VDRL documents past review SLA",
      count: counts.overdue_docs,
      icon: Clock,
      color: "border-orange-200 bg-orange-50/80 hover:bg-orange-100 text-orange-900",
      badgeColor: "bg-orange-600 text-white",
      dot: "bg-orange-500",
    },
    {
      id: "escalated_rail",
      label: "Escalated RAIL Actions",
      sub: "Tier 2/3 critical quality & schedule bottlenecks",
      count: counts.escalated_rail,
      icon: ShieldAlert,
      color: "border-purple-200 bg-purple-50/80 hover:bg-purple-100 text-purple-900",
      badgeColor: "bg-purple-600 text-white",
      dot: "bg-purple-500",
    },
    {
      id: "ld_risks",
      label: "Liquidated Damages (LD) Risk",
      sub: "Late lots exceeding contractual grace period",
      count: counts.ld_risks,
      icon: AlertTriangle,
      color: "border-rose-200 bg-rose-50/80 hover:bg-rose-100 text-rose-900",
      badgeColor: "bg-rose-600 text-white",
      dot: "bg-rose-500",
    },
  ];

  const getDialogDetails = () => {
    switch (activeRiskCategory) {
      case "missing_itp":
        return {
          title: "Upcoming Milestones Missing Code 1 / Code 2 Approved ITP",
          description: "Contractual quality gate: fabrication witness/hold tests cannot proceed without approved ITP.",
          items: alerts.missing_itp || [],
        };
      case "fab_variance":
        return {
          title: "Fabrication Variance Discrepancies (>10% Shop Slip)",
          description: "Variance detected between vendor-claimed progress and field expeditor physical surveillance audit.",
          items: alerts.fab_variance || [],
        };
      case "overdue_docs":
        return {
          title: "Overdue VDRL / SDRL Document Submissions",
          description: "Documents past planned contractual submission date or returned under Code 3 (Revise & Resubmit).",
          items: alerts.overdue_docs || [],
        };
      case "escalated_rail":
        return {
          title: "Escalated Tier 2 & Tier 3 RAIL Action Items",
          description: "Inspection-triggered NCRs, Holds, or Punches requiring Project Expediting Manager (PExM) escalation.",
          items: alerts.escalated_rail || [],
        };
      case "ld_risks":
        return {
          title: "Delivery Lots under Liquidated Damages (LD) Exposure",
          description: "Orders projecting delivery past the contractual delivery date without approved Extension of Time (EOT).",
          items: alerts.ld_risks || [],
        };
      default:
        return { title: "", description: "", items: [] };
    }
  };

  const dialogDetails = getDialogDetails();

  return (
    <>
      {/* Dynamic Alert Banner Strip */}
      <div className="bg-white rounded-xl border border-gray-200/90 shadow-sm p-3">
        <div className="flex items-center justify-between pb-2 mb-2 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-700">
              Procurement &amp; Inspection Risk Matrix — Traffic Light Early Warning
            </h3>
          </div>
          <span className="text-[11px] font-semibold text-gray-500">
            Total Open Risk Flags: <strong className="text-gray-900">{counts.total_alerts}</strong>
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5">
          {riskTiles.map((tile) => (
            <button
              key={tile.id}
              type="button"
              onClick={() => setActiveRiskCategory(tile.id)}
              className={`flex flex-col text-left p-2.5 rounded-lg border transition-all cursor-pointer relative overflow-hidden ${tile.color} shadow-xs hover:shadow-sm`}
            >
              <div className="flex items-center justify-between mb-1">
                <tile.icon className="w-4 h-4 opacity-80" />
                <Badge className={`${tile.badgeColor} text-[10px] px-1.5 py-0 h-4 min-w-[20px] font-bold flex items-center justify-center`}>
                  {isLoading ? "..." : tile.count}
                </Badge>
              </div>
              <p className="text-xs font-bold leading-tight">{tile.label}</p>
              <p className="text-[10px] opacity-75 line-clamp-1 mt-0.5">{tile.sub}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Drill-down Detail Dialog */}
      <Dialog open={!!activeRiskCategory} onOpenChange={() => setActiveRiskCategory(null)}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm md:text-base font-bold text-gray-900">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              <span>{dialogDetails.title}</span>
            </DialogTitle>
          </DialogHeader>

          <p className="text-xs text-gray-600 bg-gray-50 p-2.5 rounded-lg border border-gray-200">
            {dialogDetails.description}
          </p>

          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-100 text-xs">
                  <TableHead className="font-semibold">PO Number</TableHead>
                  <TableHead className="font-semibold">Supplier / Package</TableHead>
                  <TableHead className="font-semibold">Details / Variance</TableHead>
                  <TableHead className="font-semibold text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dialogDetails.items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center py-6 text-xs text-gray-500">
                      ✓ No active risks in this category. All criteria satisfied.
                    </TableCell>
                  </TableRow>
                ) : (
                  dialogDetails.items.map((item, idx) => (
                    <TableRow key={idx} className="hover:bg-gray-50 text-xs">
                      <TableCell className="font-mono font-bold text-indigo-700">
                        {item.po}
                      </TableCell>
                      <TableCell className="font-medium text-gray-900">
                        {item.supplier || item.title || item.doc_no || "-"}
                      </TableCell>
                      <TableCell>
                        {item.variance !== undefined ? (
                          <div className="space-y-0.5">
                            <span className="text-amber-800 font-semibold block">
                              Vendor: {item.claimed}% vs Field: {item.audited}%
                            </span>
                            <span className="text-[10px] text-red-600 font-bold block">
                              Slip Variance: +{item.variance.toFixed(1)}%
                            </span>
                          </div>
                        ) : item.warning ? (
                          <span className="text-red-700 font-medium">{item.warning}</span>
                        ) : item.code ? (
                          <span className="text-orange-700 font-mono font-semibold">{item.code} — {item.doc_no}</span>
                        ) : item.desc ? (
                          <span className="text-purple-700 font-medium">Tier {item.tier}: {item.desc}</span>
                        ) : (
                          <span className="text-rose-700 font-medium">Delivery: {item.contractual_date}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="xs"
                          variant="outline"
                          onClick={() => {
                            if (onSelectPo) onSelectPo(item.po);
                            setActiveRiskCategory(null);
                          }}
                          className="text-indigo-600 border-indigo-200 hover:bg-indigo-50 text-[11px] h-7"
                        >
                          View PO
                          <ChevronRight className="w-3 h-3 ml-0.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

