import React, { useState, useEffect } from "react";
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
import {
  CheckCircle2,
  Download,
  ShieldCheck,
  Calendar,
  Truck,
  FileText,
  AlertTriangle,
  Plus,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { downloadAuthFile } from "@/utils/downloadAuthFile";

export function Phase4OperationsTab({ activePo, projectId, onUpdated }) {
  const [iapData, setIapData] = useState(null);
  const [iapDocNo, setIapDocNo] = useState("");
  const [iapDossier, setIapDossier] = useState("");
  const [iapComments, setIapComments] = useState("");

  const [meetings, setMeetings] = useState([]);
  const [meetForm, setMeetForm] = useState({
    meeting_type: "KOM",
    meeting_date: new Date().toISOString().split("T")[0],
    mode: "TEAMS",
    location: "MS Teams",
    attendees: "",
    dossier_ref: "",
    mom_summary: "",
    action_items_text: "",
  });

  const [lookDays, setLookDays] = useState("28");
  const [lookEvents, setLookEvents] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const lookRes = await fetch(
        `/api/v1/expediting/look-ahead?project_id=${encodeURIComponent(projectId || "all")}&days=${lookDays}`
      );
      const lookJson = await lookRes.json();
      if (lookJson.ok) setLookEvents(lookJson.events || []);

      if (activePo) {
        const [iapRes, meetRes] = await Promise.all([
          fetch(`/api/v1/po/${encodeURIComponent(activePo)}/iap`),
          fetch(`/api/v1/po/${encodeURIComponent(activePo)}/meetings`),
        ]);
        const iapJson = await iapRes.json();
        const meetJson = await meetRes.json();
        if (iapJson.ok) {
          setIapData(iapJson);
          setIapDocNo(iapJson.iap_package?.doc_no || "");
          setIapDossier(iapJson.iap_package?.dossier_ref || "");
          setIapComments(iapJson.iap_package?.comments || "");
        }
        if (meetJson.ok) setMeetings(meetJson.meetings || []);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, [activePo, projectId, lookDays]);

  const handleIapAction = async (action, toggleRequired = undefined) => {
    if (!activePo) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/iap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          doc_no: iapDocNo,
          dossier_ref: iapDossier,
          comments: iapComments,
          ...(toggleRequired !== undefined ? { requires_client_iap: toggleRequired } : {}),
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "IAP update failed");
        return;
      }
      toast.success(`Client IAP ${action} (${json.iap_package?.client_status})`);
      await loadAll();
      if (onUpdated) onUpdated();
    } finally {
      setLoading(false);
    }
  };

  const handleRecordMeeting = async (e) => {
    e.preventDefault();
    if (!activePo) return;
    setLoading(true);
    try {
      const actionItems = meetForm.action_items_text
        .split(/\r?\n/)
        .map((x) => x.trim())
        .filter(Boolean);
      const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          meeting_type: meetForm.meeting_type,
          meeting_date: meetForm.meeting_date,
          mode: meetForm.mode,
          location: meetForm.location,
          attendees: meetForm.attendees,
          dossier_ref: meetForm.dossier_ref,
          mom_summary: meetForm.mom_summary,
          action_items: actionItems,
          spawn_rail: true,
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        toast.error(json.detail || "Failed recording MOM");
        return;
      }
      toast.success(
        `${meetForm.meeting_type} MOM logged` +
          (json.spawned_rail_ids?.length ? ` + ${json.spawned_rail_ids.length} RAIL action(s) created` : "")
      );
      setMeetForm({ ...meetForm, mom_summary: "", action_items_text: "", dossier_ref: "" });
      await loadAll();
      if (onUpdated) onUpdated();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 text-xs">
      {/* 4A. Client IAP Gate (Steps 6-7) */}
      {activePo && (
        <div className="border rounded-xl p-4 bg-white space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="font-bold text-indigo-950 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-indigo-600" />
                Client IAP Submission (PMT) &amp; Approval Gate (Steps 6–7)
              </h4>
              <p className="text-[11px] text-gray-500">
                Required on Aramco / flagged projects before inspection mobilization.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 bg-slate-50 px-2.5 py-1 rounded border cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(iapData?.requires_client_iap)}
                  onChange={(e) => handleIapAction("toggle_required", e.target.checked)}
                />
                <span className="font-semibold">Requires Client IAP</span>
              </label>
              <Badge className={iapData?.iap_cleared ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}>
                {iapData?.iap_package?.client_status || "NOT_SUBMITTED"}
              </Badge>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <Input value={iapDocNo} onChange={(e) => setIapDocNo(e.target.value)} placeholder="IAP Doc #" className="h-7 text-xs font-mono" />
            <Input value={iapDossier} onChange={(e) => setIapDossier(e.target.value)} placeholder="IAP Dossier Ref / URL" className="h-7 text-xs" />
            <Input value={iapComments} onChange={(e) => setIapComments(e.target.value)} placeholder="PMT / Client Comments" className="h-7 text-xs" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="xs" variant="outline" onClick={() => handleIapAction("submit")} disabled={loading} className="h-7">
              PMT Submit IAP to Client
            </Button>
            <Button size="xs" onClick={() => handleIapAction("approve")} disabled={loading} className="h-7 bg-emerald-600 hover:bg-emerald-700 text-white">
              <CheckCircle2 className="w-3 h-3 mr-1" /> Record Client IAP Approved
            </Button>
            <Button size="xs" variant="outline" onClick={() => handleIapAction("return")} disabled={loading} className="h-7 text-rose-700 border-rose-300">
              Return with Client Comments
            </Button>
          </div>
        </div>
      )}

      {/* 4B. KOM / Tech Clarification / PIM MOM + Dossier */}
      {activePo && (
        <div className="border rounded-xl p-4 bg-white space-y-3">
          <h4 className="font-bold text-slate-900">KOM / Technical Meeting &amp; PIM MOM + Dossier (Step 8, Actions #11, #13, #17)</h4>
          <form onSubmit={handleRecordMeeting} className="grid grid-cols-1 md:grid-cols-4 gap-2 bg-slate-50 p-3 rounded-lg border">
            <Select value={meetForm.meeting_type} onValueChange={(v) => setMeetForm({ ...meetForm, meeting_type: v })}>
              <SelectTrigger className="h-7 text-xs bg-white"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="KOM">Kick-Off Meeting (KOM)</SelectItem>
                <SelectItem value="TECH_CLARIFICATION">Technical Comment Resolution</SelectItem>
                <SelectItem value="PIM">Pre-Inspection Meeting (PIM + Dossier)</SelectItem>
              </SelectContent>
            </Select>
            <Input type="date" value={meetForm.meeting_date} onChange={(e) => setMeetForm({ ...meetForm, meeting_date: e.target.value })} className="h-7 text-xs bg-white" />
            <Input value={meetForm.location} onChange={(e) => setMeetForm({ ...meetForm, location: e.target.value })} placeholder="MS Teams / Shop Location" className="h-7 text-xs bg-white" />
            <Input value={meetForm.dossier_ref} onChange={(e) => setMeetForm({ ...meetForm, dossier_ref: e.target.value })} placeholder="MOM / PIM Dossier Ref" className="h-7 text-xs bg-white" />
            <Input value={meetForm.attendees} onChange={(e) => setMeetForm({ ...meetForm, attendees: e.target.value })} placeholder="Attendees (PMT, TPIA, Vendor)" className="h-7 text-xs bg-white md:col-span-2" />
            <Input value={meetForm.mom_summary} onChange={(e) => setMeetForm({ ...meetForm, mom_summary: e.target.value })} placeholder="Meeting Summary & Key Decisions *" className="h-7 text-xs bg-white md:col-span-2" required />
            <Textarea
              rows={2}
              value={meetForm.action_items_text}
              onChange={(e) => setMeetForm({ ...meetForm, action_items_text: e.target.value })}
              placeholder="Action items (one per line — auto-creates RAIL concerns)..."
              className="text-xs bg-white md:col-span-3"
            />
            <Button type="submit" size="sm" disabled={loading} className="h-full bg-indigo-600 hover:bg-indigo-700 text-white">
              <Plus className="w-3.5 h-3.5 mr-1" /> Save MOM &amp; Sync Schedule
            </Button>
          </form>

          {meetings.length > 0 && (
            <div className="space-y-1.5 max-h-36 overflow-y-auto">
              {meetings.slice().reverse().map((m) => (
                <div key={m.id} className="p-2 rounded border bg-slate-50 flex items-center justify-between">
                  <div>
                    <Badge variant="outline" className="mr-1.5 text-[10px]">{m.meeting_type}</Badge>
                    <b>{m.meeting_date}</b> ({m.location}) — {m.mom_summary}
                    {m.dossier_ref && <span className="ml-2 text-indigo-700 font-mono">Dossier: {m.dossier_ref}</span>}
                  </div>
                  <span className="text-[10px] text-gray-500">{m.recorded_by}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 4C. Client Inspection Look-Ahead Schedule */}
      <div className="border rounded-xl p-4 bg-white space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="font-bold text-teal-950 flex items-center gap-1.5">
            <Calendar className="w-4 h-4 text-teal-600" />
            Client Inspection Look-Ahead Schedule (PIM, Sub-Order, Stage &amp; FAT)
          </h4>
          <div className="flex items-center gap-2">
            <Select value={lookDays} onValueChange={setLookDays}>
              <SelectTrigger className="h-7 w-28 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="14">Next 14 Days</SelectItem>
                <SelectItem value="28">Next 28 Days</SelectItem>
                <SelectItem value="60">Next 60 Days</SelectItem>
              </SelectContent>
            </Select>
            <Button
              size="xs"
              onClick={() =>
                downloadAuthFile(
                  `/api/v1/expediting/look-ahead/export-xlsx?project_id=${encodeURIComponent(projectId || "all")}&days=${lookDays}`,
                  `Client_Inspection_LookAhead_${lookDays}d.xlsx`
                )
              }
              className="h-7 bg-teal-600 hover:bg-teal-700 text-white"
            >
              <Download className="w-3 h-3 mr-1" /> Export Look-Ahead .xlsx
            </Button>
          </div>
        </div>
        <div className="border rounded overflow-x-auto max-h-56 overflow-y-auto">
          <table className="w-full text-[11px] text-left">
            <thead className="bg-teal-900 text-white sticky top-0">
              <tr>
                <th className="p-2">Date</th>
                <th className="p-2">PO #</th>
                <th className="p-2">Supplier</th>
                <th className="p-2">Scope</th>
                <th className="p-2">Activity / Callout</th>
                <th className="p-2">Location</th>
                <th className="p-2">Inspector / TPI</th>
                <th className="p-2">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {lookEvents.length === 0 ? (
                <tr><td colSpan={8} className="p-4 text-center text-gray-500">No upcoming inspection events within {lookDays} days.</td></tr>
              ) : (
                lookEvents.map((ev, idx) => (
                  <tr key={idx} className="hover:bg-teal-50/30">
                    <td className="p-2 font-mono font-bold">{ev.date}</td>
                    <td className="p-2 font-mono">{ev.po}</td>
                    <td className="p-2">{ev.supplier}</td>
                    <td className="p-2"><Badge variant="outline" className="text-[10px]">{ev.scope}</Badge></td>
                    <td className="p-2">{ev.activity}</td>
                    <td className="p-2">{ev.location}</td>
                    <td className="p-2">{ev.inspector_tpi}</td>
                    <td className="p-2 text-gray-500">{ev.source} ({ev.reference})</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function Phase5CloseoutMncrTab({ activePo, onUpdated }) {
  const [mncrs, setMncrs] = useState([]);
  const [mncrForm, setMncrForm] = useState({ mrv_no: "", item_no: "10", stamped_delivery_note_ref: "", description: "" });

  const [ldData, setLdData] = useState(null);
  const [ldForm, setLdForm] = useState({
    mode: "PENDING",
    rate_per_day: 0,
    cap_pct: 10,
    settled_amount: 0,
    waiver_justification: "",
    final_invoice_no: "",
    final_invoice_paid_on: "",
  });
  const [loading, setLoading] = useState(false);

  const loadPhase5 = async () => {
    if (!activePo) return;
    setLoading(true);
    try {
      const [mRes, lRes] = await Promise.all([
        fetch(`/api/v1/po/${encodeURIComponent(activePo)}/mncr`),
        fetch(`/api/v1/po/${encodeURIComponent(activePo)}/closeout/ld`),
      ]);
      const mJson = await mRes.json();
      const lJson = await lRes.json();
      if (mJson.ok) setMncrs(mJson.mncrs || []);
      if (lJson.ok) {
        setLdData(lJson);
        setLdForm({
          mode: lJson.ld?.mode || "PENDING",
          rate_per_day: lJson.ld?.rate_per_day ?? 0,
          cap_pct: lJson.ld?.cap_pct ?? 10,
          settled_amount: lJson.ld?.settled_amount ?? 0,
          waiver_justification: lJson.ld?.waiver_justification || "",
          final_invoice_no: lJson.ld?.final_invoice_no || "",
          final_invoice_paid_on: lJson.ld?.final_invoice_paid_on || "",
        });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPhase5();
  }, [activePo]);

  const handleRaiseMncr = async (e) => {
    e.preventDefault();
    const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/mncr`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(mncrForm),
    });
    const json = await res.json();
    if (!res.ok) return toast.error(json.detail || "Failed raising MNCR");
    toast.success(`Stores raised ${json.mncr?.mncr_no}`);
    setMncrForm({ mrv_no: "", item_no: "10", stamped_delivery_note_ref: "", description: "" });
    await loadPhase5();
    if (onUpdated) onUpdated();
  };

  const handleMncrTransition = async (mncrId, endpoint, body = {}) => {
    const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/mncr/${encodeURIComponent(mncrId)}/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const json = await res.json();
    if (!res.ok) return toast.error(json.detail || "MNCR action failed");
    toast.success(`MNCR ${mncrId} updated (${json.mncr?.status})`);
    await loadPhase5();
    if (onUpdated) onUpdated();
  };

  const handleSaveLd = async (opts = {}) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/po/${encodeURIComponent(activePo)}/closeout/ld`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...ldForm, ...opts }),
      });
      const json = await res.json();
      if (!res.ok) return toast.error(json.detail || "LD closeout save failed");
      setLdData(json);
      toast.success(`Commercial Closeout Updated — Stage: ${json.closeout?.stage_label}`);
      if (onUpdated) onUpdated();
    } finally {
      setLoading(false);
    }
  };

  if (!activePo) return <p className="text-xs text-gray-500 py-8 text-center">Select a Purchase Order first.</p>;

  const cs = ldData?.closeout || {};
  return (
    <div className="space-y-4 text-xs">
      {/* 5A. Stores MNCR Return/Close Loop */}
      <div className="border rounded-xl p-4 bg-white space-y-3">
        <h4 className="font-bold text-rose-950 flex items-center gap-1.5">
          <AlertTriangle className="w-4 h-4 text-rose-600" />
          Stores MRV / Stamped Delivery Note &amp; MNCR Shortage/Damage Loop (Step 18, Action #29)
        </h4>
        <form onSubmit={handleRaiseMncr} className="grid grid-cols-1 md:grid-cols-5 gap-2 bg-rose-50/40 p-3 rounded-lg border border-rose-200">
          <Input value={mncrForm.mrv_no} onChange={(e) => setMncrForm({ ...mncrForm, mrv_no: e.target.value })} placeholder="MRV No." className="h-7 text-xs bg-white" />
          <Input value={mncrForm.stamped_delivery_note_ref} onChange={(e) => setMncrForm({ ...mncrForm, stamped_delivery_note_ref: e.target.value })} placeholder="Stamped Delivery Note Ref" className="h-7 text-xs bg-white" />
          <Input value={mncrForm.item_no} onChange={(e) => setMncrForm({ ...mncrForm, item_no: e.target.value })} placeholder="Item #" className="h-7 text-xs bg-white" />
          <Input value={mncrForm.description} onChange={(e) => setMncrForm({ ...mncrForm, description: e.target.value })} placeholder="Shortage / Transit Damage Details *" className="h-7 text-xs bg-white" required />
          <Button type="submit" size="xs" className="h-7 bg-rose-600 hover:bg-rose-700 text-white">Raise Stores MNCR</Button>
        </form>

        <div className="space-y-2">
          {mncrs.length === 0 ? (
            <p className="text-gray-500">Zero Stores MNCRs raised on PO #{activePo}.</p>
          ) : (
            mncrs.map((m, i) => {
              const mid = m.id || m.mncr_no || `mncr-${i}`;
              const st = m.status || m.Status || "OPEN";
              return (
                <div key={mid} className="p-2.5 rounded-lg border bg-slate-50 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="font-mono font-bold mr-2">{m.mncr_no || m["MNCR no."] || mid}</span>
                    <Badge variant="outline" className="mr-2 text-[10px]">{st}</Badge>
                    <span>{m.description || m.Description}</span>
                    {m.stamped_delivery_note_ref && <span className="ml-2 text-gray-500 font-mono">[DN: {m.stamped_delivery_note_ref}]</span>}
                  </div>
                  <div className="flex gap-1.5">
                    {st === "RAISED_BY_STORES" && (
                      <Button size="xs" variant="outline" onClick={() => handleMncrTransition(mid, "return-to-vendor")} className="h-6 text-[11px]">
                        PMT Return to Vendor
                      </Button>
                    )}
                    {st !== "CLOSED" && (
                      <Button size="xs" onClick={() => handleMncrTransition(mid, "close")} className="h-6 text-[11px] bg-emerald-600 text-white">
                        PMT Close MNCR
                      </Button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 5B. Two-Stage Commercial Closeout & LD Waiver/Report */}
      <div className="border rounded-xl p-4 bg-white space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="font-bold text-slate-900 flex items-center gap-1.5">
              <FileText className="w-4 h-4 text-indigo-600" />
              Two-Stage Closeout: LD Settlement / Waiver Memo &amp; Final Invoice (Steps 19–21, Actions #26–28)
            </h4>
            <p className="text-[11px] text-gray-500">
              MRV: {cs.mrv_pct ?? 0}% | MRB Approved: {cs.mrb_approved_on || "Pending"} | Stage: <b>{cs.stage_label || "Open"}</b>
            </p>
          </div>
          <Button
            size="xs"
            variant="outline"
            onClick={() =>
              downloadAuthFile(
                `/api/v1/po/${encodeURIComponent(activePo)}/closeout/ld-memo-docx`,
                `${activePo}_LD_Settlement_${ldForm.mode}.docx`
              )
            }
            className="h-7 border-indigo-200 text-indigo-700 bg-indigo-50"
          >
            <Download className="w-3 h-3 mr-1" /> Download LD Memo / Report (.docx)
          </Button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 bg-slate-50 p-3 rounded-lg border">
          <div>
            <Label className="text-[10px]">LD Mode</Label>
            <Select value={ldForm.mode} onValueChange={(v) => setLdForm({ ...ldForm, mode: v })}>
              <SelectTrigger className="h-7 text-xs bg-white mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="PENDING">Pending Assessment</SelectItem>
                <SelectItem value="FULL_LD">Full LD Applicable</SelectItem>
                <SelectItem value="PARTIAL_WAIVER">Partial LD Waiver</SelectItem>
                <SelectItem value="FULL_WAIVER">Full LD Waiver</SelectItem>
                <SelectItem value="NOT_APPLICABLE">No Delay / N/A</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-[10px]">Rate / Day ({ldData?.ld?.ccy || "USD"})</Label>
            <Input type="number" value={ldForm.rate_per_day} onChange={(e) => setLdForm({ ...ldForm, rate_per_day: Number(e.target.value) })} className="h-7 text-xs bg-white mt-1" />
          </div>
          <div>
            <Label className="text-[10px]">Cap %</Label>
            <Input type="number" value={ldForm.cap_pct} onChange={(e) => setLdForm({ ...ldForm, cap_pct: Number(e.target.value) })} className="h-7 text-xs bg-white mt-1" />
          </div>
          <div>
            <Label className="text-[10px]">Agreed Settlement Amt</Label>
            <Input type="number" value={ldForm.settled_amount} onChange={(e) => setLdForm({ ...ldForm, settled_amount: Number(e.target.value) })} className="h-7 text-xs bg-white mt-1" />
          </div>
          <div>
            <Label className="text-[10px]">Final Invoice Ref</Label>
            <Input value={ldForm.final_invoice_no} onChange={(e) => setLdForm({ ...ldForm, final_invoice_no: e.target.value })} placeholder="INV-FINAL-01" className="h-7 text-xs bg-white mt-1" />
          </div>
          <div>
            <Label className="text-[10px]">Final Invoice Paid On</Label>
            <Input type="date" value={ldForm.final_invoice_paid_on} onChange={(e) => setLdForm({ ...ldForm, final_invoice_paid_on: e.target.value })} className="h-7 text-xs bg-white mt-1" />
          </div>
          <div className="col-span-2 md:col-span-4">
            <Input value={ldForm.waiver_justification} onChange={(e) => setLdForm({ ...ldForm, waiver_justification: e.target.value })} placeholder="LD Intimation / Waiver Justification Notes..." className="h-7 text-xs bg-white" />
          </div>
          <div className="col-span-2 flex gap-1.5 justify-end">
            <Button size="xs" variant="outline" onClick={() => handleSaveLd({ mark_intimated: true })} disabled={loading} className="h-7">Intimate LD</Button>
            <Button size="xs" onClick={() => handleSaveLd({ mark_settled: true, issue_memo: true })} disabled={loading} className="h-7 bg-emerald-600 hover:bg-emerald-700 text-white">
              Settle LD &amp; Update Closeout
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Phase5GovernanceRegistersTab({ projectId, activePo }) {
  const [regType, setRegType] = useState("tpia-billing");
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ title: "", party: "", ref_no: "", amount: "", notes: "" });

  const loadReg = async () => {
    const res = await fetch(
      `/api/v1/governance/registers/${regType}?project_id=${encodeURIComponent(projectId || "all")}`
    );
    const json = await res.json();
    if (json.ok) setItems(json.items || []);
  };

  useEffect(() => {
    loadReg();
  }, [regType, projectId]);

  const handleAdd = async (e) => {
    e.preventDefault();
    const res = await fetch(`/api/v1/governance/registers/${regType}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...form,
        project_id: projectId && projectId !== "all" ? projectId : undefined,
        po: activePo || undefined,
      }),
    });
    const json = await res.json();
    if (!res.ok) return toast.error(json.detail || "Failed adding entry");
    toast.success("Governance register entry saved.");
    setForm({ title: "", party: "", ref_no: "", amount: "", notes: "" });
    await loadReg();
  };

  const handleDecide = async (id, decision) => {
    const res = await fetch(`/api/v1/governance/registers/${regType}/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    if (res.ok) {
      toast.success(`Marked ${decision}`);
      await loadReg();
    }
  };

  return (
    <div className="space-y-3 text-xs">
      <div className="flex flex-wrap gap-1.5">
        {[
          ["tpia-billing", "TPIA / Freight Timesheets & Invoices"],
          ["tpi-credentials", "TPI CV / QM / Certs Approval"],
          ["prequalification", "Supplier Pre-Qualification Audits"],
          ["lessons-letters", "Client Letters & Lessons Learnt"],
        ].map(([k, lbl]) => (
          <Button
            key={k}
            size="xs"
            variant={regType === k ? "default" : "outline"}
            onClick={() => setRegType(k)}
            className="h-7 text-xs"
          >
            {lbl}
          </Button>
        ))}
      </div>

      <form onSubmit={handleAdd} className="grid grid-cols-2 md:grid-cols-6 gap-2 bg-slate-50 p-3 rounded-lg border">
        <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Title / Inspector Name / Subject *" className="h-7 text-xs bg-white md:col-span-2" required />
        <Input value={form.party} onChange={(e) => setForm({ ...form, party: e.target.value })} placeholder="TPIA / Vendor / Client" className="h-7 text-xs bg-white" />
        <Input value={form.ref_no} onChange={(e) => setForm({ ...form, ref_no: e.target.value })} placeholder="Ref / Invoice / Cert #" className="h-7 text-xs bg-white" />
        <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Amount / Findings / Notes" className="h-7 text-xs bg-white" />
        <Button type="submit" size="xs" className="h-7 bg-indigo-600 text-white"><Plus className="w-3 h-3 mr-1" /> Add Entry</Button>
      </form>

      <div className="border rounded-lg divide-y max-h-64 overflow-y-auto bg-white">
        {items.length === 0 ? (
          <div className="p-6 text-center text-gray-500">No entries recorded in this register yet.</div>
        ) : (
          items.map((it) => (
            <div key={it.id} className="p-2.5 flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-bold mr-2">{it.title}</span>
                {it.party && <span className="text-gray-600 mr-2">• {it.party}</span>}
                {it.ref_no && <span className="font-mono text-indigo-700 mr-2">[{it.ref_no}]</span>}
                <Badge variant="outline" className="text-[10px]">{it.status}</Badge>
                {it.notes && <span className="block text-[11px] text-gray-500">{it.notes}</span>}
              </div>
              {it.status === "PENDING_APPROVAL" && (
                <div className="flex gap-1">
                  <Button size="xs" onClick={() => handleDecide(it.id, "APPROVED")} className="h-6 bg-emerald-600 text-white text-[10px]">Approve</Button>
                  <Button size="xs" variant="outline" onClick={() => handleDecide(it.id, "REJECTED")} className="h-6 text-rose-700 text-[10px]">Reject</Button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
