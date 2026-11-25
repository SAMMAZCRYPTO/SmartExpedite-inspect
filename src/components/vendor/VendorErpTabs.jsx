import React, { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CheckCircle2, AlertTriangle, Plus, Trash2, Download, FileText, PackageCheck } from "lucide-react";
import { toast } from "sonner";
import { downloadAuthFile } from "@/utils/downloadAuthFile";

export function VendorAckAndCloseoutTab({ selectedPo, poContext, onUpdated }) {
  const [ackStatus, setAckStatus] = useState("Unconditional");
  const [openPoints, setOpenPoints] = useState("");
  const [mrbDate, setMrbDate] = useState("");
  const [spirDate, setSpirDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [iapData, setIapData] = useState(null);
  const [mncrs, setMncrs] = useState([]);
  const [rectifyNotes, setRectifyNotes] = useState({});

  const loadPhase45Vendor = async () => {
    if (!selectedPo) return;
    try {
      const [iRes, mRes] = await Promise.all([
        fetch(`/api/v1/po/${encodeURIComponent(selectedPo)}/iap`),
        fetch(`/api/v1/po/${encodeURIComponent(selectedPo)}/mncr`),
      ]);
      const [iJson, mJson] = await Promise.all([iRes.json(), mRes.json()]);
      if (iJson.ok) setIapData(iJson);
      if (mJson.ok) setMncrs(mJson.mncrs || []);
    } catch {
      /* ignore transient fetch error */
    }
  };

  useEffect(() => {
    setAckStatus(poContext?.ack?.st || "Unconditional");
    setOpenPoints(poContext?.ack?.pts || "");
    setMrbDate(poContext?.close_state?.mrb_submitted_on || poContext?.close_state?.mrbSubOn || "");
    setSpirDate(poContext?.close_state?.spir_submitted_on || poContext?.close_state?.spirSubOn || "");
    loadPhase45Vendor();
  }, [poContext, selectedPo]);

  const handleRectifyMncr = async (mncrId) => {
    const notes = (rectifyNotes[mncrId] || "").trim();
    if (!notes) {
      toast.error("Enter rectification / replacement delivery note reference.");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(
        `/api/v1/po/${encodeURIComponent(selectedPo)}/mncr/${encodeURIComponent(mncrId)}/vendor-rectify`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rectification_details: notes, rectification_notes: notes }),
        }
      );
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Failed submitting MNCR rectification");
        return;
      }
      toast.success(`Rectification submitted for ${json.mncr?.mncr_no || "MNCR"}.`);
      setRectifyNotes((prev) => ({ ...prev, [mncrId]: "" }));
      await loadPhase45Vendor();
      if (onUpdated) onUpdated();
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAck = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/v1/vendor/po-acknowledgement", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          po_number: selectedPo,
          status: ackStatus,
          open_points: openPoints,
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Failed saving PO acknowledgement");
        return;
      }
      toast.success(
        ackStatus === "With comments"
          ? "PO Acknowledgement submitted with comments — escalated to Buyer for settlement."
          : "Unconditional PO Acknowledgement recorded."
      );
      if (onUpdated) onUpdated();
    } finally {
      setSaving(false);
    }
  };

  const handleSaveMrbSpir = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/v1/vendor/mrb-spir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          po_number: selectedPo,
          mrb_submitted_on: mrbDate,
          spir_submitted_on: spirDate,
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Failed updating MRB/SPIR dates");
        return;
      }
      toast.success(`Closeout milestones saved (${json.closeout?.stage_label || "Open"})`);
      if (onUpdated) onUpdated();
    } finally {
      setSaving(false);
    }
  };

  const cs = poContext?.close_state || {};
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card className="border-gray-200/80 shadow-xs">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-bold">PO Acknowledgement (Workflow Action #8)</CardTitle>
            <Badge className={poContext?.ack?.buyer_escalation_required ? "bg-rose-100 text-rose-800" : "bg-emerald-100 text-emerald-800"}>
              {poContext?.ack?.st || "Pending"}
            </Badge>
          </div>
          <CardDescription className="text-xs">
            Confirm unconditional PO acceptance or list commercial/technical exceptions requiring Buyer settlement.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          <div>
            <Label className="text-xs">Acknowledgement Status</Label>
            <Select value={ackStatus} onValueChange={setAckStatus}>
              <SelectTrigger className="h-8 text-xs mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Pending">Pending</SelectItem>
                <SelectItem value="With comments">With comments (Escalate to Buyer)</SelectItem>
                <SelectItem value="Unconditional">Unconditional</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Exceptions / Open Points for Buyer</Label>
            <Textarea
              rows={3}
              value={openPoints}
              onChange={(e) => setOpenPoints(e.target.value)}
              placeholder="If acknowledging with comments, specify exact clause deviations..."
              className="text-xs mt-1"
            />
          </div>
          {poContext?.ack?.buyer_escalation_required && (
            <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>Pending Buyer Settlement — unconditional acknowledgement required before fabrication gate.</span>
            </div>
          )}
          <Button size="sm" onClick={handleSaveAck} disabled={saving} className="bg-indigo-600 hover:bg-indigo-700 text-white h-8">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" /> Submit PO Acknowledgement
          </Button>
        </CardContent>
      </Card>

      <Card className="border-gray-200/80 shadow-xs">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-bold">SPIR &amp; Databook (MRB) Submission</CardTitle>
            <Badge variant="outline">{cs.stage_label || "Open"}</Badge>
          </div>
          <CardDescription className="text-xs">
            Track Spare Parts Interchangeability Record (SPIR) &amp; Manufacturer Record Book (MRB) toward Technical Closeout.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">SPIR Submission Date (If Applicable)</Label>
              <Input type="date" value={spirDate} onChange={(e) => setSpirDate(e.target.value)} className="h-8 text-xs mt-1" />
            </div>
            <div>
              <Label className="text-xs">MRB Databook Submission Date</Label>
              <Input type="date" value={mrbDate} onChange={(e) => setMrbDate(e.target.value)} className="h-8 text-xs mt-1" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 pt-1 text-center">
            <div className="p-2 rounded bg-slate-50 border">
              <div className="text-[10px] text-gray-500">Site MRV</div>
              <div className="font-bold">{cs.mrv_pct ?? 0}%</div>
            </div>
            <div className="p-2 rounded bg-slate-50 border">
              <div className="text-[10px] text-gray-500">MRB Custodian Approval</div>
              <div className="font-bold">{cs.mrb_approved_on || "Pending"}</div>
            </div>
            <div className="p-2 rounded bg-slate-50 border">
              <div className="text-[10px] text-gray-500">Commercial Settlement</div>
              <div className="font-bold">{cs.commercially_closed ? "Cleared" : "Open"}</div>
            </div>
          </div>
          <Button size="sm" onClick={handleSaveMrbSpir} disabled={saving} className="bg-emerald-600 hover:bg-emerald-700 text-white h-8">
            <PackageCheck className="w-3.5 h-3.5 mr-1.5" /> Save SPIR / MRB Dates
          </Button>
        </CardContent>
      </Card>

      {(iapData?.requires_client_iap || mncrs.length > 0) && (
        <Card className="lg:col-span-2 border-gray-200/80 shadow-xs">
          <CardHeader className="pb-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-sm font-bold">Client IAP Gate &amp; Stores MNCR Rectifications</CardTitle>
              {iapData?.requires_client_iap && (
                <Badge
                  className={
                    iapData?.iap_package?.client_status === "APPROVED"
                      ? "bg-emerald-100 text-emerald-800 text-[10px]"
                      : "bg-amber-100 text-amber-800 text-[10px]"
                  }
                >
                  Client IAP: {iapData?.iap_package?.client_status || "NOT_SUBMITTED"}
                </Badge>
              )}
            </div>
            <CardDescription className="text-xs">
              Track Client Inspection &amp; Acceptance Plan clearance and respond to any Stores Material Non-Conformance Reports (MNCR).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            {mncrs.length === 0 ? (
              <p className="text-gray-500 py-1">No Stores MNCR shortage or damage items recorded for PO #{selectedPo}.</p>
            ) : (
              mncrs.map((m) => (
                <div key={m.id} className="p-3 rounded-lg border bg-slate-50 flex flex-col md:flex-row md:items-center justify-between gap-2">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-rose-800">{m.mncr_no}</span>
                      <Badge variant="outline" className="text-[10px]">{m.status}</Badge>
                      {m.stamped_delivery_note_ref && (
                        <span className="text-[10px] text-gray-500 font-mono">DN: {m.stamped_delivery_note_ref}</span>
                      )}
                    </div>
                    <p className="text-gray-800">{m.description}</p>
                    {m.pmt_return_notes && (
                      <p className="text-[11px] text-rose-700"><b>PMT Instructions:</b> {m.pmt_return_notes}</p>
                    )}
                    {m.vendor_rectification_notes && (
                      <p className="text-[11px] text-emerald-700"><b>Vendor Rectification:</b> {m.vendor_rectification_notes}</p>
                    )}
                  </div>
                  {m.status === "RETURNED_TO_VENDOR" && (
                    <div className="flex items-center gap-2 md:w-80 shrink-0">
                      <Input
                        value={rectifyNotes[m.id] || ""}
                        onChange={(e) => setRectifyNotes((p) => ({ ...p, [m.id]: e.target.value }))}
                        placeholder="Replacement dispatch / action ref..."
                        className="h-7 text-xs bg-white"
                      />
                      <Button size="xs" onClick={() => handleRectifyMncr(m.id)} disabled={saving} className="h-7 bg-indigo-600 hover:bg-indigo-700 text-white shrink-0">
                        Rectify
                      </Button>
                    </div>
                  )}
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function VendorSubOrdersTab({ selectedPo, poContext, onUpdated, onRaiseSubOrderNoi }) {
  const [form, setForm] = useState({
    vendor: "",
    material: "",
    sub_po_no: "",
    req_delivery: "",
    forecast_delivery: "",
    unpriced_po_ref: "",
    critical: true,
  });
  const [saving, setSaving] = useState(false);

  const subOrders = poContext?.sub_orders || [];

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await fetch("/api/v1/vendor/sub-orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ po_number: selectedPo, ...form }),
      });
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Failed adding sub-order");
        return;
      }
      toast.success("Sub-order saved & mirrored to Expeditor Plan / Schedule.");
      setForm({ vendor: "", material: "", sub_po_no: "", req_delivery: "", forecast_delivery: "", unpriced_po_ref: "", critical: true });
      if (onUpdated) onUpdated();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    const res = await fetch(`/api/v1/vendor/sub-orders/${encodeURIComponent(id)}?po=${encodeURIComponent(selectedPo)}`, {
      method: "DELETE",
    });
    if (res.ok) {
      toast.success("Sub-order removed.");
      if (onUpdated) onUpdated();
    }
  };

  return (
    <Card className="border-gray-200/80 shadow-xs">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-bold">Critical Sub-Orders &amp; Unpriced Sub-PO Copies (Z002 / Rule 3)</CardTitle>
        <CardDescription className="text-xs">
          Declare all bought-out components, unpriced sub-order PO references, and forecast deliveries. Critical items automatically appear in the 9-column schedule and NMDC Progress Report Annexure.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-xs">
        <form onSubmit={handleAdd} className="grid grid-cols-2 md:grid-cols-7 gap-2 bg-slate-50 p-3 rounded-lg border">
          <Input value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} placeholder="Sub-Vendor *" className="h-8 text-xs bg-white" required />
          <Input value={form.material} onChange={(e) => setForm({ ...form, material: e.target.value })} placeholder="Bought-out Material *" className="h-8 text-xs bg-white" required />
          <Input value={form.sub_po_no} onChange={(e) => setForm({ ...form, sub_po_no: e.target.value })} placeholder="Sub-PO #" className="h-8 text-xs bg-white" />
          <Input type="date" value={form.req_delivery} onChange={(e) => setForm({ ...form, req_delivery: e.target.value })} title="Required Delivery" className="h-8 text-xs bg-white" />
          <Input type="date" value={form.forecast_delivery} onChange={(e) => setForm({ ...form, forecast_delivery: e.target.value })} title="Forecast Delivery" className="h-8 text-xs bg-white" />
          <Input value={form.unpriced_po_ref} onChange={(e) => setForm({ ...form, unpriced_po_ref: e.target.value })} placeholder="Unpriced PO Ref" className="h-8 text-xs bg-white" />
          <Button type="submit" size="sm" disabled={saving} className="h-8 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold">
            <Plus className="w-3.5 h-3.5 mr-1" /> Add
          </Button>
        </form>

        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-gray-50 border-b text-gray-600 font-semibold">
              <tr>
                <th className="p-2.5">Sub-Vendor</th>
                <th className="p-2.5">Material / Scope</th>
                <th className="p-2.5">Sub-PO #</th>
                <th className="p-2.5">Unpriced PO</th>
                <th className="p-2.5">Required Date</th>
                <th className="p-2.5">Forecast Date</th>
                <th className="p-2.5">Float Status</th>
                <th className="p-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {subOrders.length === 0 ? (
                <tr><td colSpan={8} className="p-6 text-center text-gray-500">No sub-orders listed yet.</td></tr>
              ) : (
                subOrders.map((raw) => {
                  const s = {
                    ...raw,
                    vendor: raw.vendor || raw.sub || "",
                    material: raw.material || raw.item || "",
                    sub_po_no: raw.sub_po_no || raw.no || "",
                    req_delivery: raw.req_delivery || raw.req || raw.raw || "",
                    forecast_delivery: raw.forecast_delivery || raw.fc || raw.over || raw.clear || "",
                    location: raw.location || raw.loc || "",
                  };
                  const negFloat = s.forecast_delivery && s.req_delivery && s.forecast_delivery > s.req_delivery;
                  return (
                    <tr key={s.id} className="hover:bg-gray-50/70">
                      <td className="p-2.5 font-medium">
                        {s.vendor}
                        {s.location && <span className="block text-[10px] text-gray-500">{s.location}</span>}
                      </td>
                      <td className="p-2.5">{s.material}</td>
                      <td className="p-2.5 font-mono">{s.sub_po_no || "Enquiry"}</td>
                      <td className="p-2.5 font-mono text-indigo-700">{s.unpriced_po_ref || "Pending"}</td>
                      <td className="p-2.5 font-mono">{s.req_delivery || "—"}</td>
                      <td className="p-2.5 font-mono">{s.forecast_delivery || "—"}</td>
                      <td className="p-2.5">
                        <Badge className={negFloat ? "bg-rose-100 text-rose-800 text-[10px]" : "bg-emerald-100 text-emerald-800 text-[10px]"}>
                          {negFloat ? "Negative Float" : "On Track"}
                        </Badge>
                        {s.linked_noi && (
                          <Badge variant="outline" className="ml-1 text-[10px] text-indigo-700 border-indigo-200">
                            {s.linked_noi}
                          </Badge>
                        )}
                      </td>
                      <td className="p-2.5 text-right">
                        <div className="inline-flex items-center gap-1 justify-end">
                          {onRaiseSubOrderNoi && (
                            <Button
                              type="button"
                              variant="outline"
                              size="xs"
                              onClick={() => onRaiseSubOrderNoi(s)}
                              className="h-7 px-2 text-[11px] text-indigo-700 border-indigo-200 hover:bg-indigo-50"
                            >
                              Raise NOI
                            </Button>
                          )}
                          <Button variant="ghost" size="xs" onClick={() => handleDelete(s.id)} className="text-rose-600 h-7 w-7 p-0">
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

export function VendorProgressReportsTab({ selectedPo, onUpdated }) {
  const [reports, setReports] = useState([]);
  const [defaults, setDefaults] = useState(null);
  const [saving, setSaving] = useState(false);

  const [reportNo, setReportNo] = useState("01");
  const [periodFrom, setPeriodFrom] = useState(new Date(Date.now() - 30 * 86400000).toISOString().split("T")[0]);
  const [periodTo, setPeriodTo] = useState(new Date().toISOString().split("T")[0]);
  const [summary, setSummary] = useState({
    engineering: { planned: 0, actual: 0 },
    procurement: { planned: 0, actual: 0 },
    manufacturing: { planned: 0, actual: 0 },
    delivery: { planned: 0, actual: 0 },
    overall: { planned: 0, actual: 0 },
  });
  const [ach, setAch] = useState({ engineering: "", procurement: "", manufacturing: "", delivery: "" });
  const [nxt, setNxt] = useState({ engineering: "", procurement: "", manufacturing: "", delivery: "" });
  const [aoc, setAoc] = useState("");
  const [docs13, setDocs13] = useState([]);
  const [mfgNotes, setMfgNotes] = useState("");
  const [schedAttached, setSchedAttached] = useState(true);
  const [subAttached, setSubAttached] = useState(true);

  const loadReports = async () => {
    if (!selectedPo) return;
    const res = await fetch(`/api/v1/po/${encodeURIComponent(selectedPo)}/progress-reports`);
    const json = await res.json();
    if (json.ok) {
      setReports(json.reports || []);
      setDefaults(json.template_defaults);
      setDocs13(json.template_defaults?.engineering_docs_13 || []);
      setReportNo(String((json.reports || []).length + 1).padStart(2, "0"));
      if (!aoc && json.template_defaults?.open_concerns_summary) {
        setAoc(json.template_defaults.open_concerns_summary);
      }
    }
  };

  useEffect(() => {
    loadReports();
  }, [selectedPo]);

  const handleSubmit = async (submit = true) => {
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/po/${encodeURIComponent(selectedPo)}/progress-reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          submit,
          report_no: reportNo,
          period_from: periodFrom,
          period_to: periodTo,
          po_summary: summary,
          achievements_this_month: ach,
          planned_next_month: nxt,
          areas_of_concern: aoc,
          engineering_detail: {
            planned_cum: summary.engineering.planned,
            actual_cum: summary.engineering.actual,
            docs_13: docs13,
          },
          manufacturing_detail: { status_notes: mfgNotes },
          delivery_detail: { items: defaults?.delivery_items || [] },
          attachments: {
            schedule_attached: schedAttached,
            suborder_status_attached: subAttached,
          },
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Progress Report validation failed");
        return;
      }
      toast.success(`NMDC Progress Report #${reportNo} ${submit ? "submitted" : "saved as draft"}!`);
      await loadReports();
      if (onUpdated) onUpdated();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border-gray-200/80 shadow-xs">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="text-sm font-bold">NMDC 7-Section Monthly Progress Report Builder</CardTitle>
              <CardDescription className="text-xs">
                Contract: {defaults?.contract_no || "N/A"} | Budget: {defaults?.budget_no || "N/A"} | Equipment: {defaults?.equipment_material || selectedPo}
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button size="xs" variant="outline" onClick={() => handleSubmit(false)} disabled={saving} className="h-8">Save Draft</Button>
              <Button size="xs" onClick={() => handleSubmit(true)} disabled={saving} className="h-8 bg-indigo-600 hover:bg-indigo-700 text-white">
                <FileText className="w-3.5 h-3.5 mr-1" /> Submit Official Report
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 text-xs">
          <div className="grid grid-cols-3 gap-3">
            <div><Label className="text-[11px]">Report No.</Label><Input value={reportNo} onChange={(e) => setReportNo(e.target.value)} className="h-8 text-xs mt-1" /></div>
            <div><Label className="text-[11px]">Period From</Label><Input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} className="h-8 text-xs mt-1" /></div>
            <div><Label className="text-[11px]">Period To</Label><Input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} className="h-8 text-xs mt-1" /></div>
          </div>

          <div className="border rounded-lg p-3 space-y-2">
            <div className="font-bold text-gray-800">1. PO Summary (Planned % vs Actual %)</div>
            <div className="grid grid-cols-5 gap-2">
              {["engineering", "procurement", "manufacturing", "delivery", "overall"].map((k) => (
                <div key={k} className="p-2 rounded bg-slate-50 border space-y-1">
                  <div className="font-semibold uppercase text-[10px]">{k}</div>
                  <Input
                    type="number"
                    placeholder="Planned %"
                    value={summary[k].planned}
                    onChange={(e) => setSummary({ ...summary, [k]: { ...summary[k], planned: Number(e.target.value) } })}
                    className="h-7 text-xs bg-white"
                  />
                  <Input
                    type="number"
                    placeholder="Actual %"
                    value={summary[k].actual}
                    onChange={(e) => setSummary({ ...summary, [k]: { ...summary[k], actual: Number(e.target.value) } })}
                    className="h-7 text-xs bg-white"
                  />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3 pt-1">
              <div className="space-y-1">
                <Label className="text-[11px]">Achievements This Month (Eng / Proc / Mfg / Del)</Label>
                <Input placeholder="Engineering achievements" value={ach.engineering} onChange={(e) => setAch({ ...ach, engineering: e.target.value })} className="h-7 text-xs" />
                <Input placeholder="Manufacturing achievements" value={ach.manufacturing} onChange={(e) => setAch({ ...ach, manufacturing: e.target.value })} className="h-7 text-xs" />
              </div>
              <div className="space-y-1">
                <Label className="text-[11px]">Planned Activities Next Month</Label>
                <Input placeholder="Next month engineering/procurement" value={nxt.engineering} onChange={(e) => setNxt({ ...nxt, engineering: e.target.value })} className="h-7 text-xs" />
                <Input placeholder="Next month manufacturing/delivery" value={nxt.manufacturing} onChange={(e) => setNxt({ ...nxt, manufacturing: e.target.value })} className="h-7 text-xs" />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-[11px] font-bold">2. Areas of Concern</Label>
              <Textarea rows={3} value={aoc} onChange={(e) => setAoc(e.target.value)} className="text-xs mt-1" placeholder="List critical constraints or open NCR/material bottlenecks..." />
            </div>
            <div>
              <Label className="text-[11px] font-bold">5. Manufacturing Detail Status</Label>
              <Textarea rows={3} value={mfgNotes} onChange={(e) => setMfgNotes(e.target.value)} className="text-xs mt-1" placeholder="Shop fabrication, welding, NDT, assembly progress..." />
            </div>
          </div>

          <div className="border rounded-lg p-3 space-y-2">
            <div className="font-bold text-gray-800">3. Engineering Detail — 13 SDR Document Categories (Auto-Counted from VDMS)</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {docs13.map((d, idx) => (
                <div key={d.sr} className="flex items-center gap-1.5 bg-slate-50 p-1.5 rounded border">
                  <span className="flex-1 truncate font-medium">{d.sr}. {d.category}</span>
                  <Input
                    type="number"
                    value={d.submitted_qty}
                    onChange={(e) => setDocs13((prev) => prev.map((x, i) => (i === idx ? { ...x, submitted_qty: Number(e.target.value) } : x)))}
                    className="h-6 w-14 text-xs bg-white text-center"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-indigo-50/70 border border-indigo-200 space-y-1.5">
            <div className="font-bold text-indigo-950">7. Mandatory Section 7 Attachments</div>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={schedAttached} onChange={(e) => setSchedAttached(e.target.checked)} />
                Vendor 9-Column Schedule Attached / Synced
              </label>
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={subAttached} onChange={(e) => setSubAttached(e.target.checked)} />
                Sub-Order Status Annexure Attached (Section 4)
              </label>
            </div>
          </div>
        </CardContent>
      </Card>

      {reports.length > 0 && (
        <Card className="border-gray-200/80 shadow-xs">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-bold">Submitted Progress Reports History ({reports.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {reports.slice().reverse().map((r) => (
                <div key={r.id} className="flex items-center justify-between p-2.5 rounded-lg border bg-white">
                  <div>
                    <span className="font-bold">Report #{r.report_no}</span>
                    <span className="ml-2 text-gray-500">{r.period_from || "—"} to {r.period_to || "—"}</span>
                    <Badge variant="outline" className="ml-2 text-[10px]">{r.status}</Badge>
                    {r.reviewer_comments && <span className="ml-2 text-rose-700">Note: {r.reviewer_comments}</span>}
                  </div>
                  <div className="flex gap-1.5">
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() =>
                        downloadAuthFile(
                          `/api/v1/po/${encodeURIComponent(selectedPo)}/progress-reports/${encodeURIComponent(r.id)}/export-docx`,
                          `${selectedPo}_Progress_Report_${r.report_no || "01"}.docx`
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
                          `/api/v1/po/${encodeURIComponent(selectedPo)}/progress-reports/${encodeURIComponent(r.id)}/export-pdf`,
                          `${selectedPo}_Progress_Report_${r.report_no || "01"}.pdf`
                        )
                      }
                      className="h-7 bg-rose-50 text-rose-800 border-rose-200 font-semibold"
                    >
                      <Download className="w-3 h-3 mr-1" /> .pdf
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
