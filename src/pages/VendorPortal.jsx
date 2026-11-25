import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Store,
  FileText,
  Calendar,
  BellRing,
  AlertOctagon,
  Truck,
  Plus,
  RefreshCw,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileCheck2,
  Download,
  Upload,
  Info,
  Users,
  FolderGit2,
  PackageCheck,
  Layers,
  Lock
} from "lucide-react";
import { toast } from "sonner";
import { downloadAuthFile } from "@/utils/downloadAuthFile";
import { useProject } from "@/components/context/ProjectContext";
import {
  VendorAckAndCloseoutTab,
  VendorSubOrdersTab,
  VendorProgressReportsTab,
} from "@/components/vendor/VendorErpTabs";

export default function VendorPortal() {
  const { selectedProjectId, currentProject } = useProject();
  const [selectedPo, setSelectedPo] = useState("");
  const [activeTab, setActiveTab] = useState("schedule");
  const [loading, setLoading] = useState(false);

  // Data states
  const [availablePos, setAvailablePos] = useState([]);
  const [poContext, setPoContext] = useState(null);
  const [vdmsDocs, setVdmsDocs] = useState([]);
  const [nois, setNois] = useState([]);
  const [findings, setFindings] = useState([]);
  const [releasedItems, setReleasedItems] = useState([]);
  const [dispatchRequests, setDispatchRequests] = useState([]);
  const [sched9Data, setSched9Data] = useState(null);
  const [selectedNoiItems, setSelectedNoiItems] = useState({});

  // Modals state
  const [issueNoiOpen, setIssueNoiOpen] = useState(false);
  const [cancelNoiOpen, setCancelNoiOpen] = useState(false);
  const [reviseNoiOpen, setReviseNoiOpen] = useState(false);
  const [targetNoi, setTargetNoi] = useState(null);

  const [ncrModalOpen, setNcrModalOpen] = useState(false);
  const [quickCloseOpen, setQuickCloseOpen] = useState(false);
  const [targetFinding, setTargetFinding] = useState(null);

  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [dispatchModalOpen, setDispatchModalOpen] = useState(false);

  // Form states
  const [noiForm, setNoiForm] = useState({
    item_number: "10.1",
    item_description: "Skid Base Sub-Assembly",
    milestone_name: "Hydrostatic Pressure Test",
    inspection_scope: "Stage Inspection",
    sub_order_id: "",
    scheduled_date: new Date(Date.now() + 7 * 86400000).toISOString().split("T")[0],
    inspection_location: "Vendor Fabrication Yard B",
    scope: "100% witness hydrostatic pressure test per approved ITP",
  });

  const [cancelForm, setCancelForm] = useState({
    reason: "",
  });

  const [reviseForm, setReviseForm] = useState({
    scheduled_date: "",
    location: "",
    scope: "",
    revision_notes: "",
  });

  const [ncrForm, setNcrForm] = useState({
    containment_action: "",
    root_cause: "",
    capa_plan: "",
    target_closure_date: "",
    rework_evidence_file: "NDE_Ultrasonic_Report_PostRework.pdf",
  });

  const [quickForm, setQuickForm] = useState({
    correction_details: "",
    uploaded_document_name: "",
    uploaded_document_url: "",
    remarks: "",
  });

  const [dispatchForm, setDispatchForm] = useState({
    item_id: "",
    irc_number: "",
    dispatch_qty: 0,
    packing_list_ref: "",
    gross_weight_kg: 0,
    net_weight_kg: 0,
    crate_dimensions: "",
    invoice_draft_ref: "",
  });

  const [scheduleForm, setScheduleForm] = useState({
    item_id: "",
    forecast_date: "",
    baseline_date: "",
    delay_reason_code: "ON_TRACK",
    recovery_plan: "",
    eng_pct: 0,
    proc_pct: 0,
    fab_pct: 0,
    insp_pct: 0,
  });

  const fetchVendorData = async () => {
    if (!selectedPo) {
      setVdmsDocs([]);
      setNois([]);
      setFindings([]);
      setPoContext(null);
      setReleasedItems([]);
      return;
    }
    setLoading(true);
    try {
      // 1. VDMS Documents
      const docRes = await fetch(`/api/v1/vdms/documents?po=${encodeURIComponent(selectedPo)}`);
      const docJson = await docRes.json();
      if (docJson.ok) setVdmsDocs(docJson.documents || []);

      // 2. Inspections / NOIs
      const inspUrl = selectedProjectId && selectedProjectId !== "all"
        ? `/api/Inspections?project_id=${encodeURIComponent(selectedProjectId)}`
        : "/api/Inspections";
      const inspRes = await fetch(inspUrl);
      const inspList = await inspRes.json();
      const filteredNois = (Array.isArray(inspList) ? inspList : []).filter(
        (i) => String(i.po_number || "") === selectedPo
      );
      setNois(filteredNois);

      // Extract findings across both flattened `i.findings` and nested `inspection_reports[].findings`
      const fList = [];
      const seenFindingIds = new Set();
      filteredNois.forEach((i) => {
        const pushFinding = (f, repName = "") => {
          const fid = f.id || `${i.id}_${fList.length}`;
          if (seenFindingIds.has(fid)) return;
          seenFindingIds.add(fid);
          fList.push({
            ...f,
            id: fid,
            inspection_id: i.id,
            notification_number: i.notification_number,
            report_name: f.report_name || repName,
          });
        };
        (i.findings || []).forEach((f) => pushFinding(f));
        (i.inspection_reports || []).forEach((rep) => {
          (rep.findings || []).forEach((f) => pushFinding(f, rep.name));
        });
      });
      setFindings(fList);

      // 3. PO Context + 9-Col Minimum Schedule
      const [ctxRes, schRes] = await Promise.all([
        fetch(`/api/v1/po/${encodeURIComponent(selectedPo)}/context`),
        fetch(`/api/v1/po/${encodeURIComponent(selectedPo)}/schedule`),
      ]);
      const ctxJson = await ctxRes.json();
      const schJson = schRes && schRes.ok ? await schRes.json() : null;
      if (schJson?.ok) setSched9Data(schJson);
      if (ctxJson.ok) {
        setPoContext(ctxJson);
        setDispatchRequests(ctxJson.dispatch_requests || []);
        const poItems = ctxJson.items || [];
        setReleasedItems(poItems);
        // Initialize multi-item NOI selection map cleanly for the active PO
        const initSel = {};
        poItems.forEach((itm, idx) => {
          const ik = String(itm.item || "");
          if (!ik) return;
          initSel[ik] = {
            checked: idx === 0,
            item_number: ik,
            description: itm.desc || `BOM Item ${ik}`,
            qty: Number(itm.ordered_qty ?? itm.qty ?? 1),
            unit: itm.unit || "EA",
            tag: itm.tag || "",
          };
        });
        setSelectedNoiItems(initSel);
        const firstItm = poItems.find((x) => !x.is_split_parent) || poItems[0];
        if (firstItm) {
          setScheduleForm((prev) => ({
            ...prev,
            item_id: String(firstItm.item || "10"),
            baseline_date: firstItm.baseline_date || prev.baseline_date || "",
            forecast_date: firstItm.forecast_date || firstItm.baseline_date || prev.forecast_date || "",
            eng_pct: Number(firstItm.eng_pct ?? 0),
            proc_pct: Number(firstItm.proc_pct ?? 0),
            fab_pct: Number(firstItm.fab_pct ?? 0),
            insp_pct: Number(firstItm.insp_pct ?? 0),
            delay_reason_code: firstItm.delay_reason_code || "ON_TRACK",
            recovery_plan: firstItm.recovery_plan || "",
          }));
        }
      }
    } catch (e) {
      console.error("Error loading vendor portal data:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const loadProjectPos = async () => {
      try {
        const res = await fetch(
          `/api/v1/governance/overview?project_id=${encodeURIComponent(
            selectedProjectId || "all"
          )}`
        );
        const json = await res.json();
        if (json.ok) {
          const list = json.pos || [];
          setAvailablePos(list);
          if (list.length > 0 && !list.find((p) => p.po === selectedPo)) {
            setSelectedPo(list[0].po);
          } else if (list.length === 0) {
            setSelectedPo("");
          }
        }
      } catch (e) {
        console.error("Failed to fetch project POs:", e);
      }
    };
    loadProjectPos();
  }, [selectedProjectId]);

  useEffect(() => {
    fetchVendorData();
  }, [selectedPo]);

  // Lead-time validator (Domestic >= 5 days)
  const isShortNotice = (dateStr) => {
    if (!dateStr) return false;
    const diffDays = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
    return diffDays < 5;
  };

  // Submit NOI (supports single or multi-selected BOM items)
  const handleIssueNoi = async (e) => {
    e.preventDefault();
    try {
      const checkedItems = Object.values(selectedNoiItems || {}).filter((x) => x.checked);
      if (releasedItems.length > 0 && checkedItems.length === 0 && !noiForm.sub_order_id) {
        toast.error("Please select at least one BOM line item for this NOI.");
        return;
      }
      const itemsPayload =
        checkedItems.length > 0
          ? checkedItems.map((x) => ({
              item_number: x.item_number,
              description: x.description,
              qty: Number(x.qty || 1),
              unit: x.unit || "EA",
              tag: x.tag || "",
            }))
          : [
              {
                item_number: noiForm.item_number || "10",
                description: noiForm.item_description || "Offered Material Item",
                qty: 1,
                unit: "EA",
              },
            ];
      const payload = {
        po_number: selectedPo,
        supplier_name: poContext?.supplier || "Vendor",
        items: itemsPayload,
        item_number: itemsPayload[0].item_number,
        item_description: itemsPayload[0].description,
        item_qty: itemsPayload[0].qty,
        item_unit: itemsPayload[0].unit,
        milestone_name: noiForm.milestone_name,
        inspection_scope: noiForm.inspection_scope || "Stage Inspection",
        sub_order_id: noiForm.sub_order_id || undefined,
        start_date: noiForm.scheduled_date,
        inspection_location: noiForm.inspection_location,
        scope: noiForm.scope,
      };
      const res = await fetch("/api/v1/vendor-noi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (json.ok) {
        toast.success(`NOI ${json.notification_number} issued successfully!`);
        if (json.itp_warning) {
          toast.warning(json.itp_warning, { duration: 6000 });
        }
        if (json.iap_warning) {
          toast.warning(json.iap_warning, { duration: 7000 });
        }
        setNoiForm((prev) => ({ ...prev, sub_order_id: "" }));
        setIssueNoiOpen(false);
        fetchVendorData();
      } else {
        toast.error(json.detail || "Failed to issue NOI");
      }
    } catch (e) {
      toast.error("Error submitting NOI");
    }
  };

  // Cancel NOI
  const handleCancelNoi = async () => {
    if (!targetNoi) return;
    try {
      const res = await fetch(`/api/v1/vendor-noi/${targetNoi.id}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: cancelForm.reason,
          requested_by: "Vendor Representative",
        }),
      });
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        setCancelNoiOpen(false);
        setCancelForm({ reason: "" });
        fetchVendorData();
      } else {
        toast.error(json.detail || "Cancellation failed");
      }
    } catch (e) {
      toast.error("Error cancelling NOI");
    }
  };

  // Revise NOI
  const handleReviseNoi = async () => {
    if (!targetNoi) return;
    try {
      const res = await fetch(`/api/v1/vendor-noi/${targetNoi.id}/revise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scheduled_date: reviseForm.scheduled_date,
          location: reviseForm.location,
          scope: reviseForm.scope,
          revision_notes: reviseForm.revision_notes,
        }),
      });
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        setReviseNoiOpen(false);
        fetchVendorData();
      } else {
        toast.error(json.detail || "Revision failed");
      }
    } catch (e) {
      toast.error("Error revising NOI");
    }
  };

  // Submit Major NCR RCA/CAPA
  const handleNcrSubmit = async () => {
    if (!targetFinding) return;
    try {
      const res = await fetch(
        `/api/v1/vendor/ncr/${targetFinding.id}/submit-resolution`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            containment_action: ncrForm.containment_action,
            root_cause: ncrForm.root_cause,
            capa_plan: ncrForm.capa_plan,
            target_closure_date: ncrForm.target_closure_date,
            rework_evidence_files: [ncrForm.rework_evidence_file],
          }),
        }
      );
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        setNcrModalOpen(false);
        fetchVendorData();
      } else {
        toast.error(json.detail || "NCR submission failed");
      }
    } catch (e) {
      toast.error("Error submitting NCR resolution");
    }
  };

  // Quick Correction Submit
  const handleQuickSubmit = async () => {
    if (!targetFinding) return;
    try {
      const res = await fetch(
        `/api/v1/vendor/ncr/${targetFinding.id}/quick-close`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            correction_details: quickForm.correction_details,
            uploaded_document_name: quickForm.uploaded_document_name,
            remarks: quickForm.remarks,
          }),
        }
      );
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        setQuickCloseOpen(false);
        fetchVendorData();
      } else {
        toast.error(json.detail || "Correction submission failed");
      }
    } catch (e) {
      toast.error("Error submitting correction");
    }
  };

  // Submit Schedule Update
  const handleScheduleSubmit = async () => {
    try {
      const targetItemId = scheduleForm.item_id || releasedItems.find((x) => !x.is_split_parent)?.item || releasedItems[0]?.item || "10";
      const payload = {
        po_number: selectedPo,
        items: [
          {
            item_id: targetItemId,
            forecast_date: scheduleForm.forecast_date,
            baseline_date: scheduleForm.baseline_date,
            delay_reason_code: scheduleForm.delay_reason_code,
            recovery_plan: scheduleForm.recovery_plan,
            eng_pct: scheduleForm.eng_pct,
            proc_pct: scheduleForm.proc_pct,
            fab_pct: scheduleForm.fab_pct,
            insp_pct: scheduleForm.insp_pct,
          },
        ],
      };
      const res = await fetch("/api/v1/vendor/schedule-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        setScheduleModalOpen(false);
        fetchVendorData();
      } else {
        toast.error(json.detail || "Schedule update rejected");
      }
    } catch (e) {
      toast.error("Error updating schedule");
    }
  };

  // Submit Dispatch Request
  const handleDispatchSubmit = async () => {
    try {
      const res = await fetch("/api/v1/vendor/dispatch-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          po_number: selectedPo,
          item_id: dispatchForm.item_id,
          irc_number: dispatchForm.irc_number,
          dispatch_qty: Number(dispatchForm.dispatch_qty),
          packing_list_ref: dispatchForm.packing_list_ref,
          gross_weight_kg: Number(dispatchForm.gross_weight_kg),
          net_weight_kg: Number(dispatchForm.net_weight_kg),
          crate_dimensions: dispatchForm.crate_dimensions,
          invoice_draft_ref: dispatchForm.invoice_draft_ref,
        }),
      });
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        setDispatchModalOpen(false);
        fetchVendorData();
      } else {
        toast.error(json.detail || "Dispatch request rejected");
      }
    } catch (e) {
      toast.error("Error submitting dispatch request");
    }
  };

  return (
    <div className="space-y-4 pb-8 max-w-7xl mx-auto">
      {/* Vendor Portal Top Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white p-5 rounded-2xl shadow-lg border border-indigo-900/40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-indigo-600/30 border border-indigo-400/30 flex items-center justify-center text-indigo-300">
              <Store className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-white tracking-tight">
                  Dedicated Vendor Expediting & Quality Portal
                </h1>
                <Badge className="bg-indigo-500/20 text-indigo-300 border-indigo-400/30 text-[10px]">
                  Role-Isolated
                </Badge>
              </div>
              <p className="text-xs text-indigo-200/80">
                Direct supplier collaboration for VDMS deliverables, schedule updates, NOI callouts, and dispatch requests.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 bg-black/20 p-2 rounded-xl border border-white/10 shrink-0">
            <Label className="text-xs text-indigo-200">Active Order:</Label>
            <Select value={selectedPo} onValueChange={setSelectedPo}>
              <SelectTrigger className="w-64 h-8 text-xs bg-white text-gray-900 border-0 font-bold" disabled={availablePos.length === 0}>
                <SelectValue placeholder={availablePos.length === 0 ? "No POs in this project" : "Select PO"} />
              </SelectTrigger>
              <SelectContent>
                {availablePos.length > 0 ? (
                  availablePos.map((pItem) => (
                    <SelectItem key={pItem.po} value={pItem.po} className="text-xs">
                      PO #{pItem.po} ({pItem.head || pItem.supplier})
                    </SelectItem>
                  ))
                ) : (
                  <SelectItem value="__none" disabled className="text-xs text-gray-400">
                    No POs in this project
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="xs"
              onClick={fetchVendorData}
              disabled={loading}
              className="text-white border-white/20 hover:bg-white/10 h-8 px-2"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>

        {/* Interlinked Project & Paired Team Roster Bar */}
        <div className="mt-4 pt-3 border-t border-white/10 flex flex-wrap items-center justify-between gap-2 text-xs text-indigo-100">
          <div className="flex items-center gap-2">
            <FolderGit2 className="w-3.5 h-3.5 text-indigo-300" />
            <span>
              <b>Assigned Project:</b>{" "}
              {poContext?.project_code ? `[${poContext.project_code}] ` : ""}
              {poContext?.project || currentProject?.name || "Offshore Gas Expansion Project (Train-3)"}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-[11px]">
            <span>
              <b className="text-indigo-300">Expediting Mgr:</b>{" "}
              {(poContext?.roster?.expediting_manager_name || "Tariq Al-Mansoor").split("(")[0].trim()}
            </span>
            <span>•</span>
            <span>
              <b className="text-sky-300">Package Expeditor:</b>{" "}
              {(poContext?.roster?.assigned_expeditor_name || "Ali Al-Rashid").split("(")[0].trim()}
            </span>
            <span>•</span>
            <span>
              <b className="text-emerald-300">QC Manager:</b>{" "}
              {(poContext?.roster?.inspection_manager_name || "Dr. Henrik Lindqvist").split("(")[0].trim()}
            </span>
            <span>•</span>
            <span>
              <b className="text-teal-300">Inspection Engineer:</b>{" "}
              {(poContext?.roster?.assigned_inspection_engineer_name || "Omar Farooq").split("(")[0].trim()}
            </span>
          </div>
        </div>

        {/* NEAS PO Summary Bar */}
        {poContext && (
          <div className="mt-3 pt-2.5 border-t border-white/10 flex flex-wrap items-center gap-2 text-[11px]">
            <span className="px-2 py-0.5 rounded bg-white/10 text-indigo-100">
              <b>Contract:</b> {poContext.contract_no || "N/A"}
            </span>
            <span className="px-2 py-0.5 rounded bg-white/10 text-indigo-100">
              <b>MR:</b> {poContext.mr_ref || "N/A"}
            </span>
            <span className="px-2 py-0.5 rounded bg-white/10 text-indigo-100">
              <b>Incoterm:</b> {poContext.incoterm || "N/A"}
            </span>
            <span className="px-2 py-0.5 rounded bg-white/10 text-indigo-100">
              <b>CDD:</b> {poContext.cdd_date || "TBD"}
            </span>
            <span className="px-2 py-0.5 rounded bg-white/10 text-indigo-100">
              <b>ROS:</b> {poContext.ros_date || "TBD"}
            </span>
            <span className="px-2 py-0.5 rounded bg-white/10 text-indigo-100">
              <b>Platform:</b> {poContext.platform || "Project Facility"}
            </span>
            <span className="px-2 py-0.5 rounded bg-white/10 text-indigo-100">
              <b>Despatch:</b> {poContext.despatch_location || "Site Stores"}
            </span>
            <Badge className={poContext.ack?.buyer_escalation_required ? "bg-rose-500 text-white text-[10px]" : "bg-emerald-500/80 text-white text-[10px]"}>
              PO Ack: {poContext.ack?.st || "Pending"}
            </Badge>
          </div>
        )}
      </div>

      {/* Main Tabs Navigation */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="bg-white p-1 rounded-xl border border-gray-200 shadow-xs grid grid-cols-4 md:grid-cols-8 gap-1 h-auto">
          <TabsTrigger
            value="ack"
            className="flex items-center gap-1 py-2 text-[11px] font-semibold data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
          >
            <PackageCheck className="w-3.5 h-3.5" />
            PO Ack &amp; MRB
          </TabsTrigger>

          <TabsTrigger
            value="nois"
            className="flex items-center gap-1.5 py-2 text-xs font-semibold data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
          >
            <BellRing className="w-3.5 h-3.5" />
            Notice of Inspection (NOI)
            <Badge variant="secondary" className="ml-1 text-[10px] px-1.5 py-0 h-4">
              {nois.length}
            </Badge>
          </TabsTrigger>

          <TabsTrigger
            value="vdms"
            className="flex items-center gap-1.5 py-2 text-xs font-semibold data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
          >
            <FileText className="w-3.5 h-3.5" />
            VDMS Documents
            <Badge variant="secondary" className="ml-1 text-[10px] px-1.5 py-0 h-4">
              {vdmsDocs.length}
            </Badge>
          </TabsTrigger>

          <TabsTrigger
            value="schedule"
            className="flex items-center gap-1 py-2 text-[11px] font-semibold data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
          >
            <Calendar className="w-3.5 h-3.5" />
            9-Col Schedule
          </TabsTrigger>

          <TabsTrigger
            value="suborders"
            className="flex items-center gap-1 py-2 text-[11px] font-semibold data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
          >
            <Layers className="w-3.5 h-3.5" />
            Sub-Orders
            <Badge variant="secondary" className="ml-0.5 text-[10px] px-1 py-0 h-4">
              {poContext?.sub_orders?.length || 0}
            </Badge>
          </TabsTrigger>

          <TabsTrigger
            value="vpr"
            className="flex items-center gap-1 py-2 text-[11px] font-semibold data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
          >
            <FileText className="w-3.5 h-3.5" />
            Progress Report
          </TabsTrigger>

          <TabsTrigger
            value="ncrs"
            className="flex items-center gap-1.5 py-2 text-xs font-semibold data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
          >
            <AlertOctagon className="w-3.5 h-3.5" />
            NCR & Punch Actions
            <Badge
              variant="secondary"
              className={`ml-1 text-[10px] px-1.5 py-0 h-4 ${
                findings.length > 0 ? "bg-rose-100 text-rose-700 font-bold" : ""
              }`}
            >
              {findings.length}
            </Badge>
          </TabsTrigger>

          <TabsTrigger
            value="dispatch"
            className="flex items-center gap-1.5 py-2 text-xs font-semibold data-[state=active]:bg-indigo-50 data-[state=active]:text-indigo-700"
          >
            <Truck className="w-3.5 h-3.5" />
            Dispatch Requests
          </TabsTrigger>
        </TabsList>

        {/* ── TAB: PO ACKNOWLEDGEMENT & MRB/SPIR CLOSEOUT ─────────────────────── */}
        <TabsContent value="ack" className="space-y-4">
          <VendorAckAndCloseoutTab selectedPo={selectedPo} poContext={poContext} onUpdated={fetchVendorData} />
        </TabsContent>

        {/* ── TAB: SUB-ORDERS (Z002 / CRITICAL BOUGHT-OUT) ────────────────────── */}
        <TabsContent value="suborders" className="space-y-4">
          <VendorSubOrdersTab
            selectedPo={selectedPo}
            poContext={poContext}
            onUpdated={fetchVendorData}
            onRaiseSubOrderNoi={(sub) => {
              setNoiForm((prev) => ({
                ...prev,
                inspection_scope: "Sub-Order Material",
                sub_order_id: sub.id || "",
                item_number: sub.sub_po_no || "SUB-1",
                item_description: `${sub.material || "Sub-Order Material"} (${sub.vendor || "Sub-Vendor"})`,
                milestone_name: `Sub-Order Material Inspection — ${sub.material || ""}`.trim(),
                inspection_location: sub.location
                  ? `${sub.vendor || "Sub-Vendor"} (${sub.location})`
                  : `${sub.vendor || "Sub-Vendor"} Works`,
                scope: `Sub-Order ${sub.sub_po_no || sub.id || ""} (${sub.unpriced_po_ref || "Unpriced PO"}) inspection per approved ITP`,
              }));
              setSelectedNoiItems((prev) => {
                const next = { ...prev };
                Object.keys(next).forEach((k) => {
                  next[k] = { ...next[k], checked: false };
                });
                return next;
              });
              setIssueNoiOpen(true);
            }}
          />
        </TabsContent>

        {/* ── TAB: NMDC 7-SECTION PROGRESS REPORTS ────────────────────────────── */}
        <TabsContent value="vpr" className="space-y-4">
          <VendorProgressReportsTab selectedPo={selectedPo} onUpdated={fetchVendorData} />
        </TabsContent>

        {/* ── TAB 1: NOTICE OF INSPECTION (NOI) ─────────────────────────────── */}
        <TabsContent value="nois" className="space-y-4">
          <Card className="border-gray-200/80 shadow-xs">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-bold text-gray-900">
                  Inspection Callouts & Status Tracking
                </CardTitle>
                <CardDescription className="text-xs">
                  Issue formal callouts, manage scope revisions (Rev 01), and handle cancellations.
                </CardDescription>
              </div>
              <Button
                size="sm"
                onClick={() => setIssueNoiOpen(true)}
                className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs h-8 font-semibold shadow-xs"
              >
                <Plus className="w-3.5 h-3.5 mr-1" />
                Issue New NOI
              </Button>
            </CardHeader>

            <CardContent>
              {nois.length === 0 ? (
                <div className="py-12 text-center text-gray-500 text-xs">
                  No inspection callouts raised yet for PO #{selectedPo}. Click "Issue New NOI" above.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-gray-50 text-gray-600 font-semibold border-b border-gray-200">
                      <tr>
                        <th className="py-2.5 px-3">NOI Number</th>
                        <th className="py-2.5 px-3">Rev</th>
                        <th className="py-2.5 px-3">Inspection Date</th>
                        <th className="py-2.5 px-3">Milestone / Scope</th>
                        <th className="py-2.5 px-3">Yard Location</th>
                        <th className="py-2.5 px-3">Inspector Status</th>
                        <th className="py-2.5 px-3">Inspection Status</th>
                        <th className="py-2.5 px-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {nois.map((noi) => {
                        const hasInspector = Boolean(
                          noi.assigned_inspector_id || noi.assigned_inspector_name
                        );
                        const isCancelled = noi.status === "cancelled";
                        return (
                          <tr key={noi.id} className="hover:bg-gray-50/60">
                            <td className="py-2.5 px-3 font-mono font-bold text-indigo-700">
                              {noi.notification_number || noi.id}
                            </td>
                            <td className="py-2.5 px-3">
                              <Badge variant="outline" className="text-[10px] bg-slate-50">
                                Rev {noi.notification_revision || "0"}
                              </Badge>
                            </td>
                            <td className="py-2.5 px-3 font-medium text-gray-900">
                              {noi.start_date || "TBD"}
                            </td>
                            <td className="py-2.5 px-3 text-gray-700 max-w-xs">
                              <div className="truncate">{noi.po_description || "Witness Inspection"}</div>
                              {noi.inspection_scope && (
                                <Badge variant="outline" className="mt-0.5 text-[9px] text-teal-700 border-teal-200 bg-teal-50/40">
                                  {noi.inspection_scope}
                                </Badge>
                              )}
                            </td>
                            <td className="py-2.5 px-3 text-gray-600">
                              {noi.inspection_location || "Shop Floor"}
                            </td>
                            <td className="py-2.5 px-3">
                              {isCancelled ? (
                                <Badge variant="secondary" className="text-[10px] bg-gray-100 text-gray-500">
                                  N/A
                                </Badge>
                              ) : hasInspector ? (
                                noi.inspector_confirmation_status === "pending_reconfirmation" ? (
                                  <Badge className="bg-amber-100 text-amber-800 border-amber-300 text-[10px]">
                                    Pending Re-confirmation
                                  </Badge>
                                ) : (
                                  <Badge className="bg-emerald-100 text-emerald-800 border-emerald-300 text-[10px]">
                                    Assigned & Confirmed
                                  </Badge>
                                )
                              ) : (
                                <Badge variant="outline" className="text-gray-500 text-[10px]">
                                  Unassigned
                                </Badge>
                              )}
                            </td>
                            <td className="py-2.5 px-3">
                              <Badge
                                className={
                                  isCancelled
                                    ? "bg-rose-100 text-rose-800 border-rose-300 text-[10px]"
                                    : "bg-blue-100 text-blue-800 border-blue-300 text-[10px]"
                                }
                              >
                                {noi.status}
                              </Badge>
                            </td>
                            <td className="py-2.5 px-3 text-right space-x-1">
                              {!isCancelled && (
                                <>
                                  <Button
                                    variant="outline"
                                    size="xs"
                                    onClick={() => {
                                      setTargetNoi(noi);
                                      setReviseForm({
                                        scheduled_date: noi.start_date || "",
                                        location: noi.inspection_location || "",
                                        scope: noi.po_description || "",
                                        revision_notes: "",
                                      });
                                      setReviseNoiOpen(true);
                                    }}
                                    className="text-[11px] h-6 px-2 text-indigo-600 hover:bg-indigo-50"
                                  >
                                    Revise
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="xs"
                                    onClick={() => {
                                      setTargetNoi(noi);
                                      setCancelNoiOpen(true);
                                    }}
                                    className="text-[11px] h-6 px-2 text-rose-600 hover:bg-rose-50 border-rose-200"
                                  >
                                    Cancel
                                  </Button>
                                </>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 2: VDMS DOCUMENTS ─────────────────────────────────────────── */}
        <TabsContent value="vdms" className="space-y-4">
          <Card className="border-gray-200/80 shadow-xs">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-bold text-gray-900">
                  VDMS Engineering Deliverables & Live Countdown SLA
                </CardTitle>
                <CardDescription className="text-xs">
                  Synchronized with corporate VDMS. Code 1/2 required for Inspection Release.
                </CardDescription>
              </div>
              <Badge variant="outline" className="bg-indigo-50 text-indigo-700 text-xs">
                VDMS Live Bridge
              </Badge>
            </CardHeader>

            <CardContent>
              {vdmsDocs.length === 0 ? (
                <div className="py-12 text-center text-gray-500 text-xs">
                  No deliverables registered for PO #{selectedPo}.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-gray-50 text-gray-600 font-semibold border-b border-gray-200">
                      <tr>
                        <th className="py-2.5 px-3">Document No</th>
                        <th className="py-2.5 px-3">Title</th>
                        <th className="py-2.5 px-3">Rev</th>
                        <th className="py-2.5 px-3">Review Code</th>
                        <th className="py-2.5 px-3">Submitted</th>
                        <th className="py-2.5 px-3">Returned</th>
                        <th className="py-2.5 px-3">SLA Countdown</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {vdmsDocs.map((doc, idx) => {
                        const isCode1 = doc.code === "Code 1";
                        const isCode2 = doc.code === "Code 2";
                        const isCode3 = doc.code === "Code 3";
                        return (
                          <tr key={idx} className="hover:bg-gray-50/60">
                            <td className="py-2.5 px-3 font-mono font-bold text-gray-900">
                              {doc.doc_no}
                            </td>
                            <td className="py-2.5 px-3 text-gray-700">{doc.title}</td>
                            <td className="py-2.5 px-3 font-semibold text-gray-600">
                              {doc.rev}
                            </td>
                            <td className="py-2.5 px-3">
                              <Badge
                                className={
                                  isCode1
                                    ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                                    : isCode2
                                    ? "bg-blue-100 text-blue-800 border-blue-300"
                                    : "bg-rose-100 text-rose-800 border-rose-300"
                                }
                              >
                                {doc.code}
                              </Badge>
                            </td>
                            <td className="py-2.5 px-3 text-gray-500">{doc.submitted}</td>
                            <td className="py-2.5 px-3 text-gray-500">{doc.returned}</td>
                            <td className="py-2.5 px-3">
                              {doc.is_overdue ? (
                                <span className="inline-flex items-center text-[11px] font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                                  <Clock className="w-3 h-3 mr-1" /> Overdue ({doc.days_remaining}d)
                                </span>
                              ) : (
                                <span className="inline-flex items-center text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                                  <Clock className="w-3 h-3 mr-1" /> {doc.days_remaining}d remaining
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 3: SCHEDULE & PROGRESS ─────────────────────────────────────── */}
        <TabsContent value="schedule" className="space-y-4">
          <Card className="border-gray-200/80 shadow-xs">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <CardTitle className="text-sm font-bold text-gray-900">
                    Manufacturing Progress &amp; Schedule Alignment
                  </CardTitle>
                  {poContext?.procurement_class && (
                    <Badge className="bg-indigo-100 text-indigo-800 border-indigo-200 text-[10px] uppercase">
                      {poContext.procurement_class}
                    </Badge>
                  )}
                </div>
                <CardDescription className="text-xs">
                  Submit progress updates. If forecast slips past contractual baseline, delay reason and recovery plan are required.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {selectedPo && (
                  <a
                    href={`/Expediting?sec=portal&tab=sched&po=${encodeURIComponent(selectedPo)}`}
                    className="inline-flex items-center gap-1 px-2.5 h-7 rounded-md border border-indigo-300 bg-white text-indigo-700 hover:bg-indigo-50 text-xs font-semibold"
                  >
                    Open Full Z003 Schedule
                  </a>
                )}
                <Button
                  variant="outline"
                  size="xs"
                  onClick={() => {
                    if (!selectedPo) return;
                    downloadAuthFile(
                      `/api/v1/po/${encodeURIComponent(selectedPo)}/schedule/export-xlsx`,
                      `${selectedPo}_Schedule_9Col.xlsx`
                    );
                  }}
                  className="text-xs h-7"
                >
                  <Download className="w-3 h-3 mr-1 text-emerald-700" />
                  9-Col Excel (.xlsx)
                </Button>
                <label className="inline-flex items-center gap-1 px-2.5 h-7 rounded-md border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 text-xs font-semibold cursor-pointer">
                  <Upload className="w-3 h-3" />
                  Upload Schedule File
                  <input
                    type="file"
                    accept=".xlsx,.xlsm,.csv,.pdf"
                    className="hidden"
                    onChange={async (e) => {
                      const f = e.target.files?.[0];
                      e.target.value = "";
                      if (!f || !selectedPo) return;
                      toast.info(`Uploading & parsing "${f.name}" for PO #${selectedPo}...`);
                      try {
                        const fd = new FormData();
                        fd.append("file", f, f.name);
                        const res = await fetch(
                          `/api/v1/po/${encodeURIComponent(selectedPo)}/schedule/upload`,
                          { method: "POST", body: fd }
                        );
                        const json = await res.json().catch(() => ({}));
                        if (!res.ok || !json.ok) {
                          toast.error(json.detail || `Could not parse schedule file "${f.name}"`);
                          return;
                        }
                        setSched9Data((prev) => ({ ...(prev || {}), ...json }));
                        toast.success(
                          `Parsed ${json.parsed_count} row(s) via ${json.engine} (${json.matched_count} matched, ${json.added_count} added) & saved to PO schedule.`
                        );
                        (json.warnings || []).forEach((w) => toast.warning(w, { duration: 6000 }));
                        if (json.target_delivery) {
                          setScheduleForm((prev) => ({
                            ...prev,
                            forecast_date: prev.forecast_date || json.target_delivery,
                          }));
                        }
                        await fetchVendorData();
                      } catch (err) {
                        console.error("Schedule upload parse error:", err);
                        toast.error(`Error uploading schedule "${f.name}"`);
                      }
                    }}
                  />
                </label>
                <Button
                  size="xs"
                  onClick={() => setScheduleModalOpen(true)}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs h-7 font-semibold"
                >
                  Update Schedule & Progress
                </Button>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-gray-50 text-gray-600 font-semibold border-b border-gray-200">
                    <tr>
                      <th className="py-2.5 px-3">Item #</th>
                      <th className="py-2.5 px-3">Description</th>
                      <th className="py-2.5 px-3">Manufacturing Location</th>
                      <th className="py-2.5 px-3">PO Ordered Qty</th>
                      <th className="py-2.5 px-3">Released (IRC)</th>
                      <th className="py-2.5 px-3">Shipped (BL)</th>
                      <th className="py-2.5 px-3">Site MRV</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {releasedItems.map((itm, idx) => {
                      const isSplitChild = itm.is_split || String(itm.item).includes(".");
                      return (
                        <tr key={idx} className={isSplitChild ? "bg-indigo-50/20 hover:bg-indigo-50/40" : "hover:bg-gray-50/60"}>
                          <td className="py-2.5 px-3 font-mono font-bold text-gray-900">
                            {isSplitChild ? `↳ ${itm.item}` : itm.item}
                          </td>
                          <td className="py-2.5 px-3">
                            <span className="font-medium text-gray-800">{itm.desc}</span>
                            {itm.tag && <span className="block text-[10px] font-mono text-gray-400">Tag: {itm.tag}</span>}
                          </td>
                          <td className="py-2.5 px-3 text-gray-600">{itm.location || "Vendor Works"}</td>
                          <td className="py-2.5 px-3 font-bold text-gray-900">{itm.ordered_qty} {itm.unit}</td>
                          <td className="py-2.5 px-3 font-semibold text-emerald-700">{itm.released_qty || 0} {itm.unit}</td>
                          <td className="py-2.5 px-3 font-semibold text-blue-700">{itm.shipped_qty || 0} {itm.unit}</td>
                          <td className="py-2.5 px-3 font-semibold text-purple-700">{itm.delivered_qty || 0} {itm.unit}</td>
                          <td className="py-2.5 px-3 text-right">
                            <Button
                              variant="outline"
                              size="xs"
                              onClick={() => {
                                setScheduleForm({
                                  item_id: String(itm.item || ""),
                                  baseline_date: itm.baseline_date || "",
                                  forecast_date: itm.forecast_date || itm.baseline_date || "",
                                  delay_reason_code: itm.delay_reason_code || "ON_TRACK",
                                  recovery_plan: itm.recovery_plan || "",
                                  eng_pct: Number(itm.eng_pct ?? 0),
                                  proc_pct: Number(itm.proc_pct ?? 0),
                                  fab_pct: Number(itm.fab_pct ?? 0),
                                  insp_pct: Number(itm.insp_pct ?? 0),
                                });
                                setScheduleModalOpen(true);
                              }}
                              className="text-[11px] h-6 px-2 text-indigo-600 hover:bg-indigo-50 border-indigo-200"
                            >
                              Update
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {(() => {
                const liveItm = releasedItems.find((x) => !x.is_split_parent) || releasedItems[0];
                if (!liveItm) return null;
                return (
              <div className="p-4 rounded-xl border border-gray-200 bg-gray-50/50 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-xs text-gray-900">
                      Item {liveItm.item}: {liveItm.desc} ({liveItm.location || "Vendor Works"})
                    </h3>
                    <p className="text-[11px] text-gray-500">
                      Contractual Baseline: {liveItm.baseline_date || "TBD"} • Current Forecast: {liveItm.forecast_date || "TBD"} • ROS: {liveItm.ros_date || "TBD"} • Platform: {liveItm.platform || "—"}
                    </p>
                  </div>
                  <Badge className="bg-amber-100 text-amber-800 border-amber-300 text-[10px]">
                    {liveItm.delay_reason_code || "Live Progress"}
                  </Badge>
                </div>

                <div className="grid grid-cols-4 gap-3 text-center">
                  <div className="p-2.5 rounded-lg bg-white border border-gray-200">
                    <span className="text-[10px] text-gray-500 font-semibold block">Engineering</span>
                    <span className="text-sm font-bold text-gray-900">{liveItm.eng_pct ?? 0}%</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-white border border-gray-200">
                    <span className="text-[10px] text-gray-500 font-semibold block">Procurement</span>
                    <span className="text-sm font-bold text-gray-900">{liveItm.proc_pct ?? 0}%</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-white border border-gray-200">
                    <span className="text-[10px] text-gray-500 font-semibold block">Fabrication</span>
                    <span className="text-sm font-bold text-indigo-700">{liveItm.fab_pct ?? 0}%</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-white border border-gray-200">
                    <span className="text-[10px] text-gray-500 font-semibold block">Inspection</span>
                    <span className="text-sm font-bold text-emerald-700">{liveItm.insp_pct ?? 0}%</span>
                  </div>
                </div>

                {liveItm.recovery_plan && (
                <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-xs space-y-1">
                  <div className="flex items-center gap-1.5 text-amber-800 font-semibold">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    <span><b>Delay / Status:</b> {liveItm.delay_reason_code || "Update"}</span>
                  </div>
                  <p className="text-[11px] text-amber-700">
                    <b>Recovery Plan:</b> {liveItm.recovery_plan}
                  </p>
                </div>
                )}
              </div>
                );
              })()}

              {/* 9-Column Minimum Requirement Schedule Matrix (23 Activities + ITP W/H + Sub-Orders) */}
              {sched9Data?.rows?.length > 0 && (
                <div className="border rounded-xl overflow-hidden bg-white">
                  <div className="p-3 bg-slate-50 border-b flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900">
                      Minimum Requirement 9-Column Schedule ({sched9Data.rows.length} activities incl. ITP W/H &amp; Sub-Orders)
                    </span>
                    <Badge className={sched9Data.frozen ? "bg-indigo-100 text-indigo-800 text-[10px]" : "bg-amber-100 text-amber-800 text-[10px]"}>
                      {sched9Data.frozen ? <Lock className="w-3 h-3 mr-1" /> : null}
                      {sched9Data.frozen ? "Baseline Frozen (Rule 2)" : "Pre-Freeze"}
                    </Badge>
                  </div>
                  <div className="overflow-x-auto max-h-80 overflow-y-auto">
                    <table className="w-full text-[11px] text-left">
                      <thead className="bg-slate-900 text-white sticky top-0">
                        <tr>
                          <th className="p-2">Sr.</th>
                          <th className="p-2">Activity</th>
                          <th className="p-2">Dur (d)</th>
                          <th className="p-2">Baseline Start</th>
                          <th className="p-2">Baseline End</th>
                          <th className="p-2">Forecast Start</th>
                          <th className="p-2">Forecast End</th>
                          <th className="p-2">Dependency</th>
                          <th className="p-2">%</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {sched9Data.rows.map((sr, sidx) => (
                          <tr key={sr.id || sidx} className={sr.source_kind === "itp_witness_hold" ? "bg-teal-50/40" : sr.source_kind === "suborder" ? "bg-amber-50/40" : ""}>
                            <td className="p-2 font-mono text-gray-500">{sr.sr}</td>
                            <td className="p-2 font-medium text-gray-900">{sr.act}</td>
                            <td className="p-2 font-mono">{sr.duration_days || "—"}</td>
                            <td className="p-2 font-mono">{sr.bS || "—"}</td>
                            <td className="p-2 font-mono">{sr.bE || "—"}</td>
                            <td className="p-2 font-mono">{sr.fS || "—"}</td>
                            <td className="p-2 font-mono">{sr.fE || "—"}</td>
                            <td className="p-2 font-mono">{sr.dependency || "—"}</td>
                            <td className="p-2 font-bold">{sr.pct !== "" ? `${sr.pct}%` : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 4: NCR & PUNCH ACTIONS ────────────────────────────────────── */}
        <TabsContent value="ncrs" className="space-y-4">
          <Card className="border-gray-200/80 shadow-xs">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-bold text-gray-900">
                  Quality Findings, NCRs & Punch List Actions
                </CardTitle>
                <CardDescription className="text-xs">
                  Major NCRs require formal 3-Stage RCA/CAPA. Minor punch items can be closed directly with photo/document upload.
                </CardDescription>
              </div>
            </CardHeader>

            <CardContent>
              {findings.length === 0 ? (
                <div className="py-12 text-center text-gray-500 text-xs flex flex-col items-center">
                  <CheckCircle2 className="w-8 h-8 text-emerald-500 mb-2" />
                  <p className="font-semibold text-gray-700">Zero Open Quality Findings</p>
                  <p className="text-gray-400">All witness points clean. No corrective actions pending.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {findings.map((f, idx) => {
                    const isMajor =
                      String(f.severity || f.type || "").toUpperCase() === "CRITICAL" ||
                      String(f.severity || f.type || "").toUpperCase() === "MAJOR" ||
                      String(f.type || "").toUpperCase() === "NCR";
                    const isPendingIe = f.status === "pending_ie_review";

                    return (
                      <div
                        key={idx}
                        className="p-3.5 rounded-xl border border-gray-200/90 bg-white shadow-xs space-y-2"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <Badge
                                className={
                                  isMajor
                                    ? "bg-rose-100 text-rose-800 border-rose-300"
                                    : "bg-blue-100 text-blue-800 border-blue-300"
                                }
                              >
                                {isMajor ? "Major NCR" : "Minor Punch Item"}
                              </Badge>
                              <span className="font-bold text-xs text-gray-900">
                                {f.notification_number}
                              </span>
                              <span className="text-gray-400 text-xs">•</span>
                              <span className="text-[11px] font-mono text-gray-500">
                                Item ID: {f.id}
                              </span>
                            </div>
                            <p className="text-xs font-medium text-gray-800">
                              {f.description || f.issue}
                            </p>
                          </div>

                          <div className="text-right shrink-0">
                            {isPendingIe ? (
                              <Badge className="bg-amber-100 text-amber-800 border-amber-300 text-[10px]">
                                Awaiting IE Review
                              </Badge>
                            ) : (
                              <Badge className="bg-rose-100 text-rose-800 border-rose-300 text-[10px]">
                                Action Required
                              </Badge>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center justify-between pt-1 border-t border-gray-100">
                          <span className="text-[11px] text-gray-500">
                            {isMajor
                              ? "Requires 3-Stage Form: Containment, RCA/CAPA & Rework Evidence"
                              : "Requires direct document or photo submission (no RCA needed)"}
                          </span>

                          <div className="space-x-1.5">
                            {isMajor ? (
                              <Button
                                size="xs"
                                onClick={() => {
                                  setTargetFinding(f);
                                  setNcrModalOpen(true);
                                }}
                                className="bg-rose-600 hover:bg-rose-700 text-white text-xs h-7 px-2.5 font-semibold"
                              >
                                Submit 3-Stage RCA & CAPA
                              </Button>
                            ) : (
                              <Button
                                size="xs"
                                onClick={() => {
                                  setTargetFinding(f);
                                  setQuickCloseOpen(true);
                                }}
                                className="bg-blue-600 hover:bg-blue-700 text-white text-xs h-7 px-2.5 font-semibold"
                              >
                                Upload Quick Correction
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── TAB 5: DISPATCH REQUESTS ───────────────────────────────────────── */}
        <TabsContent value="dispatch" className="space-y-4">
          <Card className="border-gray-200/80 shadow-xs">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-bold text-gray-900">
                  Post-IRC Dispatch Requests & Movement Clearances
                </CardTitle>
                <CardDescription className="text-xs">
                  Submit packing lists, crate dimensions, and weights for materials released under statutory IRCs.
                </CardDescription>
              </div>
              <Button
                size="sm"
                onClick={() => setDispatchModalOpen(true)}
                className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-8 font-semibold shadow-xs"
              >
                <Plus className="w-3.5 h-3.5 mr-1" />
                New Dispatch Request
              </Button>
            </CardHeader>

            <CardContent className="space-y-4">
              <div className="p-3.5 rounded-xl border border-gray-200 bg-emerald-50/40 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileCheck2 className="w-4 h-4 text-emerald-600" />
                    <span className="font-bold text-xs text-gray-900">
                      Eligible Released Inventory for PO #{selectedPo}
                    </span>
                  </div>
                  <Badge variant="outline" className="bg-emerald-100 text-emerald-800 text-[10px]">
                    {releasedItems.some((it) => (it.available_to_dispatch || 0) > 0) ? "IRC Released" : "Awaiting IRC Release"}
                  </Badge>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs text-gray-700">
                  {releasedItems.map((it) => (
                    <div key={it.item} className="p-2.5 bg-white rounded border border-gray-200">
                      <span className="text-[10px] text-gray-500 block font-semibold">Item {it.item}: {it.desc}</span>
                      <span className="font-bold text-emerald-700">{it.available_to_dispatch || 0} {it.unit} Available</span>
                      <span className="block text-[10px] text-gray-400">
                        Released: {it.released_qty || 0} | Shipped: {it.shipped_qty || 0} | Reserved: {it.pending_dispatch_qty || 0}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-3.5 rounded-xl border border-gray-200 bg-white space-y-2">
                <h4 className="font-bold text-xs text-gray-900">
                  Submitted Dispatch Requests &amp; Movement Clearances ({dispatchRequests.length})
                </h4>
                {dispatchRequests.length === 0 ? (
                  <p className="text-xs text-gray-500">No dispatch movement requests submitted for PO #{selectedPo} yet.</p>
                ) : (
                  dispatchRequests.map((dr) => (
                    <div key={dr.id} className="p-3 rounded-lg bg-gray-50 border border-gray-200 text-xs flex items-center justify-between">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-gray-900">{dr.id}</span>
                          <Badge className="bg-amber-100 text-amber-800 text-[10px]">{dr.status}</Badge>
                        </div>
                        <p className="text-[11px] text-gray-500">
                          Item {dr.item_id} • Qty: {dr.dispatch_qty} • IRC: {dr.irc_number || "N/A"} • PL: {dr.packing_list_ref || "N/A"} ({dr.crate_dimensions || "—"}, {dr.gross_weight_kg || 0} kg)
                        </p>
                      </div>
                      <span className="text-gray-500 text-[11px] font-medium">{dr.submitted_at}</span>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── MODAL: ISSUE NEW NOI (MULTI-ITEM BOM SELECTION) ───────────────── */}
      <Dialog open={issueNoiOpen} onOpenChange={setIssueNoiOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto p-6">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-gray-900">
              Issue Notice of Inspection (NOI)
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              Select one or multiple PO BOM items to include on a single NOI. Contractual lead time: Domestic &ge; 5 days, Overseas &ge; 14 days.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleIssueNoi} className="space-y-3 py-2 text-xs">
            {releasedItems.length > 0 && !noiForm.sub_order_id ? (
              <div className="space-y-1.5 border rounded-lg p-2.5 bg-slate-50">
                <div className="flex items-center justify-between">
                  <Label className="text-xs font-bold text-gray-900">
                    Select PO BOM Items Covered ({Object.values(selectedNoiItems || {}).filter((x) => x.checked).length} of {releasedItems.length})
                  </Label>
                  <div className="flex gap-1.5">
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      className="h-6 text-[10px] px-2"
                      onClick={() => {
                        const next = { ...selectedNoiItems };
                        Object.keys(next).forEach((k) => { next[k] = { ...next[k], checked: true }; });
                        setSelectedNoiItems(next);
                      }}
                    >
                      Select All
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      className="h-6 text-[10px] px-2"
                      onClick={() => {
                        const next = { ...selectedNoiItems };
                        Object.keys(next).forEach((k) => { next[k] = { ...next[k], checked: false }; });
                        setSelectedNoiItems(next);
                      }}
                    >
                      Clear
                    </Button>
                  </div>
                </div>
                <div className="max-h-44 overflow-y-auto space-y-1.5 pr-1">
                  {releasedItems.map((itm) => {
                    const ik = String(itm.item || "");
                    const sel = selectedNoiItems[ik] || {
                      checked: false,
                      item_number: ik,
                      description: itm.desc || "",
                      qty: Number(itm.ordered_qty ?? 1),
                      unit: itm.unit || "EA",
                      tag: itm.tag || "",
                    };
                    return (
                      <div
                        key={ik}
                        className={`flex items-center gap-2 p-2 rounded border text-xs ${
                          sel.checked ? "bg-indigo-50/70 border-indigo-300" : "bg-white border-gray-200"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={Boolean(sel.checked)}
                          onChange={(e) =>
                            setSelectedNoiItems((prev) => ({
                              ...prev,
                              [ik]: { ...sel, checked: e.target.checked },
                            }))
                          }
                        />
                        <div className="flex-1 min-w-0">
                          <div className="font-semibold text-gray-900 truncate">
                            <span className="font-mono text-indigo-700 mr-1">Item {ik}</span>
                            {itm.desc}
                          </div>
                          <div className="text-[10px] text-gray-500">
                            {itm.tag ? `Tag: ${itm.tag} • ` : ""}Ordered: {itm.ordered_qty} {itm.unit}
                          </div>
                        </div>
                        <div className="w-20 shrink-0">
                          <Input
                            type="number"
                            min="0.01"
                            step="any"
                            disabled={!sel.checked}
                            value={sel.qty}
                            onChange={(e) =>
                              setSelectedNoiItems((prev) => ({
                                ...prev,
                                [ik]: { ...sel, qty: e.target.value },
                              }))
                            }
                            title="Offered Qty for this NOI"
                            className="h-7 text-xs bg-white text-right font-semibold"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">PO Line Item / Sub-Split</Label>
                  <Input
                    value={noiForm.item_number}
                    onChange={(e) => setNoiForm({ ...noiForm, item_number: e.target.value })}
                    className="h-8 text-xs font-mono mt-1"
                    required
                  />
                </div>
                <div>
                  <Label className="text-xs">Offered Item Description</Label>
                  <Input
                    value={noiForm.item_description}
                    onChange={(e) => setNoiForm({ ...noiForm, item_description: e.target.value })}
                    className="h-8 text-xs mt-1"
                    required
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Inspection Scope (21-Step Flowchart)</Label>
                <Select
                  value={noiForm.inspection_scope || "Stage Inspection"}
                  onValueChange={(v) => setNoiForm({ ...noiForm, inspection_scope: v })}
                >
                  <SelectTrigger className="h-8 text-xs mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Stage Inspection">Stage Inspection</SelectItem>
                    <SelectItem value="Final FAT">Final FAT</SelectItem>
                    <SelectItem value="Pre-Inspection Meeting (PIM)">Pre-Inspection Meeting (PIM)</SelectItem>
                    <SelectItem value="Sub-Order Material">Sub-Order Material</SelectItem>
                    <SelectItem value="External Client Witness">External Client Witness</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Inspection Milestone / Test</Label>
                <Input
                  value={noiForm.milestone_name}
                  onChange={(e) => setNoiForm({ ...noiForm, milestone_name: e.target.value })}
                  className="h-8 text-xs mt-1"
                  required
                />
              </div>
            </div>
            {noiForm.sub_order_id && (
              <div className="p-2 rounded bg-teal-50 border border-teal-200 text-teal-800 text-[11px] flex items-center justify-between">
                <span>Linked Sub-Order ID: <span className="font-mono font-semibold">{noiForm.sub_order_id}</span></span>
                <button
                  type="button"
                  onClick={() => setNoiForm({ ...noiForm, sub_order_id: "" })}
                  className="text-teal-700 underline text-[10px]"
                >
                  Unlink
                </button>
              </div>
            )}

            <div>
              <Label className="text-xs">Requested Inspection Date</Label>
              <Input
                type="date"
                value={noiForm.scheduled_date}
                onChange={(e) => setNoiForm({ ...noiForm, scheduled_date: e.target.value })}
                className="h-8 text-xs mt-1 font-mono"
                required
              />
              {isShortNotice(noiForm.scheduled_date) && (
                <div className="mt-1.5 p-2 rounded bg-amber-50 border border-amber-200 text-amber-800 text-[11px] flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  <span><b>Short Notice:</b> Less than 5 days. Flags for emergency coordinator approval.</span>
                </div>
              )}
            </div>

            <div>
              <Label className="text-xs">Yard / Shop Location</Label>
              <Input
                value={noiForm.inspection_location}
                onChange={(e) => setNoiForm({ ...noiForm, inspection_location: e.target.value })}
                className="h-8 text-xs mt-1"
                required
              />
            </div>

            <div>
              <Label className="text-xs">Detailed Scope / Procedure Reference</Label>
              <Textarea
                value={noiForm.scope}
                onChange={(e) => setNoiForm({ ...noiForm, scope: e.target.value })}
                className="text-xs min-h-[60px] mt-1"
              />
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="xs" onClick={() => setIssueNoiOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" size="xs" className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold">
                Submit NOI Callout
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── MODAL: CANCEL NOI ─────────────────────────────────────────────── */}
      <Dialog open={cancelNoiOpen} onOpenChange={setCancelNoiOpen}>
        <DialogContent className="max-w-md p-6">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-rose-700 flex items-center gap-1.5">
              <XCircle className="w-4 h-4" /> Cancel Notice of Inspection
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              {targetNoi?.assigned_inspector_id
                ? "An inspector is already assigned. Cancellation requires a mandatory reason and records an abortive inspection fee entry."
                : "No inspector assigned yet. Will cancel cleanly without abortive charges."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div className="p-2.5 rounded bg-gray-50 border border-gray-200 space-y-1 font-mono text-[11px]">
              <p><b>NOI Number:</b> {targetNoi?.notification_number || targetNoi?.id}</p>
              <p><b>Scheduled Date:</b> {targetNoi?.start_date}</p>
            </div>

            {targetNoi?.assigned_inspector_id && (
              <div className="p-2.5 rounded bg-rose-50 border border-rose-200 text-rose-800 text-xs">
                <b>Abortive Notice:</b> Inspector travel/standby costs may apply under contractual terms.
              </div>
            )}

            <div>
              <Label className="text-xs font-semibold">Mandatory Cancellation Reason</Label>
              <Textarea
                placeholder="Explain why the inspection cannot proceed as scheduled..."
                value={cancelForm.reason}
                onChange={(e) => setCancelForm({ reason: e.target.value })}
                className="text-xs min-h-[70px] mt-1"
                required
              />
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" size="xs" onClick={() => setCancelNoiOpen(false)}>
                Go Back
              </Button>
              <Button
                size="xs"
                onClick={handleCancelNoi}
                className="bg-rose-600 hover:bg-rose-700 text-white font-semibold"
              >
                Confirm Cancellation
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── MODAL: REVISE NOI ─────────────────────────────────────────────── */}
      <Dialog open={reviseNoiOpen} onOpenChange={setReviseNoiOpen}>
        <DialogContent className="max-w-md p-6">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-gray-900">
              Revise Notice of Inspection (Create Rev 01)
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              Updates will increment the revision counter and notify assigned inspectors for re-confirmation.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div>
              <Label className="text-xs">Rescheduled Date</Label>
              <Input
                type="date"
                value={reviseForm.scheduled_date}
                onChange={(e) => setReviseForm({ ...reviseForm, scheduled_date: e.target.value })}
                className="h-8 text-xs mt-1 font-mono"
              />
            </div>

            <div>
              <Label className="text-xs">Inspection Yard / Location</Label>
              <Input
                value={reviseForm.location}
                onChange={(e) => setReviseForm({ ...reviseForm, location: e.target.value })}
                className="h-8 text-xs mt-1"
              />
            </div>

            <div>
              <Label className="text-xs">Updated Scope / Notes</Label>
              <Input
                value={reviseForm.scope}
                onChange={(e) => setReviseForm({ ...reviseForm, scope: e.target.value })}
                className="h-8 text-xs mt-1"
              />
            </div>

            <div>
              <Label className="text-xs">Reason for Revision</Label>
              <Textarea
                placeholder="State reason for rescheduling or scope change..."
                value={reviseForm.revision_notes}
                onChange={(e) => setReviseForm({ ...reviseForm, revision_notes: e.target.value })}
                className="text-xs min-h-[60px] mt-1"
              />
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" size="xs" onClick={() => setReviseNoiOpen(false)}>
                Cancel
              </Button>
              <Button
                size="xs"
                onClick={handleReviseNoi}
                className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
              >
                Submit Revision
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── MODAL: 3-STAGE NCR RESOLUTION ─────────────────────────────────── */}
      <Dialog open={ncrModalOpen} onOpenChange={setNcrModalOpen}>
        <DialogContent className="max-w-lg p-6">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-rose-700 flex items-center gap-1.5">
              <AlertOctagon className="w-4 h-4" /> 3-Stage Vendor NCR Resolution Form
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              Mandatory formal RCA, CAPA, and rework verification evidence for Major NCR closeout.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div>
              <Label className="text-xs font-semibold">Stage 1: Immediate Containment Action</Label>
              <Textarea
                placeholder="What actions were taken immediately to quarantine defective material?"
                value={ncrForm.containment_action}
                onChange={(e) => setNcrForm({ ...ncrForm, containment_action: e.target.value })}
                className="text-xs min-h-[50px] mt-1"
                required
              />
            </div>

            <div>
              <Label className="text-xs font-semibold">Stage 2A: Root Cause Analysis (RCA)</Label>
              <Textarea
                placeholder="Detailed 5-Why or fishbone root cause finding..."
                value={ncrForm.root_cause}
                onChange={(e) => setNcrForm({ ...ncrForm, root_cause: e.target.value })}
                className="text-xs min-h-[50px] mt-1"
                required
              />
            </div>

            <div>
              <Label className="text-xs font-semibold">Stage 2B: Corrective & Preventive Action Plan (CAPA)</Label>
              <Textarea
                placeholder="Actions taken to permanently eliminate recurrence..."
                value={ncrForm.capa_plan}
                onChange={(e) => setNcrForm({ ...ncrForm, capa_plan: e.target.value })}
                className="text-xs min-h-[50px] mt-1"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-semibold">Committed Target Closure Date</Label>
                <Input
                  type="date"
                  value={ncrForm.target_closure_date}
                  onChange={(e) => setNcrForm({ ...ncrForm, target_closure_date: e.target.value })}
                  className="h-8 text-xs mt-1 font-mono"
                  required
                />
              </div>
              <div>
                <Label className="text-xs font-semibold">Stage 3: Rework Evidence File</Label>
                <Input
                  value={ncrForm.rework_evidence_file}
                  onChange={(e) => setNcrForm({ ...ncrForm, rework_evidence_file: e.target.value })}
                  className="h-8 text-xs mt-1 font-mono"
                  placeholder="Filename of NDE or chart"
                  required
                />
              </div>
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" size="xs" onClick={() => setNcrModalOpen(false)}>
                Cancel
              </Button>
              <Button
                size="xs"
                onClick={handleNcrSubmit}
                className="bg-rose-600 hover:bg-rose-700 text-white font-semibold"
              >
                Submit for IE Technical Review
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── MODAL: QUICK CORRECTION ───────────────────────────────────────── */}
      <Dialog open={quickCloseOpen} onOpenChange={setQuickCloseOpen}>
        <DialogContent className="max-w-md p-6">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-gray-900">
              Quick Correction / Missing Document Upload
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              For minor findings & punch items. Fast-tracked for IE sign-off without RCA/CAPA.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div>
              <Label className="text-xs font-semibold">Correction Details / Actions Taken</Label>
              <Textarea
                placeholder="Describe how the minor item was resolved (e.g. tag re-affixed, paint touched up)..."
                value={quickForm.correction_details}
                onChange={(e) => setQuickForm({ ...quickForm, correction_details: e.target.value })}
                className="text-xs min-h-[60px] mt-1"
                required
              />
            </div>

            <div>
              <Label className="text-xs font-semibold">Document / Photo Attachment</Label>
              <Input
                value={quickForm.uploaded_document_name}
                onChange={(e) => setQuickForm({ ...quickForm, uploaded_document_name: e.target.value })}
                className="h-8 text-xs mt-1 font-mono"
                placeholder="e.g. Photo_Tag_Replacement.jpg"
              />
            </div>

            <div>
              <Label className="text-xs">Remarks</Label>
              <Input
                value={quickForm.remarks}
                onChange={(e) => setQuickForm({ ...quickForm, remarks: e.target.value })}
                className="h-8 text-xs mt-1"
                placeholder="Optional notes"
              />
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" size="xs" onClick={() => setQuickCloseOpen(false)}>
                Cancel
              </Button>
              <Button
                size="xs"
                onClick={handleQuickSubmit}
                className="bg-blue-600 hover:bg-blue-700 text-white font-semibold"
              >
                Submit Correction
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── MODAL: UPDATE SCHEDULE & PROGRESS ─────────────────────────────── */}
      <Dialog open={scheduleModalOpen} onOpenChange={setScheduleModalOpen}>
        <DialogContent className="max-w-md p-6">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-gray-900">
              Update Milestone Schedule & Fabrication %
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              Baseline shifts mandate a delay reason code and recovery plan.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Contractual Baseline</Label>
                <Input
                  value={scheduleForm.baseline_date}
                  disabled
                  className="h-8 text-xs mt-1 bg-gray-100 font-mono"
                />
              </div>
              <div>
                <Label className="text-xs">Current Forecast Date</Label>
                <Input
                  type="date"
                  value={scheduleForm.forecast_date}
                  onChange={(e) => setScheduleForm({ ...scheduleForm, forecast_date: e.target.value })}
                  className="h-8 text-xs mt-1 font-mono"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-4 gap-2">
              <div>
                <Label className="text-[10px]">Eng %</Label>
                <Input
                  type="number"
                  value={scheduleForm.eng_pct}
                  onChange={(e) => setScheduleForm({ ...scheduleForm, eng_pct: Number(e.target.value) })}
                  className="h-8 text-xs mt-1"
                />
              </div>
              <div>
                <Label className="text-[10px]">Proc %</Label>
                <Input
                  type="number"
                  value={scheduleForm.proc_pct}
                  onChange={(e) => setScheduleForm({ ...scheduleForm, proc_pct: Number(e.target.value) })}
                  className="h-8 text-xs mt-1"
                />
              </div>
              <div>
                <Label className="text-[10px]">Fab %</Label>
                <Input
                  type="number"
                  value={scheduleForm.fab_pct}
                  onChange={(e) => setScheduleForm({ ...scheduleForm, fab_pct: Number(e.target.value) })}
                  className="h-8 text-xs mt-1 font-bold text-indigo-700"
                />
              </div>
              <div>
                <Label className="text-[10px]">Insp %</Label>
                <Input
                  type="number"
                  value={scheduleForm.insp_pct}
                  onChange={(e) => setScheduleForm({ ...scheduleForm, insp_pct: Number(e.target.value) })}
                  className="h-8 text-xs mt-1 font-bold text-emerald-700"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs font-semibold">Standard Delay Reason Code</Label>
              <Select
                value={scheduleForm.delay_reason_code}
                onValueChange={(val) => setScheduleForm({ ...scheduleForm, delay_reason_code: val })}
              >
                <SelectTrigger className="h-8 text-xs mt-1">
                  <SelectValue placeholder="Select reason" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="RAW_MATERIAL_DELAY">Raw Material Mill Bottleneck</SelectItem>
                  <SelectItem value="DESIGN_CLARIFICATION">Engineering / TQ Clarification Hold</SelectItem>
                  <SelectItem value="SHOP_CAPACITY">Shop Floor Machine Maintenance</SelectItem>
                  <SelectItem value="SUB_VENDOR">Sub-vendor Component Delivery</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-xs font-semibold">Committed Schedule Recovery Plan</Label>
              <Textarea
                placeholder="Explain specific mitigation (second shift, overtime, expedited freight)..."
                value={scheduleForm.recovery_plan}
                onChange={(e) => setScheduleForm({ ...scheduleForm, recovery_plan: e.target.value })}
                className="text-xs min-h-[50px] mt-1"
                required
              />
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" size="xs" onClick={() => setScheduleModalOpen(false)}>
                Cancel
              </Button>
              <Button
                size="xs"
                onClick={handleScheduleSubmit}
                className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
              >
                Save Schedule Update
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── MODAL: SUBMIT DISPATCH REQUEST ─────────────────────────────────── */}
      <Dialog open={dispatchModalOpen} onOpenChange={setDispatchModalOpen}>
        <DialogContent className="max-w-md p-6">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-gray-900">
              Submit Material Dispatch Request
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              Attach final packing list and crate measurements for Logistics Coordinator clearance.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">PO Line Item</Label>
                <Input
                  value={dispatchForm.item_id}
                  onChange={(e) => setDispatchForm({ ...dispatchForm, item_id: e.target.value })}
                  className="h-8 text-xs mt-1 font-mono"
                  required
                />
              </div>
              <div>
                <Label className="text-xs">Governing IRC No.</Label>
                <Input
                  value={dispatchForm.irc_number}
                  onChange={(e) => setDispatchForm({ ...dispatchForm, irc_number: e.target.value })}
                  className="h-8 text-xs mt-1 font-mono font-bold text-emerald-700"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Dispatch Quantity</Label>
                <Input
                  type="number"
                  value={dispatchForm.dispatch_qty}
                  onChange={(e) => setDispatchForm({ ...dispatchForm, dispatch_qty: e.target.value })}
                  className="h-8 text-xs mt-1 font-bold"
                  required
                />
              </div>
              <div>
                <Label className="text-xs">Packing List Reference</Label>
                <Input
                  value={dispatchForm.packing_list_ref}
                  onChange={(e) => setDispatchForm({ ...dispatchForm, packing_list_ref: e.target.value })}
                  className="h-8 text-xs mt-1 font-mono"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <Label className="text-[10px]">Gross Wt (kg)</Label>
                <Input
                  type="number"
                  value={dispatchForm.gross_weight_kg}
                  onChange={(e) => setDispatchForm({ ...dispatchForm, gross_weight_kg: e.target.value })}
                  className="h-8 text-xs mt-1"
                />
              </div>
              <div>
                <Label className="text-[10px]">Net Wt (kg)</Label>
                <Input
                  type="number"
                  value={dispatchForm.net_weight_kg}
                  onChange={(e) => setDispatchForm({ ...dispatchForm, net_weight_kg: e.target.value })}
                  className="h-8 text-xs mt-1"
                />
              </div>
              <div>
                <Label className="text-[10px]">Draft Invoice No</Label>
                <Input
                  value={dispatchForm.invoice_draft_ref}
                  onChange={(e) => setDispatchForm({ ...dispatchForm, invoice_draft_ref: e.target.value })}
                  className="h-8 text-xs mt-1 font-mono"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs">Crate Dimensions (L x W x H)</Label>
              <Input
                value={dispatchForm.crate_dimensions}
                onChange={(e) => setDispatchForm({ ...dispatchForm, crate_dimensions: e.target.value })}
                className="h-8 text-xs mt-1 font-mono"
                placeholder="e.g. 4.2m x 2.1m x 1.8m"
                required
              />
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" size="xs" onClick={() => setDispatchModalOpen(false)}>
                Cancel
              </Button>
              <Button
                size="xs"
                onClick={handleDispatchSubmit}
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
              >
                Submit Movement Request
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

