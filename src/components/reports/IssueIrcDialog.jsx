import React, { useState, useEffect, useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  ShieldCheck,
  CheckCircle2,
  FileText,
  Plus,
  RefreshCw,
  Sparkles,
  AlertTriangle,
  Upload,
  ArrowRight,
  PackageCheck,
  Info,
  Check,
  X,
  Search,
} from "lucide-react";
import { toast } from "sonner";
import { base44 } from "@/api/base44Client";

export default function IssueIrcDialog({
  open,
  onClose,
  inspection,
  currentUser,
  onSuccess,
}) {
  const [mode, setMode] = useState("guided"); // 'guided' (Option 1) | 'manual' (Option 2)
  const [ircNumber, setIrcNumber] = useState("");
  const [releaseDate, setReleaseDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [remarks, setRemarks] = useState("");
  const [certificateFile, setCertificateFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Field / Revised Item Modal State (for Option 1)
  const [fieldItemModalOpen, setFieldItemModalOpen] = useState(false);
  const [newItemNumber, setNewItemNumber] = useState("");
  const [newItemDesc, setNewItemDesc] = useState("");
  const [newItemQty, setNewItemQty] = useState("");
  const [newItemUnit, setNewItemUnit] = useState("EA");
  const [newItemHeat, setNewItemHeat] = useState("");

  // Option 1: Available PO Items (Combines NOI items + PO Master BOM + Field Added)
  const [poItems, setPoItems] = useState([]);
  const [hasApprovedItp, setHasApprovedItp] = useState(true);

  // Quality & Quantity Guardrail States
  const [concessionGranted, setConcessionGranted] = useState(false);
  const [concessionReason, setConcessionReason] = useState("");
  const [poRevisionOverride, setPoRevisionOverride] = useState(false);
  const [poRevisionJustification, setPoRevisionJustification] = useState("");

  // Option 2: Manual Text / Items Input & Reconciliation Match State
  const [manualText, setManualText] = useState("");
  const [matchedItems, setMatchedItems] = useState([]);
  const [isMatching, setIsMatching] = useState(false);

  // Compute Quality & IE Review Gates from inspection reports
  const { openCriticalMajorNcrs, openMinorFindings, isReportIeApproved, hasAnyInspectionReport } = useMemo(() => {
    const reports = (inspection?.inspection_reports || []).filter(
      (r) => r.category !== "release_note" && r.report_type !== "release_note"
    );
    const critMajor = [];
    const minor = [];
    for (const r of reports) {
      for (const f of r.findings || []) {
        const isClosed = String(f.closure_status || f.status || "").toLowerCase() === "closed";
        if (!isClosed) {
          const sev = String(f.severity || f.SEVERITY || "").toLowerCase();
          const ftype = String(f.type || f.TYPE || "").toLowerCase();
          if (sev.includes("critical") || sev.includes("major") || ftype.includes("ncr")) {
            critMajor.push(f);
          } else {
            minor.push(f);
          }
        }
      }
    }
    const anyApproved = reports.some((r) => r.approval_status === "approved") || Boolean(inspection?.ie_approved_for_release);
    return {
      openCriticalMajorNcrs: critMajor,
      openMinorFindings: minor,
      isReportIeApproved: anyApproved,
      hasAnyInspectionReport: reports.length > 0,
    };
  }, [inspection]);

  const userRole = String(currentUser?.inspection_role || currentUser?.role || "").toLowerCase();
  const isIeOrQcOrAdmin = ["admin", "inspection_engineer", "qc_manager"].includes(userRole);

  // Initialize data when dialog opens
  useEffect(() => {
    if (!inspection) return;

    // Default IRC Number
    const poNum = inspection.po_number || "PO";
    const notifNo = inspection.notification_number || "NOI";
    const defaultNo = `IRC-${notifNo}`;
    setIrcNumber(defaultNo);
    setConcessionGranted(false);
    setConcessionReason("");
    setPoRevisionOverride(false);
    setPoRevisionJustification("");
    setRemarks(
      `Items inspected and accepted in accordance with approved Inspection and Test Plan (ITP). Visual, dimensional, and MTC verification completed with zero outstanding punch points.`
    );

    // Build PO items list starting from inspection's items_being_offered
    const offered = (inspection.items_being_offered || []).map((it, idx) => {
      const ordQty = Number(String(it.quantity || it.qty || 1).split(" ")[0]) || 1;
      return {
        id: `noi-${idx}`,
        itemNumber: String(it.itemNumber || it.item_number || it.item || (idx + 1) * 10),
        description: it.description || inspection.po_description || "Material Line Item",
        ordered_qty: ordQty,
        prev_released_qty: 0,
        remaining_qty: ordQty,
        qty_released: ordQty,
        unit: it.unit || "EA",
        heat_number: it.heat_number || it.heat_no || "",
        location: it.location || "",
        tag: it.tag_number || it.tag || "",
        is_split: it.is_split_sub_item || it.is_split || false,
        selected: true, // Default to offered
        source: it.is_split_sub_item || it.is_split ? "Split Sub-Item" : "NOI Scope",
      };
    });

    // Fetch live PO BOM & Cumulative Ledger from SmartExpedit (/api/v1/po/{po}/context)
    const fetchPoBom = async () => {
      try {
        const res = await fetch(`/api/v1/po/${encodeURIComponent(inspection.po_number)}/context`);
        if (res.ok) {
          const ctxData = await res.json();
          if (ctxData && ctxData.found && Array.isArray(ctxData.items)) {
            setHasApprovedItp(ctxData.has_approved_itp ?? true);
            const byKey = {};
            ctxData.items.forEach((ci) => {
              byKey[String(ci.item)] = ci;
            });

            // Enrich offered items with cumulative ledger quantities
            const enrichedOffered = offered.map((oi) => {
              const match = byKey[String(oi.itemNumber)];
              if (!match) return oi;
              const ord = Number(match.ordered_qty || oi.ordered_qty || 1);
              const prevRel = Number(match.released_qty || 0);
              const rem = Math.max(0, ord - prevRel);
              return {
                ...oi,
                description: match.desc || oi.description,
                ordered_qty: ord,
                prev_released_qty: prevRel,
                remaining_qty: rem,
                qty_released: rem > 0 ? Math.min(oi.qty_released, rem) : oi.qty_released,
                unit: match.unit || oi.unit,
                location: match.location || oi.location,
                tag: match.tag || oi.tag,
                is_split: match.is_split || oi.is_split,
                source: match.is_split ? "Split Sub-Item" : oi.source,
              };
            });

            const extraItems = ctxData.items
              .filter(
                (pi) =>
                  !enrichedOffered.some(
                    (oi) => String(oi.itemNumber) === String(pi.item)
                  )
              )
              .map((pi, idx) => {
                const ord = Number(pi.ordered_qty || 0);
                const prevRel = Number(pi.released_qty || 0);
                const rem = Math.max(0, ord - prevRel);
                return {
                  id: `po-${idx}`,
                  itemNumber: String(pi.item),
                  description: pi.desc || "PO Contract Item",
                  ordered_qty: ord,
                  prev_released_qty: prevRel,
                  remaining_qty: rem,
                  qty_released: rem > 0 ? rem : ord,
                  unit: pi.unit || "EA",
                  heat_number: "",
                  location: pi.location || "",
                  tag: pi.tag || "",
                  is_split: pi.is_split || false,
                  selected: false,
                  source: pi.is_split ? "Split Sub-Item" : "PO BOM",
                };
              });
            setPoItems([...enrichedOffered, ...extraItems]);
            return;
          }
        }
      } catch (e) {
        // Fallback to offered
      }
      setPoItems(offered);
    };

    fetchPoBom();
  }, [inspection, open]);

  // Option 1 Actions
  const handlePreselectAllAsPerNoi = () => {
    const noiNumbers = new Set(
      (inspection.items_being_offered || []).map((it, idx) =>
        String(it.itemNumber || it.item_number || (idx + 1) * 10)
      )
    );
    setPoItems((prev) =>
      prev.map((item) => {
        const isNoi = noiNumbers.has(String(item.itemNumber));
        return {
          ...item,
          selected: isNoi,
          qty_released: isNoi ? item.ordered_qty : 0,
        };
      })
    );
    toast.success("Pre-selected all items offered in the Notice of Inspection (NOI)");
  };

  const handleSelectAll = (checked) => {
    setPoItems((prev) =>
      prev.map((item) => ({
        ...item,
        selected: checked,
        qty_released: checked ? item.ordered_qty : 0,
      }))
    );
  };

  const handleToggleItem = (id) => {
    setPoItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, selected: !item.selected } : item
      )
    );
  };

  const handleQtyChange = (id, val) => {
    const num = Math.max(0, parseFloat(val) || 0);
    setPoItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, qty_released: num, selected: num > 0 } : item
      )
    );
  };

  const handleHeatChange = (id, val) => {
    setPoItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, heat_number: val } : item))
    );
  };

  // Add Item from Revised PO (for when PO revision is not yet in system)
  const handleSaveFieldItem = () => {
    if (!newItemNumber.trim() || !newItemDesc.trim() || !newItemQty) {
      toast.error("Please provide Item #, Exact Description, and Quantity.");
      return;
    }
    const addedItem = {
      id: `field-${Date.now()}`,
      itemNumber: newItemNumber.trim(),
      description: newItemDesc.trim(),
      ordered_qty: Number(newItemQty),
      qty_released: Number(newItemQty),
      unit: newItemUnit.trim() || "EA",
      heat_number: newItemHeat.trim(),
      selected: true,
      source: "Field Revised PO",
    };
    setPoItems((prev) => [...prev, addedItem]);
    setFieldItemModalOpen(false);
    setNewItemNumber("");
    setNewItemDesc("");
    setNewItemQty("");
    setNewItemHeat("");
    toast.success(`Item ${addedItem.itemNumber} added from Revised PO scope!`);
  };

  // Option 2: Smart Fuzzy Matcher
  const handleRunMatcher = () => {
    if (!manualText.trim()) {
      toast.error("Please enter or paste line items to reconcile.");
      return;
    }
    setIsMatching(true);

    // Split input text by lines
    const lines = manualText
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    const results = lines.map((line, idx) => {
      // Extract explicit item / line numbers cleanly (avoids matching QTY numbers)
      const itemNumMatch = line.match(/(?:item|line)\s*#?\s*([0-9]+(?:\.[0-9]+)?)|^\s*([0-9]+(?:\.[0-9]+)?)\b/i);
      const extractedNum = itemNumMatch ? (itemNumMatch[1] || itemNumMatch[2]) : null;

      // Extract quantities (e.g. "Qty: 100", "100 EA", "100EA")
      const qtyMatch = line.match(/(?:qty|quantity)?\s*[:=-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(ea|pcs|m|mtr|set|nos)?/i);
      const extractedQty = qtyMatch ? parseFloat(qtyMatch[1]) : 1;
      const extractedUnit = qtyMatch && qtyMatch[2] ? qtyMatch[2].toUpperCase() : "EA";

      // Match against available PO items
      let bestMatch = null;
      let highestScore = 0;

      for (const poItem of poItems) {
        let score = 0;
        if (extractedNum && String(poItem.itemNumber) === extractedNum) {
          score += 60; // Strong match on Item Number
        }
        // Substring / keyword matching
        const words = line.toLowerCase().split(/\W+/).filter((w) => w.length > 2);
        const poWords = (poItem.description || "").toLowerCase();
        let wordHits = 0;
        for (const w of words) {
          if (poWords.includes(w)) wordHits++;
        }
        if (words.length > 0) {
          score += Math.min(40, Math.round((wordHits / words.length) * 40));
        }

        if (score > highestScore) {
          highestScore = score;
          bestMatch = poItem;
        }
      }

      return {
        id: `match-${idx}`,
        inputText: line,
        matchedPoItem: bestMatch || poItems[0] || null,
        confidence: Math.min(100, highestScore || 50),
        itemNumber: bestMatch ? bestMatch.itemNumber : extractedNum || String((idx + 1) * 10),
        exactDescription: bestMatch ? bestMatch.description : line,
        qty_released: extractedQty,
        unit: extractedUnit,
        heat_number: "",
        confirmed: true,
      };
    });

    setMatchedItems(results);
    setIsMatching(false);
    toast.success(`Matched ${results.length} item(s) against PO Bill of Materials!`);
  };

  const handleUpdateMatchedPoItem = (matchId, selectedPoItemNumber) => {
    const targetPoItem = poItems.find((p) => String(p.itemNumber) === String(selectedPoItemNumber));
    if (!targetPoItem) return;
    setMatchedItems((prev) =>
      prev.map((m) =>
        m.id === matchId
          ? {
              ...m,
              matchedPoItem: targetPoItem,
              itemNumber: targetPoItem.itemNumber,
              exactDescription: targetPoItem.description,
              confidence: 100,
            }
          : m
      )
    );
  };

  const handleToggleConfirmMatch = (matchId) => {
    setMatchedItems((prev) =>
      prev.map((m) => (m.id === matchId ? { ...m, confirmed: !m.confirmed } : m))
    );
  };

  // Compile final items to release
  const itemsToRelease = useMemo(() => {
    if (mode === "guided") {
      return poItems
        .filter((it) => it.selected && it.qty_released > 0)
        .map((it) => ({
          itemNumber: it.itemNumber,
          description: it.description,
          ordered_quantity: it.ordered_qty,
          quantity: it.qty_released,
          qty_released: it.qty_released,
          unit: it.unit,
          heat_number: it.heat_number,
          source: it.source,
        }));
    } else {
      return matchedItems
        .filter((m) => m.confirmed && m.qty_released > 0)
        .map((m) => ({
          itemNumber: m.itemNumber,
          description: m.exactDescription,
          ordered_quantity: m.matchedPoItem ? m.matchedPoItem.ordered_qty : m.qty_released,
          quantity: m.qty_released,
          qty_released: m.qty_released,
          unit: m.unit,
          heat_number: m.heat_number,
          source: "Reconciled Match",
        }));
    }
  }, [mode, poItems, matchedItems]);

  // Detect if any selected/matched item exceeds Remaining PO Ordered Quantity
  const overReleasedItems = useMemo(() => {
    if (mode === "guided") {
      return poItems.filter(
        (it) =>
          it.selected &&
          it.ordered_qty > 0 &&
          (Number(it.prev_released_qty || 0) + Number(it.qty_released || 0)) > Number(it.ordered_qty)
      );
    }
    return matchedItems.filter((m) => {
      if (!m.confirmed || !m.matchedPoItem || !(m.matchedPoItem.ordered_qty > 0)) return false;
      return (
        (Number(m.matchedPoItem.prev_released_qty || 0) + Number(m.qty_released || 0)) >
        Number(m.matchedPoItem.ordered_qty)
      );
    });
  }, [mode, poItems, matchedItems]);

  // Submit and Issue IRC
  const handleConfirmAndIssue = async () => {
    if (itemsToRelease.length === 0) {
      toast.error("Please select or match at least one item to release with quantity > 0.");
      return;
    }

    if (hasAnyInspectionReport && !isReportIeApproved && !isIeOrQcOrAdmin) {
      toast.error("Mandatory IE Review Gate: The Inspection Engineer must review and approve the uploaded Inspection Report before an IRC can be issued.");
      return;
    }

    if (openCriticalMajorNcrs.length > 0 && !concessionGranted) {
      toast.error(`Strict Quality Gate: ${openCriticalMajorNcrs.length} open Critical/Major NCR(s) block release. Complete Stage 1 Technical Closeout or obtain IE/QC Concession.`);
      return;
    }

    if (concessionGranted && !concessionReason.trim()) {
      toast.error("Please provide the mandatory engineering/QC justification for granting a Concession Release.");
      return;
    }

    if (overReleasedItems.length > 0 && !poRevisionOverride) {
      toast.error(`Cumulative Quantity Guardrail: Item(s) ${overReleasedItems.map((i) => i.itemNumber).join(", ")} exceed PO Ordered Quantity. Check 'Pending PO Revision Override' to proceed.`);
      return;
    }

    if (overReleasedItems.length > 0 && poRevisionOverride && !poRevisionJustification.trim()) {
      toast.error("Please provide the mandatory PO Revision reference / justification for exceeding PO Ordered Quantity.");
      return;
    }

    if (!remarks.trim()) {
      toast.error("Inspector remarks / findings summary is mandatory.");
      return;
    }

    if (!ircNumber.trim()) {
      toast.error("Please specify the IRC Certificate Number.");
      return;
    }

    setSubmitting(true);
    try {
      let fileUrl = "";
      if (certificateFile) {
        const uploadRes = await base44.integrations.Core.UploadFile({ file: certificateFile });
        fileUrl = uploadRes?.file_url || "";
      }

      const payload = {
        inspection_id: inspection.id,
        po_number: inspection.po_number,
        notification_number: inspection.notification_number,
        irc_number: ircNumber.trim(),
        release_date: releaseDate,
        inspector_name: currentUser?.full_name || currentUser?.email || "Inspector",
        user_role: userRole,
        remarks: remarks.trim(),
        mode: mode,
        items_released: itemsToRelease,
        file_url: fileUrl,
        concession_granted: concessionGranted,
        concession_reason: concessionReason.trim(),
        po_revision_override: poRevisionOverride,
        po_revision_justification: poRevisionJustification.trim(),
      };

      const res = await fetch("/api/v1/issue-irc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to issue IRC");
      }

      toast.success(
        `✓ ${ircNumber} (${data.release_status || "APPROVED"}) officially issued! Dispatched to Vendor, TPI, Expediting & Logistics.`
      );
      if (onSuccess) onSuccess();
      onClose();
    } catch (err) {
      console.error("IRC Issue Error:", err);
      toast.error(err.message || "Failed to issue IRC");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto p-6">
          <DialogHeader className="border-b pb-4">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-green-50 border border-green-200 flex items-center justify-center text-green-600 shadow-sm">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <div>
                  <DialogTitle className="text-xl font-bold text-gray-900 flex items-center gap-2">
                    Issue Inspection Release Certificate (IRC)
                  </DialogTitle>
                  <p className="text-xs text-gray-500 mt-0.5">
                    PO: <span className="font-semibold text-gray-800">{inspection?.po_number}</span> · NOI:{" "}
                    <span className="font-semibold text-gray-800">{inspection?.notification_number}</span> · Vendor:{" "}
                    <span className="font-semibold text-gray-800">{inspection?.supplier_name}</span>
                  </p>
                </div>
              </div>
              <Badge variant="outline" className="bg-indigo-50 text-indigo-700 border-indigo-200 text-xs px-2.5 py-1">
                Quality Clearance
              </Badge>
            </div>
          </DialogHeader>

          <div className="space-y-4 pt-3">
            {/* GATE 1: Inspection Engineer Report Review & Endorsement Banner */}
            {hasAnyInspectionReport && !isReportIeApproved && (
              <Alert className={isIeOrQcOrAdmin ? "bg-indigo-50 border-indigo-200" : "bg-red-50 border-red-200"}>
                <AlertTriangle className={`h-4 w-4 ${isIeOrQcOrAdmin ? "text-indigo-600" : "text-red-600"}`} />
                <AlertDescription className={`text-xs ${isIeOrQcOrAdmin ? "text-indigo-900" : "text-red-900"}`}>
                  {isIeOrQcOrAdmin ? (
                    <>
                      <strong>Inspection Engineer Authority:</strong> The uploaded Inspection Report is currently pending formal IE approval. Issuing this IRC as an Inspection Engineer / QC Manager will automatically endorse the report and authorize release.
                    </>
                  ) : (
                    <>
                      <strong>🔒 Mandatory IE Review Gate:</strong> The uploaded Inspection Report &amp; MTC deliverables are currently <strong>Under Inspection Engineer Review</strong>. The Inspection Engineer must click <em>Approve</em> on the report before an Inspector can issue the IRC.
                    </>
                  )}
                </AlertDescription>
              </Alert>
            )}

            {/* GATE 2: Open Critical/Major NCR Quality Gate Banner */}
            {openCriticalMajorNcrs.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-3.5 space-y-2.5">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
                  <div className="text-xs text-red-900">
                    <strong>🚨 Strict Quality Gate — {openCriticalMajorNcrs.length} Open Critical/Major NCR(s):</strong>
                    <p className="mt-0.5 text-red-800">
                      IRC issuance is blocked until Stage 1 Technical Closeout is completed in the Findings &amp; NCRs tab, unless a formal Engineering/QC Concession is granted below.
                    </p>
                  </div>
                </div>
                {isIeOrQcOrAdmin && (
                  <div className="bg-white/90 border border-red-200 rounded-lg p-2.5 space-y-2">
                    <label className="flex items-center gap-2 text-xs font-bold text-red-900 cursor-pointer">
                      <Checkbox
                        checked={concessionGranted}
                        onCheckedChange={(v) => setConcessionGranted(Boolean(v))}
                      />
                      <span>Grant QC / Inspection Engineer Concession (Conditional Release)</span>
                    </label>
                    {concessionGranted && (
                      <Input
                        value={concessionReason}
                        onChange={(e) => setConcessionReason(e.target.value)}
                        placeholder="Mandatory Concession / Deviation Request reference & justification..."
                        className="h-8 text-xs"
                      />
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Minor Punch Banner */}
            {openCriticalMajorNcrs.length === 0 && openMinorFindings.length > 0 && (
              <Alert className="bg-amber-50 border-amber-200">
                <Info className="h-4 w-4 text-amber-600" />
                <AlertDescription className="text-amber-900 text-xs">
                  <strong>⚠️ {openMinorFindings.length} Open Minor Punch Item(s):</strong> IRC issuance is permitted and will be automatically badged as <strong>APPROVED (WITH MINOR PUNCH)</strong> in SmartExpedit.
                </AlertDescription>
              </Alert>
            )}

            {/* GATE 3: Cumulative Quantity Over-Release Guardrail */}
            {overReleasedItems.length > 0 && (
              <div className="bg-amber-50 border border-amber-300 rounded-xl p-3.5 space-y-2">
                <div className="text-xs text-amber-900">
                  <strong>⚠️ Cumulative Quantity Guardrail:</strong> Item(s){" "}
                  <strong>{overReleasedItems.map((i) => i.itemNumber).join(", ")}</strong> exceed the remaining PO Ordered Quantity balance (`Prev. Released + Current Release &gt; Ordered Qty`).
                </div>
                <label className="flex items-center gap-2 text-xs font-bold text-amber-950 cursor-pointer">
                  <Checkbox
                    checked={poRevisionOverride}
                    onCheckedChange={(v) => setPoRevisionOverride(Boolean(v))}
                  />
                  <span>Authorize &apos;Pending PO Revision / Tolerance Override&apos;</span>
                </label>
                {poRevisionOverride && (
                  <Input
                    value={poRevisionJustification}
                    onChange={(e) => setPoRevisionJustification(e.target.value)}
                    placeholder="Enter PO Amendment / Revision reference or shop floor tolerance justification *"
                    className="h-8 text-xs bg-white"
                  />
                )}
              </div>
            )}

            {/* Mode Switcher Tabs */}
            <Tabs value={mode} onValueChange={setMode} className="w-full">
              <TabsList className="grid w-full grid-cols-2 p-1 bg-gray-100 rounded-xl">
                <TabsTrigger
                  value="guided"
                  className="rounded-lg text-xs font-semibold py-2 data-[state=active]:bg-white data-[state=active]:text-indigo-700 data-[state=active]:shadow-sm"
                >
                  Option 1: PO BOM Linked (Guided Selection)
                </TabsTrigger>
                <TabsTrigger
                  value="manual"
                  className="rounded-lg text-xs font-semibold py-2 data-[state=active]:bg-white data-[state=active]:text-indigo-700 data-[state=active]:shadow-sm"
                >
                  Option 2: Manual IRC Entry &amp; Smart BOM Matcher
                </TabsTrigger>
              </TabsList>

              {/* OPTION 1 CONTENT */}
              <TabsContent value="guided" className="space-y-4 pt-3">
                <div className="flex flex-wrap items-center justify-between gap-3 bg-gray-50 p-3 rounded-xl border border-gray-200">
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={handlePreselectAllAsPerNoi}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs h-8 shadow-sm font-semibold"
                    >
                      <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                      Pre-select All as per NOI
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleSelectAll(true)}
                      className="text-xs h-8 text-gray-700"
                    >
                      Select All
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleSelectAll(false)}
                      className="text-xs h-8 text-gray-700"
                    >
                      Clear All
                    </Button>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setFieldItemModalOpen(true)}
                    className="border-indigo-300 text-indigo-700 hover:bg-indigo-50 text-xs h-8 font-medium"
                  >
                    <Plus className="w-3.5 h-3.5 mr-1.5" />
                    + Add Revised / Field Item
                  </Button>
                </div>

                {/* Items Table */}
                <div className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm">
                  <div className="overflow-x-auto max-h-72">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-gray-50 text-gray-700 font-bold uppercase tracking-wider border-b border-gray-200 sticky top-0 z-10">
                        <tr>
                          <th className="p-3 w-10 text-center">Sel</th>
                          <th className="p-3 w-16">Item #</th>
                          <th className="p-3">Exact Material Description (As per PO)</th>
                          <th className="p-3 w-20 text-right">Ordered</th>
                          <th className="p-3 w-20 text-right">Prev. Rel</th>
                          <th className="p-3 w-20 text-right">Remaining</th>
                          <th className="p-3 w-24">Release Now</th>
                          <th className="p-3 w-28">Heat / Batch #</th>
                          <th className="p-3 w-24 text-center">Scope</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {poItems.map((item) => (
                          <tr
                            key={item.id}
                            className={`transition-colors ${
                              item.selected ? "bg-indigo-50/40" : "hover:bg-gray-50"
                            }`}
                          >
                            <td className="p-3 text-center">
                              <Checkbox
                                checked={item.selected}
                                onCheckedChange={() => handleToggleItem(item.id)}
                              />
                            </td>
                            <td className="p-3 font-bold text-gray-900 font-mono">{item.itemNumber}</td>
                            <td className="p-3 text-gray-800">
                              <div className="font-medium line-clamp-2">{item.description}</div>
                              {(item.tag || item.location) && (
                                <div className="flex items-center gap-2 mt-0.5 text-[10px] text-gray-500">
                                  {item.tag && <span>Tag: <strong className="font-mono text-gray-700">{item.tag}</strong></span>}
                                  {item.location && <span>📍 {item.location}</span>}
                                </div>
                              )}
                            </td>
                            <td className="p-3 text-right text-gray-700 font-mono font-medium">
                              {item.ordered_qty} {item.unit}
                            </td>
                            <td className="p-3 text-right text-emerald-700 font-mono font-semibold">
                              {item.prev_released_qty || 0}
                            </td>
                            <td className="p-3 text-right text-amber-700 font-mono font-bold">
                              {item.remaining_qty ?? item.ordered_qty}
                            </td>
                            <td className="p-3">
                              <Input
                                type="number"
                                min="0"
                                value={item.qty_released}
                                onChange={(e) => handleQtyChange(item.id, e.target.value)}
                                className="h-7 text-xs font-semibold px-2 w-20 font-mono"
                                disabled={!item.selected}
                              />
                            </td>
                            <td className="p-3">
                              <Input
                                type="text"
                                placeholder="Heat/Serial..."
                                value={item.heat_number || ""}
                                onChange={(e) => handleHeatChange(item.id, e.target.value)}
                                className="h-7 text-xs px-2 w-28"
                                disabled={!item.selected}
                              />
                            </td>
                            <td className="p-3 text-center">
                              <span
                                className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                                  item.source === "NOI Scope"
                                    ? "bg-blue-100 text-blue-800"
                                    : item.source === "Split Sub-Item"
                                    ? "bg-purple-100 text-purple-800 font-bold"
                                    : item.source === "Field Revised PO"
                                    ? "bg-amber-100 text-amber-800"
                                    : "bg-gray-100 text-gray-700"
                                }`}
                              >
                                {item.source}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </TabsContent>

              {/* OPTION 2 CONTENT */}
              <TabsContent value="manual" className="space-y-4 pt-3">
                <div className="bg-amber-50/70 p-3.5 rounded-xl border border-amber-200/80 text-xs text-amber-900 flex items-start gap-2.5">
                  <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold">Manual IRC Entry &amp; Smart Reconciler:</span> Paste or enter the
                    inspector's release note lines below. The system will fuzzy-match each line with the active PO BOM,
                    allowing you to review, adjust, and lock in exact descriptions before releasing.
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-semibold text-gray-700">
                    Paste / Enter Release Note Lines (e.g. "1011 - Stud Bolt 1/2 x 70mm - Qty: 100"):
                  </Label>
                  <Textarea
                    rows={4}
                    value={manualText}
                    onChange={(e) => setManualText(e.target.value)}
                    placeholder="Example:
1011 - STUD BOLT 1/2 x 70mm - Qty: 100 EA - Heat: H7892
2012 - HEAVY HEX NUT 1/2 - Qty: 200 EA - Heat: N114"
                    className="font-mono text-xs"
                  />
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      size="sm"
                      onClick={handleRunMatcher}
                      disabled={isMatching || !manualText.trim()}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs h-8 shadow-sm font-semibold"
                    >
                      <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                      {isMatching ? "Reconciling..." : "Run Smart BOM Matcher"}
                    </Button>
                  </div>
                </div>

                {/* Match Results Table */}
                {matchedItems.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-gray-800 uppercase tracking-wider">
                      Reconciliation &amp; Match Review ({matchedItems.length} items):
                    </p>
                    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm max-h-64 overflow-y-auto">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-gray-50 text-gray-700 font-bold uppercase tracking-wider border-b border-gray-200 sticky top-0">
                          <tr>
                            <th className="p-2.5 w-10 text-center">Confirm</th>
                            <th className="p-2.5 w-1/3">Input Text</th>
                            <th className="p-2.5 w-1/3">Matched PO BOM Line (Exact Description)</th>
                            <th className="p-2.5 w-20 text-center">Match</th>
                            <th className="p-2.5 w-24">Release Qty</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {matchedItems.map((m) => (
                            <tr key={m.id} className={m.confirmed ? "bg-green-50/30" : "bg-gray-50/50"}>
                              <td className="p-2.5 text-center">
                                <Checkbox
                                  checked={m.confirmed}
                                  onCheckedChange={() => handleToggleConfirmMatch(m.id)}
                                />
                              </td>
                              <td className="p-2.5 font-mono text-[11px] text-gray-700">{m.inputText}</td>
                              <td className="p-2.5">
                                <select
                                  value={m.itemNumber}
                                  onChange={(e) => handleUpdateMatchedPoItem(m.id, e.target.value)}
                                  className="w-full text-xs border border-gray-200 rounded p-1 font-medium bg-white"
                                >
                                  {poItems.map((p) => (
                                    <option key={p.id} value={p.itemNumber}>
                                      Item {p.itemNumber} — {p.description.slice(0, 50)}...
                                    </option>
                                  ))}
                                </select>
                                <div className="text-[11px] text-gray-500 mt-0.5 italic">
                                  {m.exactDescription}
                                </div>
                              </td>
                              <td className="p-2.5 text-center">
                                <span className="bg-green-100 text-green-800 text-[10px] font-bold px-2 py-0.5 rounded-full">
                                  {m.confidence}%
                                </span>
                              </td>
                              <td className="p-2.5 font-bold">
                                {m.qty_released} {m.unit}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </TabsContent>
            </Tabs>

            {/* MANDATORY RELEASE DETAILS (BOTH OPTIONS) */}
            <div className="bg-gray-50 p-4 rounded-xl border border-gray-200 space-y-4">
              <p className="text-xs font-bold text-gray-700 uppercase tracking-wider flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-indigo-600" />
                Mandatory Release Note Stamped Information
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs font-semibold text-gray-700">IRC Number *</Label>
                  <Input
                    value={ircNumber}
                    onChange={(e) => setIrcNumber(e.target.value)}
                    className="h-8 text-xs font-mono font-semibold"
                    placeholder="e.g. IRC-2820-2025-74259-001"
                    required
                  />
                </div>
                <div>
                  <Label className="text-xs font-semibold text-gray-700">Release Date *</Label>
                  <Input
                    type="date"
                    value={releaseDate}
                    onChange={(e) => setReleaseDate(e.target.value)}
                    className="h-8 text-xs font-semibold"
                    required
                  />
                </div>
                <div>
                  <Label className="text-xs font-semibold text-gray-700">Attach Signed Certificate (Optional)</Label>
                  <Input
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg"
                    onChange={(e) => setCertificateFile(e.target.files[0] || null)}
                    className="h-8 text-xs"
                  />
                </div>
              </div>

              <div>
                <Label className="text-xs font-semibold text-gray-700 flex items-center justify-between">
                  <span>Inspector Remarks &amp; Clearance Findings *</span>
                  <span className="text-[10px] font-normal text-gray-400">Mandatory on all IRC issues</span>
                </Label>
                <Textarea
                  rows={2}
                  value={remarks}
                  onChange={(e) => setRemarks(e.target.value)}
                  placeholder="Record ITP clause compliance, heat numbers witnessed, punch points cleared, and storage advice..."
                  className="text-xs mt-1"
                  required
                />
              </div>
            </div>

            {/* Summary Banner & Action Buttons */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2 border-t">
              <div className="flex items-center gap-2">
                <Badge className="bg-emerald-100 text-emerald-800 border-emerald-300 text-xs px-3 py-1 font-semibold">
                  <PackageCheck className="w-3.5 h-3.5 mr-1.5" />
                  Releasing {itemsToRelease.length} Line Item(s)
                </Badge>
                <span className="text-xs text-gray-500">
                  Total Units:{" "}
                  <b>{itemsToRelease.reduce((acc, it) => acc + (parseFloat(it.qty_released) || 0), 0)}</b>
                </span>
              </div>
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onClose}
                  disabled={submitting}
                  className="flex-1 sm:flex-none text-xs h-9 px-4"
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  onClick={handleConfirmAndIssue}
                  disabled={submitting || itemsToRelease.length === 0}
                  className="flex-1 sm:flex-none bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-9 px-6 font-bold shadow-md shadow-emerald-600/20"
                >
                  {submitting ? "Issuing & Syncing..." : "Confirm & Issue IRC"}
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* MODAL: Add Field / Revised Item */}
      <Dialog open={fieldItemModalOpen} onOpenChange={setFieldItemModalOpen}>
        <DialogContent className="max-w-md p-5">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-gray-900 flex items-center gap-2">
              <Plus className="w-4 h-4 text-indigo-600" />
              Add Item from Revised PO / Shop Scope
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 pt-2 text-xs">
            <p className="text-gray-500">
              Use when the vendor presented additional items from a revised PO that is not yet reflected in the system.
            </p>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs font-semibold">Item # *</Label>
                <Input
                  placeholder="e.g. 2010"
                  value={newItemNumber}
                  onChange={(e) => setNewItemNumber(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <Label className="text-xs font-semibold">Quantity *</Label>
                <Input
                  type="number"
                  placeholder="e.g. 50"
                  value={newItemQty}
                  onChange={(e) => setNewItemQty(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs font-semibold">Exact Material Description *</Label>
              <Textarea
                rows={2}
                placeholder="Exact material description and specification as per revised PO..."
                value={newItemDesc}
                onChange={(e) => setNewItemDesc(e.target.value)}
                className="text-xs"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs font-semibold">Unit</Label>
                <Input
                  placeholder="EA, M, LOT"
                  value={newItemUnit}
                  onChange={(e) => setNewItemUnit(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <Label className="text-xs font-semibold">Heat / Batch #</Label>
                <Input
                  placeholder="e.g. H-7821"
                  value={newItemHeat}
                  onChange={(e) => setNewItemHeat(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setFieldItemModalOpen(false)}
                className="text-xs h-8"
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={handleSaveFieldItem}
                className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs h-8 font-semibold"
              >
                Add to Scope
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

