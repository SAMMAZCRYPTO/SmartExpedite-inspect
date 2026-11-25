import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Package,
  FileCheck2,
  AlertTriangle,
  CheckCircle2,
  MapPin,
  Tag,
  Clock,
  Scissors,
  Truck,
  ShieldAlert,
} from "lucide-react";

export default function PoExpeditingContextTab({ inspection }) {
  const poNumber = inspection?.po_number || "";

  const { data, isLoading } = useQuery({
    queryKey: ["po-expediting-context", poNumber],
    queryFn: async () => {
      if (!poNumber) return null;
      const res = await fetch(`/api/v1/po/${encodeURIComponent(poNumber)}/context`);
      if (!res.ok) throw new Error("Failed to fetch PO context");
      return res.json();
    },
    enabled: !!poNumber,
    refetchInterval: 10000,
  });

  if (isLoading) {
    return (
      <div className="py-12 text-center text-gray-500 text-sm">
        Loading live PO BOM Ledger &amp; EDMS VDRL/ITP status from SmartExpedit...
      </div>
    );
  }

  const items = data?.items || [];
  const leafItems = items.filter((i) => !i.is_split_parent);
  const docs = data?.vdrl_documents || [];
  const concerns = data?.rail_concerns || [];
  const hasApprovedItp = data?.has_approved_itp ?? false;

  const totalOrdered = leafItems.reduce((s, i) => s + (Number(i.ordered_qty) || 0), 0);
  const totalReleased = leafItems.reduce((s, i) => s + (Number(i.released_qty) || 0), 0);
  const totalShipped = leafItems.reduce((s, i) => s + (Number(i.shipped_qty) || 0), 0);
  const totalDelivered = leafItems.reduce((s, i) => s + (Number(i.delivered_qty) || 0), 0);

  const getCodeBadge = (code) => {
    const c = String(code || "").toLowerCase();
    if (c.includes("code 1")) return <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">Code 1 — Approved</Badge>;
    if (c.includes("code 2")) return <Badge className="bg-blue-100 text-blue-800 border-blue-200">Code 2 — Approved w/ Comments</Badge>;
    if (c.includes("code 3")) return <Badge className="bg-red-100 text-red-800 border-red-200">Code 3 — Revise &amp; Resubmit</Badge>;
    return <Badge className="bg-gray-100 text-gray-800">{code || "Under Review"}</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Top Quality Gate Banner for ITP Status */}
      {hasApprovedItp ? (
        <Alert className="bg-emerald-50 border-emerald-200">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          <AlertDescription className="text-emerald-900 text-xs">
            <strong>✓ EDMS Quality Gate Satisfied:</strong> Governing Inspection &amp; Test Plan (ITP) is <strong>Code 1 / Code 2 Approved</strong>. Witness/Hold inspections and IRC issuance are authorized.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert className="bg-red-50 border-red-200">
          <AlertTriangle className="h-4 w-4 text-red-600" />
          <AlertDescription className="text-red-900 text-xs">
            <strong>⚠️ EDMS Quality Gate Warning:</strong> Governing ITP for PO <strong>{poNumber}</strong> is currently missing or in <strong>Code 3 (Revise &amp; Resubmit)</strong>. Verify approved revision with the Inspection Engineer prior to releasing items.
          </AlertDescription>
        </Alert>
      )}

      {/* Unified PO Paired Ownership Roster Card (Expediting <-> Inspection Hand-in-Hand) */}
      <Card className="p-3.5 bg-indigo-50/40 border-indigo-200/80">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pb-2 border-b border-indigo-100">
          <div className="flex items-center gap-2">
            <Badge className="bg-indigo-600 text-white text-[10px]">
              {data?.project_code || "PROJECT"}
            </Badge>
            <span className="text-xs font-bold text-gray-900">
              {data?.project || "Capital Project"}
            </span>
          </div>
          <span className="text-[11px] text-indigo-700 font-semibold">
            Paired Dual-Department PO Governance Roster
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 text-xs">
          <div className="p-2 rounded-lg bg-white border border-gray-200">
            <span className="text-[10px] text-indigo-600 font-bold uppercase block">
              1. Expediting Manager
            </span>
            <span className="font-bold text-gray-900 block truncate">
              {data?.roster?.expediting_manager_name || data?.expediting_manager || "Unassigned"}
            </span>
            <span className="text-[10px] text-gray-500 block truncate">
              {data?.roster?.expediting_manager_email || ""}
            </span>
          </div>
          <div className="p-2 rounded-lg bg-white border border-indigo-200">
            <span className="text-[10px] text-indigo-700 font-bold uppercase block">
              2. Package Expeditor
            </span>
            <span className="font-bold text-indigo-900 block truncate">
              {data?.roster?.assigned_expeditor_name || data?.expeditor || "Unassigned"}
            </span>
            <span className="text-[10px] text-gray-500 block truncate">
              {data?.roster?.assigned_expeditor_email || "expeditor@inspectflow.com"}
            </span>
          </div>
          <div className="p-2 rounded-lg bg-white border border-gray-200">
            <span className="text-[10px] text-emerald-600 font-bold uppercase block">
              3. QC / Inspection Mgr
            </span>
            <span className="font-bold text-gray-900 block truncate">
              {data?.roster?.inspection_manager_name || data?.inspection_manager || "Dr. Henrik Lindqvist"}
            </span>
            <span className="text-[10px] text-gray-500 block truncate">
              {data?.roster?.inspection_manager_email || "qc@inspectflow.com"}
            </span>
          </div>
          <div className="p-2 rounded-lg bg-white border border-emerald-200">
            <span className="text-[10px] text-emerald-700 font-bold uppercase block">
              4. Inspection Engineer
            </span>
            <span className="font-bold text-emerald-900 block truncate">
              {data?.roster?.assigned_inspection_engineer_name || data?.inspection_engineer || "Omar Farooq"}
            </span>
            <span className="text-[10px] text-gray-500 block truncate">
              {data?.roster?.assigned_inspection_engineer_email || "engineer@inspectflow.com"}
            </span>
          </div>
          <div className="p-2 rounded-lg bg-white border border-amber-200">
            <span className="text-[10px] text-amber-700 font-bold uppercase block">
              5. Assigned Vendor
            </span>
            <span className="font-bold text-gray-900 block truncate">
              {data?.roster?.assigned_vendor_name || data?.supplier || "Flowserve-Sulzer"}
            </span>
            <span className="text-[10px] text-gray-500 block truncate">
              {data?.roster?.assigned_vendor_email || "vendor@petronash.com"}
            </span>
          </div>
        </div>
      </Card>

      {/* PO Summary KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Card className="p-3 bg-gray-50/70 border-gray-200">
          <p className="text-[11px] text-gray-500 uppercase font-semibold">PO &amp; Expeditor</p>
          <p className="text-sm font-bold text-indigo-700 font-mono mt-0.5">{poNumber}</p>
          <p className="text-[11px] text-gray-600">Expeditor: {data?.expeditor || "Ali"}</p>
        </Card>
        <Card className="p-3 bg-white border-gray-200">
          <p className="text-[11px] text-gray-500 uppercase font-semibold">Total Ordered Qty</p>
          <p className="text-xl font-bold text-gray-900 font-mono mt-0.5">{totalOrdered}</p>
          <p className="text-[11px] text-gray-500">{items.length} BOM Line(s)</p>
        </Card>
        <Card className="p-3 bg-emerald-50/60 border-emerald-200">
          <p className="text-[11px] text-emerald-700 uppercase font-semibold">IRC Released Qty</p>
          <p className="text-xl font-bold text-emerald-700 font-mono mt-0.5">{totalReleased}</p>
          <p className="text-[11px] text-emerald-600">Remaining: {Math.max(0, totalOrdered - totalReleased)}</p>
        </Card>
        <Card className="p-3 bg-blue-50/60 border-blue-200">
          <p className="text-[11px] text-blue-700 uppercase font-semibold">Shipped (Ex-Works)</p>
          <p className="text-xl font-bold text-blue-700 font-mono mt-0.5">{totalShipped}</p>
          <p className="text-[11px] text-blue-600">Stage: {(data?.stage || "insp").toUpperCase()}</p>
        </Card>
        <Card className="p-3 bg-purple-50/60 border-purple-200">
          <p className="text-[11px] text-purple-700 uppercase font-semibold">Site Receipt (MRV)</p>
          <p className="text-xl font-bold text-purple-700 font-mono mt-0.5">{totalDelivered}</p>
          <p className="text-[11px] text-purple-600">{totalOrdered > 0 ? Math.round((totalDelivered / totalOrdered) * 100) : 0}% Delivered</p>
        </Card>
      </div>

      {/* 1. Cumulative PO BOM Quantity Ledger & Expeditor Split Sub-Items */}
      <Card className="p-4 border-gray-200 shadow-xs">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Package className="w-4 h-4 text-indigo-600" />
            <h4 className="text-sm font-bold text-gray-900">
              Cumulative PO BOM Quantity Ledger &amp; Multi-Location Split Sub-Items
            </h4>
          </div>
          <Badge variant="outline" className="text-[10px] bg-indigo-50 text-indigo-700 border-indigo-200">
            Synced Live from SmartExpedit
          </Badge>
        </div>

        <div className="border rounded-xl overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-gray-50 text-xs">
                <TableHead className="font-semibold w-24">Item #</TableHead>
                <TableHead className="font-semibold">Exact Material Description (As Per PO / Drawings)</TableHead>
                <TableHead className="font-semibold text-right w-24">Ordered</TableHead>
                <TableHead className="font-semibold text-right w-28">Released (IRC)</TableHead>
                <TableHead className="font-semibold text-right w-28">Remaining</TableHead>
                <TableHead className="font-semibold text-right w-24">Shipped</TableHead>
                <TableHead className="font-semibold text-right w-24">Site MRV</TableHead>
                <TableHead className="font-semibold text-center w-28">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-6 text-xs text-gray-500">
                    No PO BOM items mapped yet.
                  </TableCell>
                </TableRow>
              ) : (
                items.map((it, idx) => (
                  <TableRow key={idx} className="text-xs hover:bg-gray-50/80">
                    <TableCell className="font-mono font-bold text-indigo-700">
                      <div className="flex items-center gap-1">
                        <span>{it.item}</span>
                        {it.is_split && (
                          <Badge className="bg-purple-100 text-purple-800 border-purple-200 text-[9px] px-1 py-0">
                            <Scissors className="w-2.5 h-2.5 mr-0.5" />
                            Split
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <p className="font-medium text-gray-900">{it.desc}</p>
                      <div className="flex flex-wrap items-center gap-3 mt-0.5 text-[10px] text-gray-500">
                        {it.tag && (
                          <span className="flex items-center gap-0.5 font-mono text-gray-700">
                            <Tag className="w-2.5 h-2.5" /> Tag: {it.tag}
                          </span>
                        )}
                        {it.location && (
                          <span className="flex items-center gap-0.5">
                            <MapPin className="w-2.5 h-2.5" /> {it.location}
                          </span>
                        )}
                        {it.batches && it.batches.length > 0 && (
                          <span className="text-emerald-700 font-medium">
                            IRCs: {it.batches.map((b) => `${b.irc_no} (${b.qty})`).join(", ")}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono font-semibold">
                      {it.ordered_qty} {it.unit}
                    </TableCell>
                    <TableCell className="text-right font-mono font-bold text-emerald-700">
                      {it.released_qty} {it.unit}
                    </TableCell>
                    <TableCell className="text-right font-mono font-bold text-amber-700">
                      {it.remaining_to_release} {it.unit}
                    </TableCell>
                    <TableCell className="text-right font-mono text-blue-700">
                      {it.shipped_qty}
                    </TableCell>
                    <TableCell className="text-right font-mono text-purple-700">
                      {it.delivered_qty}
                    </TableCell>
                    <TableCell className="text-center">
                      {it.delivered_qty >= it.ordered_qty && it.ordered_qty > 0 ? (
                        <Badge className="bg-purple-100 text-purple-800 text-[10px]">Site Delivered</Badge>
                      ) : it.released_qty >= it.ordered_qty && it.ordered_qty > 0 ? (
                        <Badge className="bg-emerald-100 text-emerald-800 text-[10px]">100% Released</Badge>
                      ) : it.released_qty > 0 ? (
                        <Badge className="bg-amber-100 text-amber-800 text-[10px]">Partial Release</Badge>
                      ) : (
                        <Badge className="bg-gray-100 text-gray-700 text-[10px]">In Inspection</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* 2. EDMS VDRL / SDRL Engineering & Quality Deliverables Table */}
      <Card className="p-4 border-gray-200 shadow-xs">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <FileCheck2 className="w-4 h-4 text-indigo-600" />
            <h4 className="text-sm font-bold text-gray-900">
              EDMS VDRL / SDRL Quality Deliverables (ITP, WPS/PQR, Hydrotest Procedures, MTCs)
            </h4>
          </div>
          <Badge variant="outline" className="text-[10px] bg-gray-50 text-gray-700">
            Periodic EDMS Sync
          </Badge>
        </div>

        <div className="border rounded-xl overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-gray-50 text-xs">
                <TableHead className="font-semibold">Document No.</TableHead>
                <TableHead className="font-semibold">Deliverable Title</TableHead>
                <TableHead className="font-semibold w-16">Rev</TableHead>
                <TableHead className="font-semibold">Linked Milestone</TableHead>
                <TableHead className="font-semibold">Planned Date</TableHead>
                <TableHead className="font-semibold">Review Code</TableHead>
                <TableHead className="font-semibold text-center">SLA Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.map((doc, idx) => (
                <TableRow key={idx} className="text-xs hover:bg-gray-50/80">
                  <TableCell className="font-mono font-bold text-indigo-700">{doc.doc_no}</TableCell>
                  <TableCell className="font-medium text-gray-900">{doc.title}</TableCell>
                  <TableCell className="font-mono">{doc.rev}</TableCell>
                  <TableCell className="text-gray-600">{doc.milestone}</TableCell>
                  <TableCell className="font-mono text-gray-600">{doc.planned_date}</TableCell>
                  <TableCell>{getCodeBadge(doc.code)}</TableCell>
                  <TableCell className="text-center">
                    {doc.is_overdue ? (
                      <Badge className="bg-red-100 text-red-800 border-red-200 text-[10px]">
                        <Clock className="w-3 h-3 mr-1" />
                        Overdue
                      </Badge>
                    ) : (
                      <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px]">
                        On Track
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

