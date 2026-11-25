import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Calendar,
  FileSpreadsheet,
  Sparkles,
  Mail,
  Download,
  Lock,
  Unlock,
  CheckCircle2,
  AlertTriangle,
  FileText,
  RefreshCw,
  Upload,
  ShieldCheck,
  Truck,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { downloadAuthFile } from "@/utils/downloadAuthFile";
import {
  Phase4OperationsTab,
  Phase5CloseoutMncrTab,
  Phase5GovernanceRegistersTab,
} from "@/components/expediting/Phase45OperationsTabs";

export default function ExpeditingErpHubModal({
  open,
  onOpenChange,
  defaultTab = "schedule9",
  activePo,
  projectId,
  onUpdated,
}) {
  const [tab, setTab] = useState(defaultTab);
  const [loading, setLoading] = useState(false);

  // Tab 1: 9-Column Minimum Schedule
  const [scheduleData, setScheduleData] = useState(null);
  const [editedRows, setEditedRows] = useState([]);
  const [rebaselineReason, setRebaselineReason] = useState("");

  // Tab 2: Consolidated Project Weekly MSSR
  const [mssrData, setMssrData] = useState(null);

  // Tab 3: Progress Reports Review
  const [vprList, setVprList] = useState([]);
  const [reviewComment, setReviewComment] = useState("");

  // Tab 4: AI Agents (#2 PO/MR Review & #3 First Contact)
  const [mrNotes, setMrNotes] = useState("");
  const [mrFile, setMrFile] = useState(null);
  const [mrReview, setMrReview] = useState(null);
  const [contactDraft, setContactDraft] = useState(null);
  const [issueVdmsAccess, setIssueVdmsAccess] = useState(true);

  useEffect(() => {
    if (open) setTab(defaultTab);
  }, [open, defaultTab]);

  const loadSchedule = async () => {
    if (!activePo) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/schedule`);
      const json = await res.json();
      if (json.ok) {
        setScheduleData(json);
        setEditedRows(json.rows || []);
      }
    } catch (e) {
      toast.error("Failed to load 9-column PO schedule");
    } finally {
      setLoading(false);
    }
  };

  const loadMssr = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/v1/expediting/mssr/consolidated?project_id=${encodeURIComponent(projectId || "all")}`
      );
      const json = await res.json();
      if (json.ok) setMssrData(json);
    } catch (e) {
      toast.error("Failed to load consolidated MSSR");
    } finally {
      setLoading(false);
    }
  };

  const loadReportsAndAi = async () => {
    if (!activePo) return;
    setLoading(true);
    try {
      const [vprRes, ctxRes] = await Promise.all([
        fetch(`/api/v1/po/${encodeURIComponent(activePo)}/progress-reports`),
        fetch(`/api/v1/po/${encodeURIComponent(activePo)}/context`),
      ]);
      const vprJson = await vprRes.json();
      const ctxJson = await ctxRes.json();
      if (vprJson.ok) setVprList(vprJson.reports || []);
      if (ctxJson.ok) {
        if (ctxJson.ai_mr_review) setMrReview(ctxJson.ai_mr_review);
        if (ctxJson.first_contact_draft) setContactDraft(ctxJson.first_contact_draft);
      }
    } catch (e) {
      toast.error("Failed to load progress reports / AI context");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    if (tab === "schedule9") loadSchedule();
    else if (tab === "mssr") loadMssr();
    else if (tab === "vpr" || tab === "ai_agents") loadReportsAndAi();
  }, [open, tab, activePo, projectId]);

  const handleRowChange = (idx, field, val) => {
    setEditedRows((prev) => prev.map((r, i) => (i === idx ? { ...r, [field]: val } : r)));
  };

  const handleSaveSchedule = async ({ freeze = false } = {}) => {
    if (!activePo) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rows: editedRows,
          freeze_baseline: freeze,
          rebaseline_reason: rebaselineReason.trim() || undefined,
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Failed to save schedule");
        return;
      }
      setScheduleData((prev) => ({ ...prev, ...json }));
      setEditedRows(json.rows || []);
      setRebaselineReason("");
      toast.success(freeze ? "9-Column Schedule Baseline frozen!" : "9-Column Schedule saved.");
      if (onUpdated) onUpdated();
    } catch (e) {
      toast.error("Error saving schedule");
    } finally {
      setLoading(false);
    }
  };

  const handleReviewVpr = async (reportId, decision) => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/v1/po/${encodeURIComponent(activePo)}/progress-reports/${encodeURIComponent(reportId)}/review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, comments: reviewComment }),
        }
      );
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Failed to review progress report");
        return;
      }
      toast.success(`Progress Report marked ${decision}`);
      setReviewComment("");
      await loadReportsAndAi();
      if (onUpdated) onUpdated();
    } finally {
      setLoading(false);
    }
  };

  const handleRunAiMrReview = async () => {
    if (!activePo) return;
    setLoading(true);
    try {
      let res;
      if (mrFile) {
        const fd = new FormData();
        fd.append("file", mrFile);
        fd.append("notes", mrNotes);
        res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/ai-review-mr`, {
          method: "POST",
          body: fd,
        });
      } else {
        res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/ai-review-mr`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ notes: mrNotes }),
        });
      }
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "AI PO/MR Review failed");
        return;
      }
      setMrReview(json.review);
      toast.success(`PO/MR Review extracted (${json.review?.engine || "AI"})`);
      if (onUpdated) onUpdated();
    } catch (e) {
      toast.error("Failed to run AI PO/MR Review");
    } finally {
      setLoading(false);
    }
  };

  const handleRunFirstContact = async (markSent = false) => {
    if (!activePo) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/ai-first-contact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mark_sent: markSent,
          issue_vdms_access: markSent && issueVdmsAccess,
          subject: contactDraft?.subject,
          body: contactDraft?.body,
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Failed generating First Expediting Contact");
        return;
      }
      setContactDraft(json.draft);
      toast.success(
        markSent
          ? "First Expediting Contact logged as sent & VDMS access recorded!"
          : `First Expediting Contact drafted (${json.draft?.engine || "AI"})`
      );
      if (onUpdated) onUpdated();
    } catch (e) {
      toast.error("Error generating First Expediting Contact");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl max-h-[92vh] flex flex-col p-6 overflow-hidden">
        <DialogHeader className="pb-2 border-b border-gray-200 shrink-0">
          <DialogTitle className="text-base font-bold text-gray-900 flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-indigo-600" />
            NMDC Expediting ERP Workbench — {activePo ? `PO #${activePo}` : "Portfolio View"}
          </DialogTitle>
          <DialogDescription className="text-xs text-gray-500">
            9-Column Minimum Schedule &amp; ITP/Sub-Order matrix, Consolidated Weekly MSSR export, NMDC 7-Section Progress Reports, and PO/MR + First Contact AI Agents.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 h-auto p-1 bg-slate-100 rounded-lg shrink-0 gap-1">
            <TabsTrigger value="schedule9" className="text-[11px] py-1.5 font-semibold">
              <Calendar className="w-3.5 h-3.5 mr-1" /> 9-Col Schedule
            </TabsTrigger>
            <TabsTrigger value="mssr" className="text-[11px] py-1.5 font-semibold">
              <FileSpreadsheet className="w-3.5 h-3.5 mr-1" /> Weekly MSSR
            </TabsTrigger>
            <TabsTrigger value="vpr" className="text-[11px] py-1.5 font-semibold">
              <FileText className="w-3.5 h-3.5 mr-1" /> Progress Reports
            </TabsTrigger>
            <TabsTrigger value="ai_agents" className="text-[11px] py-1.5 font-semibold">
              <Sparkles className="w-3.5 h-3.5 mr-1" /> AI Agents (#2 &amp; #3)
            </TabsTrigger>
            <TabsTrigger value="phase4_ops" className="text-[11px] py-1.5 font-semibold">
              <ShieldCheck className="w-3.5 h-3.5 mr-1" /> IAP, MOM &amp; Look-Ahead
            </TabsTrigger>
            <TabsTrigger value="phase5_closeout" className="text-[11px] py-1.5 font-semibold">
              <Truck className="w-3.5 h-3.5 mr-1" /> MNCR &amp; LD Closeout
            </TabsTrigger>
            <TabsTrigger value="phase5_registers" className="text-[11px] py-1.5 font-semibold">
              <Users className="w-3.5 h-3.5 mr-1" /> Governance Registers
            </TabsTrigger>
          </TabsList>

          {/* ── TAB 1: 9-COLUMN SCHEDULE ───────────────────────────────────── */}
          <TabsContent value="schedule9" className="flex-1 overflow-y-auto py-3 space-y-3">
            {!activePo ? (
              <p className="text-xs text-gray-500 py-8 text-center">Select a Purchase Order first.</p>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-50 p-3 rounded-lg border text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={scheduleData?.frozen ? "bg-indigo-100 text-indigo-800" : "bg-amber-100 text-amber-800"}>
                      {scheduleData?.frozen ? <Lock className="w-3 h-3 mr-1" /> : <Unlock className="w-3 h-3 mr-1" />}
                      {scheduleData?.frozen ? `Baseline Frozen (${scheduleData?.frozen_by || "Locked"})` : "Baseline Editable (Pre-Freeze)"}
                    </Badge>
                    {scheduleData?.neas?.platform && <Badge variant="outline">Platform: {scheduleData.neas.platform}</Badge>}
                    {scheduleData?.neas?.ros_date && <Badge variant="outline">ROS: {scheduleData.neas.ros_date}</Badge>}
                    {scheduleData?.neas?.cdd_date && <Badge variant="outline">CDD: {scheduleData.neas.cdd_date}</Badge>}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <label className="inline-flex items-center px-2.5 h-7 rounded-md border border-indigo-300 bg-indigo-50 text-indigo-800 hover:bg-indigo-100 text-xs font-semibold cursor-pointer">
                      <Upload className="w-3.5 h-3.5 mr-1" /> Import (.xlsx/.csv/.pdf)
                      <input
                        type="file"
                        accept=".xlsx,.xlsm,.csv,.pdf"
                        className="hidden"
                        onChange={async (e) => {
                          const f = e.target.files?.[0];
                          e.target.value = "";
                          if (!f || !activePo) return;
                          setLoading(true);
                          try {
                            const fd = new FormData();
                            fd.append("file", f, f.name);
                            const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/schedule/upload`, {
                              method: "POST",
                              body: fd,
                            });
                            const json = await res.json().catch(() => ({}));
                            if (!res.ok || !json.ok) {
                              toast.error(json.detail || "Failed importing schedule file");
                              return;
                            }
                            setScheduleData((prev) => ({ ...(prev || {}), ...json }));
                            setEditedRows(json.rows || []);
                            toast.success(`Imported ${json.parsed_count} rows via ${json.engine}`);
                            (json.warnings || []).forEach((w) => toast.warning(w, { duration: 6000 }));
                            if (onUpdated) onUpdated();
                          } finally {
                            setLoading(false);
                          }
                        }}
                      />
                    </label>
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() =>
                        downloadAuthFile(
                          `/api/v1/po/${encodeURIComponent(activePo)}/schedule/export-xlsx`,
                          `${activePo}_Schedule_9Col.xlsx`
                        )
                      }
                      className="border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 h-7 text-xs font-semibold"
                    >
                      <Download className="w-3.5 h-3.5 mr-1" /> Export 9-Col .xlsx
                    </Button>
                    {!scheduleData?.frozen && (
                      <Button size="xs" onClick={() => handleSaveSchedule({ freeze: true })} disabled={loading} className="bg-slate-800 hover:bg-slate-900 text-white h-7 text-xs">
                        <Lock className="w-3 h-3 mr-1" /> Freeze Baseline
                      </Button>
                    )}
                    <Button size="xs" onClick={() => handleSaveSchedule({ freeze: false })} disabled={loading} className="bg-indigo-600 hover:bg-indigo-700 text-white h-7 text-xs">
                      Save Changes
                    </Button>
                  </div>
                </div>

                {scheduleData?.frozen && (
                  <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 p-2 rounded-lg text-xs">
                    <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0" />
                    <Input
                      value={rebaselineReason}
                      onChange={(e) => setRebaselineReason(e.target.value)}
                      placeholder="Rule 2: Baseline is locked. Enter Expediting Manager Re-Baseline Justification only if moving contractual baseline..."
                      className="h-7 text-xs bg-white flex-1"
                    />
                  </div>
                )}

                <div className="border rounded-lg overflow-x-auto">
                  <table className="w-full text-[11px] text-left">
                    <thead className="bg-slate-900 text-white">
                      <tr>
                        <th className="p-2 w-10">Sr.</th>
                        <th className="p-2 min-w-[230px]">Activity</th>
                        <th className="p-2 w-20">Dur (d)</th>
                        <th className="p-2 w-28">Baseline Start</th>
                        <th className="p-2 w-28">Baseline End</th>
                        <th className="p-2 w-28">Forecast Start</th>
                        <th className="p-2 w-28">Forecast End</th>
                        <th className="p-2 w-24">Dependency</th>
                        <th className="p-2 w-16">%</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {editedRows.map((r, idx) => (
                        <tr
                          key={r.id || idx}
                          className={
                            r.source_kind === "itp_witness_hold"
                              ? "bg-teal-50/40"
                              : r.source_kind === "suborder"
                                ? "bg-amber-50/40"
                                : "hover:bg-slate-50"
                          }
                        >
                          <td className="p-1.5 font-mono text-gray-500">{r.sr}</td>
                          <td className="p-1.5 font-medium text-gray-900">
                            {r.act}
                            {r.source_kind !== "minimum" && (
                              <Badge variant="outline" className="ml-1.5 text-[9px] uppercase">
                                {r.source_kind === "itp_witness_hold" ? "ITP W/H" : r.source_kind}
                              </Badge>
                            )}
                          </td>
                          <td className="p-1">
                            <Input
                              value={r.duration_days || ""}
                              disabled={scheduleData?.frozen && !rebaselineReason}
                              onChange={(e) => handleRowChange(idx, "duration_days", e.target.value)}
                              className="h-6 text-[11px] px-1.5"
                            />
                          </td>
                          <td className="p-1">
                            <Input
                              type="date"
                              value={r.bS || ""}
                              disabled={scheduleData?.frozen && !rebaselineReason}
                              onChange={(e) => handleRowChange(idx, "bS", e.target.value)}
                              className="h-6 text-[11px] px-1"
                            />
                          </td>
                          <td className="p-1">
                            <Input
                              type="date"
                              value={r.bE || ""}
                              disabled={scheduleData?.frozen && !rebaselineReason}
                              onChange={(e) => handleRowChange(idx, "bE", e.target.value)}
                              className="h-6 text-[11px] px-1"
                            />
                          </td>
                          <td className="p-1">
                            <Input
                              type="date"
                              value={r.fS || ""}
                              onChange={(e) => handleRowChange(idx, "fS", e.target.value)}
                              className="h-6 text-[11px] px-1"
                            />
                          </td>
                          <td className="p-1">
                            <Input
                              type="date"
                              value={r.fE || ""}
                              onChange={(e) => handleRowChange(idx, "fE", e.target.value)}
                              className="h-6 text-[11px] px-1"
                            />
                          </td>
                          <td className="p-1">
                            <Input
                              value={r.dependency || ""}
                              onChange={(e) => handleRowChange(idx, "dependency", e.target.value)}
                              placeholder="FS / Predec."
                              className="h-6 text-[11px] px-1.5"
                            />
                          </td>
                          <td className="p-1">
                            <Input
                              value={r.pct || ""}
                              onChange={(e) => handleRowChange(idx, "pct", e.target.value)}
                              placeholder="0"
                              className="h-6 text-[11px] px-1.5"
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </TabsContent>

          {/* ── TAB 2: CONSOLIDATED PROJECT WEEKLY MSSR ────────────────────── */}
          <TabsContent value="mssr" className="flex-1 overflow-y-auto py-3 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="grid grid-cols-5 gap-2 flex-1">
                {[
                  ["Total POs", mssrData?.kpis?.total_pos ?? 0, "bg-slate-50"],
                  ["Slipped POs", mssrData?.kpis?.pos_with_slips ?? 0, "bg-rose-50 text-rose-800"],
                  ["Open AOC", mssrData?.kpis?.open_concerns ?? 0, "bg-amber-50 text-amber-800"],
                  ["Buyer Ack Escal.", mssrData?.kpis?.buyer_ack_escalations ?? 0, "bg-orange-50 text-orange-800"],
                  ["Tech. Closed", mssrData?.kpis?.technically_closed ?? 0, "bg-emerald-50 text-emerald-800"],
                ].map(([lbl, val, cls]) => (
                  <div key={lbl} className={`p-2 rounded-lg border text-center ${cls}`}>
                    <div className="text-[10px] font-semibold uppercase opacity-75">{lbl}</div>
                    <div className="text-base font-bold">{val}</div>
                  </div>
                ))}
              </div>
              <Button
                size="sm"
                onClick={() =>
                  downloadAuthFile(
                    `/api/v1/expediting/mssr/export-xlsx?project_id=${encodeURIComponent(projectId || "all")}`,
                    "Consolidated_Weekly_MSSR.xlsx"
                  )
                }
                className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-9 font-semibold shrink-0"
              >
                <Download className="w-3.5 h-3.5 mr-1.5" /> Export Weekly MSSR (.xlsx)
              </Button>
            </div>

            <div className="border rounded-lg overflow-x-auto">
              <table className="w-full text-[11px] text-left">
                <thead className="bg-slate-800 text-white">
                  <tr>
                    <th className="p-2">PO #</th>
                    <th className="p-2">Supplier</th>
                    <th className="p-2">Platform</th>
                    <th className="p-2">CDD</th>
                    <th className="p-2">ROS</th>
                    <th className="p-2">PO Ack</th>
                    <th className="p-2">Slips</th>
                    <th className="p-2">Crit Sub</th>
                    <th className="p-2">Overdue Docs</th>
                    <th className="p-2">AOC</th>
                    <th className="p-2">Latest VPR</th>
                    <th className="p-2">Closeout</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(mssrData?.po_rows || []).map((r) => (
                    <tr key={r.po} className="hover:bg-slate-50">
                      <td className="p-2 font-mono font-bold text-indigo-700">{r.po}</td>
                      <td className="p-2">{r.supplier}</td>
                      <td className="p-2">{r.platform || "—"}</td>
                      <td className="p-2 font-mono">{r.cdd_date || "—"}</td>
                      <td className="p-2 font-mono">{r.ros_date || "—"}</td>
                      <td className="p-2">
                        <Badge className={r.buyer_escalation ? "bg-rose-100 text-rose-800 text-[10px]" : "bg-slate-100 text-slate-700 text-[10px]"}>
                          {r.ack_status}
                        </Badge>
                      </td>
                      <td className="p-2 font-bold text-rose-700">{r.slipped_tasks}</td>
                      <td className="p-2">{r.critical_suborders}</td>
                      <td className="p-2">{r.overdue_docs}</td>
                      <td className="p-2">{r.open_concerns}</td>
                      <td className="p-2">{r.latest_vpr}</td>
                      <td className="p-2">{r.closeout_stage} ({r.mrv_pct}%)</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </TabsContent>

          {/* ── TAB 3: PROGRESS REPORT REVIEW & EXPORT ─────────────────────── */}
          <TabsContent value="vpr" className="flex-1 overflow-y-auto py-3 space-y-3">
            {vprList.length === 0 ? (
              <div className="text-center py-10 text-xs text-gray-500">
                No Vendor Progress Reports submitted yet for PO #{activePo}. Vendors can create &amp; submit 7-Section Progress Reports in Vendor Portal.
              </div>
            ) : (
              vprList.slice().reverse().map((rep) => (
                <div key={rep.id} className="border rounded-xl p-4 bg-white space-y-2 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="font-bold text-sm">Progress Report #{rep.report_no}</span>
                      <span className="ml-2 text-gray-500">
                        Period: {rep.period_from || "—"} to {rep.period_to || "—"} (Round {rep.round})
                      </span>
                      <Badge className="ml-2 text-[10px]" variant={rep.status === "Agreed" ? "default" : "outline"}>
                        {rep.status}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() =>
                          downloadAuthFile(
                            `/api/v1/po/${encodeURIComponent(activePo)}/progress-reports/${encodeURIComponent(rep.id)}/export-docx`,
                            `${activePo}_Progress_Report_${rep.report_no || "01"}.docx`
                          )
                        }
                        className="h-7 bg-blue-50 text-blue-800 border-blue-200 font-semibold"
                      >
                        <Download className="w-3 h-3 mr-1" /> .docx
                      </Button>
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() =>
                          downloadAuthFile(
                            `/api/v1/po/${encodeURIComponent(activePo)}/progress-reports/${encodeURIComponent(rep.id)}/export-pdf`,
                            `${activePo}_Progress_Report_${rep.report_no || "01"}.pdf`
                          )
                        }
                        className="h-7 bg-rose-50 text-rose-800 border-rose-200 font-semibold"
                      >
                        <Download className="w-3 h-3 mr-1" /> .pdf
                      </Button>
                    </div>
                  </div>
                  <div className="grid grid-cols-5 gap-2 bg-slate-50 p-2 rounded">
                    {["engineering", "procurement", "manufacturing", "delivery", "overall"].map((k) => (
                      <div key={k} className="text-center">
                        <div className="text-[10px] uppercase text-gray-500">{k}</div>
                        <div className="font-bold">
                          P: {rep.po_summary?.[k]?.planned ?? 0}% / A: {rep.po_summary?.[k]?.actual ?? 0}%
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="text-gray-700"><b>Areas of Concern:</b> {rep.areas_of_concern || "None"}</div>
                  {rep.status !== "Agreed" && (
                    <div className="flex items-center gap-2 pt-2 border-t">
                      <Input
                        value={reviewComment}
                        onChange={(e) => setReviewComment(e.target.value)}
                        placeholder="Expeditor review comment (required if returning)..."
                        className="h-7 text-xs flex-1"
                      />
                      <Button size="xs" onClick={() => handleReviewVpr(rep.id, "Returned")} disabled={loading} variant="outline" className="h-7 text-rose-700 border-rose-300">
                        Return
                      </Button>
                      <Button size="xs" onClick={() => handleReviewVpr(rep.id, "Agreed")} disabled={loading} className="h-7 bg-emerald-600 hover:bg-emerald-700 text-white">
                        <CheckCircle2 className="w-3 h-3 mr-1" /> Agree Report
                      </Button>
                    </div>
                  )}
                </div>
              ))
            )}
          </TabsContent>

          {/* ── TAB 4: AI AGENTS (#2 PO/MR & #3 FIRST CONTACT) ─────────────── */}
          <TabsContent value="ai_agents" className="flex-1 overflow-y-auto py-3 space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Agent #2 */}
              <div className="border rounded-xl p-4 bg-white space-y-3 text-xs">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-indigo-900 flex items-center gap-1.5">
                    <Sparkles className="w-4 h-4 text-indigo-600" />
                    Action #2 AI Agent: PO &amp; MR Review
                  </h4>
                  {mrReview?.engine && <Badge variant="outline" className="text-[10px]">{mrReview.engine}</Badge>}
                </div>
                <div className="space-y-2">
                  <Label className="text-[11px]">Optional PO / Material Requisition PDF</Label>
                  <Input type="file" accept=".pdf" onChange={(e) => setMrFile(e.target.files?.[0] || null)} className="h-8 text-xs" />
                  <Textarea
                    rows={2}
                    value={mrNotes}
                    onChange={(e) => setMrNotes(e.target.value)}
                    placeholder="Additional PO/MR clauses, SIL/HAZOP, PBG/LC, or PIM requirements..."
                    className="text-xs"
                  />
                  <Button size="sm" onClick={handleRunAiMrReview} disabled={loading || !activePo} className="w-full bg-indigo-600 hover:bg-indigo-700 text-white h-8">
                    {loading ? <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Sparkles className="w-3.5 h-3.5 mr-1" />}
                    Analyze PO &amp; MR Requirements
                  </Button>
                </div>
                {mrReview && (
                  <div className="bg-indigo-50/60 border border-indigo-200 rounded-lg p-3 space-y-2 max-h-64 overflow-y-auto">
                    <div className="font-semibold text-indigo-950">{mrReview.expeditor_risk_notes}</div>
                    <div><b>HOLDs:</b> {(mrReview.holds || []).join(" • ") || "None"}</div>
                    <div><b>Tech Req:</b> {(mrReview.technical_requirements || []).join(" • ")}</div>
                    <div><b>Docs/SDRL:</b> {(mrReview.doc_requirements || []).join(" • ")}</div>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      <Badge variant="outline">PIM: {mrReview.pim_required?.required ? "Yes" : "No"}</Badge>
                      <Badge variant="outline">HAZOP/SIL: {mrReview.hazop_sil?.required ? "Yes" : "No"}</Badge>
                      <Badge variant="outline">PBG: {mrReview.pbg_required?.required ? "Yes" : "Verify"}</Badge>
                      <Badge variant="outline">LC: {mrReview.lc_requirement?.required ? "Yes" : "Verify"}</Badge>
                    </div>
                  </div>
                )}
              </div>

              {/* Agent #3 */}
              <div className="border rounded-xl p-4 bg-white space-y-3 text-xs">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-emerald-900 flex items-center gap-1.5">
                    <Mail className="w-4 h-4 text-emerald-600" />
                    Action #3 AI Agent: First Expediting Contact
                  </h4>
                  <Button size="xs" variant="outline" onClick={() => handleRunFirstContact(false)} disabled={loading || !activePo} className="h-7">
                    <Sparkles className="w-3 h-3 mr-1" /> Generate Draft
                  </Button>
                </div>
                <div className="space-y-2">
                  <Label className="text-[11px]">Email Subject</Label>
                  <Input
                    value={contactDraft?.subject || ""}
                    onChange={(e) => setContactDraft((prev) => ({ ...(prev || {}), subject: e.target.value }))}
                    placeholder="Click 'Generate Draft' to populate from Action #2 + NEAS PO terms..."
                    className="h-8 text-xs"
                  />
                  <Label className="text-[11px]">Letter / Email Body</Label>
                  <Textarea
                    rows={8}
                    value={contactDraft?.body || ""}
                    onChange={(e) => setContactDraft((prev) => ({ ...(prev || {}), body: e.target.value }))}
                    className="text-xs font-mono"
                  />
                  <label className="flex items-center gap-2 text-[11px] text-gray-700">
                    <input type="checkbox" checked={issueVdmsAccess} onChange={(e) => setIssueVdmsAccess(e.target.checked)} />
                    Also record Doc Controller VDMS Templates &amp; Portal Access Issued (Action #4)
                  </label>
                  <Button size="sm" onClick={() => handleRunFirstContact(true)} disabled={loading || !activePo} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white h-8">
                    <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Approve, Log Sent &amp; Record Intro Contact
                  </Button>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* ── TAB 5: PHASE 4 CLIENT IAP, MOM & LOOK-AHEAD ────────────────── */}
          <TabsContent value="phase4_ops" className="flex-1 overflow-y-auto py-3">
            <Phase4OperationsTab activePo={activePo} projectId={projectId} onUpdated={onUpdated} />
          </TabsContent>

          {/* ── TAB 6: PHASE 5A/5B STORES MNCR & LD CLOSEOUT ───────────────── */}
          <TabsContent value="phase5_closeout" className="flex-1 overflow-y-auto py-3">
            <Phase5CloseoutMncrTab activePo={activePo} onUpdated={onUpdated} />
          </TabsContent>

          {/* ── TAB 7: PHASE 5C GOVERNANCE REGISTERS ──────────────────────── */}
          <TabsContent value="phase5_registers" className="flex-1 overflow-y-auto py-3">
            <Phase5GovernanceRegistersTab activePo={activePo} projectId={projectId} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
