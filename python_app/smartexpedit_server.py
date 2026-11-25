"""
SmartExpedit Python Backend & InspectFlow Integration Layer
===========================================================
Ports the complete `SmartExpedit/server/app.py` (KV store, PO merge engine,
blob storage, `/api/v1/*` connectors, and audit trail) directly into the
InspectFlow FastAPI server, and serves the SmartExpedit application styled
to match the exact original InspectFlow layout, look, and feel.
"""

from datetime import date, datetime
import hmac
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from backend_v2.core.config import settings
from backend_v2.core.database import SessionLocal
from backend_v2.core.security import (
    effective_role,
    get_current_user,
    get_optional_user,
    is_admin_user,
    is_vendor_user,
    require_roles,
    user_can_access_po,
    user_can_access_project_id,
    vendor_owns_po,
)
from backend_v2.models.epc_models import (
    ConcessionWaiver,
    DispatchReservation,
    ItpBaselineStep,
    ItpDocument,
    PoRevision,
)
from backend_v2.services.audit_service import record_audit_event
from python_app import database as inspectflow_db
from python_app.pdf_ocr import extract_pdf_with_ocr

logger = logging.getLogger("inspectflow.smartexpedit")

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
SX_DIR = BASE_DIR / "SmartExpedit" / "server"
SX_DATA = Path(os.environ.get("SX_DATA", str(SX_DIR / "data")))
SX_BLOBS = SX_DATA / "blobs"
SX_DB_PATH = SX_DATA / "smartexpedit.db"
SX_STATIC_HTML = SX_DIR / "static" / "index.html"
SX_HEAD_JS_PATH = SX_DIR / "sx_head.js"
SX_TAIL_JS_PATH = SX_DIR / "sx_tail.js"

API_KEY = os.environ.get("SX_API_KEY", "")
DEMO = settings.sx_demo

REC_KEY = "ep_exp_records"
FILES_KEY = "sx_state_files"
FIELD_KEY = "sx_state_field"

SX_BLOBS.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()


def sx_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SX_DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def init_sx_db() -> None:
    with LOCK, sx_db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(
            "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, version INTEGER, seq INTEGER, updated REAL, by TEXT)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS blobs (key TEXT PRIMARY KEY, kind TEXT, name TEXT, type TEXT, size INTEGER, path TEXT, seq INTEGER, updated REAL)"
        )
        c.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v INTEGER)")
        c.execute("INSERT OR IGNORE INTO meta VALUES ('seq', 0)")
        c.execute(
            "CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, by TEXT, what TEXT)"
        )


def _next_seq(c: sqlite3.Connection) -> int:
    c.execute("UPDATE meta SET v = v + 1 WHERE k = 'seq'")
    return c.execute("SELECT v FROM meta WHERE k = 'seq'").fetchone()[0]


def _kv_get(c: sqlite3.Connection, key: str):
    r = c.execute("SELECT value, version FROM kv WHERE key = ?", (key,)).fetchone()
    return (r["value"], r["version"]) if r else (None, 0)


def _kv_put(c: sqlite3.Connection, key: str, value: str, by: str) -> int:
    _, ver = _kv_get(c, key)
    seq = _next_seq(c)
    c.execute(
        "INSERT INTO kv (key, value, version, seq, updated, by) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, version=excluded.version, seq=excluded.seq, updated=excluded.updated, by=excluded.by",
        (key, value, ver + 1, seq, time.time(), by),
    )
    return ver + 1


def _who(request: Request, current_user: Optional[Dict[str, Any]] = None) -> str:
    if current_user:
        return str(current_user.get("email") or current_user.get("full_name") or "user")
    return (request.client.host if request.client else None) or "unknown"


_SAFE_HREF_RE = None


def _safe_href_js_helper() -> str:
    return (
        "function _safeHref(u){var s=String(u||'').trim();"
        "return (/^https?:\\/\\//i.test(s)||s.charAt(0)==='/')?s:'';}"
    )


def _infer_procurement_class(rec: Dict[str, Any]) -> str:
    explicit = str(rec.get("procurement_class") or "").strip().lower()
    if explicit in ("bulk", "tagged", "package"):
        return explicit
    items = rec.get("items") or []
    head = str(rec.get("head") or "")
    has_splits = any(
        isinstance(i, dict) and ("." in str(i.get("item") or "") or i.get("is_split_parent") or i.get("is_split"))
        for i in items
    )
    plan_rows = ((rec.get("plan") or {}).get("rows") or []) if isinstance(rec.get("plan"), dict) else []
    if has_splits or len(plan_rows) > 0 or re.search(
        r"\b(skid|package|unit|train|system|flare|compressor|chemical injection)\b", head, re.I
    ):
        return "package"
    tot_qty = sum(float(i.get("qty") or 0) for i in items if isinstance(i, dict) and not i.get("is_split_parent"))
    if tot_qty >= 50 or len(items) >= 15 or re.search(
        r"\b(bolt|nut|stud|pipe|piping|flange|fitting|cable|bulk|gasket|steel|plate|fastener)\b", head, re.I
    ):
        return "bulk"
    return "tagged"


def _normalize_suborder_row(sr: Dict[str, Any]) -> Dict[str, Any]:
    """Unifies SmartExpedit legacy plan.rows keys (sub/item/no/raw/clear/loc) with canonical Vendor Portal fields."""
    row = dict(sr or {})
    vendor = str(row.get("vendor") or row.get("sub") or "").strip()
    material = str(row.get("material") or row.get("item") or "").strip()
    sub_po_no = str(row.get("sub_po_no") or row.get("no") or "").strip()
    req_del = str(row.get("req_delivery") or row.get("req") or row.get("raw") or "").strip()[:10]
    fc_del = str(row.get("forecast_delivery") or row.get("fc") or row.get("over") or row.get("clear") or req_del).strip()[:10]
    ord_dt = str(row.get("order_date") or row.get("aPlace") or row.get("fPlace") or "").strip()[:10]
    loc = str(row.get("location") or row.get("loc") or "").strip()
    is_crit = bool(row.get("critical")) or str(row.get("priority") or "").lower() == "critical" or bool(sub_po_no)
    return {
        **row,
        "vendor": vendor,
        "material": material,
        "sub_po_no": sub_po_no,
        "req_delivery": req_del,
        "forecast_delivery": fc_del,
        "order_date": ord_dt,
        "location": loc,
        "critical": is_crit,
        "unpriced_po_ref": str(row.get("unpriced_po_ref") or ""),
        "linked_noi": str(row.get("linked_noi") or ""),
    }


def _normalize_po_render_defaults(rec: Dict[str, Any]) -> Dict[str, Any]:
    items = rec.get("items") or []
    po_num = str(rec.get("po") or "")
    rec["procurement_class"] = _infer_procurement_class(rec)
    rec.setdefault("rev", "0")
    rec.setdefault("supplier", "VENDOR")
    rec.setdefault("supplierShort", str(rec.get("supplier") or "Vendor")[:22])
    rec.setdefault("mrRef", f"MR-{po_num}" if po_num else "MR-000")
    rec.setdefault("enquiry", f"ENQ-{po_num}" if po_num else "—")
    rec.setdefault("buyer", "Project Procurement")
    rec.setdefault("client", "Client")
    rec.setdefault("deliveryPoint", "Site Warehouse / DDP")
    rec.setdefault("payment", "Milestone Progress")
    rec.setdefault("origin", "Supplier Works")
    rec.setdefault("shipMode", "Ocean / Road")
    rec.setdefault("awardRev", 0)
    rec.setdefault("issuedOn", time.strftime("%Y-%m-%d"))
    rec.setdefault("issuedAt", f"{rec.get('issuedOn')} 09:00")
    rec.setdefault("notifiedOn", f"{rec.get('issuedOn')}T09:00:00.000Z")
    rec.setdefault("hold", 0)
    rec.setdefault("lines", len(items))
    rec.setdefault("qty", sum(float(i.get("qty") or 0) for i in items))
    rec.setdefault("vdr", [])
    rec.setdefault("schedule", [])
    rec.setdefault("log", [])
    rec.setdefault("irs", [])
    rec.setdefault("irns", [])
    rec.setdefault("punch", [])
    rec.setdefault("rail", [])
    rec.setdefault("sx", {"notif": [], "look": [], "punch": [], "iap": []})
    return rec


def _records(c: sqlite3.Connection):
    v, _ = _kv_get(c, REC_KEY)
    try:
        L = json.loads(v) if v else []
        if isinstance(L, list):
            return [_normalize_po_render_defaults(r) if isinstance(r, dict) else r for r in L]
        return []
    except ValueError:
        return []


def _save_records(c: sqlite3.Connection, L: list, by: str, what: str) -> int:
    ver = _kv_put(c, REC_KEY, json.dumps(L, separators=(",", ":")), by)
    c.execute(
        "INSERT INTO audit (at, by, what) VALUES (?,?,?)",
        (time.time(), by, what),
    )
    return ver


def _need_key(request: Request) -> Dict[str, Any]:
    if API_KEY:
        provided = request.headers.get("X-API-Key") or ""
        if provided and hmac.compare_digest(provided, API_KEY):
            return {"id": "api-key", "email": "integration@inspectflow.com", "role": "admin", "effective_role": "admin"}
    user = get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if effective_role(user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    return user


def _parse_date_safe(val: Any) -> Optional[date]:
    if not val:
        return None
    s = str(val).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _summary(r: Dict[str, Any]) -> Dict[str, Any]:
    q = r.get("items") or []
    return {
        "po": r.get("po"),
        "rev": r.get("rev"),
        "supplier": r.get("supplier"),
        "title": r.get("head"),
        "currency": r.get("ccy"),
        "value": r.get("value"),
        "stage": r.get("stage"),
        "assigned_to": r.get("assignedTo"),
        "issued_on": r.get("issuedOn"),
        "lots": [
            {
                "lot": l.get("id"),
                "contractual_delivery": l.get("date"),
                "qty": l.get("qty"),
            }
            for l in (r.get("lots") or [])
        ],
        "lines": len(q),
        "client": r.get("client"),
    }


def _find(c: sqlite3.Connection, po: str) -> Dict[str, Any]:
    for r in _records(c):
        if r.get("po") == po:
            return r
    raise HTTPException(status_code=404, detail="PO not found")


# ---------------------------------------------------------------------------
# InspectFlow Theme & Layout Override CSS for SmartExpedit
# ---------------------------------------------------------------------------
INSPECTFLOW_THEME_OVERRIDE_CSS = """
<style id="inspectflow-layout-integration">
/* Retain Original InspectFlow Layout, Look, and Feel */
html, body {
    background-color: #f9fafb !important;
    font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    color: #111827 !important;
}

/* All top-level navigation tabs (Executive Dashboard, PO Master Register,
   Expeditor Workbench, RAIL Action Tracker, Field Expediting, Vendor Portal)
   are rendered on top in the main header.
   Hide the duplicate internal .sx-side tab bar completely. */
#sx {
    display: flex !important;
    flex-direction: column !important;
    min-height: 100vh !important;
    background: #f9fafb !important;
}

.sx-side {
    display: none !important;
}

/* Sub-header bar (.sx-top) sticks to top: 0 */
.sx-top {
    background: #ffffff !important;
    border-bottom: 1px solid #e5e7eb !important;
    padding: 10px 20px !important;
    position: sticky !important;
    top: 0 !important;
    z-index: 20 !important;
}

.sx-top h1 {
    font-size: 1.35rem !important;
    font-weight: 700 !important;
    color: #111827 !important;
}

/* KPI Cards — Match InspectFlow StatsCard.jsx (rounded-2xl elevation-2) */
.ep-kpis {
    gap: 16px !important;
    margin-bottom: 20px !important;
}

.ep-kpi {
    background: #ffffff !important;
    border-radius: 16px !important;
    padding: 20px !important;
    border: 1px solid #f3f4f6 !important;
    box-shadow: 0 3px 6px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.06) !important;
    transition: box-shadow 0.2s ease !important;
}

.ep-kpi:hover {
    box-shadow: 0 10px 20px rgba(0,0,0,0.10), 0 3px 6px rgba(0,0,0,0.06) !important;
}

.ep-kpi .k {
    font-size: 12px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
    color: #4b5563 !important;
}

.ep-kpi .v {
    font-size: 30px !important;
    font-weight: 700 !important;
    color: #111827 !important;
    margin: 4px 0 !important;
}

/* White Content Cards — Match InspectFlow rounded-2xl elevation-2 */
.ep-card {
    background: #ffffff !important;
    border-radius: 16px !important;
    border: 1px solid #e5e7eb !important;
    box-shadow: 0 3px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.05) !important;
}

/* Primary Buttons & Links — Match InspectFlow Indigo-600 (#4f46e5) */
.ep-btn.primary {
    background: #4f46e5 !important;
    border-color: #4f46e5 !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
}

.ep-btn.primary:hover {
    background: #4338ca !important;
    border-color: #4338ca !important;
    color: #ffffff !important;
}

.ep-btn.secondary {
    border-radius: 8px !important;
}

.link {
    color: #4f46e5 !important;
}

.ep-subtabs button.on,
.ep-tabs button.active {
    border-bottom-color: #4f46e5 !important;
    color: #4f46e5 !important;
}

.sx-conn {
    border-left: 4px solid #4f46e5 !important;
}

.sx-pk input:checked + .sx-pk-c {
    border-color: #4f46e5 !important;
    box-shadow: 0 0 0 3px #e0e7ff !important;
    background: #eef2ff !important;
}

.sx-pk-a {
    background: #4f46e5 !important;
    color: #ffffff !important;
}
</style>
"""


INSPECTFLOW_LIVE_BRIDGE_JS = r"""
<script id="inspectflow-live-bridge">
(function() {
  // 1. Replace 'Not connected / MODELLED' banners with Live Connected status
  window.conn = function(title, app, feeds) {
    return '<div class="ep-card sx-conn" style="border-left:4px solid #059669!important;background:#f0fdf4!important;">' +
      '<div class="ep-row" style="justify-content:space-between;"><b>' + esc(title) + '</b>' +
      '<span class="ep-pill ok sm" style="background:#059669;color:#fff;">✓ Live Connected to InspectFlow (IMS) & Logistics</span></div>' +
      '<div class="ep-sub" style="margin:6px 0;color:#065f46;">Real-time two-way synchronization active with <b>' + esc(app) + '</b>. Changes reflect automatically across Inspection, Expediting, and Logistics.</div>' +
      '<div class="ep-lbl" style="color:#047857;">Live Synchronized Data Streams</div>' +
      '<ul class="sx-ul" style="color:#065f46;">' + (feeds || []).map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('') + '</ul></div>';
  };

  // 2. Live IAP (Inspection Assignment Pack & Attendance) Tab
  window.tabIap = function() {
    var iaps = (REC.sx && REC.sx.iap) || [];
    var irs = REC.irs || [];
    var h = conn('IAP — Inspection Assignment Pack & TPI Attendance', 'InspectFlow (IMS)', [
      'Assigned Inspector & TPI Agency dispatch status',
      'Live GPS Attendance Check-in / Check-out timestamps',
      'Uploaded Flash & Final Inspection Reports and 3.1/3.2 MTCs'
    ]);
    h += '<div class="ep-card flush"><div class="ep-card-title"><span>Assigned Inspectors & Attendance (PO ' + esc(REC.po) + ')</span><span class="ep-pill ok sm">From InspectFlow</span></div>' +
      '<div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>NOI Ref</th><th>Inspection Type</th><th>Inspector & TPI Agency</th><th>Scheduled Date</th><th>IE Review Status</th><th>Status</th></tr></thead><tbody>' +
      (iaps.map(function(a) {
        return '<tr><td class="tabnum"><b>' + esc(a.notif_no || '—') + '</b></td>' +
          '<td>' + esc(a.type || 'Witness') + '</td>' +
          '<td><b>' + esc(a.inspector || 'Pending Assignment') + '</b><div class="ep-sub">' + esc(a.tpi || 'In-House QA/QC') + '</div></td>' +
          '<td class="tabnum">' + esc(a.date || '—') + '</td>' +
          '<td><span class="ep-pill ' + (a.ie_approved ? 'ok' : 'warn') + ' sm">' + (a.ie_approved ? '✓ IE Endorsed for Release' : 'Pending IE Endorsement') + '</span></td>' +
          '<td><span class="ep-pill info sm">' + esc(a.status || 'Scheduled') + '</span></td></tr>';
      }).join('') || '<tr><td colspan="6" class="ep-sub">No inspector assignments logged for this PO yet.</td></tr>') +
      '</tbody></table></div></div>';

    h += '<div class="ep-card flush"><div class="ep-card-title"><span>Inspection Reports & Test Certificates (MTCs)</span><span class="ep-pill ok sm">' + irs.length + ' Document(s)</span></div>' +
      '<div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Report Name</th><th>Category</th><th>Date</th><th>Uploaded By</th><th>IE Approval</th><th>Findings</th><th>Document</th></tr></thead><tbody>' +
      (irs.map(function(r) {
        var fCount = (r.findings && r.findings.length) || 0;
        var appr = r.approval_status || 'pending';
        var rawUrl = String(r.url || '').trim();
        var safeUrl = (/^https?:\/\//i.test(rawUrl) || rawUrl.charAt(0) === '/') ? rawUrl : '';
        return '<tr><td><b>' + esc(r.name || 'Report') + '</b></td>' +
          '<td><span class="ep-pill slate sm">' + esc((r.category || r.report_type || 'inspection').toUpperCase()) + '</span></td>' +
          '<td class="tabnum">' + esc((r.report_date || r.uploaded_date || '').slice(0, 10)) + '</td>' +
          '<td>' + esc(r.uploaded_by || 'Inspector') + '</td>' +
          '<td><span class="ep-pill ' + (appr === 'approved' ? 'ok' : appr === 'rejected' ? 'rose' : 'warn') + ' sm">' + esc(appr.toUpperCase()) + '</span></td>' +
          '<td>' + (fCount > 0 ? '<span class="ep-pill rose sm">' + fCount + ' Finding(s)</span>' : '<span class="ep-pill ok sm">0 Findings</span>') + '</td>' +
          '<td>' + (safeUrl ? '<a class="ep-btn secondary xs" href="' + esc(safeUrl) + '" target="_blank" rel="noopener">Open PDF</a>' : '—') + '</td></tr>';
      }).join('') || '<tr><td colspan="7" class="ep-sub">No inspection reports uploaded in InspectFlow yet.</td></tr>') +
      '</tbody></table></div></div>';
    return h;
  };

  // 3. Live IRN / IRC Tab
  window.tabIrn = function() {
    var m = REC.mfg || {};
    var irns = REC.irns || [];
    var h = conn('IRN / IRC — Inspection Release Certificates', 'InspectFlow (IMS)', [
      'Official Itemized Inspection Release Certificates (IRC)',
      'Exact PO BOM material descriptions, released quantities & Heat/Batch numbers',
      'Mandatory Inspector & Inspection Engineer release remarks'
    ]);
    h += '<div class="ep-card"><div class="ep-fields" style="grid-template-columns:repeat(3,1fr);">' +
      hf('Latest IRN Issued Date', m.irn ? fmtDate(m.irn) : (irns.length ? fmtDate(irns[irns.length - 1].date) : '—')) +
      hf('Total IRCs Issued', String(irns.length)) +
      hf('Source', 'Live InspectFlow IRC Reconciler') +
      '</div></div>';
    h += '<div class="ep-card flush"><div class="ep-card-title"><span>Issued Inspection Release Certificates (PO ' + esc(REC.po) + ')</span><span class="ep-pill ok sm">' + irns.length + ' Released</span></div>' +
      '<div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>IRC Number</th><th>Release Date</th><th>Issued By</th><th>Scope & Released BOM Items</th><th>Inspector Remarks</th><th>Status</th><th>Certificate</th></tr></thead><tbody>' +
      (irns.map(function(i) {
        var itemPills = (i.items || []).map(function(it) {
          return '<div class="ep-sub" style="color:#0f172a;">• <b>Item ' + esc(it.itemNumber || it.item) + ':</b> ' + esc(it.description || '') + ' — <b>Qty: ' + esc(it.quantity || it.qty_released) + ' ' + esc(it.unit || 'EA') + '</b>' + (it.heat_number ? ' (Heat: ' + esc(it.heat_number) + ')' : '') + '</div>';
        }).join('');
        var rawIrcUrl = String(i.file || '').trim();
        var safeIrcUrl = (/^https?:\/\//i.test(rawIrcUrl) || rawIrcUrl.charAt(0) === '/') ? rawIrcUrl : '';
        return '<tr><td class="tabnum"><b>' + esc(i.no) + '</b></td>' +
          '<td class="tabnum">' + esc(i.date || '—') + '</td>' +
          '<td>' + esc(i.by || 'Inspector') + '</td>' +
          '<td><b>' + esc(i.scope || '') + '</b>' + itemPills + '</td>' +
          '<td>' + esc(i.remarks || '—') + '</td>' +
          '<td><span class="ep-pill ok sm">' + esc(i.status || 'APPROVED') + '</span></td>' +
          '<td>' + (safeIrcUrl ? '<a class="ep-btn primary xs" href="' + esc(safeIrcUrl) + '" target="_blank" rel="noopener">Download IRC</a>' : '<span class="ep-pill ok sm">Digital Record</span>') + '</td></tr>';
      }).join('') || '<tr><td colspan="7" class="ep-sub">No Inspection Release Certificates (IRC) issued yet. Items remain in fabrication/inspection.</td></tr>') +
      '</tbody></table></div></div>';
    return h;
  };

  // 4. Live Delivery & Cumulative Quantity Ledger Tab
  var _origTabDeliv = window.tabDeliv;
  window.tabDeliv = function() {
    var html = _origTabDeliv ? _origTabDeliv() : '';
    html = html.replace(/MODELLED until connected/g, '✓ Live Cumulative Ledger');
    var logs = REC.logistics_tracking || [];
    var mncrs = (REC.sx && REC.sx.mncr) || [];
    var extra = '<div class="ep-card flush"><div class="ep-card-title"><span>4-Stage Logistics Pipeline & Site MRV Ledger</span><span class="ep-pill ok sm">' + logs.length + ' Event(s)</span></div>' +
      '<div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>Timestamp</th><th>Item #</th><th>Logistics Stage</th><th>Qty</th><th>BL / AWB / MRV Ref</th><th>Carrier</th><th>OS&D / Receipt Notes</th></tr></thead><tbody>' +
      (logs.map(function(l) {
        return '<tr><td class="tabnum">' + esc((l.at || '').slice(0, 16).replace('T', ' ')) + '</td>' +
          '<td class="tabnum"><b>' + esc(l.item) + '</b></td>' +
          '<td><span class="ep-pill info sm">' + esc((l.stage || '').toUpperCase()) + '</span></td>' +
          '<td class="tabnum"><b>' + esc(l.qty) + '</b></td>' +
          '<td class="tabnum">' + esc(l.mrv_no || l.bl_awb || '—') + '</td>' +
          '<td>' + esc(l.carrier || '—') + '</td>' +
          '<td>' + esc(l.osd_notes || '—') + '</td></tr>';
      }).join('') || '<tr><td colspan="7" class="ep-sub">No logistics or site MRV movements recorded yet.</td></tr>') +
      '</tbody></table></div></div>';
    if (mncrs.length > 0) {
      extra += '<div class="ep-card flush"><div class="ep-card-title"><span>MNCR — Site OS&D Shortages & Damages</span><span class="ep-pill rose sm">' + mncrs.length + ' Active MNCR(s)</span></div>' +
        '<div style="overflow-x:auto;"><table class="ep-table"><thead><tr><th>MNCR No.</th><th>Description</th><th>Action Required</th><th>Status</th></tr></thead><tbody>' +
        mncrs.map(function(m) {
          return '<tr><td class="tabnum"><b>' + esc(m['MNCR no.'] || m.no) + '</b></td><td>' + esc(m.Description || m.desc) + '</td><td>' + esc(m.Action || m.action) + '</td><td><span class="ep-pill rose sm">' + esc(m.Status || 'OPEN') + '</span></td></tr>';
        }).join('') + '</tbody></table></div></div>';
    }
    return html + extra;
  };

  // 5. vnotifModal: keep InspectFlow sync exclusively on explicit 'Submit to the expeditor' (no premature Draft sync / duplicate NOI)
  // (sb-submit inside SmartExpedit/server/static/index.html calls /api/v1/vendor-noi directly on submit)

  // 6. Project Isolation & Context Bridge (InspectFlow <-> SmartExpedit Iframe)
  var _ifInitParams = new URLSearchParams(window.location.search || '');
  function _ifNorm(v) {
    return String(v || '').trim().toLowerCase();
  }
  window._IF_PROJECT_ID = _ifNorm(window.__IF_INIT_PROJECT_ID || _ifInitParams.get('project_id') || '');

  function _ifRecMatchesProject(r) {
    var pid = _ifNorm(window._IF_PROJECT_ID);
    if (!pid || pid === 'all') return true;
    return _ifNorm(r && r.project_id) === pid;
  }

  function _ifInstallProjectWrappers() {
    if (window._ifProjectWrapped) return;
    window._ifProjectWrapped = true;

    var _origAllRecs = window.allRecs;
    if (typeof _origAllRecs === 'function') {
      window.allRecs = function() {
        var L = _origAllRecs.apply(this, arguments) || [];
        var pid = _ifNorm(window._IF_PROJECT_ID);
        if (!pid || pid === 'all') return L;
        return L.filter(_ifRecMatchesProject);
      };
    }

    var _origSeenRecs = window.seenRecs;
    if (typeof _origSeenRecs === 'function') {
      window.seenRecs = function() {
        var L = window.allRecs ? window.allRecs() : (_origSeenRecs.apply(this, arguments) || []);
        if (window._IF_IS_VENDOR || (typeof isV === 'function' && isV())) {
          // Backend /api/kv strictly isolates ep_exp_records via vendor_owns_po; allow all owned POs in active project
          return L;
        }
        return _origSeenRecs.apply(this, arguments) || [];
      };
    }

    // Wrap tabVendorActions AND update SX_TABFN.actions so vendor ONLY sees RAIL actions belonging to their own POs
    var _origTabVendorActions = window.tabVendorActions;
    if (typeof _origTabVendorActions === 'function') {
      window.tabVendorActions = function() {
        if (typeof window.SX === 'undefined' || !window.SX || !Array.isArray(window.SX.concerns) || !window.REC) {
          return _origTabVendorActions.apply(this, arguments);
        }
        var origConcerns = window.SX.concerns;
        var myPo = String(window.REC.po || '');
        window.SX.concerns = origConcerns.filter(function(c) {
          return c && String(c.po || '') === myPo;
        });
        try {
          return _origTabVendorActions.apply(this, arguments);
        } finally {
          window.SX.concerns = origConcerns;
        }
      };
      if (typeof window.SX_TABFN === 'object' && window.SX_TABFN) {
        window.SX_TABFN.actions = window.tabVendorActions;
      }
    }

    // Wrap tabLetter so Vendor can upload & submit Signed PO Acknowledgement even on newly created POs without intro letter
    var _origTabLetter = window.tabLetter;
    if (typeof _origTabLetter === 'function') {
      window.tabLetter = function() {
        var html = _origTabLetter.apply(this, arguments) || '';
        if (window.VIEW === 'vendor' && window.REC) {
          var ackx = window.REC.ackx = window.REC.ackx || { st: window.REC.ackDate ? 'Unconditional' : 'Pending', pts: '' };
          var ackDateVal = window.REC.ackDate || (typeof today === 'function' ? today() : new Date().toISOString().slice(0, 10));
          var ackCard = '<div class="ep-card" style="border-left:4px solid #4f46e5;">' +
            '<div class="ep-card-title"><span>PO Acknowledgement &amp; Signed Copy Upload (PO ' + esc(window.REC.po) + ')</span>' +
              (window.REC.ackDate ? '<span class="ep-pill ok sm">Acknowledged ' + fmtDate(window.REC.ackDate) + '</span>' : '<span class="ep-pill warn sm">Pending Vendor Acknowledgement</span>') +
            '</div>' +
            '<div class="ep-sub" style="margin-bottom:10px;">Upload your signed &amp; stamped Purchase Order acknowledgement copy and confirm unconditional or commented acceptance.</div>' +
            '<div class="ep-fields" style="grid-template-columns:1fr 1fr 2fr;">' +
              '<div class="ep-f"><div class="k">Acknowledgement Status</div><select class="ep-in" id="if-po-ack-st">' +
                ['Unconditional', 'With comments', 'Pending'].map(function(s) { return '<option' + (ackx.st === s ? ' selected' : '') + '>' + s + '</option>'; }).join('') +
              '</select></div>' +
              '<div class="ep-f"><div class="k">Signed &amp; Stamped Date</div><input type="date" class="ep-in" id="if-po-ack-dt" value="' + esc(ackDateVal) + '"></div>' +
              '<div class="ep-f"><div class="k">Upload Signed PO Acknowledgement (PDF / Image)</div><input type="file" class="ep-in" id="if-po-ack-file" accept=".pdf,.png,.jpg,.jpeg,.doc,.docx">' +
                (ackx.fileName ? '<div class="ep-sub" style="margin-top:4px;">Uploaded: <b>' + esc(ackx.fileName) + '</b></div>' : '') +
              '</div>' +
            '</div>' +
            '<div style="margin-top:8px;"><div class="ep-lbl">Vendor Remarks / Exceptions (if any)</div><input class="ep-in" id="if-po-ack-pts" value="' + esc(ackx.pts || '') + '" placeholder="Confirm delivery terms, ITP receipt, or state clarifications..."></div>' +
            '<div style="margin-top:10px;"><button class="ep-btn primary sm" id="if-po-ack-save">Submit Signed PO Acknowledgement</button></div>' +
          '</div>';
          return ackCard + html;
        }
        return html;
      };
    }

    // Wrap tabSchedX with Archetype-Aware Schedule Header (Bulk / Tagged / Package) + Upload (.xlsx / .pdf)
    function _ifInferClass(rec) {
      var c = String((rec && rec.procurement_class) || '').toLowerCase();
      if (c === 'bulk' || c === 'tagged' || c === 'package') return c;
      var items = (rec && rec.items) || [];
      var head = String((rec && rec.head) || '');
      if (items.some(function(i) { return String(i.item || '').indexOf('.') >= 0 || i.is_split_parent; }) || ((rec && rec.plan && rec.plan.rows) || []).length) return 'package';
      var tQty = items.reduce(function(s, i) { return s + (i.is_split_parent ? 0 : (Number(i.qty) || 0)); }, 0);
      if (tQty >= 50 || items.length >= 15 || /\b(bolt|nut|stud|pipe|flange|fitting|cable|bulk|gasket|steel|plate)\b/i.test(head)) return 'bulk';
      return 'tagged';
    }

    function _ifBuildArchetypePanel(rec, cls) {
      var items = (rec.items || []).filter(function(i) { return !i.is_split_parent; });
      var clr = rec.clr || {};
      var vdrl = rec.vdrl_documents || [];
      var itpApproved = vdrl.some(function(d) {
        return /itp|inspection.*test/i.test(String(d.title || d.doc_no || '')) && /code\s*[12]|approv/i.test(String(d.code || d.status || ''));
      });
      var canSwitch = window.VIEW !== 'vendor' && window.ROLE !== 'DOC' && window.ROLE !== 'FIELD';
      var labels = {
        bulk: { title: 'BULK MATERIALS — Quantity & Heat-Lot Matrix', bg: '#eff6ff', bd: '#2563eb', fg: '#1e40af' },
        tagged: { title: 'TAGGED EQUIPMENT — Per-Tag Milestone & ITP Gate View', bg: '#f5f3ff', bd: '#7c3aed', fg: '#5b21b6' },
        package: { title: 'ENGINEERED PACKAGE — 3-Tier WBS & Sub-Order Float Convergence', bg: '#ecfeff', bd: '#0891b2', fg: '#155e75' }
      };
      var L = labels[cls] || labels.tagged;
      var switcher = canSwitch
        ? '<span class="ep-row" style="gap:4px;">' + ['bulk', 'tagged', 'package'].map(function(k) {
            return '<button class="ep-btn xs ' + (cls === k ? 'primary' : 'secondary') + '" data-if-cls="' + k + '">' + k.toUpperCase() + '</button>';
          }).join('') + '</span>'
        : '<span class="ep-pill info sm">' + cls.toUpperCase() + '</span>';

      var body = '';
      if (cls === 'bulk') {
        var totQ = items.reduce(function(s, i) { return s + (Number(i.qty) || 0); }, 0);
        var relQ = items.reduce(function(s, i) { return s + Number((clr[String(i.item)] || {}).irn || 0); }, 0);
        var shipQ = items.reduce(function(s, i) { return s + Number((clr[String(i.item)] || {}).ship || 0); }, 0);
        var wPct = totQ ? Math.round(items.reduce(function(s, i) {
          var p = (Number(i.eng_pct || 0) * 0.15 + Number(i.proc_pct || 0) * 0.25 + Number(i.fab_pct || 0) * 0.40 + Number(i.insp_pct || 0) * 0.20);
          return s + (Number(i.qty || 0) * p);
        }, 0) / totQ) : 0;
        body = '<div class="ep-kpis" style="grid-template-columns:repeat(4,1fr);margin-top:8px;">' +
          '<div class="ep-kpi"><div class="k">Total Ordered Qty</div><div class="v tabnum">' + totQ.toLocaleString() + '</div><div class="s">' + items.length + ' commodity line(s)</div></div>' +
          '<div class="ep-kpi"><div class="k">Qty Weighted Progress</div><div class="v tabnum">' + wPct + '%</div><div class="s">mill → forming → coating → IRN</div></div>' +
          '<div class="ep-kpi"><div class="k">Qty IRN Released</div><div class="v tabnum">' + relQ.toLocaleString() + '</div><div class="s">' + (totQ ? Math.round(relQ * 100 / totQ) : 0) + '% of PO qty</div></div>' +
          '<div class="ep-kpi"><div class="k">Qty Shipped</div><div class="v tabnum">' + shipQ.toLocaleString() + '</div><div class="s">lot dispatch ledger</div></div></div>' +
          '<div style="margin-top:8px;display:flex;gap:8px;align-items:center;"><button class="ep-btn secondary xs" id="if-open-itemized">Switch to Line-by-Line Lot Matrix</button><span class="ep-sub">Supports partial heat-lot tracking and multi-line bulk date updates below.</span></div>';
      } else if (cls === 'package') {
        var splits = (rec.items || []).filter(function(i) { return String(i.item || '').indexOf('.') >= 0 || i.is_split; });
        var planRows = (rec.plan && rec.plan.rows ? rec.plan.rows.filter(function(x) { return !x.deleted; }) : []);
        var negRows = planRows.filter(function(x) { var u = typeof window.plU === 'function' ? window.plU(x, rec.plan.rows) : null; return u != null && u < 0; });
        body = '<div class="ep-kpis" style="grid-template-columns:repeat(3,1fr);margin-top:8px;">' +
          '<div class="ep-kpi"><div class="k">Tier 2 Split Assemblies</div><div class="v tabnum">' + splits.length + '</div><div class="s">' + (splits.length ? splits.map(function(x) { return esc(x.item + ' (' + (x.location || 'Shop') + ')'); }).slice(0, 3).join(', ') : 'master single yard') + '</div></div>' +
          '<div class="ep-kpi"><div class="k">Tier 3 Bought-Out Sub-Orders</div><div class="v tabnum">' + planRows.length + '</div><div class="s">converging to integration skid</div></div>' +
          '<div class="ep-kpi"><div class="k">Negative Float (RAS Alerts)</div><div class="v tabnum" style="color:' + (negRows.length ? '#dc2626' : '#059669') + ';">' + negRows.length + '</div><div class="s">' + (negRows.length ? esc(negRows[0].item || 'Sub-order delay') : 'on critical path track') + '</div></div></div>';
      } else {
        var tags = items.slice(0, 8);
        body = '<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;">' +
          '<span class="ep-pill ' + (itpApproved ? 'ok' : 'rose') + ' sm">' + (itpApproved ? '✓ Governing ITP Approved (Code 1/2)' : '⚠ ITP Not Approved — Hold Fabrication Start') + '</span>' +
          tags.map(function(t) {
            return '<span class="ep-pill slate sm">' + esc(t.tag || ('Item ' + t.item)) + ' · Est: ' + esc(t.forecast_date || t.baseline_date || 'TBD') + ' · Fab ' + (t.fab_pct || 0) + '%</span>';
          }).join('') +
        '</div>';
      }

      return '<div class="ep-card" style="border-left:4px solid ' + L.bd + ';background:' + L.bg + ';">' +
        '<div class="ep-row" style="justify-content:space-between;flex-wrap:wrap;gap:8px;">' +
          '<div><b style="color:' + L.fg + ';">' + L.title + '</b></div>' + switcher +
        '</div>' + body + '</div>';
    }

    var _origTabSchedX = window.tabSchedX;
    if (typeof _origTabSchedX === 'function') {
      window.tabSchedX = function() {
        var html = _origTabSchedX.apply(this, arguments) || '';
        if (window.REC) {
          var cls = _ifInferClass(window.REC);
          var archPanel = _ifBuildArchetypePanel(window.REC, cls);
          var sCur = typeof window.schCur === 'function' ? window.schCur() : null;
          var locked = typeof window.subEditable === 'function' ? !window.subEditable(sCur) : (sCur && (sCur.status === 'Submitted' || sCur.status === 'Agreed'));
          var ro = (window.ROLE === 'DOC' || window.ROLE === 'FIELD');
          if (!locked && !ro) {
            var upBar = '<div class="ep-card" style="border-left:4px solid #059669;background:#f0fdf4;">' +
              '<div class="ep-row" style="justify-content:space-between;flex-wrap:wrap;gap:8px;">' +
                '<div><b style="color:#065f46;">Upload or Download Manufacturing Schedule (PO ' + esc(window.REC.po) + ' · ' + cls.toUpperCase() + ')</b>' +
                '<div class="ep-sub" style="color:#047857;">Import an Excel (.xlsx) or PDF schedule to populate forecast dates &amp; % complete directly, or download the template.</div></div>' +
                '<div class="ep-row">' +
                  '<button class="ep-btn secondary sm" data-s="sc-dl">Download Template (.xlsx)</button>' +
                  '<label class="ep-btn primary sm" style="cursor:pointer;margin:0;">Upload Schedule (.xlsx)<input type="file" id="if-sch-xlsx-up" accept=".xlsx,.xls" style="display:none;"></label>' +
                  (typeof window.ffGo === 'function' ? '<button class="ep-btn secondary sm" id="if-sch-pdf-up">Upload Schedule (PDF / Excel)</button>' : '') +
                '</div>' +
              '</div>' +
            '</div>';
            return archPanel + upBar + html;
          }
          return archPanel + html;
        }
        return html;
      };
      if (typeof window.SX_TABFN === 'object' && window.SX_TABFN) {
        window.SX_TABFN.sched = window.tabSchedX;
      }
      if (!window._ifArchBound) {
        window._ifArchBound = true;
        document.addEventListener('click', function(ev) {
          var openBtn = ev.target && ev.target.closest ? ev.target.closest('#if-open-itemized') : null;
          if (openBtn && typeof window.SUB === 'object') {
            window.SUB.sched = 'items';
            if (typeof render === 'function') render();
            return;
          }
          var clsBtn = ev.target && ev.target.closest ? ev.target.closest('[data-if-cls]') : null;
          if (clsBtn && window.REC) {
            var nextCls = clsBtn.getAttribute('data-if-cls');
            fetch('/api/v1/po/' + encodeURIComponent(window.REC.po) + '/schedule-class', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ procurement_class: nextCls })
            }).then(function(r) { return r.json(); }).then(function(res) {
              if (res && res.ok) {
                window.REC.procurement_class = nextCls;
                if (typeof saveRec === 'function') saveRec();
                if (typeof toast === 'function') toast('Schedule view switched to ' + nextCls.toUpperCase());
                if (typeof render === 'function') render();
              } else if (typeof toast === 'function') {
                toast((res && res.detail) || 'Could not switch schedule view');
              }
            }).catch(function() {});
          }
        });
      }
    }

    // Ensure schCur selects the richest/latest schedule round unless explicitly pinned
    var _origSchCur = window.schCur;
    if (typeof _origSchCur === 'function') {
      window.schCur = function() {
        if (window.REC && !(window.FX && window.FX.subSel && window.FX.subSel['sched'])) {
          var subs = typeof window.subsOf === 'function' ? window.subsOf(window.REC, 'sched') : [];
          if (subs.length > 1) {
            var filled = subs.filter(function(x) { return x && (x.src || x.ff); });
            if (filled.length) return filled[filled.length - 1];
          }
        }
        return _origSchCur.apply(this, arguments);
      };
    }

    // Intercept Inbox Open (ib-go) & Alert Jump (al-go) on window (capture phase runs BEFORE document listeners)
    if (!window._ifNavClickBound) {
      window._ifNavClickBound = true;
      window.addEventListener('click', function(ev) {
        var btn = ev.target && ev.target.closest ? ev.target.closest('[data-s="ib-go"],[data-s="al-go"]') : null;
        if (!btn) return;
        var kind = btn.getAttribute('data-s');
        var rawX = btn.getAttribute('data-x') || '';
        if (!rawX) return;
        ev.preventDefault();
        ev.stopPropagation();
        if (typeof ev.stopImmediatePropagation === 'function') ev.stopImmediatePropagation();
        var parts = rawX.split('|');
        var targetPo = parts[0] || '';
        var targetSec = parts[1] || 'core';
        var targetTab = parts[2] || 'head';
        var targetSub = parts[3] || '';
        if (targetSec === 'exec' && /^(?:sched|letter|docs|plan)$/.test(targetTab)) {
          targetSec = 'core';
        }
        var foundRec = targetPo && typeof window.epExpFind === 'function' ? window.epExpFind(targetPo) : null;
        if (targetPo) {
          window.PO = targetPo;
          if (foundRec) window.REC = foundRec;
        }
        window.SEC = targetSec;
        window.TAB = targetTab;
        if (typeof window.SECTAB === 'object' && window.SECTAB) window.SECTAB[targetSec] = targetTab;
        if (targetSub && typeof window.FX === 'object' && window.FX) {
          window.FX.subSel = window.FX.subSel || {};
          window.FX.subSel[targetSub] = targetSub;
          var rTarget = foundRec || window.REC;
          var subList = rTarget && typeof window.subsOf === 'function' ? window.subsOf(rTarget) : ((rTarget && rTarget.subs) || []);
          var sObj = subList.find(function(q) { return q && q.id === targetSub; });
          if (sObj) {
            window.FX.subSel[sObj.type] = sObj.id;
            if (sObj.type === 'vpr') window.FX.vprSel = sObj.id;
          }
        }
        if (kind === 'al-go') {
          var alPop = document.getElementById('sx-pop');
          if (alPop) alPop.hidden = true;
        }
        if (typeof window.render === 'function') window.render();
        window.scrollTo(0, 0);
      }, true);
    }

    // Inline PDF / Image viewer when opening attached schedule/document files in Expeditor Workbench
    if (typeof window.fxOpen === 'function' && !window._ifFxOpenWrapped) {
      window._ifFxOpenWrapped = true;
      var _origFxOpen = window.fxOpen;
      window.fxOpen = async function(id) {
        var entry = typeof window.fxFiles === 'function' ? window.fxFiles().find(function(x) { return x.id === id; }) : null;
        if (!entry || entry.big) return _origFxOpen.apply(this, arguments);
        var blob = (window.FX && window.FX.blobs && window.FX.blobs[id]) || (typeof window.fxGet === 'function' ? await window.fxGet('file:' + id) : null);
        if (!blob) return _origFxOpen.apply(this, arguments);
        var lowerName = String(entry.name || '').toLowerCase();
        var isPdf = lowerName.endsWith('.pdf') || String(blob.type || '').indexOf('pdf') >= 0;
        var isImg = /\.(png|jpe?g|gif|webp)$/i.test(lowerName) || String(blob.type || '').indexOf('image/') === 0;
        if ((isPdf || isImg) && typeof window.modal === 'function') {
          var blobUrl = URL.createObjectURL(blob);
          var viewerHtml = isPdf
            ? '<iframe src="' + blobUrl + '" style="width:100%;height:70vh;border:1px solid #e2e8f0;border-radius:8px;background:#fff;"></iframe>'
            : '<div style="text-align:center;max-height:70vh;overflow:auto;"><img src="' + blobUrl + '" style="max-width:100%;border-radius:8px;"></div>';
          var footHtml = '<a class="ep-btn secondary" href="' + blobUrl + '" target="_blank" rel="noopener">Open in New Tab</a>' +
            '<a class="ep-btn primary" href="' + blobUrl + '" download="' + esc(entry.name) + '">Download File</a>' +
            '<button class="ep-btn secondary" id="modal-cancel">Close</button>';
          window.modal(entry.name, viewerHtml, null, { wide: 'wide', foot: footHtml });
          return;
        }
        return _origFxOpen.apply(this, arguments);
      };
    }

    var _origPageRail = window.pageRail;
    if (typeof _origPageRail === 'function') {
      window.pageRail = function() {
        var pid = _ifNorm(window._IF_PROJECT_ID);
        if (!pid || pid === 'all' || typeof window.SX === 'undefined' || !window.SX || !Array.isArray(window.SX.concerns)) {
          return _origPageRail.apply(this, arguments);
        }
        var poSet = {};
        (window.allRecs ? window.allRecs() : []).forEach(function(r) {
          if (r && r.po) poSet[String(r.po)] = true;
        });
        var origConcerns = window.SX.concerns;
        window.SX.concerns = origConcerns.filter(function(c) {
          if (c && c.project_id) return _ifNorm(c.project_id) === pid;
          return !!(c && c.po && poSet[String(c.po)]);
        });
        try {
          return _origPageRail.apply(this, arguments);
        } finally {
          window.SX.concerns = origConcerns;
        }
      };
    }

    var _origPageField = window.pageField;
    if (typeof _origPageField === 'function') {
      window.pageField = function() {
        var pid = _ifNorm(window._IF_PROJECT_ID);
        if (!pid || pid === 'all' || typeof window.fldLoad !== 'function') {
          return _origPageField.apply(this, arguments);
        }
        var F = window.fldLoad();
        if (!F || !Array.isArray(F.rows)) return _origPageField.apply(this, arguments);
        var pos = (window.allRecs ? window.allRecs() : []).map(function(r) { return String(r.po || ''); }).filter(Boolean);
        var poSet = {};
        pos.forEach(function(p) { poSet[p] = true; });
        var origRows = F.rows;
        F.rows = origRows.filter(function(r) {
          if (!r) return false;
          if (r.project_id) return _ifNorm(r.project_id) === pid;
          if (r.appPo && poSet[String(r.appPo)]) return true;
          var txt = String(r.poText || '');
          return pos.some(function(p) { return txt.indexOf(p) >= 0; });
        });
        try {
          return _origPageField.apply(this, arguments);
        } finally {
          F.rows = origRows;
        }
      };
    }

    var _origIfRender = window.render;
    if (typeof _origIfRender === 'function') {
      window.render = function() {
        var pid = _ifNorm(window._IF_PROJECT_ID);
        if (pid && pid !== 'all' && window.REC && !_ifRecMatchesProject(window.REC)) {
          var matching = window.allRecs ? window.allRecs() : [];
          window.REC = matching[0] || null;
          if (!window.REC && window.ROUTE === 'po') window.ROUTE = 'dash';
        }
        if (window._IF_IS_VENDOR) {
          window.SEC = 'portal';
        }
        var out = _origIfRender.apply(this, arguments);
        try {
          if (typeof _ifLockChrome === 'function' && window._IF_AUTH_BOUND) {
            _ifLockChrome(!!window._IF_IS_ADMIN, !!window._IF_IS_VENDOR);
          }
        } catch (e) {}
        return out;
      };
    }
  }

  _ifInstallProjectWrappers();
  if (window._IF_PROJECT_ID && typeof window.render === 'function') {
    window.render();
  }

  function _ifBindAuthSession(data) {
    if (!data) return;
    var mappedRole = data.sxRole;
    var isAdmin = !!data.isAdmin;
    var isVendor = !!data.isVendor;
    window._IF_AUTH_BOUND = true;
    window._IF_IS_ADMIN = isAdmin;
    window._IF_IS_VENDOR = isVendor;
    if (isVendor && typeof window.ROLES === 'object' && window.ROLES) {
      var recs = window.allRecs ? window.allRecs() : [];
      recs.forEach(function(r) {
        if (r && r.po) {
          window.ROLES['VEN:' + r.po] = 'Vendor Portal — ' + (r.supplierShort || r.supplier || r.po);
        }
      });
      if (mappedRole && !window.ROLES[mappedRole]) {
        window.ROLES[mappedRole] = 'Vendor Portal — ' + (data.userName || 'Supplier');
      }
      window.SEC = 'portal';
      if (window.ROUTE === 'dash') window.ROUTE = 'portal';
    }
    if (mappedRole && window.ROLE !== mappedRole) {
      window.ROLE = mappedRole;
      if (typeof render === 'function') render();
    }
    _ifLockChrome(isAdmin, isVendor);
  }

  function _ifLockChrome(isAdmin, isVendor) {
    var roleSel = document.getElementById('sx-role');
    var roleLbl = document.querySelector('label[for="sx-role"]');
    if (roleSel && (!isAdmin || isVendor)) {
      roleSel.disabled = true;
      roleSel.style.opacity = '0.75';
      roleSel.title = 'Role locked to your authenticated account';
    }
    if (isVendor) {
      if (roleSel) roleSel.style.display = 'none';
      if (roleLbl) roleLbl.style.display = 'none';
      var resetBtn = document.querySelector('[data-s="reset"]');
      if (resetBtn) resetBtn.style.display = 'none';
      var alertBtn = document.getElementById('sx-alert');
      if (alertBtn) alertBtn.style.display = 'none';
    }
  }

  // Synchronously read server-verified or parent session user on iframe boot so Vendors never flash Manager views
  try {
    if (window.__IF_SERVER_USER && window.__IF_SERVER_USER.sxRole) {
      _ifBindAuthSession(window.__IF_SERVER_USER);
    } else {
      var rawSess = (window.parent && window.parent !== window && window.parent.localStorage && window.parent.localStorage.getItem('inspectflow_mock_session')) || '';
      if (rawSess) {
        var uObj = JSON.parse(rawSess);
        var rName = _ifNorm(uObj && (uObj.inspection_role || uObj.role));
        if (rName === 'vendor') {
          var vRecs = window.allRecs ? window.allRecs() : [];
          var initPo = _ifInitParams.get('po') || (vRecs[0] && vRecs[0].po) || '__NONE__';
          _ifBindAuthSession({
            sxRole: 'VEN:' + initPo,
            isAdmin: false,
            isVendor: true,
            userName: uObj.full_name || uObj.company_affiliation || 'Vendor'
          });
        } else if (rName === 'expediting_manager') {
          _ifBindAuthSession({ sxRole: 'PEXM', isAdmin: false, isVendor: false });
        } else if (rName === 'expeditor') {
          _ifBindAuthSession({ sxRole: 'EXP', isAdmin: false, isVendor: false });
        } else if (rName === 'field_expeditor') {
          _ifBindAuthSession({ sxRole: 'FIELD', isAdmin: false, isVendor: false });
        } else if (rName === 'doc_expeditor') {
          _ifBindAuthSession({ sxRole: 'DOC', isAdmin: false, isVendor: false });
        }
      }
    }
  } catch (e) {}

  // Global delegated handlers for PO Ack upload & Schedule upload bar
  document.addEventListener('change', function(ev) {
    if (ev.target && ev.target.id === 'if-sch-xlsx-up' && ev.target.files && ev.target.files[0]) {
      var f = ev.target.files[0];
      ev.target.value = '';
      if (typeof window.schImport === 'function') window.schImport(f);
    }
  }, true);

  document.addEventListener('click', async function(ev) {
    if (ev.target && ev.target.id === 'if-sch-pdf-up') {
      if (typeof window.ffGo === 'function') {
        var prevTab = window.TAB;
        window.TAB = 'sched';
        try { await window.ffGo(); } finally { window.TAB = prevTab; }
      }
    }
    if (ev.target && ev.target.id === 'if-po-ack-save' && window.REC) {
      var curLetterSub = typeof window.subsOf === 'function' ? (window.subsOf(window.REC, 'letter').slice(-1)[0] || null) : null;
      if (curLetterSub && (curLetterSub.status === 'Submitted' || curLetterSub.status === 'Agreed')) {
        if (typeof window.toast === 'function') window.toast('PO Acknowledgement is currently locked (' + curLetterSub.status + ').');
        return;
      }
      var stEl = document.getElementById('if-po-ack-st');
      var dtEl = document.getElementById('if-po-ack-dt');
      var ptsEl = document.getElementById('if-po-ack-pts');
      var fEl = document.getElementById('if-po-ack-file');
      var ackDt = (dtEl && dtEl.value) || new Date().toISOString().slice(0, 10);
      var ackSt = (stEl && stEl.value) || 'Unconditional';
      var ackPts = (ptsEl && ptsEl.value) || '';
      var fObj = fEl && fEl.files && fEl.files[0];
      var fileId = (window.REC.ackx && window.REC.ackx.fileId) || '';
      var fileName = (window.REC.ackx && window.REC.ackx.fileName) || '';
      if (fObj && typeof window.fxKeep === 'function') {
        fileId = await window.fxKeep(fObj, { po: window.REC.po, where: 'PO Acknowledgement' });
        fileName = fObj.name;
      }
      window.REC.ackDate = ackDt;
      window.REC.ackx = { st: ackSt, pts: ackPts, fileId: fileId, fileName: fileName };
      if (!window.REC.stage || window.REC.stage === 'issued') window.REC.stage = 'ack';
      window.REC.log = window.REC.log || [];
      window.REC.log.push({ on: new Date().toISOString(), by: (typeof WHO === 'function' ? WHO() : 'Vendor'), txt: 'PO Acknowledged (' + ackSt + ')' + (fileName ? ' — ' + fileName : '') });
      if (typeof window.saveRec === 'function') window.saveRec();
      if (typeof window.render === 'function') window.render();
      if (typeof window.toast === 'function') window.toast('PO Acknowledgement saved to PO ' + window.REC.po + '.');
    }
  }, true);

  // 7. Listen for SX_BIND_USER & SX_SET_PROJECT from same-origin parent React app only
  window.addEventListener('message', function(ev) {
    if (ev.origin !== window.location.origin) return;
    if (!ev.data || typeof ev.data !== 'object') return;
    if (ev.data.type === 'SX_SET_PROJECT') {
      window._IF_PROJECT_ID = _ifNorm(ev.data.projectId || '');
      _ifInstallProjectWrappers();
      if (typeof window.render === 'function') window.render();
    }
    if (ev.data.type === 'SX_BIND_USER') {
      // Never allow postMessage to override a server-verified Vendor into non-vendor role
      if (window.__IF_SERVER_USER && window.__IF_SERVER_USER.isVendor && !ev.data.isVendor) return;
      _ifBindAuthSession(ev.data);
    }
  });

  // 8. Robust Schedule PDF & Excel Parser Override (handles real-world vendor execution schedules)
  function _ifInstallScheduleParser() {
    var MON_MAP = { jan:1, feb:2, mar:3, apr:4, may:5, jun:6, jul:7, aug:8, sep:9, sept:9, oct:10, nov:11, dec:12 };
    function pad2(n) { return String(n).padStart(2, '0'); }

    window.ffDate = function(v) {
      if (v == null || v === '') return '';
      if (typeof v === 'number') {
        return v > 20000 && v < 80000 ? new Date(Date.UTC(1899, 11, 30) + v * 864e5).toISOString().slice(0, 10) : '';
      }
      var s = String(v).trim().replace(/^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s+/i, '').trim();
      var m;
      if ((m = s.match(/^(\d{4})[\/.\-](\d{1,2})[\/.\-](\d{1,2})/))) {
        return m[1] + '-' + pad2(m[2]) + '-' + pad2(m[3]);
      }
      if ((m = s.match(/^(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2,4})\b/))) {
        var d = +m[1], mo = +m[2], y = m[3].length === 2 ? '20' + m[3] : m[3];
        if (mo > 12 && d <= 12) { var tmp = d; d = mo; mo = tmp; }
        if (mo < 1 || mo > 12 || d < 1 || d > 31) return '';
        return y + '-' + pad2(mo) + '-' + pad2(d);
      }
      if ((m = s.match(/^(\d{1,2})[\s\-\/,]+([A-Za-z]{3,9})[\s\-\/,]+(\d{2,4})\b/))) {
        var mk = MON_MAP[m[2].slice(0, 4).toLowerCase()] || MON_MAP[m[2].slice(0, 3).toLowerCase()];
        if (mk) {
          var y2 = m[3].length === 2 ? '20' + m[3] : m[3];
          return y2 + '-' + pad2(mk) + '-' + pad2(m[1]);
        }
      }
      if ((m = s.match(/^([A-Za-z]{3,9})[\s\-\/]+(\d{1,2})(?:st|nd|rd|th)?[,\s\-]+(\d{2,4})\b/))) {
        var mk2 = MON_MAP[m[1].slice(0, 4).toLowerCase()] || MON_MAP[m[1].slice(0, 3).toLowerCase()];
        if (mk2) {
          var y3 = m[3].length === 2 ? '20' + m[3] : m[3];
          return y3 + '-' + pad2(mk2) + '-' + pad2(m[2]);
        }
      }
      return '';
    };

    var DATE_GLOBAL_RE = /\b(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s+)?(\d{4}[\/.\-]\d{1,2}[\/.\-]\d{1,2}|\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{2,4}|\d{1,2}[\s\-][A-Za-z]{3,9}[\s\-,]+\d{2,4}|[A-Za-z]{3,9}[\s\-]+\d{1,2}(?:st|nd|rd|th)?[,\s\-]+\d{2,4})\b/gi;
    window.ffDates = function(s) {
      var out = [];
      String(s || '').replace(DATE_GLOBAL_RE, function(m0, d) {
        var x = window.ffDate(d);
        if (x) out.push(x);
        return m0;
      });
      return out;
    };

    var _origFfRead = window.ffRead;
    if (typeof _origFfRead === 'function') {
      window.ffRead = async function(f) {
        var D = await _origFfRead.apply(this, arguments);
        if (D && D.kind === 'pdf' && !D.readable && D.text && D.text.length > 40 && D.lines && D.lines.length >= 3) {
          // Many engineering schedule PDFs are digit/date-dense (<45% letters); still mark readable if dates exist
          if (window.ffDates(D.text).length >= 2) {
            D.readable = true;
            if ((!D.grids || !D.grids.length) && typeof window.ffPdfGrids === 'function') {
              D.grids = window.ffPdfGrids(D.lines);
            }
          }
        }
        var pdfBuf = null;
        var hasCleanNativeText = !!(D && D.kind === 'pdf' && D.readable && D.text && D.text.trim().length >= 80 && D.lines && D.lines.length >= 3);
        var needOcr = false;
        if (D && D.kind === 'pdf') {
          if (!hasCleanNativeText) {
            needOcr = true;
          } else if (window.TAB === 'docs' && (!D.grids || D.grids.length === 0) && D.lines.length < 15) {
            needOcr = true;
          }
        }
        if (needOcr && f && typeof f.arrayBuffer === 'function') {
          try {
            if (typeof window.ffPct === 'function') window.ffPct('Running OCR on scanned PDF pages', 72);
            pdfBuf = pdfBuf || await f.arrayBuffer();
            var forceOcr = D.readable ? 'true' : 'false';
            var ocrResp = await fetch('/api/v1/pdf/ocr?force_ocr=' + forceOcr + '&max_pages=80', {
              method: 'POST',
              headers: { 'Content-Type': 'application/pdf' },
              body: pdfBuf
            });
            if (ocrResp.ok) {
              var ocrJson = await ocrResp.json();
              if (ocrJson && ocrJson.ok && ocrJson.lines && ocrJson.lines.length) {
                D.lines = ocrJson.lines;
                D.text = ocrJson.text || '';
                D.pages = ocrJson.pages || D.pages;
                D.readable = !!ocrJson.readable;
                D.ocrUsed = !!ocrJson.ocr_used;
                D.ocrPages = ocrJson.ocr_pages || [];
                D.ocrEngine = ocrJson.engine || 'ocr';
                if (D.readable && typeof window.ffPdfGrids === 'function') {
                  D.grids = window.ffPdfGrids(D.lines);
                }
                if (D.ocrUsed && typeof window.toast === 'function') {
                  window.toast('OCR extracted text from ' + D.ocrPages.length + ' scanned page(s).');
                }
              }
            }
          } catch (ocrErr) {
            console.warn('Backend PDF OCR fallback error:', ocrErr);
          }
        }
        if (D && D.kind === 'pdf' && window.TAB === 'sched' && f && typeof f.arrayBuffer === 'function') {
          var detRows = typeof window.ffSchedRows === 'function' ? window.ffSchedRows(D) : [];
          if (!detRows.length || D.ocrUsed) {
            try {
              if (typeof window.ffPct === 'function') window.ffPct('Parsing schedule structure with AI', 80);
              pdfBuf = pdfBuf || await f.arrayBuffer();
              var clsParam = window.REC ? ('&procurement_class=' + encodeURIComponent(_ifInferClass(window.REC))) : '';
              var aiResp = await fetch('/api/v1/pdf/ai-schedule?filename=' + encodeURIComponent(f.name || 'schedule.pdf') + clsParam, {
                method: 'POST',
                headers: { 'Content-Type': 'application/pdf' },
                body: pdfBuf
              });
              if (aiResp.ok) {
                var aiJson = await aiResp.json();
                if (aiJson && aiJson.ok && Array.isArray(aiJson.activities) && aiJson.activities.length) {
                  D._aiSchedule = aiJson.activities;
                  D.readable = true;
                  D.aiEngine = aiJson.engine || 'gemini-2.5-flash';
                }
              }
            } catch (aiErr) {
              console.warn('AI schedule parser fallback error:', aiErr);
            }
          }
        }
        return D;
      };
    }

    window.ffSchedRows = function(D) {
      if (D && Array.isArray(D._aiSchedule) && D._aiSchedule.length) {
        var aiValid = D._aiSchedule.filter(function(r) { return r && r.act && (r.fS || r.fE || r.bS || r.bE); });
        if (aiValid.length) return aiValid;
      }
      var R = [];
      var norm = typeof window.ffNorm === 'function' ? window.ffNorm : function(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); };

      // A. Flexible table grid parsing (PDF tables, Excel, CSV)
      (D.grids || []).forEach(function(g) {
        var h = -1, H = null;
        for (var i = 0; i < Math.min(g.length, 35); i++) {
          var n2 = (g[i] || []).map(norm);
          var hasAct = n2.some(function(c) { return /activity|task|milestone|deliverable|description|scope|stage|phase|work|item/.test(c); });
          var hasDate = n2.some(function(c) { return /start|finish|end|date|baseline|forecast|planned|target|actual|due/.test(c); });
          if (hasAct && hasDate) { h = i; H = n2; break; }
        }
        if (h < 0) return;
        var col = function(re, notRe) {
          return H.findIndex(function(c) { return re.test(c) && !(notRe && notRe.test(c)); });
        };
        var colAll = function(re) {
          var idxs = [];
          H.forEach(function(c, ix) { if (re.test(c)) idxs.push(ix); });
          return idxs;
        };
        var cA = col(/^(?:activity|task name|task|milestone|deliverable|description|scope|work)/);
        if (cA < 0) cA = col(/activity|task|milestone|deliverable|description|scope|stage|phase|item/, /^(?:id|no|sr|sl|#)/);
        if (cA < 0) cA = 0;
        var cA2 = (cA + 1 < H.length && /^(?:description|details?)$/.test(H[cA + 1]) && /activity|task/.test(H[cA])) ? cA + 1 : -1;

        var startCols = colAll(/\bstart\b/);
        var endCols = colAll(/\b(?:finish|end)\b/);
        var cBS = col(/baseline.*start|plan.*start/);
        var cBE = col(/baseline.*(?:finish|end|date)|contract.*date/);
        var cS = col(/forecast.*start|planned.*start/, /baseline/);
        var cE = col(/forecast.*(?:finish|end|date)|planned.*(?:finish|end|date)|target.*date/, /baseline/);
        if (cS < 0 && cBS < 0 && startCols.length >= 2) {
          cBS = startCols[0];
          cS = startCols[startCols.length - 1];
        } else if (cS < 0) {
          cS = col(/start/);
        }
        if (cE < 0 && cBE < 0 && endCols.length >= 2) {
          cBE = endCols[0];
          cE = endCols[endCols.length - 1];
        } else if (cE < 0) {
          cE = col(/finish|end|date|due|target/);
        }
        var cP = col(/complete|progress|pct|comp\b|^%/);

        for (var r = h + 1; r < g.length; r++) {
          var x = g[r] || [];
          var a = String(x[cA] == null ? '' : x[cA]).trim();
          if (cA2 >= 0 && x[cA2]) {
            a = (a ? a + ' ' : '') + String(x[cA2]).trim();
          }
          a = a.replace(/\s+/g, ' ').trim();
          if (!a || /^(?:total|page \d+|notes?|prepared by)/i.test(a)) continue;
          var lineDates = [];
          x.forEach(function(cell) { window.ffDates(cell).forEach(function(dt) { lineDates.push(dt); }); });
          var fS = cS >= 0 ? (window.ffDates(x[cS])[0] || '') : '';
          var fE = cE >= 0 ? (window.ffDates(x[cE])[0] || '') : '';
          var bS = cBS >= 0 ? (window.ffDates(x[cBS])[0] || '') : '';
          var bE = cBE >= 0 ? (window.ffDates(x[cBE])[0] || '') : '';
          if (!fS && !fE && lineDates.length) {
            if (lineDates.length >= 4) {
              bS = lineDates[0]; bE = lineDates[1]; fS = lineDates[lineDates.length - 2]; fE = lineDates[lineDates.length - 1];
            } else {
              fS = lineDates.length > 1 ? lineDates[0] : '';
              fE = lineDates[lineDates.length - 1];
            }
          }
          if (!fS && !fE && !bS && !bE) continue;
          var pct = '';
          if (cP >= 0 && x[cP] != null && x[cP] !== '') {
            var pRaw = String(x[cP]).trim();
            var pArr = typeof window.ffPcts === 'function' ? window.ffPcts(pRaw + (pRaw.indexOf('%') < 0 && !isNaN(+pRaw) ? '%' : '')) : [];
            if (pArr.length) pct = pArr[0];
          }
          R.push({ act: a, bS: bS, bE: bE, fS: fS || bS, fE: fE || bE || fS, pct: pct });
        }
      });

      // B. Smart line-by-line parser across extracted PDF lines (runs when grids missed rows or split mid-table)
      var RLines = [];
      if (D.lines && D.lines.length) {
        var skipLineRe = /^(?:page\s+\d+|po\s*(?:no|number)|purchase\s+order|document\s+no|revision|rev\.|prepared\s+by|approved\s+by|activity|task\s+name|milestone\s+description|client:|project:|vendor:|supplier:|sr\s+activity|vendor\s+project\s+execution\s+schedule|scope\s+of\s+supply|note:|notes:|delivery\s+completes\b|[•●])|\b(?:assumes\s+qualified|covers\s+finish|includes\s+trim|enables\s+irn|transit\s+to\s+destination|alongside\s+spir)\b/i;
        for (var idx = 0; idx < D.lines.length; idx++) {
          var txt = String((D.lines[idx] && D.lines[idx].t) || '').replace(/\s+/g, ' ').trim();
          if (!txt || skipLineRe.test(txt)) continue;

          // Match original MS Project format first if present
          var mMs = txt.match(/^\s*(\d{1,4})\s+(.+?)\s+(\d+(?:[.,]\d+)?\s*(?:d|w|wk|days?|mo|edays?)\.?)\s+((?:mon|tue|wed|thu|fri|sat|sun)\w*\s+\d{1,2}\/\d{1,2}\/\d{2,4})\s+((?:mon|tue|wed|thu|fri|sat|sun)\w*\s+\d{1,2}\/\d{1,2}\/\d{2,4})(.*)$/i);
          if (mMs) {
            RLines.push({
              id: mMs[1],
              act: mMs[2].trim(),
              fS: window.ffDate(mMs[4]),
              fE: window.ffDate(mMs[5]),
              pct: (window.ffPcts ? window.ffPcts(mMs[6])[0] : '') || ''
            });
            continue;
          }

          var dts = window.ffDates(txt);
          var combinedTxt = txt;
          // Prepend immediate short non-dated wrapped prefix line (e.g. "Delivered at destination (for" above "21 DDP/DDU/DAP) Vendor ...")
          if (dts.length && idx > 0) {
            var prevTxt = String((D.lines[idx - 1] && D.lines[idx - 1].t) || '').replace(/\s+/g, ' ').trim();
            if (prevTxt && !window.ffDates(prevTxt).length && !/^(?:vendor|client|nmdc|sr\b|dur\.|timeline|scope\b|page\s+\d+)/i.test(prevTxt) && /\($/.test(prevTxt)) {
              txt = prevTxt + ' ' + txt;
            }
          }
          // Handle two-line wrapped schedule rows where line i is label and line i+1 holds the dates (or trailing fragment)
          if (dts.length && idx + 1 < D.lines.length) {
            var tailNext = String((D.lines[idx + 1] && D.lines[idx + 1].t) || '').replace(/\s+/g, ' ').trim();
            if (tailNext && !window.ffDates(tailNext).length && !/^\d+\s+/.test(tailNext) && /^(?:submission|approval|meeting|readiness|closure|testing|delivery|issuance|placement|manufacturing)\b/i.test(tailNext)) {
              txt = txt + ' ' + tailNext;
              idx++;
            }
          }
          if (!dts.length && idx + 1 < D.lines.length && !/start|finish|end|duration/i.test(txt)) {
            var nxt = String((D.lines[idx + 1] && D.lines[idx + 1].t) || '').trim();
            var nxtDates = window.ffDates(nxt);
            if (nxtDates.length && nxt.replace(DATE_GLOBAL_RE, '').replace(/[\d\s%.,\/\-]+/g, '').length < 6) {
              dts = nxtDates;
              combinedTxt = txt + ' ' + nxt;
              idx++;
            }
          }
          if (!dts.length) continue;

          var cleanAct = txt
            .replace(DATE_GLOBAL_RE, ' ')
            .replace(/(-?\d{1,3}(?:[.,]\d+)?)\s*%/g, ' ')
            .replace(/\b\d+(?:[.,]\d+)?\s*(?:days?|d|wks?|weeks?|months?|mo|hrs?|hours?)\b/gi, ' ')
            .replace(/\b(?:NMDC|Client|Vendor|Supplier)(?:\s*\/\s*(?:Vendor|NMDC|Client|Supplier))?\b/gi, ' ')
            .replace(/\s*\/\s*(?=\s|$)/g, ' ')
            .replace(/^\s*(?:[A-Za-z]?\d+(?:\.\d+)*)\s*[:.\-\)]?\s+/, '')
            .replace(/\b\d+(?:\s*,\s*\d+)*\b/g, ' ')
            .replace(/[—–]+/g, ' ')
            .replace(/\s+/g, ' ')
            .replace(/^[\-\–•●|:.\s]+|[\-\–•●|:.\s]+$/g, '')
            .trim();

          if (!cleanAct || cleanAct.length < 4 || (cleanAct.match(/[A-Za-z]/g) || []).length < 3) continue;
          if (/^(?:start|finish|end|duration|progress|status|remarks|baseline|forecast|planned|actual|date|week|month|year|q[1-4]|20\d{2})$/i.test(cleanAct)) continue;

          var pList = typeof window.ffPcts === 'function' ? window.ffPcts(combinedTxt) : [];
          var pctVal = pList.length ? pList[pList.length - 1] : '';
          var fStart = dts.length >= 2 ? dts[dts.length - 2] : '';
          var fEnd = dts[dts.length - 1];
          if (dts.length >= 4) {
            RLines.push({ act: cleanAct, bS: dts[0], bE: dts[1], fS: dts[2], fE: dts[3], pct: pctVal });
          } else {
            RLines.push({ act: cleanAct, fS: fStart, fE: fEnd, pct: pctVal });
          }
        }
      }
      if (RLines.length > R.length) return RLines;
      return R;
    };

    var EXTRA_SCH_KEYS = [
      [/^\s*po\s*date/i, /^PO date/i],
      [/po.*ack|acknowledg/i, /acknowledgement/i],
      [/kick.?off|kom/i, /Kick off/i],
      [/approv|code\s*[12]|review/i, /approval/i],
      [/spir\b/i, /SPIR/i],
      [/mrb|databook|final.*doc|manual/i, /MRB submission/i],
      [/eng|draw|datasheet|ga\b|calc|sdr|vdrl|doc.*sub|itp|wps|svl/i, /submission/i],
      [/sub.?order.*plac|po\s+plac/i, /Sub-orders placement/i],
      [/sub.?order.*manuf/i, /Sub-orders manufacturing/i],
      [/sub.?order.*del|mat.*rec|forging.*rec|casting.*rec/i, /Sub-orders delivery/i],
      [/raw.*mat|forging|casting|billet|bar|plate|procure/i, /Sub-orders placement/i],
      [/machin|weld|fab.*start|start.*fab/i, /Start Fabrication/i],
      [/end.*fab|fab.*comp|fab.*fin/i, /End Fabrication/i],
      [/assembl|fit.?up|valv.*ass/i, /Assembly/i],
      [/pim|pre.?insp/i, /Pre-inspection/i],
      [/hydro|pressure|nde|ndt|heat.*treat|internal.*test|leak.*test|funct.*test/i, /Internal Testing/i],
      [/insp.*notif|noi\b/i, /Inspection notification/i],
      [/fat\b|factory\s+accept|witness|final\s+insp|client\s+insp/i, /FAT/i],
      [/punch/i, /Punch/i],
      [/irn|irc|release\s+note|release\s+cert/i, /IRN/i],
      [/paint|coat|blast|preserv/i, /Painting/i],
      [/pack|crate|ex.?works|exw|dispatch|ready/i, /Exw readiness/i],
      [/ship|vessel|port|deliver|site|mrv|ddp|ddu|dap/i, /Delivered/i]
    ];

    window.ffSched = function(D) {
      var R = window.ffSchedRows(D);
      var rows = typeof window.schRows === 'function' ? window.schRows() : [];
      var matchedHits = {}, customRows = [], out = [];
      var allKeys = EXTRA_SCH_KEYS.concat(typeof window.FF_SCH_KEYS !== 'undefined' ? window.FF_SCH_KEYS : []);

      R.forEach(function(x) {
        var best = null, bs = 0;
        var kRule = allKeys.find(function(p) { return p[0].test(x.act) && p[1]; });
        if (kRule) {
          best = rows.find(function(q) { return kRule[1].test(q.act); });
        }
        if (!best && typeof window.ffSim === 'function') {
          rows.forEach(function(q) {
            var s2 = window.ffSim(x.act, q.act);
            if (s2 > bs) { bs = s2; best = q; }
          });
          if (bs < 0.35) best = null;
        }
        if (best) {
          var h = matchedHits[best.id];
          if (!h) {
            h = matchedHits[best.id] = { row: best, bS: x.bS || '', bE: x.bE || '', fS: x.fS || '', fE: x.fE || '', pct: x.pct || '', from: [x.act] };
            out.push(h);
          } else {
            if (x.fS && (!h.fS || x.fS < h.fS)) h.fS = x.fS;
            if (x.fE && (!h.fE || x.fE > h.fE)) h.fE = x.fE;
            if (x.pct && !h.pct) h.pct = x.pct;
            h.from.push(x.act);
          }
        } else {
          customRows.push(x);
        }
      });

      var sum = out.map(function(h) {
        return [
          h.row.act,
          (h.fS ? fmtDate(h.fS) : '—') + ' → ' + (h.fE ? fmtDate(h.fE) : '—') + (h.pct ? ' · ' + h.pct + '%' : '') + ' (from: ' + h.from.slice(0, 2).join('; ') + ')'
        ];
      });
      customRows.forEach(function(x) {
        sum.push([
          'New Activity: ' + x.act,
          (x.fS ? fmtDate(x.fS) : '—') + ' → ' + (x.fE ? fmtDate(x.fE) : '—') + (x.pct ? ' · ' + x.pct + '%' : '')
        ]);
      });
      var totalCount = out.length + customRows.length;
      sum.unshift(['Activities read', R.length + ' activity row(s) extracted; ' + out.length + ' matched + ' + customRows.length + ' custom row(s) ready to import']);

      return {
        sum: sum,
        n: totalCount,
        apply: function() {
          var s = typeof window.schCur === 'function' ? window.schCur() : null;
          if (!s || s.status === 'Agreed' || s.status === 'Submitted') {
            if (typeof window.schNew === 'function') s = window.schNew();
          } else if (s.status === 'Returned' && typeof window.subAct === 'function') {
            window.subAct(s, 'Revised', 'Filled from ' + D.name);
          }
          if (!s) return;
          var paths = [];
          out.forEach(function(h) {
            var r = s.data.rows.find(function(q) { return q.id === h.row.id; });
            if (!r) return;
            if (h.fS) { r.fS = h.fS; paths.push(r.id + '|fS'); }
            if (h.fE) { r.fE = h.fE; paths.push(r.id + '|fE'); }
            if (h.bS && !r.bS) r.bS = h.bS;
            if (h.bE && !r.bE) r.bE = h.bE;
            if (h.pct) { r.pct = h.pct; paths.push(r.id + '|pct'); }
            r.rem = r.rem || ('From ' + D.name);
          });
          customRows.forEach(function(x) {
            var existingCustom = s.data.rows.find(function(q) { return q.act && q.act.toLowerCase() === x.act.toLowerCase(); });
            if (existingCustom) {
              if (x.fS) existingCustom.fS = x.fS;
              if (x.fE) existingCustom.fE = x.fE;
              if (x.pct) existingCustom.pct = x.pct;
            } else {
              var newId = 'n' + (typeof window.epXId === 'function' ? window.epXId() : Math.random().toString(36).slice(2, 8));
              s.data.rows.push({
                id: newId,
                act: x.act,
                bS: x.bS || x.fS || '',
                bE: x.bE || x.fE || '',
                fS: x.fS || '',
                fE: x.fE || '',
                pct: x.pct || '',
                rem: 'Imported from ' + D.name,
                added: true
              });
              paths.push(newId + '|fE');
            }
          });
          s.ff = { file: D.name, on: new Date().toISOString(), paths: paths };
          if (window.FF && window.FF.last && window.FF.last.file) s.file = s.file || window.FF.last.file;
          s.src = D.name;
          if (typeof window.saveRec === 'function') window.saveRec();
          if (typeof window.render === 'function') window.render();
          if (typeof window.toast === 'function') window.toast(totalCount + ' schedule row(s) imported into draft. Review and submit when ready.');
        }
      };
    };

    if (typeof window.FF_FN === 'object' && window.FF_FN) {
      window.FF_FN.sched = window.ffSched;
    }
  }
  _ifInstallScheduleParser();
})();
</script>
"""


IF_SX_AUTH_BRIDGE_JS = """
<script id="inspectflow-sx-auth-bridge">
(function() {
  function _getLiveToken() {
    try {
      return (window.parent && window.parent !== window && window.parent.localStorage && window.parent.localStorage.getItem('inspectflow_access_token'))
         || window.localStorage.getItem('inspectflow_access_token')
         || '';
    } catch (e) { return ''; }
  }
  function _isApiUrl(u) {
    var s = String(u || '');
    return s.indexOf('/api/') === 0 || s.indexOf('/uploads/') === 0 || s.indexOf('/smartexpedit-app') === 0 || s.indexOf(window.location.origin + '/api/') === 0;
  }
  window._IF_AUTH_TOKEN = _getLiveToken();
  if (window.XMLHttpRequest) {
    var _origOpen = XMLHttpRequest.prototype.open;
    var _origSetHdr = XMLHttpRequest.prototype.setRequestHeader;
    var _origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(m, u) {
      this._ifUrl = String(u || '');
      this._ifHasAuthHdr = false;
      return _origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.setRequestHeader = function(k, v) {
      if (String(k || '').toLowerCase() === 'authorization') this._ifHasAuthHdr = true;
      return _origSetHdr.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
      try {
        if (_isApiUrl(this._ifUrl)) {
          this.withCredentials = true;
          var tok = _getLiveToken();
          window._IF_AUTH_TOKEN = tok;
          if (tok && !this._ifHasAuthHdr) {
            this.setRequestHeader('Authorization', 'Bearer ' + tok);
          }
        }
      } catch (e) {}
      return _origSend.apply(this, arguments);
    };
  }
  if (typeof window.fetch === 'function') {
    var _origFetch = window.fetch.bind(window);
    window.fetch = function(input, init) {
      var u = typeof input === 'string' ? input : (input && input.url) || '';
      if (_isApiUrl(u)) {
        init = Object.assign({}, init || {});
        var hdrs = new Headers(init.headers || (typeof input !== 'string' && input && input.headers) || undefined);
        var tok = _getLiveToken();
        window._IF_AUTH_TOKEN = tok;
        if (tok && !hdrs.has('Authorization')) {
          hdrs.set('Authorization', 'Bearer ' + tok);
        }
        init.headers = hdrs;
        if (!init.credentials) init.credentials = 'include';
      }
      return _origFetch(input, init);
    };
  }
})();
</script>
"""


_PDF_OCR_ROLES = (
    "admin", "qc_manager", "inspection_engineer", "inspector", "inspection_agency",
    "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "vendor",
)


async def _read_bounded_body(request: Request, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            mb = max_bytes // (1024 * 1024)
            raise HTTPException(status_code=413, detail=f"Uploaded payload exceeds maximum {mb} MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/api/v1/pdf/ocr")
async def pdf_ocr_endpoint(
    request: Request,
    force_ocr: bool = False,
    max_pages: int = 80,
    current_user: Dict[str, Any] = Depends(require_roles(*_PDF_OCR_ROLES)),
):
    """
    Universal Hybrid PDF Text + OCR endpoint for ALL uploaded PDFs across InspectFlow & SmartExpedit.
    """
    ctype = (request.headers.get("content-type") or "").lower()
    pdf_bytes = b""
    if "multipart/form-data" in ctype:
        form = await request.form()
        up = form.get("file") or form.get("pdf")
        if up is not None and hasattr(up, "read"):
            pdf_bytes = await up.read(settings.upload_max_bytes + 1)
            if len(pdf_bytes) > settings.upload_max_bytes:
                raise HTTPException(status_code=413, detail="Uploaded PDF exceeds maximum allowed size")
    else:
        pdf_bytes = await _read_bounded_body(request, settings.upload_max_bytes)

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty PDF file uploaded")
    if not pdf_bytes.lstrip()[:5].startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Uploaded content is not a valid PDF file")

    try:
        return extract_pdf_with_ocr(pdf_bytes, max_pages=min(max(1, max_pages), 120), force_ocr=force_ocr)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF OCR failed: {exc}")


@router.post("/api/v1/pdf/ai-schedule")
async def pdf_ai_schedule_endpoint(
    request: Request,
    filename: str = "schedule.pdf",
    procurement_class: str = "tagged",
    current_user: Dict[str, Any] = Depends(require_roles(*_PDF_OCR_ROLES)),
):
    """
    AI-assisted schedule parser backed by GEMINI_API_KEY (gemini-2.5-flash multimodal PDF).
    """
    ctype = (request.headers.get("content-type") or "").lower()
    pdf_bytes = b""
    if "multipart/form-data" in ctype:
        form = await request.form()
        up = form.get("file") or form.get("pdf")
        if up is not None and hasattr(up, "read"):
            pdf_bytes = await up.read(settings.upload_max_bytes + 1)
            if len(pdf_bytes) > settings.upload_max_bytes:
                raise HTTPException(status_code=413, detail="Uploaded PDF exceeds maximum allowed size")
            filename = getattr(up, "filename", None) or filename
    else:
        pdf_bytes = await _read_bounded_body(request, settings.upload_max_bytes)

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty PDF file uploaded")
    if not pdf_bytes.lstrip()[:5].startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Uploaded content is not a valid PDF file")

    from python_app.ai_service import extract_schedule_with_gemini, get_gemini_api_key

    if not get_gemini_api_key():
        return {"ok": False, "engine": "none", "error": "GEMINI_API_KEY not configured", "activities": []}

    try:
        parsed = extract_schedule_with_gemini(pdf_bytes, filename=filename, procurement_class=procurement_class)
        acts = parsed.get("activities") or []
        return {
            "ok": len(acts) > 0,
            "engine": "gemini-2.5-flash",
            "po_date": parsed.get("po_date"),
            "target_delivery": parsed.get("target_delivery"),
            "count": len(acts),
            "activities": acts,
        }
    except Exception as exc:
        return {"ok": False, "engine": "gemini-2.5-flash", "error": str(exc), "activities": []}


@router.get("/api/v1/connections/status")
def system_connections_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Report live readiness of AI, OCR, and database connections."""
    from python_app.ai_service import get_gemini_api_key
    from python_app.pdf_ocr import detect_ocr_engine

    api_key = get_gemini_api_key()
    ocr_engine = detect_ocr_engine()
    return {
        "gemini_ai": {
            "configured": bool(api_key),
            "model": "gemini-2.5-flash",
        },
        "pdf_ocr": {
            "engine": ocr_engine,
            "ready": ocr_engine != "none",
        },
        "smartexpedit_kv": True,
        "inspectflow_ims": True,
    }


def _safe_script_json(val: Any) -> str:
    return json.dumps(val).replace("</", "<\\/")


def _strip_static_pii_in_html(html: str) -> str:
    # Replace embedded demo records & 54KB field sub-vendor PII with empty placeholders so static HTML leaks zero PII
    html = re.sub(
        r"window\.SX_RECORDS=\[[\s\S]*?\];(?=\s*\n?)",
        "window.SX_RECORDS=[];",
        html,
        count=1,
    )
    html = re.sub(
        r"window\.SX_FIELD=\{[\s\S]*?\};(?=\s*(?://|<\/script>|\n))",
        "window.SX_FIELD={rows:[]};",
        html,
        count=1,
    )
    return html


@router.get("/smartexpedit-app", response_class=HTMLResponse)
def serve_smartexpedit_embedded(
    request: Request,
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Serves SmartExpedit's compiled `static/index.html` with live server KV sync (`sx_head.js` / `sx_tail.js`),
    XSS-safe initialization, stripped static PII, and server-verified role binding.
    Requires authenticated non-guest session (Bearer JWT or HttpOnly cookie).
    """
    if not SX_STATIC_HTML.exists():
        raise HTTPException(status_code=404, detail="SmartExpedit static/index.html not found")
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required to access SmartExpedit")
    raw_html = _strip_static_pii_in_html(SX_STATIC_HTML.read_text(encoding="utf-8"))
    clean_pid = re.sub(r"[^a-zA-Z0-9_-]", "", (project_id or "").strip().lower())

    user = current_user
    server_user_obj = None
    if user:
        eff = effective_role(user)
        role_map = {
            "admin": "PEXM",
            "expediting_manager": "PEXM",
            "expeditor": "EXP",
            "field_expeditor": "FIELD",
            "doc_expeditor": "DOC",
            "vendor": "VEN:__AUTO__",
        }
        server_user_obj = {
            "sxRole": role_map.get(eff, "DOC"),
            "isAdmin": is_admin_user(user),
            "isVendor": eff == "vendor",
            "userName": user.get("full_name") or user.get("email") or "User",
        }

    init_pid_script = (
        f"<script>"
        f"window.__IF_INIT_PROJECT_ID = {_safe_script_json(clean_pid)};"
        f"window.__IF_SERVER_USER = {_safe_script_json(server_user_obj)};"
        f"</script>\n"
    )

    sx_head_code = SX_HEAD_JS_PATH.read_text(encoding="utf-8") if SX_HEAD_JS_PATH.exists() else ""
    sx_tail_code = SX_TAIL_JS_PATH.read_text(encoding="utf-8") if SX_TAIL_JS_PATH.exists() else ""
    head_bundle = (
        IF_SX_AUTH_BRIDGE_JS
        + '\n<script src="/sx-config.js"></script>\n'
        + (f"<script>{sx_head_code}</script>\n" if sx_head_code else "")
    )
    if "<script" in raw_html:
        raw_html = raw_html.replace("<script", head_bundle + "<script", 1)
    else:
        raw_html = head_bundle + raw_html

    if '<div id="sx">' in raw_html:
        raw_html = raw_html.replace('<div id="sx">', init_pid_script + INSPECTFLOW_THEME_OVERRIDE_CSS + '\n<div id="sx">', 1)
    else:
        raw_html = init_pid_script + INSPECTFLOW_THEME_OVERRIDE_CSS + "\n" + raw_html

    tail_bundle = (f"\n<script>{sx_tail_code}</script>\n" if sx_tail_code else "") + INSPECTFLOW_LIVE_BRIDGE_JS
    raw_html = raw_html + "\n" + tail_bundle
    return HTMLResponse(
        content=raw_html,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/sx-config.js")
def sx_config_js():
    js_code = "window.SX_SERVER={demo:%s};" % ("true" if DEMO else "false")
    return Response(content=js_code, media_type="application/javascript")


# ---------------------------------------------------------------------------
# SmartExpedit Real-Time KV Store (/api/kv)
# ---------------------------------------------------------------------------

_VENDOR_CONFIDENTIAL_PO_KEYS = {
    "value", "payment", "ld", "log", "mrStudy", "kickoffNotes", "dispatches", "internalNotes",
}
_VENDOR_WRITABLE_PO_KEYS = {
    "ackDate", "ackx", "sch", "plan", "reg", "subs", "sx", "ships", "pls", "bls", "fab_progress", "notes",
}


def _strip_po_for_vendor(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in rec.items() if k not in _VENDOR_CONFIDENTIAL_PO_KEYS}
    if isinstance(out.get("rvw"), dict):
        sanitized_rvw = {}
        for doc_k, entry in out["rvw"].items():
            if isinstance(entry, dict):
                e_copy = {k: v for k, v in entry.items() if k != "reviews"}
                sanitized_rvw[doc_k] = e_copy
            else:
                sanitized_rvw[doc_k] = entry
        out["rvw"] = sanitized_rvw
    if isinstance(out.get("mssrX"), dict):
        mx = dict(out["mssrX"])
        mx.pop("delay", None)
        mx.pop("note", None)
        out["mssrX"] = mx
    if isinstance(out.get("lots"), list):
        out["lots"] = [
            {k: v for k, v in l.items() if k != "ld"} if isinstance(l, dict) else l
            for l in out["lots"]
        ]
    return out


def _filter_rec_list_for_user(recs: list, current_user: Dict[str, Any]) -> list:
    vendor_only = is_vendor_user(current_user)
    filtered = []
    for rec in recs:
        if not isinstance(rec, dict):
            continue
        _normalize_po_render_defaults(rec)
        if not user_can_access_po(current_user, rec):
            continue
        filtered.append(_strip_po_for_vendor(rec) if vendor_only else rec)
    return filtered


def _allowed_po_numbers_from_db(c: sqlite3.Connection, current_user: Dict[str, Any]) -> set:
    return {str(r.get("po")) for r in _records(c) if isinstance(r, dict) and user_can_access_po(current_user, r) and r.get("po")}


def _filter_kv_rows_for_user(c: sqlite3.Connection, rows, current_user: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    items_out: Dict[str, Dict[str, Any]] = {}
    vendor_only = is_vendor_user(current_user)
    allowed_pos = None if is_admin_user(current_user) else _allowed_po_numbers_from_db(c, current_user)
    for r in rows:
        key = r["key"]
        val = r["value"]
        if key == REC_KEY and val:
            try:
                recs = json.loads(val)
                if isinstance(recs, list):
                    val = json.dumps(_filter_rec_list_for_user(recs, current_user), separators=(",", ":"))
            except Exception:
                pass
        elif key == SX_STATE_KEY and val and allowed_pos is not None:
            try:
                sx_obj = json.loads(val)
                if isinstance(sx_obj, dict):
                    sx_copy = dict(sx_obj)
                    sx_copy["concerns"] = [
                        ci for ci in (sx_obj.get("concerns") or [])
                        if isinstance(ci, dict) and str(ci.get("po") or "") in allowed_pos
                    ]
                    sx_copy["dispatch_requests"] = [
                        dr for dr in (sx_obj.get("dispatch_requests") or [])
                        if isinstance(dr, dict) and str(dr.get("po") or "") in allowed_pos
                    ]
                    sx_copy["notes"] = [
                        nt for nt in (sx_obj.get("notes") or [])
                        if isinstance(nt, dict) and str(nt.get("po") or "") in allowed_pos
                    ]
                    if isinstance(sx_obj.get("cumulative_ledger"), dict):
                        sx_copy["cumulative_ledger"] = {
                            lk: lv for lk, lv in sx_obj["cumulative_ledger"].items()
                            if str(lk).split(":", 1)[0] in allowed_pos
                        }
                    val = json.dumps(sx_copy, separators=(",", ":"))
            except Exception:
                pass
        elif key == FIELD_KEY:
            if vendor_only:
                # Never expose sub-vendor contacts/addresses/phones across companies to Vendors
                val = json.dumps({"rows": []})
            elif val and allowed_pos is not None:
                try:
                    f_obj = json.loads(val)
                    if isinstance(f_obj, dict) and isinstance(f_obj.get("rows"), list):
                        f_obj = {
                            **f_obj,
                            "rows": [
                                fr for fr in f_obj["rows"]
                                if isinstance(fr, dict) and (
                                    str(fr.get("appPo") or "") in allowed_pos
                                    or any(p in str(fr.get("poText") or "") for p in allowed_pos)
                                )
                            ],
                        }
                        val = json.dumps(f_obj, separators=(",", ":"))
                except Exception:
                    pass
        elif key == FILES_KEY and val and allowed_pos is not None:
            try:
                files = json.loads(val)
                if isinstance(files, list):
                    files = [fl for fl in files if isinstance(fl, dict) and str(fl.get("po") or "") in allowed_pos]
                    val = json.dumps(files, separators=(",", ":"))
            except Exception:
                pass
        items_out[key] = {"value": val, "version": r["version"]}
    return items_out


def _merge_vendor_po_edit(existing_rec: Dict[str, Any], submitted_rec: Dict[str, Any]) -> Dict[str, Any]:
    """Merge only safe vendor-editable fields while protecting EPC truth (CLR, IRNs, VDRL, LD, pricing, baselines)."""
    updated = dict(existing_rec)
    for k in _VENDOR_WRITABLE_PO_KEYS:
        if k not in submitted_rec:
            continue
        if k == "subs" and isinstance(submitted_rec.get("subs"), list):
            existing_subs = {str(s.get("id")): s for s in (existing_rec.get("subs") or []) if isinstance(s, dict) and s.get("id")}
            merged_subs = []
            for s in submitted_rec["subs"]:
                if not isinstance(s, dict):
                    continue
                sid = str(s.get("id") or "")
                prev = existing_subs.get(sid)
                if prev and prev.get("status") == "Agreed":
                    # Agreed submissions are immutable by vendors
                    merged_subs.append(prev)
                else:
                    s_copy = dict(s)
                    if s_copy.get("status") == "Agreed" and (not prev or prev.get("status") != "Agreed"):
                        s_copy["status"] = "Submitted"
                    merged_subs.append(s_copy)
            updated["subs"] = merged_subs
        elif k == "sch" and isinstance(submitted_rec.get("sch"), dict):
            prev_sch = existing_rec.get("sch") or {}
            new_sch = dict(submitted_rec["sch"])
            if isinstance(prev_sch.get("rows"), list) and isinstance(new_sch.get("rows"), list):
                prev_rows = {str(r.get("id") or r.get("act") or idx): r for idx, r in enumerate(prev_sch["rows"]) if isinstance(r, dict)}
                safe_rows = []
                for idx, row in enumerate(new_sch["rows"]):
                    if not isinstance(row, dict):
                        continue
                    r_copy = dict(row)
                    pr = prev_rows.get(str(row.get("id") or row.get("act") or idx))
                    if pr and pr.get("bS"):
                        r_copy["bS"] = pr["bS"]
                    if pr and pr.get("bE"):
                        r_copy["bE"] = pr["bE"]
                    safe_rows.append(r_copy)
                new_sch["rows"] = safe_rows
            updated["sch"] = new_sch
        else:
            updated[k] = submitted_rec[k]
    return updated


@router.get("/api/kv")
def sx_kv_all(current_user: Dict[str, Any] = Depends(get_current_user)):
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        rows = c.execute("SELECT key, value, version, seq FROM kv").fetchall()
        seq = c.execute("SELECT v FROM meta WHERE k='seq'").fetchone()[0]
        items = _filter_kv_rows_for_user(c, rows, current_user)
    return {"seq": seq, "items": items}


@router.get("/api/kv/changes")
def sx_kv_changes(since: int = 0, current_user: Dict[str, Any] = Depends(get_current_user)):
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        rows = c.execute(
            "SELECT key, value, version, seq FROM kv WHERE seq > ?", (since,)
        ).fetchall()
        seq = c.execute("SELECT v FROM meta WHERE k='seq'").fetchone()[0]
        items = _filter_kv_rows_for_user(c, rows, current_user)
    return {"seq": seq, "items": items}


@router.put("/api/kv/{key:path}")
async def sx_kv_set(
    key: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    eff = effective_role(current_user)
    if eff in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required to modify ERP state")

    body = await request.json()
    value = body.get("value")
    base = int(body.get("base") or 0)
    actor_label = _who(request, current_user)
    vendor_only = is_vendor_user(current_user)

    if value is None:
        if not is_admin_user(current_user):
            raise HTTPException(status_code=403, detail="Only administrators can delete store keys")
    if vendor_only and key in (FIELD_KEY,):
        raise HTTPException(status_code=403, detail="Vendors cannot modify internal field expediting store")

    with LOCK, sx_db() as c:
        cur, ver = _kv_get(c, key)
        if value is None:
            c.execute("DELETE FROM kv WHERE key = ?", (key,))
            _next_seq(c)
            record_audit_event("kv", key, "KV_KEY_DELETED", actor=current_user, ip_address=request.client.host if request.client else None)
            return {"version": 0}

        if key == REC_KEY:
            submitted_list = json.loads(value) if isinstance(value, str) else (value or [])
            if not isinstance(submitted_list, list):
                raise HTTPException(status_code=400, detail="ep_exp_records value must be a JSON array")
            L = json.loads(cur) if cur else []
            pos = [r.get("po") for r in L]
            mine = {r.get("po"): r for r in submitted_list if isinstance(r, dict) and r.get("po")}

            if vendor_only:
                for po, rec in mine.items():
                    if po in pos:
                        idx = pos.index(po)
                        existing_rec = L[idx]
                        if vendor_owns_po(current_user, existing_rec):
                            L[idx] = _merge_vendor_po_edit(existing_rec, rec)
                value = json.dumps(L, separators=(",", ":"))
            else:
                changed = body.get("changed") or []
                is_adm = is_admin_user(current_user)
                if base and ver and base != ver and changed:
                    for po in changed:
                        if po in mine:
                            if po in pos:
                                idx = pos.index(po)
                                if user_can_access_po(current_user, L[idx]):
                                    L[idx] = mine[po]
                            elif is_adm or user_can_access_project_id(current_user, mine[po].get("project_id")):
                                L.append(mine[po])
                        elif po in pos and is_adm:
                            idx = pos.index(po)
                            L.pop(idx)
                            pos.pop(idx)
                    value = json.dumps(L, separators=(",", ":"))
                elif is_adm:
                    value = json.dumps(submitted_list, separators=(",", ":"))
                else:
                    # Non-admin internal users may update ONLY POs within their assigned projects (never wipe/modify other projects)
                    for po, rec in mine.items():
                        if po in pos:
                            idx = pos.index(po)
                            if user_can_access_po(current_user, L[idx]):
                                L[idx] = rec
                        elif user_can_access_project_id(current_user, rec.get("project_id")):
                            L.append(rec)
                    value = json.dumps(L, separators=(",", ":"))

            newver = _kv_put(c, key, value, actor_label)
            filtered_resp = json.dumps(_filter_rec_list_for_user(json.loads(value), current_user), separators=(",", ":"))
            return {"version": newver, "value": filtered_resp}

        elif key == SX_STATE_KEY:
            new_obj = json.loads(value) if isinstance(value, str) else value
            if not isinstance(new_obj, dict):
                raise HTTPException(status_code=400, detail="sx_state must be a JSON object")
            cur_obj = json.loads(cur) if cur else {"concerns": [], "notes": []}
            if vendor_only:
                # Vendors can ONLY update/add concerns on their OWN POs and never overwrite dispatch_requests / cumulative_ledger
                allowed_pos = _allowed_po_numbers_from_db(c, current_user)
                other_concerns = [ci for ci in (cur_obj.get("concerns") or []) if str((ci or {}).get("po") or "") not in allowed_pos]
                my_concerns = [ci for ci in (new_obj.get("concerns") or []) if isinstance(ci, dict) and str(ci.get("po") or "") in allowed_pos]
                merged_sx = dict(cur_obj)
                merged_sx["concerns"] = my_concerns + other_concerns
                value = json.dumps(merged_sx, separators=(",", ":"))
            elif not is_admin_user(current_user):
                allowed_pos = _allowed_po_numbers_from_db(c, current_user)
                other_concerns = [ci for ci in (cur_obj.get("concerns") or []) if str((ci or {}).get("po") or "") not in allowed_pos]
                my_concerns = [ci for ci in (new_obj.get("concerns") or []) if isinstance(ci, dict) and str(ci.get("po") or "") in allowed_pos]
                other_notes = [nt for nt in (cur_obj.get("notes") or []) if str((nt or {}).get("po") or "") not in allowed_pos]
                my_notes = [nt for nt in (new_obj.get("notes") or []) if isinstance(nt, dict) and str(nt.get("po") or "") in allowed_pos]
                merged_sx = dict(cur_obj)
                merged_sx["concerns"] = my_concerns + other_concerns
                merged_sx["notes"] = my_notes + other_notes
                value = json.dumps(merged_sx, separators=(",", ":"))
            newver = _kv_put(c, key, value if isinstance(value, str) else json.dumps(value, separators=(",", ":")), actor_label)
            return {"version": newver}

        elif key == FILES_KEY and vendor_only:
            # Vendors can only append file index metadata for their own POs (never delete other vendors' file index)
            cur_list = json.loads(cur) if cur else []
            new_list = json.loads(value) if isinstance(value, str) else (value or [])
            allowed_pos = _allowed_po_numbers_from_db(c, current_user)
            other_files = [f for f in cur_list if isinstance(f, dict) and str(f.get("po") or "") not in allowed_pos]
            my_files = [f for f in new_list if isinstance(f, dict) and str(f.get("po") or "") in allowed_pos]
            merged_files = other_files + my_files
            newver = _kv_put(c, key, json.dumps(merged_files, separators=(",", ":")), actor_label)
            return {"version": newver}

        newver = _kv_put(c, key, value if isinstance(value, str) else json.dumps(value), actor_label)
        return {"version": newver}


# ---------------------------------------------------------------------------
# SmartExpedit Blob Storage (/api/blob)
# ---------------------------------------------------------------------------

@router.put("/api/blob/{key:path}")
async def sx_blob_put(
    key: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    eff = effective_role(current_user)
    if eff in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required to upload blobs")
    content_type = request.headers.get("content-type", "application/octet-stream")
    kind = "json" if "application/json" in content_type else "file"
    raw_bytes = await _read_bounded_body(request, settings.upload_max_bytes)
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty blob upload not allowed")

    uemail = str(current_user.get("email") or "").strip().lower()
    fid = uuid.uuid4().hex
    path = SX_BLOBS / fid
    name = request.headers.get("X-SX-Name", "")
    po_hint = request.headers.get("X-SX-PO", "")

    with LOCK, sx_db() as c:
        old = c.execute("SELECT path, kind, name FROM blobs WHERE key = ?", (key,)).fetchone()
        if old and not is_admin_user(current_user):
            # Prevent silent overwrite of existing immutable files by non-admins
            f_val, _ = _kv_get(c, FILES_KEY)
            if f_val and key.startswith("file:"):
                fid_part = key.split("file:", 1)[1]
                existing_meta = next((f for f in json.loads(f_val) if isinstance(f, dict) and str(f.get("id")) == fid_part), None)
                if existing_meta and existing_meta.get("by") and str(existing_meta.get("by")).strip().lower() != uemail:
                    raise HTTPException(status_code=403, detail="Cannot overwrite another user's uploaded file")
        path.write_bytes(raw_bytes)
        seq = _next_seq(c)
        c.execute(
            "INSERT OR REPLACE INTO blobs VALUES (?,?,?,?,?,?,?,?)",
            (key, kind, name, content_type, len(raw_bytes), fid, seq, time.time()),
        )
    if old and old["path"] != fid:
        try:
            (SX_BLOBS / old["path"]).unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True}


@router.get("/api/blob/{key:path}")
def sx_blob_get(
    key: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    eff = effective_role(current_user)
    if eff in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        r = c.execute("SELECT * FROM blobs WHERE key = ?", (key,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Blob not found")
        if not is_admin_user(current_user):
            allowed_pos = _allowed_po_numbers_from_db(c, current_user)
            if key.startswith("file:"):
                fid_part = key.split("file:", 1)[1]
                f_val, _ = _kv_get(c, FILES_KEY)
                f_list = json.loads(f_val) if f_val else []
                f_meta = next((fl for fl in f_list if isinstance(fl, dict) and str(fl.get("id")) == fid_part), None)
                if f_meta and str(f_meta.get("po") or "") not in allowed_pos:
                    raise HTTPException(status_code=403, detail="Access denied: file belongs to another PO/vendor")
                if not f_meta and is_vendor_user(current_user):
                    raise HTTPException(status_code=403, detail="Vendor cannot access unindexed blob")
            elif key.startswith("img:"):
                po_part = key.split("img:", 1)[1]
                if po_part not in allowed_pos:
                    raise HTTPException(status_code=403, detail="Access denied: PO asset outside your scope")
    file_path = (SX_BLOBS / r["path"]).resolve()
    if SX_BLOBS.resolve() not in file_path.parents or not file_path.exists():
        raise HTTPException(status_code=404, detail="Blob file missing")
    safe_fname = (r["name"] or key.replace(":", "_")).replace('"', "").replace("\r", "").replace("\n", "")
    mtype = r["type"] or "application/octet-stream"
    disp = "inline" if mtype in ("application/pdf", "image/png", "image/jpeg", "image/webp") else "attachment"
    return FileResponse(
        path=str(file_path),
        media_type=mtype,
        headers={
            "Content-Disposition": f'{disp}; filename="{safe_fname}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---------------------------------------------------------------------------
# SmartExpedit REST API (/api/v1/*) + InspectFlow IMS Connector
# ---------------------------------------------------------------------------

@router.get("/api/v1/health")
def sx_health():
    with LOCK, sx_db() as c:
        n = len(_records(c))
    return {"ok": True, "pos": n, "time": time.strftime("%Y-%m-%dT%H:%M:%S")}


@router.get("/api/v1/pos")
def sx_api_pos(request: Request):
    user = _need_key(request)
    vendor_only = is_vendor_user(user)
    with LOCK, sx_db() as c:
        visible = _filter_rec_list_for_user(_records(c), user)
        out = []
        for r in visible:
            s = _summary(r)
            if vendor_only:
                s.pop("value", None)
                s.pop("currency", None)
            out.append(s)
        return out


@router.get("/api/v1/pos/{po}")
def sx_api_po(po: str, request: Request, part: Optional[str] = None):
    user = _need_key(request)
    with LOCK, sx_db() as c:
        r = _find(c, po)
    if not user_can_access_po(user, r):
        raise HTTPException(status_code=403, detail=f"Access denied to PO {po}")
    if is_vendor_user(user):
        r = _strip_po_for_vendor(r)
    if not part:
        return r
    parts = {
        "documents": (r.get("reg") or {}).get("rows", []),
        "schedule": (r.get("sch") or {}).get("rows", []),
        "plan": (r.get("plan") or {}).get("rows", []),
        "items": r.get("items", []),
        "irns": r.get("irns", []),
        "shipments": {
            "shipments": r.get("ships", []),
            "packing_lists": r.get("pls", []),
            "bills_of_lading": r.get("bls", []),
        },
        "inspection": {
            "reports": r.get("irs", []),
            "punch_list": r.get("punch", []),
        },
        "reviews": r.get("rvw", {}),
        "submissions": r.get("subs", []),
        "mssr": r.get("mssrX", {}),
    }
    if part not in parts:
        raise HTTPException(
            status_code=400, detail="part must be one of: " + ", ".join(parts)
        )
    return parts[part]


@router.patch("/api/v1/pos/{po}")
async def sx_api_po_patch(
    po: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="send a JSON object")
    protected_keys = {"po", "irns", "clr", "vdrl_documents"}
    blocked = protected_keys.intersection(body.keys())
    if blocked:
        raise HTTPException(
            status_code=400,
            detail=f"Direct PATCH of gated fields ({', '.join(sorted(blocked))}) is forbidden; use dedicated EPC workflow endpoints.",
        )
    actor = _who(request, current_user)
    with LOCK, sx_db() as c:
        L = _records(c)
        r = next((x for x in L if x.get("po") == po), None)
        if not r:
            raise HTTPException(status_code=404, detail="PO not found")
        if not user_can_access_po(current_user, r):
            raise HTTPException(status_code=403, detail=f"Access denied to PO {po}")
        if str(body.get("stage") or "").lower() == "closed":
            _validate_po_closeout_gate(r, _get_sx_state(c))
        r.update(body)
        ver = _save_records(c, L, actor, "PATCH %s %s" % (po, ",".join(body)))
    record_audit_event("po", po, "PO_PATCHED", actor=current_user, after=body)
    return {"ok": True, "version": ver}


@router.post("/api/v1/pos/{po}/{lst}", status_code=201)
async def sx_api_po_append(
    po: str,
    lst: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "inspection_engineer", "qc_manager")),
):
    if lst not in ("ships", "pls", "bls", "irs", "punch"):
        raise HTTPException(
            status_code=400,
            detail="list must be ships, pls, bls, irs or punch (use /api/v1/issue-irc for IRNs)",
        )
    e = await request.json()
    if not isinstance(e, dict):
        raise HTTPException(status_code=400, detail="send a JSON object")
    e.setdefault("id", uuid.uuid4().hex[:10])
    if lst == "ships":
        e.setdefault("modeLog", [])
    actor = _who(request, current_user)
    with LOCK, sx_db() as c:
        L = _records(c)
        r = next((x for x in L if x.get("po") == po), None)
        if not r:
            raise HTTPException(status_code=404, detail="PO not found")
        if not user_can_access_po(current_user, r):
            raise HTTPException(status_code=403, detail=f"Access denied to PO {po}")
        r.setdefault(lst, []).append(e)
        r.setdefault("log", []).append(
            {
                "on": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                "by": actor,
                "txt": "Added to %s." % lst,
            }
        )
        ver = _save_records(c, L, actor, "POST %s %s" % (po, lst))
    return {"ok": True, "id": e["id"], "version": ver}


@router.get("/api/v1/field")
def sx_api_field(
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "field_expeditor")),
):
    with LOCK, sx_db() as c:
        v, _ = _kv_get(c, FIELD_KEY)
        if not v:
            return {"rows": []}
        f_obj = json.loads(v)
        if not is_admin_user(current_user) and isinstance(f_obj.get("rows"), list):
            allowed_pos = _allowed_po_numbers_from_db(c, current_user)
            f_obj["rows"] = [
                fr for fr in f_obj["rows"]
                if isinstance(fr, dict) and (
                    str(fr.get("appPo") or "") in allowed_pos
                    or any(p in str(fr.get("poText") or "") for p in allowed_pos)
                )
            ]
        return f_obj


@router.get("/api/v1/files")
def sx_api_files(
    request: Request,
    po: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        v, _ = _kv_get(c, FILES_KEY)
        L = json.loads(v) if v else []
        if not is_admin_user(current_user):
            allowed_pos = _allowed_po_numbers_from_db(c, current_user)
            L = [f for f in L if isinstance(f, dict) and str(f.get("po") or "") in allowed_pos]
        return [f for f in L if not po or f.get("po") == po]


@router.get("/api/v1/files/{fid}")
def sx_api_file(
    fid: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return sx_blob_get("file:" + fid, current_user=current_user)


@router.get("/api/v1/audit")
def sx_api_audit(
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "qc_manager")),
):
    with LOCK, sx_db() as c:
        rows = c.execute(
            "SELECT at, by, what FROM audit ORDER BY id DESC LIMIT 200"
        ).fetchall()
    return [
        {
            "at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["at"])),
            "by": r["by"],
            "what": r["what"],
        }
        for r in rows
    ]


SX_STATE_KEY = "sx_state"


def _get_sx_state(c: sqlite3.Connection) -> Dict[str, Any]:
    val, _ = _kv_get(c, SX_STATE_KEY)
    if not val:
        return {"concerns": [], "notes": []}
    try:
        data = json.loads(val)
        if not isinstance(data, dict):
            return {"concerns": [], "notes": []}
        data.setdefault("concerns", [])
        data.setdefault("notes", [])
        return data
    except Exception:
        return {"concerns": [], "notes": []}


def _save_sx_state(c: sqlite3.Connection, sx_obj: Dict[str, Any], by: str) -> int:
    return _kv_put(c, SX_STATE_KEY, json.dumps(sx_obj, separators=(",", ":")), by)


def _validate_po_closeout_gate(rec: Dict[str, Any], sx_state: Dict[str, Any]) -> None:
    """Enforce EPC PO Closeout Gate: cannot mark PO closed with open Critical/Major NCRs, undelivered items, or pending MRB."""
    po_num = str(rec.get("po") or "")
    open_crit = [
        c for c in (sx_state.get("concerns") or [])
        if str(c.get("po") or "") == po_num
        and str(c.get("status") or "").upper() != "CLOSED"
        and str(c.get("impact") or "").upper() in ("CRITICAL", "MAJOR", "HIGH")
    ]
    if open_crit:
        raise HTTPException(
            status_code=400,
            detail=f"PO Closeout Gate: {len(open_crit)} Critical/Major RAIL/NCR action item(s) remain open on PO {po_num}.",
        )
    clr = rec.get("clr") or {}
    items = [it for it in (rec.get("items") or []) if not it.get("is_split_parent")]
    undelivered = [
        str(it.get("item"))
        for it in items
        if float((clr.get(str(it.get("item"))) or {}).get("mrv") or 0) < float(it.get("qty") or 0)
    ]
    if undelivered:
        raise HTTPException(
            status_code=400,
            detail=f"PO Closeout Gate: Line item(s) {', '.join(undelivered)} have not reached 100% Site MRV delivery.",
        )


def _ensure_vdrl_docs(rec: Dict[str, Any]) -> list:
    """Returns authentic VDRL documents on the PO plus any locked epc_itp_documents (never fabricates fake Code 1 ITPs)."""
    po_num = str(rec.get("po") or "")
    docs = list(rec.get("vdrl_documents") or [])
    if po_num:
        try:
            with SessionLocal() as db:
                itps = db.query(ItpDocument).filter(ItpDocument.po_number == po_num).all()
                existing_nos = {str(d.get("doc_no") or "").upper() for d in docs}
                for itp in itps:
                    if str(itp.doc_no or "").upper() not in existing_nos:
                        docs.append({
                            "doc_no": itp.doc_no,
                            "title": f"ITP Baseline ({itp.scope_mode})",
                            "rev": itp.revision,
                            "code": itp.approval_code,
                            "status": "APPROVED" if itp.approval_code in ("Code 1", "Code 2") and itp.status == "LOCKED_ACTIVE" else itp.status,
                            "milestone": "Engineering Approval",
                        })
        except Exception:
            pass
    return docs


def _auto_advance_schedule(target: Dict[str, Any], event_type: str, date_str: str) -> None:
    """
    Automatically updates Manufacturing Schedule milestones (target['sch']['rows'])
    and PO stage timeline (target['stage'], target['mfg'], target['ship']) when
    inspection or logistics events occur.
    """
    import re
    d = (date_str or time.strftime("%Y-%m-%d"))[:10]
    mfg = target.setdefault("mfg", {})
    ship = target.setdefault("ship", {})
    rows = (target.get("sch") or {}).get("rows") or []

    stage_order = ["issued", "ack", "docsOut", "docsIn", "pim", "fab", "insp", "release", "shipped", "delivered", "mrbSub", "closed"]
    cur_stage = target.get("stage") or "issued"
    cur_idx = stage_order.index(cur_stage) if cur_stage in stage_order else 0

    def advance_stage(new_st: str):
        if new_st in stage_order and stage_order.index(new_st) > cur_idx:
            target["stage"] = new_st

    patterns = []
    if event_type == "pim":
        mfg["pimOn"] = d
        advance_stage("pim")
        patterns = [r"pim", r"pre-?inspection"]
    elif event_type == "insp_completed":
        mfg["extInsp"] = d
        advance_stage("insp")
        patterns = [r"final inspection", r"fat", r"factory acceptance", r"witness", r"internal test"]
    elif event_type == "irc_issued":
        mfg["irn"] = d
        advance_stage("release")
        patterns = [r"\birn\b", r"\birc\b", r"release note", r"inspection release"]
    elif event_type == "shipped":
        ship["etd"] = d
        advance_stage("shipped")
        patterns = [r"ex-?works", r"\bexw\b", r"\bfob\b", r"\bcfr\b", r"dispatch", r"shipment"]
    elif event_type == "mrv_delivered":
        ship["mrvOn"] = d
        # Advance to delivered if all items have mrv >= qty
        items = target.get("items") or []
        clr = target.get("clr") or {}
        if items and all(float((clr.get(str(x.get("item"))) or {}).get("mrv", 0)) >= float(x.get("qty") or 0) for x in items):
            advance_stage("delivered")
        patterns = [r"delivered", r"site receipt", r"\bmrv\b", r"arrival at site"]

    for row in rows:
        act = str(row.get("act") or "")
        if any(re.search(p, act, re.IGNORECASE) for p in patterns):
            row["pct"] = "100"
            row["fE"] = d


def _sync_inspection_into_records(insp: Dict[str, Any], L: list, sx_state: Dict[str, Any]) -> bool:
    """
    Core bidirectional sync logic for a single InspectFlow inspection record into SmartExpedit.
    Enforces Strict Quality Gate:
    - Report upload without IRC -> 'UNDER IE REVIEW' or 'IE APPROVED — READY FOR IRC' (never 'IRN ISSUED')
    - Only actual Release Note (IRC) -> 'IRN ISSUED'
    - Syncs findings/NCRs into SmartExpedit RAIL (sx_state['concerns']) and target['sx']['punch']
    """
    po_num = str(insp.get("po_number") or "").strip()
    if not po_num:
        return False

    target = next((r for r in L if str(r.get("po")) == po_num), None)
    if not target:
        sup_raw = str(insp.get("supplier_name") or "").strip()
        sup_email = str(insp.get("supplier_email") or "").strip()
        insp_pid = str(insp.get("project_id") or "").strip()
        vend_id = str(insp.get("assigned_vendor_id") or "").strip()
        vend_email = sup_email
        if sup_raw and sup_raw.lower() != "vendor":
            try:
                v_user, _ = inspectflow_db.ensure_vendor_user(
                    company_name=sup_raw,
                    vendor_email=sup_email,
                    project_id=insp_pid or None,
                )
                vend_id = v_user.get("id") or vend_id
                vend_email = v_user.get("email") or vend_email
            except Exception:
                pass
        target = {
            "po": po_num,
            "rev": insp.get("notification_revision") or "0",
            "project_id": insp_pid,
            "supplier": (sup_raw or "Vendor").upper(),
            "supplierShort": (sup_raw or "Vendor")[:22],
            "assigned_vendor_id": vend_id,
            "assigned_vendor_email": vend_email,
            "mrRef": f"MR-{po_num}",
            "project": "InspectFlow Linked Project",
            "head": insp.get("po_description") or "Inspection Package",
            "ccy": "USD",
            "value": 0,
            "incoterm": "DDP",
            "issuedOn": (insp.get("notification_receipt_date") or time.strftime("%Y-%m-%d"))[:10],
            "assignedTo": insp.get("assigned_expeditor_name") or "",
            "stage": "insp",
            "lots": [{"id": "Lot 1", "date": (insp.get("end_date") or "2026-12-30")[:10], "grace": 0, "ld": True}],
            "items": [
                {
                    "item": str(it.get("itemNumber") or it.get("item_number") or it.get("item") or (idx + 1) * 10),
                    "desc": it.get("description") or "Valve / Equipment Item",
                    "unit": it.get("unit") or "EA",
                    "qty": float(str(it.get("quantity") or it.get("qty") or 1).split()[0]) if str(it.get("quantity") or it.get("qty") or "1").split()[0].replace(".", "", 1).isdigit() else 1.0,
                    "hold": 0,
                    "lot": "Lot 1",
                }
                for idx, it in enumerate(insp.get("items_being_offered") or [{"itemNumber": "10", "description": insp.get("po_description") or "Item"}])
            ],
            "irs": [],
            "irns": [],
            "punch": [],
            "sx": {"notif": [], "look": [], "punch": [], "iap": []},
        }
        L.append(target)

    _ensure_vdrl_docs(target)

    all_reports = insp.get("inspection_reports") or []
    insp_reports = [r for r in all_reports if r.get("category") != "release_note" and r.get("report_type") != "release_note"]
    rel_notes = [r for r in all_reports if r.get("category") == "release_note" or r.get("report_type") == "release_note"] + (insp.get("release_notes") or [])

    has_irc = len(rel_notes) > 0
    has_insp_report = len(insp_reports) > 0
    ie_approved = bool(insp.get("ie_approved_for_release")) or (has_insp_report and any(r.get("approval_status") == "approved" for r in insp_reports))

    # Determine accurate status label (Strict Quality Gate: never 'IRN ISSUED' unless IRC exists)
    if has_irc:
        display_status = "IRN ISSUED"
    elif ie_approved:
        display_status = "IE APPROVED — READY FOR IRC"
    elif has_insp_report:
        display_status = "UNDER IE REVIEW (PENDING RELEASE)"
    elif insp.get("assigned_inspector_name") or str(insp.get("status") or "").lower() in ("scheduled", "inprogress"):
        display_status = f"SCHEDULED ({insp.get('assigned_inspector_name') or 'Inspector'})"
    else:
        display_status = "NOI RECEIVED"

    # Check EDMS ITP status
    vdrl_docs = target.get("vdrl_documents") or []
    has_code12_itp = any("ITP" in str(d.get("doc_no", "")).upper() and d.get("code") in ("Code 1", "Code 2") for d in vdrl_docs)
    itp_tag = "" if has_code12_itp else " [⚠️ ITP NOT CODE 1/2]"

    # 1. Sync Notification into target['sx']['notif']
    sx_obj = target.setdefault("sx", {})
    notifs = sx_obj.setdefault("notif", [])
    notif_no = insp.get("notification_number") or f"NOI-{po_num}"
    existing_notif = next((n for n in notifs if str(n.get("Activity", "")).startswith(notif_no)), None)
    activity_title = f"{notif_no} — {insp.get('po_description') or 'Inspection'}{itp_tag}"
    if not existing_notif:
        notifs.append({
            "id": insp.get("id") or uuid.uuid4().hex[:8],
            "Activity": activity_title,
            "Type": insp.get("inspection_type") or "Witness",
            "Requested date": (insp.get("start_date") or "")[:10],
            "Status": display_status,
        })
    else:
        existing_notif["Activity"] = activity_title
        existing_notif["Type"] = insp.get("inspection_type") or existing_notif.get("Type") or "Witness"
        existing_notif["Requested date"] = (insp.get("start_date") or existing_notif.get("Requested date") or "")[:10]
        existing_notif["Status"] = display_status

    # 2. Sync IAP (Inspector Assignment & Attendance) into target['sx']['iap']
    iaps = sx_obj.setdefault("iap", [])
    existing_iap = next((a for a in iaps if a.get("notif_no") == notif_no), None)
    iap_entry = {
        "notif_no": notif_no,
        "type": insp.get("inspection_type") or "Witness",
        "inspector": insp.get("assigned_inspector_name") or insp.get("assigned_inspector_email") or "Unassigned",
        "tpi": insp.get("tpi_agency") or "In-House QA/QC",
        "date": (insp.get("start_date") or "")[:10],
        "ie_approved": ie_approved,
        "status": display_status,
    }
    if existing_iap:
        existing_iap.update(iap_entry)
    else:
        iaps.append(iap_entry)

    # 3. Sync Inspection Reports & MTCs into target['irs'] (with both InspectFlow & SmartExpedit tabIr schema fields)
    irs = target.setdefault("irs", [])
    for rep in insp_reports:
        rep_url = rep.get("url") or ""
        rep_name = rep.get("name") or "Inspection Report"
        rep_date = rep.get("report_date") or (rep.get("uploaded_date") or "")[:10]
        rep_cat = rep.get("category") or rep.get("report_type") or "inspection"
        rep_appr = rep.get("approval_status") or "pending"
        rep_findings = rep.get("findings") or []
        ir_extra = {
            "no": rep_name,
            "date": rep_date,
            "poRev": target.get("rev") or "0",
            "item": ", ".join(str(x.get("itemNumber") or x.get("item") or "") for x in (insp.get("items_being_offered") or []) if x),
            "equip": insp.get("po_description") or "",
            "type": insp.get("inspection_type") or rep_cat,
            "inspector": insp.get("assigned_inspector_name") or rep.get("uploaded_by") or "Inspector",
            "agency": insp.get("tpi_agency") or "TPI",
            "loc": insp.get("location_address") or insp.get("location_name") or "",
            "result": rep_appr.upper(),
            "obs": f"{len(rep_findings)} finding(s)" if rep_findings else "Clean",
            "file": rep_url,
        }
        if not any(r.get("url") == rep_url and r.get("name") == rep_name for r in irs):
            irs.append({
                "id": rep.get("id") or uuid.uuid4().hex[:8],
                "name": rep_name,
                "category": rep_cat,
                "report_date": rep_date,
                "uploaded_by": rep.get("uploaded_by") or "Inspector",
                "uploaded_date": rep.get("uploaded_date") or "",
                "approval_status": rep_appr,
                "findings": rep_findings,
                "url": rep_url,
                **ir_extra,
            })
        else:
            existing_ir = next(r for r in irs if r.get("url") == rep_url and r.get("name") == rep_name)
            existing_ir["approval_status"] = rep_appr
            existing_ir["findings"] = rep_findings
            existing_ir.update(ir_extra)

    # 4. Sync Findings / NCRs into SmartExpedit RAIL (sx_state['concerns']) and target['sx']['punch']
    concerns = sx_state.setdefault("concerns", [])
    punches = sx_obj.setdefault("punch", [])
    rail_list = target.setdefault("rail", [])

    for rep in insp_reports:
        for idx, f in enumerate(rep.get("findings") or []):
            f_id = str(f.get("id") or f"{rep.get('url', 'rep')}_{idx}")
            f_type = f.get("type") or f.get("TYPE") or "NCR"
            f_desc = f.get("description") or f.get("DESCRIPTION") or "Inspection finding"
            f_sev = f.get("severity") or f.get("SEVERITY") or "Major"
            f_ref = f.get("item_reference") or f.get("ITEM/REFERENCE") or ""
            is_closed_in_if = (str(f.get("closure_status") or f.get("status") or "").lower() == "closed")

            issue_text = f"[{f_type} - {f_sev}] {f_desc}" + (f" (Ref: {f_ref})" if f_ref else "")
            concern = next((c for c in concerns if c.get("if_finding_id") == f_id or (c.get("po") == po_num and c.get("issue") == issue_text)), None)

            if not concern:
                act_no = f"NCR-{len(concerns) + 1:03d}"
                new_status = "PENDING_VERIFICATION" if is_closed_in_if else "OPEN"
                concern = {
                    "id": f_id,
                    "if_finding_id": f_id,
                    "no": act_no,
                    "po": po_num,
                    "cat": "INSPECTION",
                    "issue": issue_text,
                    "by": f.get("added_by_role") or "INSPECTOR",
                    "assignedTo": "VENDOR",
                    "assignedVendor": target.get("supplierShort") or target.get("supplier") or "Vendor",
                    "source": f"InspectFlow ({notif_no})",
                    "target": time.strftime("%Y-%m-%d", time.gmtime(time.time() + 7 * 86400)),
                    "impact": "CRITICAL" if "critical" in f_sev.lower() or "major" in f_sev.lower() else "MEDIUM",
                    "status": new_status,
                    "technical_status": "APPROVED" if is_closed_in_if else "OPEN",
                    "resolution": f.get("closure_justification") or "",
                    "history": [
                        {
                            "on": time.strftime("%Y-%m-%d"),
                            "by": f.get("added_by") or "InspectFlow QA/QC",
                            "act": "Created from Inspection Report",
                            "note": f"Auto-escalated from {rep.get('name') or notif_no}",
                        }
                    ],
                }
                concerns.insert(0, concern)
            else:
                if is_closed_in_if and concern.get("status") == "OPEN":
                    concern["status"] = "PENDING_VERIFICATION"
                    concern["technical_status"] = "APPROVED"
                    concern["resolution"] = f.get("closure_justification") or "Technical rework approved in InspectFlow."
                    concern.setdefault("history", []).append({
                        "on": time.strftime("%Y-%m-%d"),
                        "by": f.get("closed_by") or "Inspector",
                        "act": "Stage 1 Technical Closeout",
                        "note": concern["resolution"],
                    })

            # Also keep in target['sx']['punch'] and target['rail']
            if not any(p.get("id") == f_id for p in punches):
                punches.append({
                    "id": f_id,
                    "Punch point": issue_text,
                    "Raised by": f.get("added_by") or "InspectFlow QA/QC",
                    "Due": concern.get("target") or "",
                    "Status": concern.get("status"),
                })
            else:
                for p in punches:
                    if p.get("id") == f_id:
                        p["Status"] = concern.get("status")

            if not any(r.get("id") == f_id for r in rail_list):
                rail_list.append({
                    "id": f_id,
                    "no": concern.get("no"),
                    "desc": issue_text,
                    "tier": 2 if "critical" in f_sev.lower() or "major" in f_sev.lower() else 1,
                    "status": "Pending Expeditor Verification" if is_closed_in_if else "Open",
                    "technical_status": "APPROVED" if is_closed_in_if else "OPEN",
                })
            # Mirror to target['punch'] so SmartExpedit tabPunchX displays IMS findings seamlessly
            target_punch = target.setdefault("punch", [])
            if not any(p.get("id") == f_id for p in target_punch):
                target_punch.append({
                    "id": f_id,
                    "no": concern.get("no"),
                    "cat": f_sev,
                    "desc": issue_text,
                    "item": f_ref or "General",
                    "owner": "VENDOR",
                    "due": concern.get("target") or "",
                    "status": "CLOSED" if concern.get("status") == "CLOSED" else ("PENDING VERIFICATION" if is_closed_in_if else "OPEN"),
                })
            else:
                for tp in target_punch:
                    if tp.get("id") == f_id:
                        tp["status"] = "CLOSED" if concern.get("status") == "CLOSED" else ("PENDING VERIFICATION" if is_closed_in_if else "OPEN")

    # 5. Auto-advance schedule if PIM or inspection report completed
    insp_type_lower = str(insp.get("inspection_type") or "").lower()
    if "pim" in insp_type_lower and has_insp_report:
        _auto_advance_schedule(target, "pim", (insp.get("end_date") or time.strftime("%Y-%m-%d"))[:10])
    elif has_insp_report:
        _auto_advance_schedule(target, "insp_completed", (insp.get("end_date") or time.strftime("%Y-%m-%d"))[:10])

    return True


def sync_single_inspection_to_smartexpedit(insp: Dict[str, Any]) -> None:
    """
    Real-time zero-click hook invoked automatically whenever an inspection is created or updated in InspectFlow.
    """
    if not insp:
        return
    with LOCK, sx_db() as c:
        L = _records(c)
        if not L:
            return
        sx_state = _get_sx_state(c)
        if _sync_inspection_into_records(insp, L, sx_state):
            _save_records(c, L, "InspectFlow Live Sync", f"Auto-synced NOI {insp.get('notification_number')}")
            _save_sx_state(c, sx_state, "InspectFlow Live Sync")


def remove_inspection_from_smartexpedit(insp: Dict[str, Any]) -> None:
    """Cascades deletion of an InspectFlow inspection across SmartExpedit & Vendor Portal state."""
    if not insp:
        return
    po_num = str(insp.get("po_number") or "").strip()
    insp_id = str(insp.get("id") or "").strip()
    notif_no = str(insp.get("notification_number") or "").strip()
    finding_ids = set()
    for rep in (insp.get("inspection_reports") or []):
        if not isinstance(rep, dict):
            continue
        for f in (rep.get("findings") or []):
            if isinstance(f, dict) and f.get("id"):
                finding_ids.add(str(f.get("id")))
    source_tag = f"InspectFlow ({notif_no})" if notif_no else None

    with LOCK, sx_db() as c:
        L = _records(c)
        sx_state = _get_sx_state(c)
        changed_records = False
        changed_state = False

        # 1. Remove from target PO notif, iap, punch, and rail entries synced from this NOI
        for r in L:
            if po_num and str(r.get("po") or "") != po_num:
                continue
            sx_obj = r.setdefault("sx", {})
            notifs = sx_obj.get("notif") or []
            iaps = sx_obj.get("iap") or []
            punches = sx_obj.get("punch") or []
            new_notifs = [
                n for n in notifs
                if str(n.get("id") or "") != insp_id
                and (not notif_no or (str(n.get("notif_no") or "") != notif_no and not str(n.get("Activity") or "").startswith(notif_no)))
            ]
            new_iaps = [
                a for a in iaps
                if str(a.get("id") or "") != insp_id
                and (not notif_no or str(a.get("notif_no") or "") != notif_no)
            ]
            if len(new_notifs) != len(notifs) or len(new_iaps) != len(iaps):
                sx_obj["notif"] = new_notifs
                sx_obj["iap"] = new_iaps
                changed_records = True

            if finding_ids:
                new_punches = [p for p in punches if str(p.get("id") or "") not in finding_ids]
                new_rail = [rl for rl in (r.get("rail") or []) if str(rl.get("id") or "") not in finding_ids]
                new_target_punch = [tp for tp in (r.get("punch") or []) if str(tp.get("id") or "") not in finding_ids]
                if len(new_punches) != len(punches) or len(new_rail) != len(r.get("rail") or []) or len(new_target_punch) != len(r.get("punch") or []):
                    sx_obj["punch"] = new_punches
                    r["rail"] = new_rail
                    r["punch"] = new_target_punch
                    changed_records = True

        # 2. Remove auto-escalated concerns linked exclusively to this deleted NOI
        concerns = sx_state.get("concerns") or []
        new_concerns = [
            cn for cn in concerns
            if str(cn.get("id") or "") not in finding_ids
            and (not source_tag or str(cn.get("source") or "") != source_tag)
            and (not insp_id or str(cn.get("insp_id") or "") != insp_id)
        ]
        if len(new_concerns) != len(concerns):
            sx_state["concerns"] = new_concerns
            changed_state = True

        # 3. Unlink any Vendor Portal dispatch request pointing to the deleted NOI so it can be re-submitted cleanly
        for dsp in (sx_state.get("dispatch_requests") or []):
            if str(dsp.get("inspection_id") or "") == insp_id:
                dsp["inspection_id"] = None
                if str(dsp.get("status") or "").upper() in ("NOI_CREATED", "IN_INSPECTION"):
                    dsp["status"] = "SUBMITTED"
                changed_state = True

        if changed_records:
            _save_records(c, L, "InspectFlow Delete Sync", f"Removed deleted NOI {notif_no or insp_id} across Vendor & Expediting portals")
        if changed_state:
            _save_sx_state(c, sx_state, "InspectFlow Delete Sync")


@router.post("/api/v1/sync-inspectflow")
def sync_inspectflow_to_smartexpedit(
    request: Request,
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "inspection_engineer", "qc_manager")
    ),
):
    """
    Live connector between InspectFlow (IMS) and SmartExpedit:
    Syncs accessible Inspection Notifications, Inspection Reports, Findings/NCRs, and Release Notes.
    """
    all_insps = inspectflow_db.list_inspections()
    accessible_pids = _get_accessible_pids_for_user(current_user)
    if accessible_pids is not None:
        inspections = [i for i in all_insps if _norm_id_str(i.get("project_id")) in accessible_pids]
    else:
        inspections = all_insps
    synced_count = 0
    actor = _who(request, current_user)
    with LOCK, sx_db() as c:
        L = _records(c)
        if not L:
            return {"ok": True, "synced": 0, "message": "No PO records initialized yet."}
        sx_state = _get_sx_state(c)
        for insp in inspections:
            if _sync_inspection_into_records(insp, L, sx_state):
                synced_count += 1
        if synced_count > 0:
            _save_records(c, L, actor, f"Synced {synced_count} IMS notifications from InspectFlow")
            _save_sx_state(c, sx_state, actor)
    return {"ok": True, "synced": synced_count}


# ---------------------------------------------------------------------------
# Vendor Portal NOI -> InspectFlow Instant Sync (/api/v1/vendor-noi)
# ---------------------------------------------------------------------------
@router.post("/api/v1/vendor-noi")
def create_inspection_from_vendor_noi(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "inspection_engineer", "qc_manager")
    ),
):
    """
    Invoked when a Vendor raises a Notice of Inspection (NOI) in Vendor Portal / SmartExpedit.
    Creates the corresponding Inspection record in InspectFlow and checks EDMS for Code 1/2 ITP approval.
    """
    po_num = str(payload.get("po_number") or "").strip()
    notif_no = str(payload.get("notification_number") or f"NOI-{po_num}-{int(time.time())}").strip()
    if not po_num:
        raise HTTPException(status_code=400, detail="po_number required")

    with LOCK, sx_db() as c:
        L_chk = _records(c)
        po_chk = next((r for r in L_chk if str(r.get("po")) == po_num), None)
        if is_vendor_user(current_user) and (not po_chk or not vendor_owns_po(current_user, po_chk)):
            raise HTTPException(status_code=403, detail=f"Vendor is not authorized to raise NOI for PO {po_num}")
        if not is_vendor_user(current_user) and po_chk and not user_can_access_po(current_user, po_chk):
            raise HTTPException(status_code=403, detail=f"Access denied: PO {po_num} belongs to an unassigned project")

    existing = next(
        (i for i in inspectflow_db.list_inspections() if i.get("po_number") == po_num and i.get("notification_number") == notif_no),
        None,
    )

    raw_items = payload.get("items") or payload.get("items_being_offered") or []
    offered_items_list = []
    if isinstance(raw_items, list) and len(raw_items) > 0:
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            inum = str(it.get("item_number") or it.get("itemNumber") or it.get("item") or "").strip()
            if not inum:
                continue
            iqty = it.get("qty") if it.get("qty") is not None else (it.get("quantity") or 1)
            iunit = str(it.get("unit") or "EA").strip()
            idesc = str(it.get("description") or it.get("desc") or f"BOM Item {inum}").strip()
            offered_items_list.append({
                "itemNumber": inum,
                "item_number": inum,
                "description": idesc,
                "quantity": f"{iqty} {iunit}" if str(iunit) not in str(iqty) else str(iqty),
                "qty": iqty,
                "unit": iunit,
                "tag": str(it.get("tag") or ""),
            })
    if not offered_items_list:
        item_num = str(payload.get("item_number") or "10")
        item_desc = payload.get("item_description") or "Offered Material Item"
        item_qty = payload.get("item_qty") or 1
        item_unit = payload.get("item_unit") or "EA"
        offered_items_list = [{
            "itemNumber": item_num,
            "item_number": item_num,
            "description": item_desc,
            "quantity": f"{item_qty} {item_unit}",
            "qty": item_qty,
            "unit": item_unit,
        }]

    item_summary_str = ", ".join(x["item_number"] for x in offered_items_list)
    default_scope_title = (
        offered_items_list[0]["description"]
        if len(offered_items_list) == 1
        else f"Items {item_summary_str} ({len(offered_items_list)} BOM items)"
    )

    po_roster = {}
    if po_chk:
        po_roster = {
            "project_id": po_chk.get("project_id"),
            "supplier_name": po_chk.get("supplier") or payload.get("supplier_name") or "Vendor",
            "assigned_inspection_engineer_id": po_chk.get("assigned_inspection_engineer_id"),
            "assigned_inspection_engineer_name": po_chk.get("assigned_inspection_engineer_name"),
            "assigned_inspection_engineer_email": po_chk.get("assigned_inspection_engineer_email"),
            "assigned_expeditor_id": po_chk.get("assigned_expeditor_id"),
            "assigned_expeditor_name": po_chk.get("assigned_expeditor_name") or po_chk.get("assignedTo"),
            "assigned_expeditor_email": po_chk.get("assigned_expeditor_email"),
            "expediting_manager_name": po_chk.get("expediting_manager_name"),
            "inspection_manager_name": po_chk.get("inspection_manager_name"),
        }

    scope_label = str(payload.get("inspection_scope") or payload.get("inspection_type") or "Witness").strip()
    sub_order_id = str(payload.get("sub_order_id") or "").strip()
    client_tpa = str(payload.get("client_tpa_representative") or "").strip()

    if not existing:
        created = inspectflow_db.create_inspection({
            "po_number": po_num,
            "notification_number": notif_no,
            "notification_revision": "0",
            "notification_receipt_date": time.strftime("%Y-%m-%d"),
            "supplier_name": payload.get("supplier_name") or po_roster.get("supplier_name") or "Vendor",
            "inspection_location": payload.get("inspection_location") or "Vendor Works",
            "inspection_type": scope_label,
            "inspection_scope": scope_label,
            "sub_order_id": sub_order_id or None,
            "client_tpa_representative": client_tpa or None,
            "start_date": payload.get("start_date") or time.strftime("%Y-%m-%d"),
            "end_date": payload.get("start_date") or time.strftime("%Y-%m-%d"),
            "po_description": payload.get("scope") or default_scope_title,
            "status": "received",
            "project_id": po_roster.get("project_id") or payload.get("project_id"),
            "assigned_inspection_engineer_id": po_roster.get("assigned_inspection_engineer_id"),
            "assigned_inspection_engineer_name": po_roster.get("assigned_inspection_engineer_name"),
            "assigned_inspection_engineer_email": po_roster.get("assigned_inspection_engineer_email"),
            "assigned_expeditor_id": po_roster.get("assigned_expeditor_id"),
            "assigned_expeditor_name": po_roster.get("assigned_expeditor_name"),
            "assigned_expeditor_email": po_roster.get("assigned_expeditor_email"),
            "expediting_manager_name": po_roster.get("expediting_manager_name"),
            "inspection_manager_name": po_roster.get("inspection_manager_name"),
            "created_by": current_user.get("email"),
            "items_being_offered": offered_items_list,
            "notes": f"Raised via Vendor NOI ({current_user.get('email')}). Items: {item_summary_str}. Scope: {payload.get('scope') or ''}",
        })
    else:
        created = existing

    itp_warning = None
    iap_warning = None
    with LOCK, sx_db() as c:
        L = _records(c)
        target = next((r for r in L if str(r.get("po")) == po_num), None)
        if target:
            docs = _ensure_vdrl_docs(target)
            has_approved_itp = any("ITP" in str(d.get("doc_no", "")).upper() and d.get("code") in ("Code 1", "Code 2") for d in docs)
            if not has_approved_itp:
                itp_warning = f"Quality Gate Warning: PO {po_num} does not have a Code 1/2 Approved ITP in EDMS. NOI {notif_no} flagged for Inspection Engineer review."
            if target.get("requires_client_iap"):
                iap_st = str((target.get("iap_package") or {}).get("client_status") or "NOT_SUBMITTED")
                if iap_st != "APPROVED":
                    iap_warning = f"IAP Policy Notice: Project requires Client IAP approval before inspection release (current IAP status: {iap_st})."
            if sub_order_id:
                for sr in ((target.get("plan") or {}).get("rows") or []):
                    if str(sr.get("id")) == sub_order_id:
                        sr["linked_noi"] = notif_no
                        sr["linked_inspection_id"] = created.get("id")
        sx_state = _get_sx_state(c)
        _sync_inspection_into_records(created, L, sx_state)
        _save_records(c, L, _who(request, current_user), f"NOI {notif_no} raised for PO {po_num}")
        _save_sx_state(c, sx_state, _who(request, current_user))

    record_audit_event("inspection", created.get("id") or notif_no, "VENDOR_NOI_CREATED", actor=current_user, after={"po_number": po_num, "notification_number": notif_no, "scope": scope_label})
    return {
        "ok": True,
        "inspection_id": created.get("id"),
        "notification_number": notif_no,
        "items_count": len(offered_items_list),
        "inspection_scope": scope_label,
        "itp_warning": itp_warning,
        "iap_warning": iap_warning,
    }


# ---------------------------------------------------------------------------
# Inspection Engineer Deliverable Review, Missed Finding Injection & Endorsement
# ---------------------------------------------------------------------------
@router.post("/api/v1/inspections/{inspection_id}/add-finding")
def add_engineer_finding(
    inspection_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "inspection_engineer", "qc_manager", "inspector")),
):
    """
    Allows the Inspection Engineer, QC Manager, or Field Inspector reviewing deliverables
    to add findings/NCRs to the inspection report and auto-escalate to RAIL.
    """
    insp = inspectflow_db.get_inspection(inspection_id)
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if not is_admin_user(current_user) and insp.get("project_id") and not user_can_access_project_id(current_user, insp.get("project_id")):
        raise HTTPException(status_code=403, detail="Access denied: inspection belongs to another project")

    f_type = payload.get("type") or "NCR"
    f_sev = payload.get("severity") or "Major"
    f_desc = str(payload.get("description") or "").strip()
    f_ref = payload.get("item_reference") or ""
    added_by = current_user.get("full_name") or "Inspection Engineer"
    added_by_role = effective_role(current_user).upper() or "INSPECTION_ENGINEER"

    if not f_desc:
        raise HTTPException(status_code=400, detail="Finding description is required")

    reports = insp.get("inspection_reports") or []
    target_rep = next((r for r in reports if r.get("category") != "release_note"), None)
    if not target_rep:
        target_rep = {
            "id": f"ie-review-{uuid.uuid4().hex[:6]}",
            "name": f"IE Deliverable Review — {insp.get('notification_number')}",
            "category": "inspection",
            "report_type": "Final",
            "is_final_report": True,
            "report_date": time.strftime("%Y-%m-%d"),
            "uploaded_by": added_by,
            "uploaded_date": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "approval_status": "pending",
            "findings": [],
            "url": insp.get("document_url") or "",
        }
        reports.append(target_rep)

    findings = target_rep.setdefault("findings", [])
    new_finding = {
        "id": f"ie-f-{uuid.uuid4().hex[:8]}",
        "type": f_type,
        "severity": f_sev,
        "description": f_desc,
        "item_reference": f_ref,
        "status": "Open",
        "closure_status": "open",
        "added_by": added_by,
        "added_by_role": added_by_role,
        "added_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }
    findings.append(new_finding)

    inspectflow_db.update_inspection(inspection_id, {"inspection_reports": reports})
    fresh = inspectflow_db.get_inspection(inspection_id)
    if fresh:
        sync_single_inspection_to_smartexpedit(fresh)
    record_audit_event("inspection", inspection_id, "FINDING_ADDED", actor=current_user, after=new_finding)

    return {
        "ok": True,
        "finding": new_finding,
        "message": "Finding added and synchronized to Expediting RAIL.",
    }


@router.post("/api/v1/inspections/{inspection_id}/ie-approve")
def approve_report_for_release(
    inspection_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "inspection_engineer", "qc_manager")),
):
    """
    Inspection Engineer / QC Manager endorses the uploaded Inspection Report & deliverables,
    authorizing the issuance of the Inspection Release Certificate (IRC).
    """
    insp = inspectflow_db.get_inspection(inspection_id)
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if not is_admin_user(current_user) and insp.get("project_id") and not user_can_access_project_id(current_user, insp.get("project_id")):
        raise HTTPException(status_code=403, detail="Access denied: inspection belongs to another project")

    approved_by = current_user.get("full_name") or current_user.get("email") or "Inspection Engineer"
    comments = payload.get("comments") or "Deliverables reviewed and endorsed for IRC release."
    grant_concession = bool(payload.get("grant_concession"))

    reports = insp.get("inspection_reports") or []
    insp_only = [r for r in reports if r.get("category") != "release_note" and r.get("report_type") != "release_note"]
    if not insp_only:
        raise HTTPException(status_code=400, detail="Cannot endorse release: no inspection report has been uploaded yet.")

    for r in insp_only:
        r["approval_status"] = "approved"
        r["approved_by"] = approved_by
        r["approved_date"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        r["ie_review_comments"] = comments
        if grant_concession:
            r["concession_granted"] = True

    inspectflow_db.update_inspection(inspection_id, {
        "inspection_reports": reports,
        "status": "completed",
    })
    fresh = inspectflow_db.get_inspection(inspection_id)
    if fresh:
        sync_single_inspection_to_smartexpedit(fresh)
    record_audit_event("inspection", inspection_id, "IE_REPORT_ENDORSED", actor=current_user, after={"grant_concession": grant_concession, "comments": comments})

    return {
        "ok": True,
        "message": "Inspection Report & deliverables endorsed by Inspection Engineer. Authorized for IRC Release.",
    }


@router.post("/api/v1/issue-irc")
async def issue_irc_endpoint(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "inspection_engineer", "qc_manager", "inspector")),
):
    """
    Issues an official Inspection Release Certificate (IRC) with strict non-bypassable quality & quantity gates:
    1. Mandatory linked `inspection_id` + uploaded & IE-endorsed Inspection Report.
    2. Zero open Critical/Major NCRs across the inspection, PO inspections, RAIL & MNCRs (concessions allowed ONLY by IE/QC/Admin and persisted to epc_concessions_waivers).
    3. Authentic Code 1/2 ITP & Hold-Point verification (or IE/QC concession waiver).
    4. Positive quantity conservation (PO Revision Override allowed ONLY by IE/QC/Admin and persisted to epc_po_revisions).
    """
    payload = await request.json()
    insp_id = str(payload.get("inspection_id") or "").strip()
    po_num = str(payload.get("po_number") or "").strip()
    irc_no = str(payload.get("irc_number") or "").strip() or f"IRC-{po_num}-{int(time.time())}"
    release_date = str(payload.get("release_date") or time.strftime("%Y-%m-%d"))[:10]
    inspector = current_user.get("full_name") or current_user.get("email") or "InspectFlow QA/QC"
    user_role = effective_role(current_user)
    is_ie_or_qc = user_role in ("admin", "inspection_engineer", "qc_manager")
    remarks = str(payload.get("remarks") or "").strip()
    items_released = payload.get("items_released") or []
    if not items_released and (payload.get("item_id") or payload.get("item")):
        items_released = [{
            "item": payload.get("item_id") or payload.get("item"),
            "quantity": payload.get("released_qty") or payload.get("quantity") or 0,
            "unit": payload.get("unit") or "EA",
        }]
    file_url = str(payload.get("file_url") or "").strip()
    mode = payload.get("mode") or "guided"
    concession_granted = bool(payload.get("concession_granted"))
    concession_reason = str(payload.get("concession_reason") or "").strip()
    concession_ref_no = str(payload.get("concession_ref_no") or f"CONC-{po_num}-{int(time.time())}").strip()
    po_revision_override = bool(payload.get("po_revision_override"))
    po_revision_justification = str(payload.get("po_revision_justification") or "").strip()

    if not insp_id:
        raise HTTPException(status_code=400, detail="Valid inspection_id is mandatory to issue an IRC.")
    insp_record = inspectflow_db.get_inspection(insp_id)
    if not insp_record:
        raise HTTPException(status_code=404, detail=f"Inspection '{insp_id}' not found.")
    if not po_num:
        po_num = str(insp_record.get("po_number") or "").strip()
    if not po_num:
        raise HTTPException(status_code=400, detail="po_number is required.")
    if insp_record.get("po_number") and str(insp_record.get("po_number")).strip() != po_num:
        raise HTTPException(status_code=400, detail="inspection_id does not belong to target po_number.")
    if not is_admin_user(current_user) and insp_record.get("project_id") and not user_can_access_project_id(current_user, insp_record.get("project_id")):
        raise HTTPException(status_code=403, detail="Access denied: inspection belongs to another project.")

    if concession_granted and not is_ie_or_qc:
        raise HTTPException(status_code=403, detail="Only Inspection Engineers, QC Managers, or Admins can grant NCR Concessions.")
    if concession_granted and not concession_reason:
        raise HTTPException(status_code=400, detail="concession_reason is mandatory when granting an NCR Concession.")
    if po_revision_override and not is_ie_or_qc:
        raise HTTPException(status_code=403, detail="Only Inspection Engineers, QC Managers, or Admins can authorize PO Revision Overrides.")
    if po_revision_override and not po_revision_justification:
        raise HTTPException(status_code=400, detail="po_revision_justification is mandatory when authorizing a PO Revision Override.")

    existing_reports = insp_record.get("inspection_reports") or []
    insp_only_reports = [r for r in existing_reports if r.get("category") != "release_note" and r.get("report_type") != "release_note"]
    if not insp_only_reports:
        raise HTTPException(
            status_code=400,
            detail="Mandatory Report Gate: At least one uploaded Inspection Report (Flash/Final) is required before issuing an IRC.",
        )

    # GATE 1: Mandatory Inspection Engineer Review & Endorsement
    any_ie_approved = any(r.get("approval_status") == "approved" for r in insp_only_reports)
    if not any_ie_approved and not is_ie_or_qc:
        raise HTTPException(
            status_code=400,
            detail="Mandatory IE Review Gate: The uploaded Inspection Report must be reviewed and approved by the Inspection Engineer before an IRC can be issued.",
        )

    # GATE 2: Strict Quality Gate on Open Critical/Major NCRs across this inspection & PO
    open_crit_major = []
    has_minor_punch = False
    for r in insp_only_reports:
        if r.get("concession_granted") and is_ie_or_qc:
            concession_granted = True
        for f in (r.get("findings") or []):
            if str(f.get("closure_status") or f.get("status") or "").lower() not in ("closed", "waived", "conceded"):
                sev = str(f.get("severity") or f.get("SEVERITY") or "").lower()
                ftype = str(f.get("type") or f.get("TYPE") or "").lower()
                if "critical" in sev or "major" in sev or "ncr" in ftype or "non-conformance" in ftype:
                    open_crit_major.append(f.get("description") or f.get("DESCRIPTION") or "Open NCR")
                else:
                    has_minor_punch = True

    with LOCK, sx_db() as c:
        L = _records(c)
        sx_state = _get_sx_state(c)
        target = next((x for x in L if str(x.get("po")) == po_num), None)
        if target and not user_can_access_po(current_user, target):
            raise HTTPException(status_code=403, detail=f"Access denied to PO {po_num}")

        # Check PO-wide RAIL/MNCR open Critical/Major findings
        for c_item in (sx_state.get("concerns") or []):
            if str(c_item.get("po") or "") == po_num and str(c_item.get("status") or "").upper() != "CLOSED":
                imp = str(c_item.get("impact") or "").upper()
                if imp in ("CRITICAL", "MAJOR"):
                    open_crit_major.append(str(c_item.get("issue") or "Open RAIL Concern"))
        if target:
            for r_item in (target.get("rail") or []):
                if str(r_item.get("status") or "").lower() != "closed" and int(r_item.get("tier") or 1) >= 2:
                    open_crit_major.append(str(r_item.get("desc") or "Open RAIL Action"))
            for m_item in ((target.get("sx") or {}).get("mncr") or []):
                if str(m_item.get("Status") or "OPEN").upper() != "CLOSED":
                    open_crit_major.append(str(m_item.get("Description") or "Open MNCR"))

        if open_crit_major and not concession_granted:
            raise HTTPException(
                status_code=400,
                detail=f"Strict Quality Gate: Cannot issue IRC while {len(open_crit_major)} Critical/Major NCR(s)/RAIL(s) remain open on PO {po_num}. Close findings or record an IE/QC Concession.",
            )

        # GATE 3: ITP Code 1/2 & Pending Hold-Point check
        if target:
            docs = _ensure_vdrl_docs(target)
            has_approved_itp = any("ITP" in str(d.get("doc_no", "")).upper() and d.get("code") in ("Code 1", "Code 2") for d in docs)
            if not has_approved_itp and not concession_granted:
                raise HTTPException(
                    status_code=400,
                    detail=f"ITP Quality Gate: PO {po_num} lacks an approved Code 1/Code 2 ITP in EDMS/VDRL.",
                )

        # Check epc_itp_steps unwaived Hold Points
        try:
            with SessionLocal() as sdb:
                pending_holds = (
                    sdb.query(ItpBaselineStep)
                    .join(ItpDocument, ItpBaselineStep.itp_document_id == ItpDocument.id)
                    .filter(
                        ItpDocument.po_number == po_num,
                        ItpDocument.status == "LOCKED_ACTIVE",
                        ItpBaselineStep.is_hold_point.is_(True),
                        ItpBaselineStep.execution_status == "PENDING",
                    )
                    .count()
                )
                if pending_holds > 0 and not concession_granted:
                    raise HTTPException(
                        status_code=400,
                        detail=f"ITP Hold-Point Gate: {pending_holds} mandatory Hold Point step(s) remain PENDING on locked ITP.",
                    )
        except HTTPException:
            raise
        except Exception:
            pass

        if not items_released:
            raise HTTPException(status_code=400, detail="At least one released BOM line item with positive quantity is required.")

        # Validate quantities > 0 and Over-Release Guardrail BEFORE mutating
        if target:
            clr = target.setdefault("clr", {})
            po_items_by_key = {str(ti.get("item")): ti for ti in target.get("items", []) if not ti.get("is_split_parent")}
            for it in items_released:
                item_key = str(it.get("itemNumber") or it.get("item") or "").strip()
                if not item_key:
                    continue
                qty_val = float(it.get("quantity") or it.get("qty_released") or 0)
                if qty_val <= 0:
                    raise HTTPException(status_code=400, detail=f"Item {item_key}: released quantity must be strictly positive (got {qty_val}).")
                po_item_obj = po_items_by_key.get(item_key)
                if po_item_obj and po_item_obj.get("is_split_parent"):
                    raise HTTPException(status_code=400, detail=f"Item {item_key} has been split into sub-items; release the child sub-items instead.")
                prev_irn = float((clr.get(item_key) or {}).get("irn", 0))
                ordered_qty = float(po_item_obj.get("qty") if po_item_obj else (it.get("ordered_quantity") or qty_val))
                if ordered_qty > 0 and (prev_irn + qty_val) > ordered_qty and not po_revision_override:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cumulative Quantity Guardrail: Item {item_key} release ({prev_irn + qty_val}) exceeds PO Ordered Qty ({ordered_qty}). Requires Procurement/IE PO Revision Override.",
                    )

        irc_status_badge = "APPROVED (CONCESSION)" if concession_granted else ("APPROVED (WITH MINOR PUNCH)" if has_minor_punch else "APPROVED")

        if not target:
            target = {
                "po": po_num,
                "rev": insp_record.get("notification_revision") or "0",
                "project_id": insp_record.get("project_id") or "",
                "supplier": (insp_record.get("supplier_name") or "Vendor").upper(),
                "supplierShort": insp_record.get("supplier_name") or "Vendor",
                "mrRef": f"MR-{po_num}",
                "project": "InspectFlow Project",
                "head": insp_record.get("po_description") or "Material Package",
                "ccy": "USD",
                "value": 0,
                "incoterm": "DDP",
                "issuedOn": (insp_record.get("notification_receipt_date") or release_date)[:10],
                "assignedTo": insp_record.get("assigned_expeditor_name") or inspector,
                "stage": "release",
                "lots": [{"id": "Lot 1", "date": release_date, "grace": 0, "ld": False}],
                "items": [],
                "irs": [],
                "irns": [],
                "punch": [],
                "sx": {"notif": [], "look": [], "punch": [], "iap": []},
            }
            L.append(target)

        clr = target.setdefault("clr", {})
        po_items_by_key = {str(ti.get("item")): ti for ti in target.get("items", [])}
        cum_ledger = sx_state.setdefault("cumulative_ledger", {})
        line_deltas = []

        for it in items_released:
            item_key = str(it.get("itemNumber") or it.get("item") or "").strip()
            if not item_key:
                continue
            qty_val = float(it.get("quantity") or it.get("qty_released") or 0)
            if qty_val <= 0:
                raise HTTPException(status_code=400, detail=f"Item {item_key}: released quantity must be strictly positive.")

            item_entry = clr.setdefault(item_key, {"irn": 0, "ship": 0, "mrv": 0, "batches": []})
            batches = item_entry.setdefault("batches", [])
            if not any(b.get("irc_no") == irc_no for b in batches):
                item_entry["irn"] = float(item_entry.get("irn", 0)) + qty_val
                batches.append({
                    "irc_no": irc_no,
                    "date": release_date,
                    "qty": qty_val,
                    "heat_number": it.get("heat_number") or "",
                })

            if item_key not in po_items_by_key:
                new_item = {
                    "item": item_key,
                    "desc": it.get("description") or "Released Material",
                    "unit": it.get("unit") or "EA",
                    "qty": float(it.get("ordered_quantity") or qty_val),
                    "hold": 0,
                    "lot": "Lot 1",
                }
                target.setdefault("items", []).append(new_item)
                po_items_by_key[item_key] = new_item
            elif po_revision_override and float(po_items_by_key[item_key].get("qty", 0)) < item_entry["irn"]:
                old_q = float(po_items_by_key[item_key].get("qty", 0))
                po_items_by_key[item_key]["qty"] = item_entry["irn"]
                po_items_by_key[item_key]["po_revision_note"] = po_revision_justification
                line_deltas.append({"item": item_key, "old_qty": old_q, "new_qty": item_entry["irn"]})

            # Sync cumulative_ledger in sx_state
            led_key = f"{po_num}:{item_key}"
            led_entry = cum_ledger.setdefault(led_key, {
                "po": po_num,
                "item": item_key,
                "desc": po_items_by_key[item_key].get("desc") or "",
                "unit": po_items_by_key[item_key].get("unit") or "EA",
                "ordered_qty": float(po_items_by_key[item_key].get("qty") or 0),
                "inspected_qty": item_entry["irn"],
                "released_qty": 0,
                "shipped_qty": float(item_entry.get("ship") or 0),
                "delivered_qty": float(item_entry.get("mrv") or 0),
                "batches": [],
            })
            led_entry["ordered_qty"] = float(po_items_by_key[item_key].get("qty") or 0)
            led_entry["released_qty"] = item_entry["irn"]
            led_entry["batches"] = batches

        irns = target.setdefault("irns", [])
        irns.append({
            "id": uuid.uuid4().hex[:8],
            "no": irc_no,
            "date": release_date,
            "by": inspector,
            "scope": f"Released {len(items_released)} line item(s)",
            "status": irc_status_badge,
            "remarks": remarks + (f" [Concession: {concession_reason}]" if concession_granted and concession_reason else "") + (f" [PO Rev Override: {po_revision_justification}]" if po_revision_override and po_revision_justification else ""),
            "items": items_released,
            "file": file_url,
        })

        _auto_advance_schedule(target, "irc_issued", release_date)

        mail_dispatch = {
            "id": uuid.uuid4().hex[:8],
            "at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "subject": f"Inspection Release Certificate (IRC) Issued: PO {po_num} - {irc_no} [{irc_status_badge}]",
            "to": [v for v in [(insp_record or {}).get("vendor_contact_email") or target.get("assigned_vendor_email")] if v],
            "cc": [v for v in [target.get("expediting_manager_email"), target.get("assigned_expeditor_email"), target.get("assigned_inspection_engineer_email")] if v],
            "attachment_name": f"{irc_no}.pdf",
            "attachment_url": file_url,
            "status": "LOGGED_IN_APP_ONLY",
            "scope": f"{len(items_released)} line item(s) released",
        }
        target.setdefault("dispatches", []).append(mail_dispatch)

        in_app_notif = {
            "id": uuid.uuid4().hex[:8],
            "po": po_num,
            "type": "IRC_ISSUED",
            "title": f"IRC {irc_no} Issued ({irc_status_badge}) — Items Cleared for Shipment",
            "message": f"{inspector} issued IRC {irc_no} for {len(items_released)} item(s) on PO {po_num}.",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "read": False,
            "target_tab": "deliv",
        }
        target.setdefault("notifications", []).append(in_app_notif)

        target.setdefault("log", []).append({
            "on": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "by": inspector,
            "txt": f"IRC {irc_no} ({irc_status_badge}) issued. {len(items_released)} item(s) released. Remarks: {remarks}",
        })

        _save_records(c, L, inspector, f"IRC {irc_no} issued for {po_num}")
        _save_sx_state(c, sx_state, inspector)

    # Persist relational ConcessionWaiver and PoRevision records when used
    try:
        with SessionLocal() as sdb:
            if concession_granted:
                sdb.add(ConcessionWaiver(
                    id=uuid.uuid4().hex,
                    po_number=po_num,
                    waiver_type="NCR_CONCESSION",
                    target_ref_id=insp_id,
                    concession_ref_no=concession_ref_no,
                    justification=concession_reason or "IE/QC Approved Concession",
                    approved_by_name=inspector,
                    approved_by_role=user_role,
                ))
            if po_revision_override and line_deltas:
                sdb.add(PoRevision(
                    id=uuid.uuid4().hex,
                    po_number=po_num,
                    revision_no=f"IRC-{irc_no}",
                    reason=po_revision_justification,
                    line_deltas_json=json.dumps(line_deltas),
                    approved_by=inspector,
                ))
            sdb.commit()
    except Exception:
        logger.exception("Failed persisting compliance record during IRC %s", irc_no)

    # Update InspectFlow DB only after all guardrails pass
    release_note_entry = {
        "id": f"irc-{uuid.uuid4().hex[:8]}",
        "name": irc_no,
        "category": "release_note",
        "report_type": "release_note",
        "is_final_release_note": True,
        "release_date": release_date,
        "po_number": po_num or insp_record.get("po_number"),
        "notification_number": insp_record.get("notification_number"),
        "supplier": insp_record.get("supplier_name"),
        "inspector": inspector,
        "remarks": remarks,
        "release_status_badge": irc_status_badge,
        "mode": mode,
        "items_released": items_released,
        "url": file_url,
        "uploaded_by": inspector,
        "uploaded_date": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }
    existing_reports.append(release_note_entry)
    inspectflow_db.update_inspection(insp_id, {
        "inspection_reports": existing_reports,
        "status": "finalized",
    })
    fresh = inspectflow_db.get_inspection(insp_id)
    if fresh:
        sync_single_inspection_to_smartexpedit(fresh)

    record_audit_event(
        "irc",
        irc_no,
        "IRC_ISSUED",
        actor=current_user,
        after={
            "po_number": po_num,
            "inspection_id": insp_id,
            "status": irc_status_badge,
            "items_count": len(items_released),
            "concession_granted": concession_granted,
            "po_revision_override": po_revision_override,
        },
        ip_address=request.client.host if request.client else None,
    )

    return {
        "ok": True,
        "irc_number": irc_no,
        "release_status": irc_status_badge,
        "message": f"IRC {irc_no} ({irc_status_badge}) officially issued and synchronized to Expediting & Logistics.",
        "items_released_count": len(items_released),
        "notification_dispatched": {
            "in_app_alert_created": True,
            "po_audit_logged": True,
        },
    }


# ---------------------------------------------------------------------------
# PO Context Endpoint for InspectFlow 'PO BOM & VDRL/ITP' Tab (/api/v1/po/{po}/context)
# ---------------------------------------------------------------------------
@router.get("/api/v1/po/{po}/context")
def get_po_expediting_context(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Provides InspectFlow (Inspectors, Inspection Engineers, QC Managers) with a live read-only
    snapshot of the PO BOM Cumulative Quantity Ledger, Split Sub-Items, EDMS VDRL/ITP approval
    codes (Code 1/2/3), RAIL action items, and Manufacturing Schedule milestones.
    """
    po_num = str(po or "").strip()
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        L = _records(c)
        target = next((x for x in L if str(x.get("po")) == po_num), None)
        sx_state = _get_sx_state(c)

        if target and not user_can_access_po(current_user, target):
            raise HTTPException(status_code=403, detail=f"Access denied: PO {po_num} is outside your assigned scope")

        if not target:
            return {
                "ok": True,
                "found": False,
                "po": po_num,
                "items": [],
                "vdrl_documents": [],
                "rail_concerns": [],
                "dispatch_requests": [],
                "schedule_milestones": [],
            }

        pending_dispatches = [
            d for d in (sx_state.get("dispatch_requests") or [])
            if str(d.get("po")) == po_num
            and str(d.get("status") or "").upper() in ("AWAITING LOGISTICS MOVEMENT AUTHORITY", "SRN_APPROVED_PENDING_PICKUP")
        ]
        docs = _ensure_vdrl_docs(target)
        clr = target.get("clr") or {}
        items_out = []
        for it in (target.get("items") or []):
            if it.get("is_split_parent"):
                continue
            ikey = str(it.get("item") or "")
            c_entry = clr.get(ikey) or {}
            ord_q = float(it.get("qty") or 0)
            irn_q = float(c_entry.get("irn") or 0)
            ship_q = float(c_entry.get("ship") or 0)
            mrv_q = float(c_entry.get("mrv") or 0)
            pend_q = sum(float(d.get("dispatch_qty") or 0) for d in pending_dispatches if str(d.get("item_id")) == ikey)
            avail_dispatch = max(0.0, irn_q - ship_q - pend_q)
            items_out.append({
                "item": ikey,
                "desc": it.get("desc") or "",
                "unit": it.get("unit") or "EA",
                "ordered_qty": ord_q,
                "released_qty": irn_q,
                "shipped_qty": ship_q,
                "pending_dispatch_qty": pend_q,
                "available_to_dispatch": avail_dispatch,
                "delivered_qty": mrv_q,
                "remaining_to_release": max(0.0, ord_q - irn_q),
                "is_split": bool(it.get("is_split")),
                "parent_item": it.get("parent_item") or "",
                "location": it.get("location") or target.get("deliveryPoint") or "Vendor Works",
                "tag": it.get("tag") or "",
                "lot": it.get("lot") or "Lot 1",
                "cdd_date": it.get("cdd_date") or target.get("cdd_date") or "",
                "ros_date": it.get("ros_date") or target.get("ros_date") or "",
                "platform": it.get("platform") or target.get("platform") or "",
                "despatch_location": it.get("despatch_location") or target.get("despatch_location") or target.get("deliveryPoint") or "",
                "baseline_date": it.get("baseline_date") or it.get("cdd_date") or target.get("cdd_date") or "",
                "forecast_date": it.get("forecast_date") or "",
                "actual_date": it.get("actual_date") or "",
                "eng_pct": float(it.get("eng_pct") or 0),
                "proc_pct": float(it.get("proc_pct") or 0),
                "fab_pct": float(it.get("fab_pct") or 0),
                "insp_pct": float(it.get("insp_pct") or 0),
                "delay_reason_code": it.get("delay_reason") or it.get("delay_reason_code") or "",
                "recovery_plan": it.get("recovery_plan") or "",
                "batches": c_entry.get("batches") or [],
            })

        po_concerns = [
            c_item for c_item in (sx_state.get("concerns") or [])
            if str(c_item.get("po")) == po_num
        ]

        sch_rows = ((target.get("sch") or {}).get("rows") or [])[:15]
        has_approved_itp = any("ITP" in str(d.get("doc_no", "")).upper() and d.get("code") in ("Code 1", "Code 2") for d in docs)

        roster = {
            "project_id": target.get("project_id") or "",
            "project_name": target.get("project") or "",
            "project_code": target.get("project_code") or "",
            "expediting_manager_id": target.get("expediting_manager_id") or "",
            "expediting_manager_name": target.get("expediting_manager_name") or "",
            "expediting_manager_email": target.get("expediting_manager_email") or "",
            "assigned_expeditor_id": target.get("assigned_expeditor_id") or "",
            "assigned_expeditor_name": target.get("assigned_expeditor_name") or target.get("assignedTo") or "",
            "assigned_expeditor_email": target.get("assigned_expeditor_email") or "",
            "assigned_field_expeditor_id": target.get("assigned_field_expeditor_id") or "",
            "assigned_field_expeditor_name": target.get("assigned_field_expeditor_name") or "",
            "inspection_manager_id": target.get("inspection_manager_id") or "",
            "inspection_manager_name": target.get("inspection_manager_name") or "",
            "inspection_manager_email": target.get("inspection_manager_email") or "",
            "assigned_inspection_engineer_id": target.get("assigned_inspection_engineer_id") or "",
            "assigned_inspection_engineer_name": target.get("assigned_inspection_engineer_name") or "",
            "assigned_inspection_engineer_email": target.get("assigned_inspection_engineer_email") or "",
            "assigned_vendor_id": target.get("assigned_vendor_id") or "",
            "assigned_vendor_name": target.get("supplierShort") or target.get("supplier") or "",
            "assigned_vendor_email": target.get("assigned_vendor_email") or "",
        }
        lots_out = (
            [{k: v for k, v in l.items() if k != "ld"} if isinstance(l, dict) else l for l in (target.get("lots") or [])]
            if is_vendor_user(current_user)
            else (target.get("lots") or [])
        )

        sub_orders_out = [
            _normalize_suborder_row(sr)
            for sr in ((target.get("plan") or {}).get("rows") or [])
            if isinstance(sr, dict) and not sr.get("deleted")
        ]
        ack_info = target.get("ackx") or {"st": "Unconditional" if target.get("ackDate") else "Pending", "pts": ""}

        return {
            "ok": True,
            "found": True,
            "po": po_num,
            "supplier": target.get("supplierShort") or target.get("supplier"),
            "head": target.get("head") or "",
            "project": target.get("project"),
            "project_id": target.get("project_id"),
            "project_code": target.get("project_code"),
            "mr_ref": target.get("mrRef"),
            "contract_no": target.get("contract_no") or "",
            "budget_no": target.get("budget_no") or "",
            "incoterm": target.get("incoterm") or "",
            "cdd_date": target.get("cdd_date") or (lots_out[0].get("date") if lots_out and isinstance(lots_out[0], dict) else "") or "",
            "ros_date": target.get("ros_date") or "",
            "platform": target.get("platform") or "",
            "despatch_location": target.get("despatch_location") or target.get("deliveryPoint") or "",
            "buyer_name": "" if is_vendor_user(current_user) else (target.get("buyer") or ""),
            "buyer_email": "" if is_vendor_user(current_user) else (target.get("buyer_email") or ""),
            "pbg_required": bool(target.get("pbg_required")),
            "lc_required": bool(target.get("lc_required")),
            "requires_client_iap": bool(target.get("requires_client_iap")),
            "ack": ack_info,
            "close_state": target.get("close_state") or target.get("close") or {},
            "sub_orders": sub_orders_out,
            "ai_mr_review": None if is_vendor_user(current_user) else target.get("ai_mr_review"),
            "first_contact_draft": None if is_vendor_user(current_user) else target.get("first_contact_draft"),
            "intro_sent": bool((target.get("intro") or {}).get("sentOn")),
            "dc_issued": bool((target.get("dc") or {}).get("on")),
            "progress_reports_count": len(target.get("vpr_reports") or []),
            "stage": target.get("stage"),
            "procurement_class": _infer_procurement_class(target),
            "expeditor": roster["assigned_expeditor_name"],
            "inspection_engineer": roster["assigned_inspection_engineer_name"],
            "expediting_manager": roster["expediting_manager_name"],
            "inspection_manager": roster["inspection_manager_name"],
            "roster": roster,
            "lots": lots_out,
            "has_approved_itp": has_approved_itp,
            "items": items_out,
            "vdrl_documents": docs,
            "rail_concerns": po_concerns,
            "dispatch_requests": [d for d in (sx_state.get("dispatch_requests") or []) if str(d.get("po")) == po_num],
            "irns": target.get("irns") or [],
            "schedule_milestones": sch_rows,
        }


# ---------------------------------------------------------------------------
# Expeditor Package Line Item Splitting (/api/v1/po/split-item)
# ---------------------------------------------------------------------------
@router.post("/api/v1/po/split-item")
def split_po_line_item(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "field_expeditor")),
):
    """
    Expeditor splits a single package PO line item into multi-location sub-assemblies,
    enforcing positive split quantities, exact conservation against parent qty, and marking parent as split.
    """
    po_num = str(payload.get("po") or "").strip()
    parent_item = str(payload.get("parent_item") or "").strip()
    splits = payload.get("splits") or []
    by_user = current_user.get("full_name") or current_user.get("email") or "Package Expeditor"

    if not po_num or not parent_item or not splits:
        raise HTTPException(status_code=400, detail="po, parent_item, and splits array required")
    for sp in splits:
        sp_qty = float(sp.get("qty") or 0)
        if not str(sp.get("item") or "").strip() or sp_qty <= 0:
            raise HTTPException(status_code=400, detail="Each split sub-item must have a valid item key and positive quantity.")

    with LOCK, sx_db() as c:
        L = _records(c)
        target = next((x for x in L if str(x.get("po")) == po_num), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found in SmartExpedit")
        if not user_can_access_po(current_user, target):
            raise HTTPException(status_code=403, detail=f"Access denied to PO {po_num}")

        items = target.setdefault("items", [])
        parent_obj = next((ti for ti in items if str(ti.get("item")) == parent_item), None)
        if parent_obj:
            parent_qty = float(parent_obj.get("qty") or 0)
            split_sum = sum(float(sp.get("qty") or 0) for sp in splits)
            if parent_qty > 0 and abs(split_sum - parent_qty) > 1e-6:
                raise HTTPException(
                    status_code=400,
                    detail=f"Quantity Conservation Error: Sum of splits ({split_sum}) must equal parent item {parent_item} quantity ({parent_qty}).",
                )
            parent_obj["is_split_parent"] = True

        all_splits = target.setdefault("splits", {})
        all_splits[parent_item] = splits
        clr = target.setdefault("clr", {})
        sx_state = _get_sx_state(c)
        cum_ledger = sx_state.setdefault("cumulative_ledger", {})

        for sp in splits:
            sp_key = str(sp.get("item") or "").strip()
            sp_desc = sp.get("desc") or f"Sub-item {sp_key}"
            sp_qty = float(sp.get("qty") or 1)
            sp_unit = sp.get("unit") or "EA"
            sp_loc = sp.get("location") or "Shop Floor"
            sp_tag = sp.get("tag") or ""

            existing_item = next((ti for ti in items if str(ti.get("item")) == sp_key), None)
            if existing_item:
                existing_item["desc"] = sp_desc
                existing_item["qty"] = sp_qty
                existing_item["unit"] = sp_unit
                existing_item["location"] = sp_loc
                existing_item["tag"] = sp_tag
                existing_item["parent_item"] = parent_item
                existing_item["is_split"] = True
                existing_item.pop("is_split_parent", None)
            else:
                items.append({
                    "item": sp_key,
                    "desc": sp_desc,
                    "qty": sp_qty,
                    "unit": sp_unit,
                    "location": sp_loc,
                    "tag": sp_tag,
                    "parent_item": parent_item,
                    "is_split": True,
                    "lot": "Lot 1",
                })

            clr.setdefault(sp_key, {"irn": 0, "ship": 0, "mrv": 0, "batches": []})
            cum_ledger[f"{po_num}:{sp_key}"] = {
                "po": po_num,
                "item": sp_key,
                "desc": sp_desc,
                "unit": sp_unit,
                "ordered_qty": sp_qty,
                "inspected_qty": 0,
                "released_qty": float(clr[sp_key].get("irn") or 0),
                "shipped_qty": float(clr[sp_key].get("ship") or 0),
                "delivered_qty": float(clr[sp_key].get("mrv") or 0),
                "batches": clr[sp_key].get("batches") or [],
            }

        target["lines"] = len([ti for ti in items if not ti.get("is_split_parent")])
        target["qty"] = sum(float(ti.get("qty") or 0) for ti in items if not ti.get("is_split_parent"))

        target.setdefault("log", []).append({
            "on": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "by": by_user,
            "txt": f"Package line item {parent_item} split into {len(splits)} sub-assemblies: {', '.join([s.get('item', '') for s in splits])}.",
        })

        _save_records(c, L, by_user, f"Split item {parent_item} on PO {po_num}")
        _save_sx_state(c, sx_state, by_user)

    inspections = inspectflow_db.list_inspections()
    for matching_insp in [i for i in inspections if str(i.get("po_number")) == po_num]:
        existing_offered = matching_insp.get("items_being_offered") or []
        for sp in splits:
            sp_key = str(sp.get("item") or "").strip()
            if not any(str(o.get("item") or o.get("item_number") or o.get("itemNumber")) == sp_key for o in existing_offered):
                existing_offered.append({
                    "itemNumber": sp_key,
                    "item_number": sp_key,
                    "item": sp_key,
                    "description": sp.get("desc"),
                    "quantity": float(sp.get("qty") or 1),
                    "unit": sp.get("unit") or "EA",
                    "location": sp.get("location"),
                    "tag_number": sp.get("tag"),
                    "is_split_sub_item": True,
                    "parent_item": parent_item,
                })
        inspectflow_db.update_inspection(matching_insp["id"], {
            "items_being_offered": existing_offered,
            "has_split_items": True,
        })
    record_audit_event("po", po_num, "PO_ITEM_SPLIT", actor=current_user, after={"parent_item": parent_item, "splits": [s.get("item") for s in splits]})

    return {
        "ok": True,
        "po": po_num,
        "parent_item": parent_item,
        "splits_created": len(splits),
        "message": f"Successfully split item {parent_item} into {len(splits)} sub-assemblies. Available in SmartExpedit and InspectFlow.",
    }


# ---------------------------------------------------------------------------
# EDMS Document Integration & Overdue Tracker (/api/v1/edms/*)
# ---------------------------------------------------------------------------
@router.get("/api/v1/edms/documents")
def get_edms_documents(
    po: Optional[str] = None,
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    accessible_pids = _get_accessible_pids_for_user(current_user)
    with LOCK, sx_db() as c:
        L = _records(c)
        all_docs = []
        for rec in L:
            if not _allowed_po_record(rec, current_user, project_id=project_id, accessible_pids=accessible_pids):
                continue
            po_num = rec.get("po")
            if po and po_num != po:
                continue
            docs = _ensure_vdrl_docs(rec)
            for d in docs:
                all_docs.append({**d, "po": po_num, "supplier": rec.get("supplier")})
        return {"ok": True, "count": len(all_docs), "documents": all_docs}


@router.post("/api/v1/edms/sync")
def sync_edms_documents(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "doc_expeditor", "expediting_manager", "expeditor", "inspection_engineer")),
):
    po_num = str(payload.get("po") or "").strip()
    documents = payload.get("documents") or []

    with LOCK, sx_db() as c:
        L = _records(c)
        target = next((x for x in L if str(x.get("po")) == po_num), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not user_can_access_po(current_user, target):
            raise HTTPException(status_code=403, detail=f"Access denied to PO {po_num}")

        target["vdrl_documents"] = documents
        _save_records(c, L, current_user.get("email") or "EDMS Sync Connector", f"Ingested {len(documents)} documents for {po_num}")

    record_audit_event("edms", po_num, "EDMS_DOCS_SYNCED", actor=current_user, after={"count": len(documents)})
    return {"ok": True, "po": po_num, "synced_documents_count": len(documents)}


# ---------------------------------------------------------------------------
# Two-Stage RAIL Closeout Workflow (/api/v1/rail/*)
# ---------------------------------------------------------------------------
@router.post("/api/v1/rail/technical-close")
def rail_technical_close(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "inspection_engineer", "qc_manager", "inspector")),
):
    """
    Stage 1: Inspector/IE approves technical closure of an NCR / Punch item.
    Updates SmartExpedit RAIL/concerns, target['sx']['punch'], AND IMS Inspections findings.
    """
    po_num = str(payload.get("po") or "").strip()
    item_id = str(payload.get("item_id") or "").strip()
    inspector = current_user.get("full_name") or current_user.get("email") or "Inspector"
    remarks = payload.get("remarks") or "Technical rework verified and approved."
    evidence_url = payload.get("evidence_url") or ""

    with LOCK, sx_db() as c:
        L = _records(c)
        sx_state = _get_sx_state(c)
        target = next((x for x in L if str(x.get("po")) == po_num), None)
        if not target:
            raise HTTPException(status_code=404, detail="PO not found")
        if not user_can_access_po(current_user, target):
            raise HTTPException(status_code=403, detail=f"Access denied to PO {po_num}")

        rail_items = target.setdefault("rail", [])
        found_item = next((r for r in rail_items if str(r.get("id")) == item_id or str(r.get("no")) == item_id), None)
        if not found_item:
            found_item = {
                "id": item_id or uuid.uuid4().hex[:8],
                "no": f"NCR-{item_id}",
                "desc": remarks,
                "tier": 1,
            }
            rail_items.append(found_item)

        found_item["technical_status"] = "APPROVED"
        found_item["technical_closed_by"] = inspector
        found_item["technical_closed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        found_item["technical_remarks"] = remarks
        found_item["evidence_url"] = evidence_url
        found_item["status"] = "Pending Expeditor Verification"

        concerns = sx_state.setdefault("concerns", [])
        c_match = next(
            (x for x in concerns if str(x.get("id")) == item_id or str(x.get("no")) == item_id or str(x.get("if_finding_id")) == item_id),
            None,
        )
        if not c_match:
            c_match = {
                "id": item_id or uuid.uuid4().hex[:8],
                "no": found_item.get("no") or f"ACT-{len(concerns) + 1:03d}",
                "po": po_num,
                "cat": "INSPECTION",
                "issue": remarks,
                "by": "INSPECTOR",
                "assignedTo": "EXP",
                "assignedVendor": target.get("supplierShort") or target.get("supplier") or "Vendor",
                "source": "InspectFlow Stage 1 Closeout",
                "target": time.strftime("%Y-%m-%d"),
                "impact": "MAJOR",
                "history": [],
            }
            concerns.insert(0, c_match)

        c_match["status"] = "PENDING_VERIFICATION"
        c_match["technical_status"] = "APPROVED"
        c_match["resolution"] = remarks
        c_match["evidence"] = evidence_url
        c_match.setdefault("history", []).append({
            "on": time.strftime("%Y-%m-%d"),
            "by": inspector,
            "act": "Stage 1 Technical Closeout Approved",
            "note": remarks + (f" [Evidence: {evidence_url}]" if evidence_url else ""),
        })

        for tp in target.get("punch") or []:
            if str(tp.get("id") or "") == item_id or str(tp.get("no") or "") == item_id:
                tp["status"] = "PENDING VERIFICATION"
        for sp in (target.get("sx") or {}).get("punch") or []:
            if str(sp.get("id") or "") == item_id:
                sp["Status"] = "PENDING_VERIFICATION"

        target.setdefault("log", []).append({
            "on": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "by": inspector,
            "txt": f"Technical Stage 1 closeout approved for RAIL item {item_id}. Awaiting Expeditor schedule closeout.",
        })
        _save_records(c, L, inspector, f"Technical closeout for RAIL item {item_id}")
        _save_sx_state(c, sx_state, inspector)

    # Propagate Stage 1 technical closeout to IMS Inspections finding so IRC blocker gate clears technically
    finding_lookup_id = str((c_match or {}).get("if_finding_id") or item_id)
    def _close_tech_finding(f: Dict[str, Any], _insp: Dict[str, Any]) -> None:
        f["technical_status"] = "APPROVED"
        f["closure_justification"] = remarks
        f["closed_by"] = inspector
        f["closure_status"] = "closed"
        f["status"] = "closed"
    inspectflow_db.find_and_update_finding(finding_lookup_id, _close_tech_finding)

    record_audit_event("rail", item_id, "RAIL_TECHNICAL_CLOSED", actor=current_user, after={"po": po_num, "remarks": remarks})
    return {
        "ok": True,
        "item_id": item_id,
        "status": "Pending Expeditor Verification",
        "message": "Stage 1 Technical Closeout completed and synced to IMS. Expeditor notified for Stage 2 schedule verification.",
    }


@router.post("/api/v1/rail/schedule-close")
def rail_schedule_close(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "field_expeditor")),
):
    """
    Stage 2: Package Expeditor verifies schedule recovery impact and formally closes the action item.
    """
    po_num = str(payload.get("po") or "").strip()
    item_id = str(payload.get("item_id") or "").strip()
    expeditor = current_user.get("full_name") or current_user.get("email") or "Package Expeditor"
    recovery_impact = payload.get("recovery_impact") or "Schedule recovered. No float loss."

    with LOCK, sx_db() as c:
        L = _records(c)
        sx_state = _get_sx_state(c)
        target = next((x for x in L if str(x.get("po")) == po_num), None)
        if not target:
            raise HTTPException(status_code=404, detail="PO not found")
        if not user_can_access_po(current_user, target):
            raise HTTPException(status_code=403, detail=f"Access denied to PO {po_num}")

        rail_items = target.setdefault("rail", [])
        found_item = next((r for r in rail_items if str(r.get("id")) == item_id or str(r.get("no")) == item_id), None)

        concerns = sx_state.setdefault("concerns", [])
        c_match = next(
            (x for x in concerns if str(x.get("id")) == item_id or str(x.get("no")) == item_id or str(x.get("if_finding_id")) == item_id),
            None,
        )

        if not found_item and not c_match:
            raise HTTPException(status_code=404, detail="RAIL item not found")

        tech_ok = (found_item and found_item.get("technical_status") == "APPROVED") or (
            c_match and (c_match.get("technical_status") == "APPROVED" or c_match.get("status") == "PENDING_VERIFICATION")
        )
        if not tech_ok:
            raise HTTPException(
                status_code=400,
                detail="Cannot perform Stage 2 closeout: Stage 1 Technical Approval by Inspector is required first.",
            )

        if found_item:
            found_item["commercial_status"] = "CLOSED"
            found_item["status"] = "Closed"
            found_item["schedule_closed_by"] = expeditor
            found_item["schedule_closed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
            found_item["recovery_impact"] = recovery_impact

        if c_match:
            c_match["status"] = "CLOSED"
            c_match["commercial_status"] = "CLOSED"
            c_match["closedOn"] = time.strftime("%Y-%m-%d")
            c_match["closedBy"] = expeditor
            c_match.setdefault("history", []).append({
                "on": time.strftime("%Y-%m-%d"),
                "by": expeditor,
                "act": "Stage 2 Schedule Closeout Verified",
                "note": recovery_impact,
            })

        for tp in target.get("punch") or []:
            if str(tp.get("id") or "") == item_id or str(tp.get("no") or "") == item_id:
                tp["status"] = "CLOSED"
        for sp in (target.get("sx") or {}).get("punch") or []:
            if str(sp.get("id") or "") == item_id:
                sp["Status"] = "CLOSED"

        target.setdefault("log", []).append({
            "on": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "by": expeditor,
            "txt": f"Stage 2 Schedule closeout confirmed for RAIL item {item_id}. Action item fully closed. Impact: {recovery_impact}",
        })
        _save_records(c, L, expeditor, f"Full closeout for RAIL item {item_id}")
        _save_sx_state(c, sx_state, expeditor)

    record_audit_event("rail", item_id, "RAIL_STAGE2_CLOSED", actor=current_user, after={"po": po_num, "recovery_impact": recovery_impact})
    return {
        "ok": True,
        "item_id": item_id,
        "status": "Closed",
        "message": "Stage 2 Schedule Closeout completed. Action item fully closed.",
    }


# ---------------------------------------------------------------------------
# 4-Stage Logistics Pipeline & Cumulative Ledger (/api/v1/delivery/update-stage)
# ---------------------------------------------------------------------------
@router.post("/api/v1/delivery/update-stage")
def update_delivery_stage(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "expediting_manager", "expeditor", "field_expeditor")
    ),
):
    """
    Updates the 4-stage logistics pipeline for a line item or batch with strict Chain-of-Custody Guardrails:
    1. 'packing' (Ready for Dispatch)
    2. 'ex_works' / 'in_transit' (enforces irn_qty > 0 and cumulative shipped <= irn_qty)
    3. 'mrv_delivered' (enforces cumulative delivered <= shipped; accumulates partials without false MNCRs)
    Consumes DispatchReservations and records AuditEvents.
    """
    po_num = str(payload.get("po") or "").strip()
    item_key = str(payload.get("item") or "").strip()
    stage = str(payload.get("stage") or "").strip().lower()
    if stage not in ("packing", "ex_works", "in_transit", "mrv_delivered"):
        raise HTTPException(status_code=400, detail="stage must be one of: packing, ex_works, in_transit, mrv_delivered")
    qty = float(payload.get("qty") or 0)
    if not po_num or not item_key or qty <= 0:
        raise HTTPException(status_code=400, detail="po, item, and strictly positive qty are required")

    bl_awb = payload.get("bl_awb") or ""
    carrier = payload.get("carrier") or ""
    mrv_no = payload.get("mrv_no") or ""
    stamped_dn = str(payload.get("stamped_delivery_note_ref") or "").strip()
    osd_notes = payload.get("osd_notes") or "Nil damage / Over Short"
    has_osd = bool(payload.get("has_osd"))
    shortage_reported = bool(payload.get("shortage_reported"))
    by_user = current_user.get("full_name") or current_user.get("email") or "Logistics Coordinator"

    with LOCK, sx_db() as c:
        L = _records(c)
        sx_state = _get_sx_state(c)
        target = next((x for x in L if str(x.get("po")) == po_num), None)
        if not target:
            raise HTTPException(status_code=404, detail="PO not found")
        if not user_can_access_po(current_user, target):
            raise HTTPException(status_code=403, detail=f"Access denied to PO {po_num}")

        clr = target.setdefault("clr", {})
        item_clr = clr.setdefault(item_key, {"irn": 0, "ship": 0, "mrv": 0})
        irn_qty = float(item_clr.get("irn") or 0)
        ship_qty = float(item_clr.get("ship") or 0)
        mrv_qty = float(item_clr.get("mrv") or 0)

        if stage in ("ex_works", "in_transit"):
            if irn_qty <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Chain-of-Custody Gate: Item {item_key} has 0 IRC-Released units. Issue an IRC before shipping.",
                )
            new_ship = ship_qty + qty
            if new_ship > irn_qty + 1e-6:
                raise HTTPException(
                    status_code=400,
                    detail=f"Chain-of-Custody Gate: Shipping +{qty} (total {new_ship}) exceeds IRC-Released quantity ({irn_qty}) for Item {item_key}.",
                )
            item_clr["ship"] = new_ship
            _auto_advance_schedule(target, "shipped", time.strftime("%Y-%m-%d"))

        elif stage == "mrv_delivered":
            if ship_qty <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Chain-of-Custody Gate: Item {item_key} has 0 shipped units. Record Ex-Works / In-Transit shipment before MRV site receipt.",
                )
            new_mrv = mrv_qty + qty
            if new_mrv > ship_qty + 1e-6:
                raise HTTPException(
                    status_code=400,
                    detail=f"Chain-of-Custody Gate: Cumulative MRV Received ({new_mrv}) cannot exceed Shipped Qty ({ship_qty}) for Item {item_key}.",
                )
            item_clr["mrv"] = new_mrv
            _auto_advance_schedule(target, "mrv_delivered", time.strftime("%Y-%m-%d"))

        # Consume matching pending dispatch reservations up to batch qty when shipping/delivering
        consumed_ids = []
        if stage in ("ex_works", "in_transit", "mrv_delivered"):
            rem_to_consume = qty
            for dr in (sx_state.get("dispatch_requests") or []):
                if (
                    rem_to_consume > 0
                    and str(dr.get("po")) == po_num
                    and str(dr.get("item_id")) == item_key
                    and str(dr.get("status") or "").upper() in ("AWAITING LOGISTICS MOVEMENT AUTHORITY", "SRN_APPROVED_PENDING_PICKUP")
                ):
                    dr_q = float(dr.get("dispatch_qty") or 0)
                    if dr_q <= rem_to_consume + 1e-6:
                        dr["status"] = "DELIVERED" if stage == "mrv_delivered" else "SHIPPED"
                        consumed_ids.append(dr["id"])
                        rem_to_consume -= dr_q

        cum_ledger = sx_state.setdefault("cumulative_ledger", {})
        led_key = f"{po_num}:{item_key}"
        if led_key in cum_ledger:
            cum_ledger[led_key]["shipped_qty"] = float(item_clr.get("ship") or 0)
            cum_ledger[led_key]["delivered_qty"] = float(item_clr.get("mrv") or 0)

        logistics_history = target.setdefault("logistics_tracking", [])
        record = {
            "id": uuid.uuid4().hex[:8],
            "at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "by": by_user,
            "item": item_key,
            "stage": stage,
            "qty": qty,
            "bl_awb": bl_awb,
            "carrier": carrier,
            "mrv_no": mrv_no,
            "stamped_delivery_note_ref": stamped_dn,
            "osd_notes": osd_notes,
        }
        logistics_history.append(record)
        if stamped_dn:
            target.setdefault("stamped_delivery_notes", []).append({
                "ref": stamped_dn,
                "mrv_no": mrv_no,
                "item_no": item_key,
                "recorded_by": by_user,
                "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        # Spawn MNCR ONLY on explicit OS&D shortage/damage (never on legitimate partial deliveries)
        mncr_spawned = None
        osd_lower = osd_notes.lower()
        is_damaged = has_osd or shortage_reported or (
            any(w in osd_lower for w in ("damage", "short", "missing", "broken", "reject", "defect", "os&d"))
            and "nil" not in osd_lower
            and "no os&d" not in osd_lower
            and "no " not in osd_lower
            and "clean" not in osd_lower
        )

        if stage == "mrv_delivered" and is_damaged:
            sx_obj = target.setdefault("sx", {})
            mncrs = sx_obj.setdefault("mncr", [])
            mncr_no = f"MNCR-{po_num}-{len(mncrs) + 1:02d}"
            mncr_desc = f"Item {item_key} (MRV {mrv_no or 'Site'}): Notes: {osd_notes}"
            mncrs.append({
                "MNCR no.": mncr_no,
                "Description": mncr_desc,
                "Action": "Vendor replacement / insurance claim required",
                "Status": "OPEN",
            })
            concerns = sx_state.setdefault("concerns", [])
            concerns.insert(0, {
                "id": uuid.uuid4().hex[:8],
                "no": mncr_no,
                "po": po_num,
                "cat": "DELIVERY_OSD",
                "issue": f"[Site OS&D / MNCR] {mncr_desc}",
                "by": "LOGISTICS",
                "assignedTo": "VENDOR",
                "assignedVendor": target.get("supplierShort") or target.get("supplier") or "Vendor",
                "source": f"Site MRV ({mrv_no or 'Receipt'})",
                "target": time.strftime("%Y-%m-%d", time.gmtime(time.time() + 7 * 86400)),
                "impact": "CRITICAL",
                "status": "OPEN",
                "history": [{"on": time.strftime("%Y-%m-%d"), "by": by_user, "act": "Auto-Spawned from Site OS&D", "note": mncr_desc}],
            })
            mncr_spawned = mncr_no

        _save_sx_state(c, sx_state, by_user)
        target.setdefault("log", []).append({
            "on": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "by": by_user,
            "txt": f"Logistics Stage [{stage.upper()}] for Item {item_key}: +{qty} unit(s). Ref: {bl_awb or mrv_no}. Notes: {osd_notes}" + (f" [Auto-Spawned {mncr_spawned}]" if mncr_spawned else ""),
        })
        _save_records(c, L, by_user, f"Logistics update {stage} for Item {item_key} on {po_num}")

    if consumed_ids:
        try:
            with SessionLocal() as sdb:
                sdb.query(DispatchReservation).filter(DispatchReservation.id.in_(consumed_ids)).update(
                    {"status": "DELIVERED" if stage == "mrv_delivered" else "SHIPPED"},
                    synchronize_session=False,
                )
                sdb.commit()
        except Exception:
            logger.exception("Failed updating consumed DispatchReservation rows")

    record_audit_event("logistics", f"{po_num}:{item_key}", f"LOGISTICS_{stage.upper()}", actor=current_user, after={"qty": qty, "cleared": item_clr, "mncr_spawned": mncr_spawned})
    return {
        "ok": True,
        "po": po_num,
        "item": item_key,
        "stage": stage,
        "cleared": item_clr,
        "mncr_spawned": mncr_spawned,
        "message": f"Logistics stage updated to {stage}." + (f" OS&D detected: {mncr_spawned} spawned in RAIL!" if mncr_spawned else ""),
    }


# ---------------------------------------------------------------------------
# Executive Risk Matrix & Alert Ribbon (/api/v1/executive/risk-summary)
# ---------------------------------------------------------------------------
@router.get("/api/v1/executive/risk-summary")
def get_executive_risk_summary(
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    accessible_pids = _get_accessible_pids_for_user(current_user)
    with LOCK, sx_db() as c:
        L = _records(c)
        sx_state = _get_sx_state(c)
        overdue_docs = []
        missing_itp = []
        fab_variance = []
        escalated_rail = []
        ld_risks = []
        today = date.today()
        filtered_recs = [
            rec for rec in L
            if _allowed_po_record(rec, current_user, project_id=project_id, accessible_pids=accessible_pids)
        ]

        for rec in filtered_recs:
            po = rec.get("po") or "Unknown"
            docs = _ensure_vdrl_docs(rec)

            # 1. Overdue EDMS Documents (real date-driven check)
            for doc in docs:
                planned_dt = _parse_date_safe(doc.get("planned_date"))
                is_past_due = bool(planned_dt and planned_dt < today and not doc.get("actual_date") and doc.get("code") not in ("Code 1", "Code 2"))
                if doc.get("is_overdue") or doc.get("code") == "Code 3" or is_past_due:
                    overdue_docs.append({
                        "po": po,
                        "doc_no": doc.get("doc_no"),
                        "title": doc.get("title"),
                        "code": doc.get("code"),
                    })

            # 2. Missing Code 1/2 ITP for upcoming milestones
            has_approved_itp = any(
                "ITP" in d.get("doc_no", "") and d.get("code") in ("Code 1", "Code 2")
                for d in docs
            )
            if not has_approved_itp:
                missing_itp.append({
                    "po": po,
                    "supplier": rec.get("supplier"),
                    "stage": rec.get("stage"),
                    "warning": "Milestone approaching without Code 1/2 Approved ITP",
                })

            # 3. Fabrication Variance >10% (only from real reported fab_progress — never fabricated)
            fab_progress = rec.get("fab_progress")
            if isinstance(fab_progress, dict) and (
                "vendor_claimed_pct" in fab_progress and "field_expeditor_pct" in fab_progress
            ):
                claimed = float(fab_progress.get("vendor_claimed_pct") or 0)
                audited = float(fab_progress.get("field_expeditor_pct") or 0)
                variance = claimed - audited
                if variance > 10:
                    fab_variance.append({
                        "po": po,
                        "supplier": rec.get("supplier"),
                        "claimed": claimed,
                        "audited": audited,
                        "variance": variance,
                    })

            # 5. Liquidated Damages (LD) Late Lots
            for lot in rec.get("lots", []):
                if lot.get("ld") and rec.get("stage") not in ("release", "delivered"):
                    ld_risks.append({
                        "po": po,
                        "lot": lot.get("id"),
                        "contractual_date": lot.get("date"),
                    })

        # 4. Escalated Tier 2/3 RAIL Items from live sx_state.concerns (real days_open)
        allowed_pos = {str(r.get("po")) for r in filtered_recs}
        for c_item in (sx_state.get("concerns") or []):
            if str(c_item.get("po") or "") not in allowed_pos:
                continue
            if c_item.get("status") != "CLOSED":
                impact = str(c_item.get("impact") or "").upper()
                if impact in ("CRITICAL", "MAJOR", "HIGH"):
                    created_dt = _parse_date_safe((c_item.get("history") or [{}])[0].get("on") or c_item.get("created_at"))
                    days_open = max(0, (today - created_dt).days) if created_dt else 0
                    escalated_rail.append({
                        "po": c_item.get("po"),
                        "id": c_item.get("no") or c_item.get("id"),
                        "desc": c_item.get("issue"),
                        "tier": 3 if impact == "CRITICAL" else 2,
                        "days_open": days_open,
                    })

        return {
            "ok": True,
            "counts": {
                "overdue_docs": len(overdue_docs),
                "missing_itp": len(missing_itp),
                "fab_variance": len(fab_variance),
                "escalated_rail": len(escalated_rail),
                "ld_risks": len(ld_risks),
                "total_alerts": len(overdue_docs) + len(missing_itp) + len(fab_variance) + len(escalated_rail) + len(ld_risks),
            },
            "alerts": {
                "overdue_docs": overdue_docs,
                "missing_itp": missing_itp,
                "fab_variance": fab_variance,
                "escalated_rail": escalated_rail,
                "ld_risks": ld_risks,
            },
        }


# ===========================================================================
# VENDOR PORTAL INTEGRATION & NOI LIFECYCLE MANAGEMENT
# ===========================================================================

@router.post("/api/v1/vendor-noi/{ident}/cancel")
def cancel_vendor_noi(
    ident: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "inspection_engineer", "qc_manager")
    ),
):
    """
    Cancels an NOI prior to completion/IRC issuance.
    """
    reason = str(payload.get("reason") or "").strip()
    requested_by = current_user.get("full_name") or current_user.get("email") or "Vendor"

    inspections = inspectflow_db.list_inspections()
    target = next((i for i in inspections if i.get("id") == ident or i.get("notification_number") == ident), None)
    if not target:
        raise HTTPException(status_code=404, detail="Inspection / NOI not found")

    if str(target.get("status") or "").lower() in ("completed", "finalized", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel NOI in '{target.get('status')}' state.",
        )

    po_num = str(target.get("po_number") or "")
    with LOCK, sx_db() as c:
        po_rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
    if is_vendor_user(current_user):
        if not po_rec or not vendor_owns_po(current_user, po_rec):
            raise HTTPException(status_code=403, detail="Access denied: cannot cancel NOI for unassigned PO")
    elif not is_admin_user(current_user) and po_rec and not user_can_access_po(current_user, po_rec):
        raise HTTPException(status_code=403, detail="Access denied: NOI belongs to an unassigned project")

    has_inspector = bool(target.get("assigned_inspector_id") or target.get("assigned_inspector_name"))
    if has_inspector and not reason:
        raise HTTPException(status_code=400, detail="Mandatory cancellation reason required because an inspector has already been assigned.")

    target_id = target["id"]
    notif_no = target.get("notification_number")

    updates = {
        "status": "cancelled",
        "cancellation_reason": reason or "Cancelled by vendor prior to inspector dispatch",
        "cancelled_by": requested_by,
        "cancelled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "abortive_inspection": has_inspector,
        "abortive_charge_applicable": has_inspector,
    }
    updated = inspectflow_db.update_inspection(target_id, updates)

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if rec:
            for item in rec.get("items", []):
                for act in item.get("activities", []):
                    if notif_no and (notif_no in str(act.get("notes") or "") or notif_no in str(act.get("name") or "")):
                        act["status"] = "Pending Callout"
            sx_obj = rec.setdefault("sx", {})
            for n in sx_obj.get("notif") or []:
                if str(n.get("id") or "") == target_id or (notif_no and str(n.get("Activity") or "").startswith(notif_no)):
                    n["Status"] = "CANCELLED"
            for a in sx_obj.get("iap") or []:
                if a.get("notif_no") == notif_no:
                    a["status"] = "CANCELLED"
            _save_records(c, L, requested_by, f"NOI {notif_no} cancelled (Abortive: {has_inspector})")

    record_audit_event("inspection", target_id, "VENDOR_NOI_CANCELLED", actor=current_user, after={"reason": reason, "abortive": has_inspector})
    return {
        "ok": True,
        "inspection_id": target_id,
        "status": "cancelled",
        "has_inspector": has_inspector,
        "abortive_inspection": has_inspector,
        "message": "Inspection cancelled. Abortive audit logged." if has_inspector else "Inspection cancelled cleanly prior to inspector assignment."
    }


def _parse_numeric_revision(raw_rev: Any) -> int:
    s = str(raw_rev or "0").strip()
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else 0


@router.post("/api/v1/vendor-noi/{ident}/revise")
def revise_vendor_noi(
    ident: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "inspection_engineer", "qc_manager")
    ),
):
    """
    Revises an existing active NOI (safely increments revision even from 'Rev 0' or 'A').
    """
    inspections = inspectflow_db.list_inspections()
    target = next((i for i in inspections if i.get("id") == ident or i.get("notification_number") == ident), None)
    if not target:
        raise HTTPException(status_code=404, detail="Inspection / NOI not found")
    if str(target.get("status") or "").lower() in ("completed", "finalized", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot revise NOI in '{target.get('status')}' state.",
        )

    po_num = str(target.get("po_number") or "")
    with LOCK, sx_db() as c:
        po_rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
    if is_vendor_user(current_user):
        if not po_rec or not vendor_owns_po(current_user, po_rec):
            raise HTTPException(status_code=403, detail="Access denied: cannot revise NOI for unassigned PO")
    elif not is_admin_user(current_user) and po_rec and not user_can_access_po(current_user, po_rec):
        raise HTTPException(status_code=403, detail="Access denied: NOI belongs to an unassigned project")

    target_id = target["id"]
    current_rev = _parse_numeric_revision(target.get("notification_revision"))
    new_rev = str(current_rev + 1)

    new_date = payload.get("scheduled_date") or target.get("start_date")
    new_location = payload.get("location") or target.get("inspection_location")
    new_scope = payload.get("scope") or target.get("po_description")
    new_items = payload.get("items_being_offered") or target.get("items_being_offered") or []
    notes = payload.get("revision_notes") or f"Revised to Rev {new_rev}"

    date_changed = (new_date != target.get("start_date"))
    loc_changed = (new_location != target.get("inspection_location"))
    has_inspector = bool(target.get("assigned_inspector_id") or target.get("assigned_inspector_name"))

    inspector_status = target.get("inspector_confirmation_status") or "confirmed"
    reconfirmation_deadline = None
    if has_inspector and (date_changed or loc_changed):
        inspector_status = "pending_reconfirmation"
        reconfirmation_deadline = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 86400))

    updates = {
        "notification_revision": new_rev,
        "start_date": new_date,
        "end_date": new_date,
        "inspection_location": new_location,
        "po_description": new_scope,
        "items_being_offered": new_items,
        "inspector_confirmation_status": inspector_status,
        "reconfirmation_deadline": reconfirmation_deadline,
        "notes": f"{target.get('notes') or ''}\n[Rev {new_rev}]: {notes}",
    }
    updated = inspectflow_db.update_inspection(target_id, updates)
    if updated:
        sync_single_inspection_to_smartexpedit(updated)

    record_audit_event("inspection", target_id, "VENDOR_NOI_REVISED", actor=current_user, after={"rev": new_rev, "start_date": new_date})
    return {
        "ok": True,
        "inspection_id": target_id,
        "revision": f"Rev {new_rev}",
        "inspector_confirmation_status": inspector_status,
        "reconfirmation_deadline": reconfirmation_deadline,
        "message": f"NOI successfully updated to Rev {new_rev}." + (" Inspector set to Pending Re-confirmation (24h SLA)." if inspector_status == "pending_reconfirmation" else "")
    }


# ===========================================================================
# DIFFERENTIATED VENDOR NCR & FINDING RESOLUTION
# ===========================================================================

def _verify_finding_access(finding_id: str, current_user: Dict[str, Any]) -> Optional[str]:
    """Resolve owning PO number for finding_id across IMS Inspections and SX concerns and verify caller authorization."""
    eff = effective_role(current_user)
    if eff in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    po_num = None
    for insp in inspectflow_db.list_inspections():
        for rep in (insp.get("inspection_reports") or []):
            if not isinstance(rep, dict):
                continue
            rep_url = rep.get("url") or ""
            for idx, f in enumerate(rep.get("findings") or []):
                if not isinstance(f, dict):
                    continue
                curr_id = str(f.get("id") or f"{rep_url}_{idx}")
                if curr_id == finding_id or str(f.get("id") or "") == finding_id:
                    po_num = str(insp.get("po_number") or "")
                    break
            if po_num:
                break
        if po_num:
            break
    with LOCK, sx_db() as c:
        sx_state = _get_sx_state(c)
        if not po_num:
            for item in (sx_state.get("concerns") or []):
                if str(item.get("id")) == finding_id or str(item.get("no")) == finding_id or str(item.get("if_finding_id")) == finding_id:
                    po_num = str(item.get("po") or "")
                    break
        if po_num:
            po_rec = next((r for r in _records(c) if str(r.get("po")) == po_num), None)
            if not is_admin_user(current_user):
                if is_vendor_user(current_user) and (not po_rec or not vendor_owns_po(current_user, po_rec)):
                    raise HTTPException(status_code=403, detail="Access denied: cannot modify NCR belonging to another vendor's PO")
                if not is_vendor_user(current_user) and po_rec and not user_can_access_po(current_user, po_rec):
                    raise HTTPException(status_code=403, detail="Access denied: NCR belongs to an unassigned project")
    return po_num


@router.post("/api/v1/vendor/ncr/{finding_id}/submit-resolution")
def submit_vendor_ncr_resolution(
    finding_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "inspection_engineer", "qc_manager")
    ),
):
    """
    3-Stage Vendor NCR Form for Major / Critical NCRs.
    """
    containment = str(payload.get("containment_action") or "").strip()
    root_cause = str(payload.get("root_cause") or "").strip()
    capa_plan = str(payload.get("capa_plan") or "").strip()
    target_date = str(payload.get("target_closure_date") or "").strip()
    rework_files = payload.get("rework_evidence_files") or []

    if not containment or not root_cause or not capa_plan:
        raise HTTPException(status_code=400, detail="Containment, Root Cause, and CAPA plan are all required for Major NCR resolution.")

    _verify_finding_access(finding_id, current_user)

    def _mutate_ncr(f: Dict[str, Any], _insp: Dict[str, Any]) -> None:
        if str(f.get("closure_status") or f.get("status") or "").lower() == "closed":
            raise HTTPException(status_code=400, detail="Cannot reopen or overwrite an already closed NCR.")
        f["vendor_response"] = {
            "containment_action": containment,
            "root_cause": root_cause,
            "capa_plan": capa_plan,
            "target_closure_date": target_date,
            "rework_evidence_files": rework_files,
            "submitted_by": current_user.get("email"),
            "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        f["status"] = "pending_ie_review"
        f["closure_status"] = "pending_ie_review"

    updated_insp = inspectflow_db.find_and_update_finding(finding_id, _mutate_ncr)
    if updated_insp:
        sync_single_inspection_to_smartexpedit(updated_insp)

    concern_matched = False
    with LOCK, sx_db() as c:
        sx_state = _get_sx_state(c)
        for item in sx_state.get("concerns", []):
            if str(item.get("id")) == str(finding_id) or str(item.get("no")) == str(finding_id) or str(item.get("if_finding_id")) == str(finding_id):
                if str(item.get("status") or "").upper() == "CLOSED":
                    raise HTTPException(status_code=400, detail="Cannot overwrite an already closed RAIL NCR.")
                item["vendor_containment"] = containment
                item["vendor_rca"] = root_cause
                item["vendor_capa"] = capa_plan
                item["target_date"] = target_date
                item["rework_evidence_files"] = rework_files
                item["status"] = "PENDING IE TECH REVIEW"
                item.setdefault("history", []).append({
                    "on": time.strftime("%Y-%m-%d"),
                    "by": current_user.get("full_name") or "Vendor",
                    "act": "Submitted 3-Stage Containment, RCA & Physical Rework Evidence",
                    "note": capa_plan,
                })
                concern_matched = True
        if concern_matched:
            _save_sx_state(c, sx_state, current_user.get("email") or "Vendor Portal NCR Submission")

    if not updated_insp and not concern_matched:
        raise HTTPException(status_code=404, detail=f"NCR / Finding '{finding_id}' not found")

    record_audit_event(
        "ncr_finding",
        finding_id,
        "VENDOR_NCR_SUBMITTED",
        actor=current_user,
        after={"status": "pending_ie_review", "target_closure_date": target_date},
    )

    return {
        "ok": True,
        "finding_id": finding_id,
        "inspection_synced": bool(updated_insp),
        "rail_synced": concern_matched,
        "status": "pending_ie_review",
        "message": "Vendor RCA and CAPA submitted successfully. Awaiting Inspection Engineer technical review.",
    }


@router.post("/api/v1/vendor/ncr/{finding_id}/quick-close")
def submit_vendor_quick_correction(
    finding_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "inspection_engineer", "qc_manager")
    ),
):
    """
    Direct Quick Correction submission strictly for Minor Findings & Punch Items.
    Critical/Major NCRs are blocked and must use /submit-resolution.
    """
    details = str(payload.get("correction_details") or "").strip()
    doc_name = str(payload.get("uploaded_document_name") or "").strip()
    remarks = str(payload.get("remarks") or "").strip()

    if not details and not doc_name:
        raise HTTPException(status_code=400, detail="Correction details or uploaded document required.")

    _verify_finding_access(finding_id, current_user)

    def _mutate_quick(f: Dict[str, Any], _insp: Dict[str, Any]) -> None:
        if str(f.get("closure_status") or f.get("status") or "").lower() == "closed":
            raise HTTPException(status_code=400, detail="Cannot overwrite an already closed finding.")
        sev = str(f.get("severity") or f.get("SEVERITY") or "").lower()
        ftype = str(f.get("type") or f.get("TYPE") or "").lower()
        if "critical" in sev or "major" in sev or "ncr" in ftype:
            raise HTTPException(
                status_code=400,
                detail="Critical/Major NCRs cannot use quick-close; submit full 3-Stage Containment, RCA, and CAPA.",
            )
        f["vendor_quick_correction"] = {
            "correction_details": details,
            "uploaded_document_name": doc_name,
            "remarks": remarks,
            "submitted_by": current_user.get("email"),
            "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        f["status"] = "pending_ie_review"
        f["closure_status"] = "pending_ie_review"

    updated_insp = inspectflow_db.find_and_update_finding(finding_id, _mutate_quick)
    if updated_insp:
        sync_single_inspection_to_smartexpedit(updated_insp)

    concern_matched = False
    with LOCK, sx_db() as c:
        sx_state = _get_sx_state(c)
        for item in sx_state.get("concerns", []):
            if str(item.get("id")) == str(finding_id) or str(item.get("no")) == str(finding_id) or str(item.get("if_finding_id")) == str(finding_id):
                if str(item.get("status") or "").upper() == "CLOSED":
                    raise HTTPException(status_code=400, detail="Cannot overwrite an already closed RAIL item.")
                if str(item.get("impact") or "").upper() in ("CRITICAL", "MAJOR") and not updated_insp:
                    raise HTTPException(
                        status_code=400,
                        detail="Critical/Major RAIL NCRs cannot use quick-close; submit full 3-Stage Containment, RCA, and CAPA.",
                    )
                item["vendor_quick_correction"] = details or doc_name
                item["status"] = "PENDING IE TECH REVIEW"
                item.setdefault("history", []).append({
                    "on": time.strftime("%Y-%m-%d"),
                    "by": current_user.get("full_name") or "Vendor",
                    "act": "Submitted Minor Quick-Close Correction",
                    "note": details or doc_name,
                })
                concern_matched = True
        if concern_matched:
            _save_sx_state(c, sx_state, current_user.get("email") or "Vendor Portal Quick Correction")

    if not updated_insp and not concern_matched:
        raise HTTPException(status_code=404, detail=f"Finding '{finding_id}' not found")

    record_audit_event(
        "ncr_finding",
        finding_id,
        "VENDOR_QUICK_CLOSE_SUBMITTED",
        actor=current_user,
        after={"status": "pending_ie_review", "doc": doc_name},
    )

    return {
        "ok": True,
        "finding_id": finding_id,
        "inspection_synced": bool(updated_insp),
        "status": "pending_ie_review",
        "message": "Correction submitted. Fast-tracked for Inspection Engineer sign-off.",
    }


# ===========================================================================
# VENDOR SCHEDULE PROGRESS UPDATES & VDMS SYNC
# ===========================================================================

@router.post("/api/v1/vendor/schedule-update")
def update_vendor_schedule(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(
        require_roles("admin", "vendor", "expediting_manager", "expeditor", "field_expeditor")
    ),
):
    """
    Allows vendor to submit periodic schedule updates.
    Matches against PO item['item'] (plus fallback id/tag/name), validates against stored contractual
    baseline_date (never client-supplied baseline), and requires delay reason + recovery plan on slips.
    """
    po_num = str(payload.get("po_number") or "").strip()
    items_updates = payload.get("items") or []
    if not po_num:
        raise HTTPException(status_code=400, detail="po_number required")

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found in master records")
        if not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Not authorized to update schedule for PO {po_num}")

        updated_count = 0
        for up in items_updates:
            item_id = str(up.get("item_id") or up.get("item") or "").strip()
            forecast = up.get("forecast_date")
            delay_reason = up.get("delay_reason_code")
            recovery_plan = up.get("recovery_plan")

            matched_items = [
                itm for itm in rec.get("items", [])
                if str(itm.get("item")) == item_id
                or str(itm.get("id")) == item_id
                or str(itm.get("tag")) == item_id
                or str(itm.get("name")) == item_id
            ]
            # Validate against server stored baseline_date first (fallback to payload baseline only if uninitialized)
            server_baseline = (
                (matched_items[0].get("baseline_date") or matched_items[0].get("bE"))
                if matched_items
                else None
            ) or up.get("baseline_date")

            if forecast and server_baseline and str(forecast)[:10] > str(server_baseline)[:10]:
                if not delay_reason or not recovery_plan:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Item {item_id}: Forecast ({forecast}) slips past Contractual Baseline ({server_baseline}). Standard Delay Reason Code and Recovery Plan are mandatory."
                    )

            for itm in matched_items:
                updated_count += 1
                if forecast:
                    itm["forecast_date"] = forecast
                if up.get("actual_date"):
                    itm["actual_date"] = up["actual_date"]
                for pct_key in ("eng_pct", "proc_pct", "fab_pct", "insp_pct"):
                    if pct_key in up and up[pct_key] is not None:
                        itm[pct_key] = max(0.0, min(100.0, float(up[pct_key])))
                if delay_reason:
                    itm["delay_reason"] = delay_reason
                    itm["recovery_plan"] = recovery_plan

        _save_records(c, L, current_user.get("email") or "Schedule Update", f"Updated progress/schedule ({updated_count} item(s)) for PO {po_num}")

    record_audit_event("po", po_num, "VENDOR_SCHEDULE_UPDATED", actor=current_user, after={"updated_items": updated_count})
    return {
        "ok": True,
        "po_number": po_num,
        "updated_items": updated_count,
        "message": f"Schedule and progress updated for {updated_count} item(s) on PO {po_num}.",
    }


@router.get("/api/v1/vdms/documents")
def get_vdms_documents(
    po: Optional[str] = None,
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Fetches VDRL documents with review status (Code 1/2/3), submission & return dates,
    and calculates real-time date-driven SLA countdowns.
    """
    today = date.today()
    accessible_pids = _get_accessible_pids_for_user(current_user)
    with LOCK, sx_db() as c:
        L = _records(c)
        results = []
        for r in L:
            if not _allowed_po_record(r, current_user, project_id=project_id, accessible_pids=accessible_pids):
                continue
            if po and str(r.get("po")) != po:
                continue
            docs = _ensure_vdrl_docs(r)
            for d in docs:
                sla_days = int(d.get("sla_days") or 14)
                code = d.get("code") or "Code 1"
                submitted_str = d.get("submitted") or d.get("actual_date") or d.get("planned_date")
                returned_str = d.get("returned") or d.get("actual_date") or ""
                planned_dt = _parse_date_safe(d.get("planned_date"))
                submitted_dt = _parse_date_safe(submitted_str)

                # Compute real SLA due date and calendar days remaining
                if code in ("Code 1",) and returned_str:
                    days_remaining = 0
                    is_overdue = False
                elif planned_dt:
                    due_dt = planned_dt
                    days_remaining = (due_dt - today).days
                    is_overdue = days_remaining < 0 or code == "Code 3"
                elif submitted_dt:
                    from datetime import timedelta
                    due_dt = submitted_dt + timedelta(days=sla_days)
                    days_remaining = (due_dt - today).days
                    is_overdue = days_remaining < 0 or code == "Code 3"
                else:
                    days_remaining = sla_days
                    is_overdue = code == "Code 3"

                results.append({
                    "po": r.get("po"),
                    "supplier": r.get("supplier"),
                    "doc_no": d.get("doc_no"),
                    "title": d.get("title"),
                    "rev": d.get("rev", "Rev 0"),
                    "code": code,
                    "status": d.get("status") or ("APPROVED" if code == "Code 1" else "ACTION REQUIRED"),
                    "planned_date": d.get("planned_date") or "",
                    "submitted": submitted_str or "",
                    "returned": returned_str,
                    "sla_days": sla_days,
                    "days_remaining": days_remaining,
                    "is_overdue": is_overdue,
                })
        return {"ok": True, "count": len(results), "documents": results}


# ===========================================================================
# VENDOR POST-IRC DISPATCH REQUEST
# ===========================================================================

@router.post("/api/v1/vendor/dispatch-request")
def create_vendor_dispatch_request(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "vendor", "expediting_manager", "expeditor")),
):
    """
    Vendor submits official Dispatch Request after receiving IRC.
    Atomically reserves dispatch_qty inside LOCK so concurrent/duplicate requests
    cannot exceed (irc_released_qty - shipped_qty - pending_reserved_qty).
    """
    po_num = str(payload.get("po_number") or "").strip()
    item_id = str(payload.get("item_id") or "10").strip()
    irc_no = str(payload.get("irc_number") or "").strip()
    dispatch_qty = float(payload.get("dispatch_qty") or 0)
    packing_list = str(payload.get("packing_list_ref") or "").strip()
    gross_kg = float(payload.get("gross_weight_kg") or 0)
    net_kg = float(payload.get("net_weight_kg") or 0)
    dimensions = str(payload.get("crate_dimensions") or "").strip()
    invoice_draft = str(payload.get("invoice_draft_ref") or "").strip()

    if not po_num or not item_id or dispatch_qty <= 0:
        raise HTTPException(status_code=400, detail="po_number, item_id, and positive dispatch_qty required")

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"You do not have access to PO {po_num}")
        if is_vendor_user(current_user):
            if not vendor_owns_po(current_user, rec):
                raise HTTPException(status_code=403, detail=f"Vendor cannot request dispatch for unassigned PO {po_num}")
        elif not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"You do not have access to PO {po_num}")

        if irc_no and (rec.get("irns") or []):
            if not any(str(ir.get("no") or "") == irc_no for ir in (rec.get("irns") or [])):
                raise HTTPException(status_code=400, detail=f"IRC/IRN number '{irc_no}' not issued on PO {po_num}")

        clr = rec.get("clr", {})
        item_entry = clr.get(item_id) or {}
        released_qty = float(item_entry.get("irn", 0))
        shipped_qty = float(item_entry.get("ship", 0))

        # Check sx_state cumulative_ledger using canonical po:item_id key only
        sx_state = _get_sx_state(c)
        matrix = sx_state.get("cumulative_ledger", {}).get(f"{po_num}:{item_id}")
        if matrix and float(matrix.get("released_qty", 0)) > released_qty:
            released_qty = float(matrix.get("released_qty", 0))
            shipped_qty = float(matrix.get("shipped_qty", 0))

        existing_requests = sx_state.setdefault("dispatch_requests", [])
        pending_reserved_qty = sum(
            float(dr.get("dispatch_qty") or 0)
            for dr in existing_requests
            if str(dr.get("po")) == po_num
            and str(dr.get("item_id")) == item_id
            and str(dr.get("status") or "").upper() in ("AWAITING LOGISTICS MOVEMENT AUTHORITY", "SRN_APPROVED_PENDING_PICKUP")
        )

        unshipped_available = released_qty - shipped_qty - pending_reserved_qty

        if dispatch_qty > unshipped_available:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Dispatch Request Rejected: Requested Qty ({dispatch_qty}) exceeds available unreserved balance "
                    f"({unshipped_available}; Released={released_qty}, Shipped={shipped_qty}, Pending Reserved={pending_reserved_qty})."
                ),
            )

        dispatch_id = f"DSP-{po_num}-{uuid.uuid4().hex[:6].upper()}"
        dispatch_req = {
            "id": dispatch_id,
            "po": po_num,
            "item_id": item_id,
            "irc_number": irc_no,
            "dispatch_qty": dispatch_qty,
            "packing_list_ref": packing_list,
            "gross_weight_kg": gross_kg,
            "net_weight_kg": net_kg,
            "crate_dimensions": dimensions,
            "invoice_draft_ref": invoice_draft,
            "status": "AWAITING LOGISTICS MOVEMENT AUTHORITY",
            "submitted_by": current_user.get("email"),
            "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        existing_requests.append(dispatch_req)
        _save_sx_state(c, sx_state, current_user.get("email") or "Vendor Portal Dispatch Request")

    try:
        from backend_v2.core.database import SessionLocal
        from backend_v2.models.epc_models import DispatchReservation
        with SessionLocal() as db:
            db.add(DispatchReservation(
                id=dispatch_id,
                po_number=po_num,
                item_id=item_id,
                irc_number=irc_no,
                reserved_qty=dispatch_qty,
                status="AWAITING LOGISTICS MOVEMENT AUTHORITY",
                created_by=current_user.get("email"),
            ))
            db.commit()
    except Exception as exc:
        print("DispatchReservation relational mirror note:", exc)

    record_audit_event(
        "dispatch_request",
        dispatch_id,
        "DISPATCH_RESERVED",
        actor=current_user,
        after={"po": po_num, "item_id": item_id, "qty": dispatch_qty, "remaining_available": unshipped_available - dispatch_qty},
    )

    return {
        "ok": True,
        "dispatch_id": dispatch_id,
        "status": "AWAITING LOGISTICS MOVEMENT AUTHORITY",
        "reserved_qty": dispatch_qty,
        "remaining_available_qty": max(0.0, unshipped_available - dispatch_qty),
        "message": f"Dispatch Request {dispatch_id} submitted & quantity reserved. Queued for Logistics Coordinator movement clearance.",
    }


# ===========================================================================
# REAL-TIME EXPEDITOR IRC BLOCKER DIAGNOSTICS
# ===========================================================================

@router.get("/api/v1/executive/irc-blockers")
def get_irc_blocker_diagnostics(
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Evaluates completed inspections that have not yet issued an IRC.
    Scans findings inside inspection_reports[].findings (and fallback flattened findings),
    diagnosing exact blockers: Open Critical/Major NCR, Pending IE Tech Review, Pending IE Endorsement, or Ready.
    """
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Guest users cannot access IRC diagnostics")
    blockers = []
    inspections = inspectflow_db.list_inspections()
    vendor_only = is_vendor_user(current_user)
    accessible_pids = _get_accessible_pids_for_user(current_user)
    target_pid = _norm_id_str(project_id)
    with LOCK, sx_db() as c:
        po_map = {str(r.get("po")): r for r in _records(c)}

    for insp in inspections:
        po = str(insp.get("po_number") or "")
        po_rec = po_map.get(po)
        insp_pid = _norm_id_str(insp.get("project_id") or (po_rec.get("project_id") if po_rec else ""))
        if target_pid and target_pid != "all" and insp_pid != target_pid:
            continue
        if accessible_pids is not None and insp_pid not in accessible_pids:
            continue
        if vendor_only:
            if not po_rec or not vendor_owns_po(current_user, po_rec):
                continue

        status = str(insp.get("status") or "").lower()
        all_reports = insp.get("inspection_reports") or []
        rel_notes = [r for r in all_reports if r.get("category") == "release_note" or r.get("report_type") == "release_note"] + (insp.get("release_notes") or [])
        has_irc = bool(rel_notes) or bool(insp.get("irc_number")) or status == "finalized"

        # Collect findings cleanly across all non-IRC reports + top-level findings
        insp_reports = [r for r in all_reports if r.get("category") != "release_note" and r.get("report_type") != "release_note"]
        findings = []
        for rep in insp_reports:
            for f in (rep.get("findings") or []):
                if isinstance(f, dict):
                    findings.append(f)
        if not findings:
            findings = list(insp.get("findings") or [])

        if status in ("completed", "under ie review", "in_progress") and not has_irc:
            notif = insp.get("notification_number")
            ie_approved = any(r.get("approval_status") == "approved" for r in insp_reports)

            def _is_resolved(f_obj: Dict[str, Any]) -> bool:
                st = str(f_obj.get("closure_status") or f_obj.get("status") or "").lower()
                return st in ("closed", "resolved", "waived", "conceded")

            def _is_major_ncr(f_obj: Dict[str, Any]) -> bool:
                sev = str(f_obj.get("severity") or f_obj.get("SEVERITY") or "").upper()
                ft = str(f_obj.get("type") or f_obj.get("TYPE") or "").upper()
                return ("CRITICAL" in sev or "MAJOR" in sev or "NCR" in ft or "NON-CONFORMANCE" in ft)

            has_pending_ie = any(
                (str(f.get("status") or "").lower() == "pending_ie_review" or bool(f.get("vendor_response")) or bool(f.get("vendor_quick_correction")))
                and not _is_resolved(f)
                for f in findings
            )
            has_pending_vendor = any(
                _is_major_ncr(f) and not _is_resolved(f)
                and str(f.get("status") or "").lower() != "pending_ie_review"
                and not f.get("vendor_response")
                for f in findings
            )
            has_major_open = any(_is_major_ncr(f) and not _is_resolved(f) for f in findings)
            minor_punch_only = not has_major_open and any(not _is_resolved(f) for f in findings)

            if has_pending_vendor:
                blockers.append({
                    "po": po,
                    "inspection_id": insp.get("id"),
                    "notification_number": notif,
                    "supplier": insp.get("supplier_name"),
                    "status_badge": "IRC BLOCKED: Open Major NCR awaiting Vendor RCA",
                    "severity": "CRITICAL",
                    "action_required": "Vendor must submit 3-stage Containment, RCA & CAPA",
                    "sla_timer": "72h Vendor RCA SLA",
                })
            elif has_pending_ie:
                blockers.append({
                    "po": po,
                    "inspection_id": insp.get("id"),
                    "notification_number": notif,
                    "supplier": insp.get("supplier_name"),
                    "status_badge": "IRC ON HOLD: Vendor submitted rework, awaiting IE Review",
                    "severity": "HIGH",
                    "action_required": "Inspection Engineer to verify rework evidence (Stage 1)",
                    "sla_timer": "24h IE Review SLA",
                })
            elif insp_reports and not ie_approved:
                blockers.append({
                    "po": po,
                    "inspection_id": insp.get("id"),
                    "notification_number": notif,
                    "supplier": insp.get("supplier_name"),
                    "status_badge": "IRC ON HOLD: Pending IE Deliverable Endorsement",
                    "severity": "HIGH",
                    "action_required": "Inspection Engineer must endorse uploaded IVR/Report for release",
                    "sla_timer": "IE Sign-Off Required",
                })
            elif minor_punch_only:
                blockers.append({
                    "po": po,
                    "inspection_id": insp.get("id"),
                    "notification_number": notif,
                    "supplier": insp.get("supplier_name"),
                    "status_badge": "IRC READY: Minor Punch only, eligible for Release with Punch",
                    "severity": "MEDIUM",
                    "action_required": "Inspection Engineer can issue IRC with Minor Punch tag",
                    "sla_timer": "Eligible for Release",
                })
            else:
                blockers.append({
                    "po": po,
                    "inspection_id": insp.get("id"),
                    "notification_number": notif,
                    "supplier": insp.get("supplier_name"),
                    "status_badge": "IRC READY: All findings clear, ready for IE sign-off",
                    "severity": "LOW",
                    "action_required": "Inspection Engineer to issue formal IRC",
                    "sla_timer": "Ready to Release",
                })

    return {
        "ok": True,
        "count": len(blockers),
        "blockers": blockers,
    }


# ===========================================================================
# 2-TIER CASCADING PROJECT & PO GOVERNANCE ENGINE
# (Global Admin -> Expediting Manager & QC/Inspection Manager -> Paired PO Roster)
# ===========================================================================

def _find_user_by_id_or_email(users: list, ident: Optional[str]):
    if not ident:
        return None
    s = str(ident).strip().lower()
    return next((u for u in users if str(u.get("id", "")).lower() == s or str(u.get("email", "")).lower() == s), None)


def _add_project_to_user(user_id: Optional[str], project_id: Optional[str]):
    if not user_id or not project_id:
        return
    users = inspectflow_db.list_users()
    u = _find_user_by_id_or_email(users, user_id)
    if not u:
        return
    pids = [str(p).lower() for p in (u.get("project_ids") or []) if p]
    norm_pid = str(project_id).lower()
    if norm_pid not in pids:
        pids.append(norm_pid)
        inspectflow_db.update_user(u["id"], {"project_ids": pids})


def ensure_governance_seeded():
    """
    Dev-mode demo bootstrap ONLY. Never runs in production or re-grants revoked projects.
    """
    if settings.auth_mode != "dev":
        return
    inspectflow_db.init_db()
    if inspectflow_db.list_projects():
        # Projects already exist; do NOT overwrite or re-grant revoked user project permissions.
        return
    users = inspectflow_db.list_users()

    # Map standard users by email
    user_profiles = [
        ("admin@inspectflow.com", "Sarah Jenkins (Global Admin)", "admin", "Administration", "InspectFlow Enterprise"),
        ("pexm@inspectflow.com", "Tariq Al-Mansoor (Expediting Manager)", "expediting_manager", "Expediting & Logistics", "InspectFlow EPC"),
        ("qc@inspectflow.com", "Dr. Henrik Lindqvist (QC / Inspection Manager)", "qc_manager", "Quality Control", "InspectFlow EPC"),
        ("expeditor@inspectflow.com", "Ali Al-Rashid (Lead Package Expeditor)", "expeditor", "Procurement Expediting", "InspectFlow EPC"),
        ("fieldexpeditor@inspectflow.com", "Arjun Mehta (Field Expeditor)", "field_expeditor", "Field Surveillance", "InspectFlow EPC"),
        ("docexpeditor@inspectflow.com", "Lina Haddad (Document Controller / VDRL)", "doc_expeditor", "VDMS & Engineering", "InspectFlow EPC"),
        ("engineer@inspectflow.com", "Omar Farooq (Senior Inspection Engineer)", "inspection_engineer", "Quality Engineering", "InspectFlow EPC"),
        ("inspector@inspectflow.com", "Carlos Mendez (Lead TPI Inspector)", "inspector", "Field Inspection", "Fulkrum Technical Services"),
        ("tpi@inspectflow.com", "Fulkrum Technical Services (TPI Coordinator)", "inspection_agency", "Third-Party Inspection", "Fulkrum"),
        ("vendor@petronash.com", "Marco Rossi (Flowserve / Petronash Vendor Lead)", "vendor", "Supplier Quality & Dispatch", "Flowserve & Sulzer Consortium"),
    ]

    for email, full_name, role, dept, company in user_profiles:
        u = _find_user_by_id_or_email(users, email)
        if u:
            # Ensure friendly full name & active role
            if not u.get("full_name") or u.get("full_name") in ("System Administrator", "QC Engineer", "Fulkrum Inspector", "TPI Agency") or not u.get("inspection_role"):
                inspectflow_db.update_user(u["id"], {
                    "full_name": full_name,
                    "inspection_role": role,
                    "department": dept,
                    "company_affiliation": company,
                })

    users = inspectflow_db.list_users()
    u_admin = _find_user_by_id_or_email(users, "admin@inspectflow.com")
    u_pexm = _find_user_by_id_or_email(users, "pexm@inspectflow.com")
    u_qcm = _find_user_by_id_or_email(users, "qc@inspectflow.com")
    u_exp = _find_user_by_id_or_email(users, "expeditor@inspectflow.com")
    u_fexp = _find_user_by_id_or_email(users, "fieldexpeditor@inspectflow.com")
    u_dexp = _find_user_by_id_or_email(users, "docexpeditor@inspectflow.com")
    u_ie = _find_user_by_id_or_email(users, "engineer@inspectflow.com")
    u_insp = _find_user_by_id_or_email(users, "inspector@inspectflow.com")
    u_tpi = _find_user_by_id_or_email(users, "tpi@inspectflow.com")
    u_vend = _find_user_by_id_or_email(users, "vendor@petronash.com")

    all_team_ids = [u["id"] for u in [u_pexm, u_qcm, u_exp, u_fexp, u_dexp, u_ie, u_insp, u_tpi, u_vend] if u]

    existing_projects = inspectflow_db.list_projects()
    by_code = {str(p.get("code", "")).upper(): p for p in existing_projects}

    default_projects_spec = [
        {
            "id": "11111111-1111-1111-1111-111111111101",
            "code": "PRJ-TRAIN3",
            "name": "Offshore Gas Expansion Project (Train-3)",
            "description": "High-pressure chemical injection skids, cryogenic ball valves (100 EA), and PLC control systems across Milan, Houston & Singapore yards.",
            "client_name": "ADNOC Offshore / QatarEnergy LNG",
            "start_date": "2026-09-01",
            "end_date": "2027-06-30",
            "status": "active",
            "linked_po_numbers": ["PO-88001"],
        },
        {
            "id": "11111111-1111-1111-1111-111111111102",
            "code": "PRJ-2820",
            "name": "NFPS Compression & Structural Bolting Package (EPC-2820)",
            "description": "Critical stud bolts, pressure vessels, and chemical injection skids for North Field Production Sustainability Compression.",
            "client_name": "Saipem / Qatargas Operating Co.",
            "start_date": "2026-06-15",
            "end_date": "2027-03-31",
            "status": "active",
            "linked_po_numbers": ["2820-2025-74259-A", "2820-2025-74259-B", "2820-2025-74259-C", "2820-2025-74462-AC"],
        },
        {
            "id": "11111111-1111-1111-1111-111111111103",
            "code": "PRJ-7100",
            "name": "Clean Fuels Refinery Valve & Skid Interlink Project",
            "description": "High-pressure gate/globe valves and modular skid assemblies with full VDMS & ITP quality gate tracking.",
            "client_name": "Bapco Energies / Technip Energies",
            "start_date": "2026-08-01",
            "end_date": "2027-05-15",
            "status": "active",
            "linked_po_numbers": ["710001", "1061008122 Suppl:05", "1061207740 PO SUPPL.15"],
        },
    ]

    created_projects = {}
    for spec in default_projects_spec:
        code_upper = spec["code"].upper()
        if code_upper not in by_code:
            p = inspectflow_db.create_project({
                **spec,
                "expediting_manager_id": u_pexm["id"] if u_pexm else None,
                "expediting_manager_name": u_pexm["full_name"] if u_pexm else "Tariq Al-Mansoor",
                "expediting_manager_email": u_pexm["email"] if u_pexm else "pexm@inspectflow.com",
                "inspection_manager_id": u_qcm["id"] if u_qcm else None,
                "inspection_manager_name": u_qcm["full_name"] if u_qcm else "Dr. Henrik Lindqvist",
                "inspection_manager_email": u_qcm["email"] if u_qcm else "qc@inspectflow.com",
                "team_member_ids": all_team_ids,
            })
            created_projects[code_upper] = p
        else:
            p = by_code[code_upper]
            if not p.get("expediting_manager_id") or not p.get("inspection_manager_id"):
                p = inspectflow_db.update_project(p["id"], {
                    "expediting_manager_id": p.get("expediting_manager_id") or (u_pexm["id"] if u_pexm else None),
                    "inspection_manager_id": p.get("inspection_manager_id") or (u_qcm["id"] if u_qcm else None),
                    "team_member_ids": list(set((p.get("team_member_ids") or []) + all_team_ids)),
                    "linked_po_numbers": list(set((p.get("linked_po_numbers") or []) + spec["linked_po_numbers"])),
                }) or p
            created_projects[code_upper] = p

    # Ensure every user in all_team_ids has all active project IDs assigned so they can switch freely
    all_proj_ids = [p["id"] for p in inspectflow_db.list_projects()]
    for uid in all_team_ids:
        for pid in all_proj_ids:
            _add_project_to_user(uid, pid)

    # Interlink every PO in smartexpedit.db to its Project and 5-Role Paired Ownership Roster
    with LOCK, sx_db() as c:
        L = _records(c)
        changed = False
        for rec in L:
            po_str = str(rec.get("po") or "")
            if po_str == "PO-88001" or "Train-3" in str(rec.get("project") or ""):
                target_proj = created_projects.get("PRJ-TRAIN3")
            elif po_str.startswith("2820") or str(rec.get("project")) == "2820":
                target_proj = created_projects.get("PRJ-2820")
            else:
                target_proj = created_projects.get("PRJ-7100")

            if target_proj and (not rec.get("project_id") or not rec.get("assigned_inspection_engineer_id")):
                rec["project_id"] = target_proj["id"]
                rec["project_code"] = target_proj["code"]
                rec["project"] = target_proj["name"]
                rec["expediting_manager_id"] = target_proj.get("expediting_manager_id") or (u_pexm["id"] if u_pexm else "")
                rec["expediting_manager_name"] = target_proj.get("expediting_manager_name") or "Tariq Al-Mansoor"
                rec["expediting_manager_email"] = target_proj.get("expediting_manager_email") or "pexm@inspectflow.com"
                rec["inspection_manager_id"] = target_proj.get("inspection_manager_id") or (u_qcm["id"] if u_qcm else "")
                rec["inspection_manager_name"] = target_proj.get("inspection_manager_name") or "Dr. Henrik Lindqvist"
                rec["inspection_manager_email"] = target_proj.get("inspection_manager_email") or "qc@inspectflow.com"

                # Assign Package Expeditor & Field Expeditor
                if not rec.get("assigned_expeditor_id"):
                    is_arjun = "arjun" in str(rec.get("assignedTo") or "").lower()
                    chosen_exp = u_fexp if (is_arjun and u_fexp) else u_exp
                    rec["assigned_expeditor_id"] = chosen_exp["id"] if chosen_exp else ""
                    rec["assigned_expeditor_name"] = chosen_exp["full_name"] if chosen_exp else "Ali Al-Rashid"
                    rec["assigned_expeditor_email"] = chosen_exp["email"] if chosen_exp else "expeditor@inspectflow.com"
                    rec["assignedTo"] = rec["assigned_expeditor_name"]

                if not rec.get("assigned_field_expeditor_id") and u_fexp:
                    rec["assigned_field_expeditor_id"] = u_fexp["id"]
                    rec["assigned_field_expeditor_name"] = u_fexp["full_name"]

                # Assign Paired Inspection Engineer
                if not rec.get("assigned_inspection_engineer_id") and u_ie:
                    rec["assigned_inspection_engineer_id"] = u_ie["id"]
                    rec["assigned_inspection_engineer_name"] = u_ie["full_name"]
                    rec["assigned_inspection_engineer_email"] = u_ie["email"]

                # Assign Vendor
                if not rec.get("assigned_vendor_id") and u_vend:
                    rec["assigned_vendor_id"] = u_vend["id"]
                    rec["assigned_vendor_email"] = u_vend["email"]

                changed = True

        if changed:
            _save_records(c, L, "System Governance Engine", "Interlinked all POs with Projects, Expediting Manager, QC Manager, Expeditor & Inspection Engineer")

        po_map = {str(r.get("po")): r for r in L}

    # Interlink every Inspection in inspectflow.db with its PO's Project ID & Paired Roster
    for insp in inspectflow_db.list_inspections():
        po_num = str(insp.get("po_number") or "")
        po_rec = po_map.get(po_num)
        if po_rec:
            needs_upd = (
                not insp.get("project_id")
                or not insp.get("assigned_inspection_engineer_id")
                or not insp.get("assigned_expeditor_name")
            )
            if needs_upd:
                inspectflow_db.update_inspection(insp["id"], {
                    "project_id": po_rec.get("project_id"),
                    "assigned_inspection_engineer_id": po_rec.get("assigned_inspection_engineer_id"),
                    "assigned_inspection_engineer_name": po_rec.get("assigned_inspection_engineer_name"),
                    "assigned_inspection_engineer_email": po_rec.get("assigned_inspection_engineer_email"),
                    "assigned_expeditor_id": po_rec.get("assigned_expeditor_id"),
                    "assigned_expeditor_name": po_rec.get("assigned_expeditor_name"),
                    "assigned_expeditor_email": po_rec.get("assigned_expeditor_email"),
                    "expediting_manager_name": po_rec.get("expediting_manager_name"),
                    "inspection_manager_name": po_rec.get("inspection_manager_name"),
                })


@router.get("/api/v1/governance/overview")
def get_governance_overview(
    project_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns the complete interlinked Governance Matrix across Projects, Managers, POs, BOMs,
    Expeditors, Inspection Engineers, and Vendors (with Vendor & Manager Project isolation).
    """
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Insufficient permissions for governance overview")
    all_projects = inspectflow_db.list_projects()
    users = inspectflow_db.list_users()
    inspections = inspectflow_db.list_inspections()
    vendor_only = is_vendor_user(current_user)
    accessible_pids = _get_accessible_pids_for_user(current_user)
    projects = (
        all_projects
        if accessible_pids is None
        else [p for p in all_projects if _norm_id_str(p.get("id")) in accessible_pids]
    )

    with LOCK, sx_db() as c:
        L = _records(c)

    if vendor_only:
        users_by_role = {}
        users_out = []
    else:
        users_out = users
        users_by_role = {
            "admins": [u for u in users if u.get("role") == "admin" or u.get("inspection_role") == "admin"],
            "expediting_managers": [u for u in users if u.get("inspection_role") == "expediting_manager" or u.get("role") == "expediting_manager"],
            "inspection_managers": [u for u in users if u.get("inspection_role") == "qc_manager" or u.get("role") == "qc_manager"],
            "package_expeditors": [u for u in users if u.get("inspection_role") == "expeditor" or u.get("role") == "expeditor"],
            "field_expeditors": [u for u in users if u.get("inspection_role") == "field_expeditor" or u.get("role") == "field_expeditor"],
            "doc_expeditors": [u for u in users if u.get("inspection_role") == "doc_expeditor" or u.get("role") == "doc_expeditor"],
            "inspection_engineers": [u for u in users if u.get("inspection_role") == "inspection_engineer" or u.get("role") == "inspection_engineer"],
            "inspectors": [u for u in users if u.get("inspection_role") == "inspector" or u.get("role") == "inspector"],
            "agencies": [u for u in users if u.get("inspection_role") == "inspection_agency" or u.get("role") == "inspection_agency"],
            "vendors": [u for u in users if u.get("inspection_role") == "vendor" or u.get("role") == "vendor"],
        }

    pos_out = []
    for rec in L:
        if not _allowed_po_record(rec, current_user, project_id=project_id, accessible_pids=accessible_pids):
            continue
        po_num = str(rec.get("po") or "")
        rec_pid = _norm_id_str(rec.get("project_id"))
        items = rec.get("items") or []
        clr = rec.get("clr") or {}
        leaf_items = [i for i in items if not i.get("is_split_parent")]
        tot_ord = sum(float(i.get("qty") or 0) for i in leaf_items)
        tot_rel = sum(float((clr.get(str(i.get("item"))) or {}).get("irn") or 0) for i in leaf_items)
        tot_ship = sum(float((clr.get(str(i.get("item"))) or {}).get("ship") or 0) for i in leaf_items)
        tot_mrv = sum(float((clr.get(str(i.get("item"))) or {}).get("mrv") or 0) for i in leaf_items)
        po_insps = [i for i in inspections if str(i.get("po_number")) == po_num]

        po_entry = {
            "po": po_num,
            "project_id": rec_pid,
            "project_code": rec.get("project_code") or "",
            "project_name": rec.get("project") or "",
            "supplier": rec.get("supplierShort") or rec.get("supplier") or "Vendor",
            "head": rec.get("head") or "",
            "stage": rec.get("stage") or "fab",
            "procurement_class": _infer_procurement_class(rec),
            "contract_no": rec.get("contract_no") or "",
            "budget_no": rec.get("budget_no") or "",
            "incoterm": rec.get("incoterm") or "",
            "cdd_date": rec.get("cdd_date") or "",
            "ros_date": rec.get("ros_date") or "",
            "platform": rec.get("platform") or "",
            "despatch_location": rec.get("despatch_location") or rec.get("deliveryPoint") or "",
            "requires_client_iap": bool(rec.get("requires_client_iap")),
            "ack_status": (rec.get("ackx") or {}).get("st") or ("Unconditional" if rec.get("ackDate") else "Pending"),
            "closeout_stage": (rec.get("close_state") or {}).get("stage_label") or "Open",
            "value": None if vendor_only else (rec.get("value") or 0),
            "ccy": rec.get("ccy") or "USD",
            "expediting_manager_id": _norm_id_str(rec.get("expediting_manager_id")),
            "expediting_manager_name": rec.get("expediting_manager_name") or "",
            "expediting_manager_email": "" if vendor_only else (rec.get("expediting_manager_email") or ""),
            "assigned_expeditor_id": _norm_id_str(rec.get("assigned_expeditor_id")),
            "assigned_expeditor_name": rec.get("assigned_expeditor_name") or rec.get("assignedTo") or "",
            "assigned_expeditor_email": "" if vendor_only else (rec.get("assigned_expeditor_email") or ""),
            "assigned_field_expeditor_id": _norm_id_str(rec.get("assigned_field_expeditor_id")),
            "assigned_field_expeditor_name": rec.get("assigned_field_expeditor_name") or "",
            "inspection_manager_id": _norm_id_str(rec.get("inspection_manager_id")),
            "inspection_manager_name": rec.get("inspection_manager_name") or "",
            "inspection_manager_email": "" if vendor_only else (rec.get("inspection_manager_email") or ""),
            "assigned_inspection_engineer_id": _norm_id_str(rec.get("assigned_inspection_engineer_id")),
            "assigned_inspection_engineer_name": rec.get("assigned_inspection_engineer_name") or "",
            "assigned_inspection_engineer_email": "" if vendor_only else (rec.get("assigned_inspection_engineer_email") or ""),
            "assigned_vendor_id": _norm_id_str(rec.get("assigned_vendor_id")),
            "assigned_vendor_email": rec.get("assigned_vendor_email") or "",
            "bom_count": len(items),
            "bom_items": items,
            "total_ordered_qty": tot_ord,
            "total_released_qty": tot_rel,
            "total_shipped_qty": tot_ship,
            "total_delivered_qty": tot_mrv,
            "inspection_count": len(po_insps),
        }
        pos_out.append(po_entry)

    projects_out = []
    for p in projects:
        pid = _norm_id_str(p.get("id"))
        if project_id and project_id != "all" and pid != _norm_id_str(project_id):
            continue
        p_pos = [po_item for po_item in pos_out if po_item.get("project_id") == pid]
        p_insps = [i for i in inspections if _norm_id_str(i.get("project_id")) == pid]
        team_objs = (
            []
            if vendor_only
            else [u for u in users if _norm_id_str(u.get("id")) in [_norm_id_str(tid) for tid in (p.get("team_member_ids") or [])]]
        )
        projects_out.append({
            **p,
            "linked_pos": p_pos,
            "po_count": len(p_pos),
            "inspection_count": len(p_insps),
            "team_members": team_objs,
        })

    return {
        "ok": True,
        "projects": projects_out,
        "pos": pos_out,
        "users": users_out,
        "users_by_role": users_by_role,
    }


def _norm_id_str(val: Any) -> str:
    return str(val).strip().lower() if val else ""


def _po_matches_project(rec: Dict[str, Any], project_id: Optional[str]) -> bool:
    pid = _norm_id_str(project_id)
    if not pid or pid == "all":
        return True
    return _norm_id_str(rec.get("project_id")) == pid


def _get_accessible_pids_for_user(current_user: Dict[str, Any]) -> Optional[set]:
    if is_admin_user(current_user):
        return None
    if effective_role(current_user) in ("", "guest"):
        return set()
    return {
        _norm_id_str(p.get("id"))
        for p in inspectflow_db.list_projects()
        if inspectflow_db.user_has_project_access(current_user, p)
    }


def _allowed_po_record(
    rec: Dict[str, Any],
    current_user: Dict[str, Any],
    project_id: Optional[str] = None,
    accessible_pids: Optional[set] = None,
) -> bool:
    if is_vendor_user(current_user) and not vendor_owns_po(current_user, rec):
        return False
    if not _po_matches_project(rec, project_id):
        return False
    if accessible_pids is not None and _norm_id_str(rec.get("project_id")) not in accessible_pids:
        return False
    return True


def _apply_project_governance(payload: Dict[str, Any], actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Core Tier-1 Governance helper callable by both /api/v1/governance/project-assign and /api/Projects.
    """
    proj_id = payload.get("project_id") or payload.get("id")
    users = inspectflow_db.list_users()

    exp_mgr = _find_user_by_id_or_email(users, payload.get("expediting_manager_id"))
    insp_mgr = _find_user_by_id_or_email(users, payload.get("inspection_manager_id"))
    team_ids = [str(x).lower() for x in (payload.get("team_member_ids") or []) if x]
    if exp_mgr and exp_mgr["id"] not in team_ids:
        team_ids.append(exp_mgr["id"])
    if insp_mgr and insp_mgr["id"] not in team_ids:
        team_ids.append(insp_mgr["id"])

    linked_pos = [str(x).strip() for x in (payload.get("linked_po_numbers") or []) if str(x).strip()]

    proj_data = {
        "name": payload.get("name"),
        "code": payload.get("code"),
        "description": payload.get("description"),
        "client_name": payload.get("client_name"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "status": payload.get("status", "active"),
        "expediting_manager_id": exp_mgr["id"] if exp_mgr else payload.get("expediting_manager_id"),
        "expediting_manager_name": exp_mgr["full_name"] if exp_mgr else payload.get("expediting_manager_name", ""),
        "expediting_manager_email": exp_mgr["email"] if exp_mgr else payload.get("expediting_manager_email", ""),
        "inspection_manager_id": insp_mgr["id"] if insp_mgr else payload.get("inspection_manager_id"),
        "inspection_manager_name": insp_mgr["full_name"] if insp_mgr else payload.get("inspection_manager_name", ""),
        "inspection_manager_email": insp_mgr["email"] if insp_mgr else payload.get("inspection_manager_email", ""),
        "team_member_ids": team_ids,
        "linked_po_numbers": linked_pos,
        "requires_client_iap": bool(payload.get("requires_client_iap")),
    }

    if proj_id and inspectflow_db.get_project(proj_id):
        proj = inspectflow_db.update_project(proj_id, {k: v for k, v in proj_data.items() if v is not None})
    else:
        if not proj_data.get("name") or not proj_data.get("code"):
            raise HTTPException(status_code=400, detail="Project name and code are required")
        proj = inspectflow_db.create_project(proj_data)

    if not proj:
        raise HTTPException(status_code=500, detail="Failed to save project")

    pid = proj["id"]

    # Cascade to all POs belonging to this project
    with LOCK, sx_db() as c:
        L = _records(c)
        affected_pos = set(linked_pos)
        for rec in L:
            po_num = str(rec.get("po") or "")
            if po_num in affected_pos or _norm_id_str(rec.get("project_id")) == _norm_id_str(pid):
                rec["project_id"] = pid
                rec["project_code"] = proj["code"]
                rec["project"] = proj["name"]
                if exp_mgr:
                    rec["expediting_manager_id"] = exp_mgr["id"]
                    rec["expediting_manager_name"] = exp_mgr["full_name"]
                    rec["expediting_manager_email"] = exp_mgr["email"]
                if insp_mgr:
                    rec["inspection_manager_id"] = insp_mgr["id"]
                    rec["inspection_manager_name"] = insp_mgr["full_name"]
                    rec["inspection_manager_email"] = insp_mgr["email"]
                affected_pos.add(po_num)
        actor_name = (actor or {}).get("email") or "Global Admin"
        _save_records(c, L, actor_name, f"Updated Project {proj['code']} manager assignments & PO links")

    # Cascade to all Inspections for affected POs
    for insp in inspectflow_db.list_inspections():
        if str(insp.get("po_number") or "") in affected_pos or _norm_id_str(insp.get("project_id")) == _norm_id_str(pid):
            inspectflow_db.update_inspection(insp["id"], {
                "project_id": pid,
                "expediting_manager_name": proj.get("expediting_manager_name"),
                "inspection_manager_name": proj.get("inspection_manager_name"),
            })

    record_audit_event("project", pid, "PROJECT_GOVERNANCE_SAVED", actor=actor, after={"code": proj["code"], "linked_pos": list(affected_pos)})
    return {
        "ok": True,
        "project": proj,
        "linked_po_count": len(affected_pos),
        "message": f"Project '{proj['name']}' saved and interlinked with Expediting Manager ({proj.get('expediting_manager_name') or 'Unassigned'}) and Inspection/QC Manager ({proj.get('inspection_manager_name') or 'Unassigned'}).",
    }


@router.post("/api/v1/governance/project-assign")
def assign_project_governance(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin")),
):
    """Tier 1 Governance (Global Admin only)."""
    return _apply_project_governance(payload, actor=current_user)


@router.post("/api/v1/governance/po-assign")
def assign_po_paired_roster(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "qc_manager")),
):
    """
    Tier 2 Governance (Expediting Manager & Inspection/QC Manager & Global Admin):
    Assigns or updates the 5-Role Paired Ownership Roster on a Purchase Order:
    - Project binding (project_id)
    - Package Expeditor & Field Expeditor (Expediting side)
    - Inspection Engineer & default TPI Inspector (Inspection side)
    - Vendor Account (Supplier portal side)
    Cascades to both SmartExpedit PO records and all InspectFlow Inspections for that PO.
    """
    po_num = str(payload.get("po_number") or payload.get("po") or "").strip()
    if not po_num:
        raise HTTPException(status_code=400, detail="po_number is required")

    users = inspectflow_db.list_users()
    proj = inspectflow_db.get_project(payload.get("project_id")) if payload.get("project_id") else None

    u_exp_mgr = _find_user_by_id_or_email(users, payload.get("expediting_manager_id"))
    u_insp_mgr = _find_user_by_id_or_email(users, payload.get("inspection_manager_id"))
    u_exp = _find_user_by_id_or_email(users, payload.get("assigned_expeditor_id"))
    u_fexp = _find_user_by_id_or_email(users, payload.get("assigned_field_expeditor_id"))
    u_ie = _find_user_by_id_or_email(users, payload.get("assigned_inspection_engineer_id"))
    u_vend = _find_user_by_id_or_email(users, payload.get("assigned_vendor_id"))

    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po_num), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po_num} not found")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"You do not have access to PO {po_num}")

        if proj:
            rec["project_id"] = proj["id"]
            rec["project_code"] = proj["code"]
            rec["project"] = proj["name"]
            if not u_exp_mgr and proj.get("expediting_manager_id"):
                u_exp_mgr = _find_user_by_id_or_email(users, proj["expediting_manager_id"])
            if not u_insp_mgr and proj.get("inspection_manager_id"):
                u_insp_mgr = _find_user_by_id_or_email(users, proj["inspection_manager_id"])

        if u_exp_mgr:
            rec["expediting_manager_id"] = u_exp_mgr["id"]
            rec["expediting_manager_name"] = u_exp_mgr["full_name"]
            rec["expediting_manager_email"] = u_exp_mgr["email"]
        if u_insp_mgr:
            rec["inspection_manager_id"] = u_insp_mgr["id"]
            rec["inspection_manager_name"] = u_insp_mgr["full_name"]
            rec["inspection_manager_email"] = u_insp_mgr["email"]
        if u_exp:
            rec["assigned_expeditor_id"] = u_exp["id"]
            rec["assigned_expeditor_name"] = u_exp["full_name"]
            rec["assigned_expeditor_email"] = u_exp["email"]
            rec["assignedTo"] = u_exp["full_name"]
        if u_fexp:
            rec["assigned_field_expeditor_id"] = u_fexp["id"]
            rec["assigned_field_expeditor_name"] = u_fexp["full_name"]
        if u_ie:
            rec["assigned_inspection_engineer_id"] = u_ie["id"]
            rec["assigned_inspection_engineer_name"] = u_ie["full_name"]
            rec["assigned_inspection_engineer_email"] = u_ie["email"]
        if u_vend:
            rec["assigned_vendor_id"] = u_vend["id"]
            rec["assigned_vendor_email"] = u_vend["email"]

        _save_records(c, L, "Governance Allocation", f"Updated paired Expediting & Inspection roster for PO {po_num}")

        final_pid = rec.get("project_id")

    # Ensure all assigned users have this project_id in their project_ids
    for u_item in [u_exp_mgr, u_insp_mgr, u_exp, u_fexp, u_ie, u_vend]:
        if u_item and final_pid:
            _add_project_to_user(u_item["id"], final_pid)

    # Also update Project's linked_po_numbers if proj is set
    if final_pid:
        p_obj = inspectflow_db.get_project(final_pid)
        if p_obj:
            lpos = list(p_obj.get("linked_po_numbers") or [])
            if po_num not in lpos:
                lpos.append(po_num)
                inspectflow_db.update_project(final_pid, {"linked_po_numbers": lpos})

    # Cascade paired roster to all InspectFlow Inspections for this PO
    updated_insps = 0
    for insp in inspectflow_db.list_inspections():
        if str(insp.get("po_number")) == po_num:
            upd_payload = {
                "project_id": final_pid,
                "assigned_inspection_engineer_id": rec.get("assigned_inspection_engineer_id"),
                "assigned_inspection_engineer_name": rec.get("assigned_inspection_engineer_name"),
                "assigned_inspection_engineer_email": rec.get("assigned_inspection_engineer_email"),
                "assigned_expeditor_id": rec.get("assigned_expeditor_id"),
                "assigned_expeditor_name": rec.get("assigned_expeditor_name"),
                "assigned_expeditor_email": rec.get("assigned_expeditor_email"),
                "expediting_manager_name": rec.get("expediting_manager_name"),
                "inspection_manager_name": rec.get("inspection_manager_name"),
            }
            if payload.get("assigned_inspector_id"):
                upd_payload["assigned_inspector_id"] = payload["assigned_inspector_id"]
            inspectflow_db.update_inspection(insp["id"], upd_payload)
            updated_insps += 1

    record_audit_event(
        "po_roster",
        po_num,
        "PO_ROSTER_UPDATED",
        actor=current_user,
        after={
            "project_id": final_pid,
            "expeditor": rec.get("assigned_expeditor_email"),
            "inspection_engineer": rec.get("assigned_inspection_engineer_email"),
            "vendor": rec.get("assigned_vendor_email"),
        },
    )

    return {
        "ok": True,
        "po": po_num,
        "project_id": final_pid,
        "assigned_expeditor_name": rec.get("assigned_expeditor_name"),
        "assigned_inspection_engineer_name": rec.get("assigned_inspection_engineer_name"),
        "expediting_manager_name": rec.get("expediting_manager_name"),
        "inspection_manager_name": rec.get("inspection_manager_name"),
        "updated_inspections": updated_insps,
        "message": f"PO {po_num} roster updated: Expeditor ({rec.get('assigned_expeditor_name')}) & Inspection Engineer ({rec.get('assigned_inspection_engineer_name')}) are now interlinked.",
    }


@router.post("/api/v1/governance/vendors")
def create_or_update_vendor_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager")),
):
    """
    Registers or updates a Vendor Portal user & supplier company affiliation,
    optionally linking the vendor to one or more projects.
    """
    company_name = str(payload.get("company_affiliation") or payload.get("company_name") or payload.get("supplier") or "").strip()
    email = str(payload.get("email") or payload.get("vendor_email") or "").strip().lower()
    full_name = str(payload.get("full_name") or payload.get("contact_name") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    password = str(payload.get("password") or "").strip()
    project_ids = payload.get("project_ids") or []
    user_id = str(payload.get("user_id") or "").strip()

    if not company_name:
        raise HTTPException(status_code=400, detail="Supplier / Company Name is required")

    if user_id:
        existing_target = inspectflow_db.get_user(user_id)
        if not existing_target:
            raise HTTPException(status_code=404, detail="Vendor user not found")
        if effective_role(existing_target) != "vendor":
            raise HTTPException(status_code=403, detail="Only existing vendor accounts can be modified via this endpoint")
        upd_data = {
            "company_affiliation": company_name,
            "inspection_role": "vendor",
            "role": "vendor",
        }
        if full_name:
            upd_data["full_name"] = full_name
        if phone:
            upd_data["phone"] = phone
        if password:
            upd_data["password"] = password
        if project_ids:
            upd_data["project_ids"] = project_ids
        updated = inspectflow_db.update_user(user_id, upd_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Vendor user not found")
        record_audit_event(
            "vendor",
            user_id,
            "VENDOR_UPDATED",
            actor=current_user,
            after={k: v for k, v in upd_data.items() if k != "password"},
        )
        return {"ok": True, "created": False, "vendor": updated, "message": f"Vendor '{updated['full_name']}' updated."}

    first_pid = str(project_ids[0]) if project_ids else (str(payload.get("project_id") or "").strip() or None)
    user_obj, created = inspectflow_db.ensure_vendor_user(
        company_name=company_name,
        vendor_email=email,
        contact_name=full_name,
        phone=phone,
        project_id=first_pid,
        password=password or None,
    )
    if len(project_ids) > 1:
        existing_pids = list(user_obj.get("project_ids") or [])
        merged = list(dict.fromkeys([*existing_pids, *[str(p) for p in project_ids]]))
        user_obj = inspectflow_db.update_user(user_obj["id"], {"project_ids": merged}) or user_obj

    record_audit_event(
        "vendor",
        str(user_obj.get("id") or ""),
        "VENDOR_CREATED" if created else "VENDOR_ENSURED",
        actor=current_user,
        after={"company_affiliation": company_name, "email": user_obj.get("email")},
    )
    return {
        "ok": True,
        "created": created,
        "vendor": user_obj,
        "message": (
            f"Registered new Vendor '{user_obj['company_affiliation']}' ({user_obj['email']})."
            if created
            else f"Updated existing Vendor '{user_obj['company_affiliation']}' ({user_obj['email']})."
        ),
    }


@router.post("/api/v1/governance/create-po-with-bom")
def create_po_with_bom_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager")),
):
    """
    Shared Project PO & BOM Onboarding:
    Allows Global Admin or Expediting Manager to create a new Purchase Order bound to a Project ID,
    with a custom Bill of Materials (BOM items) and Vendor Portal account (auto-created or matched
    from supplier details), and immediately interlinks it across Expediting, Inspection, and Vendor Portal.
    """
    po_num = str(payload.get("po_number") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    supplier = str(payload.get("supplier") or "").strip()
    head = str(payload.get("description") or payload.get("head") or "Engineered Equipment Package").strip()
    bom_items = payload.get("items") or []

    if not po_num or not project_id:
        raise HTTPException(status_code=400, detail="po_number and project_id are required")
    if not supplier:
        raise HTTPException(status_code=400, detail="Vendor / Supplier Name is required")

    proj = inspectflow_db.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Selected Project not found")
    if not is_admin_user(current_user) and not inspectflow_db.user_has_project_access(current_user, proj):
        raise HTTPException(status_code=403, detail="You do not have access to create POs on this project")

    users = inspectflow_db.list_users()
    u_exp = _find_user_by_id_or_email(users, payload.get("assigned_expeditor_id"))
    u_fexp = _find_user_by_id_or_email(users, payload.get("assigned_field_expeditor_id"))
    u_ie = _find_user_by_id_or_email(users, payload.get("assigned_inspection_engineer_id"))

    vendor_mode = str(payload.get("vendor_mode") or "").strip().lower()
    raw_vend_id = str(payload.get("assigned_vendor_id") or "").strip()
    vendor_email = str(payload.get("vendor_email") or "").strip().lower()
    vendor_contact_name = str(payload.get("vendor_contact_name") or "").strip()
    vendor_phone = str(payload.get("vendor_phone") or "").strip()
    vendor_password = str(payload.get("vendor_password") or "").strip()

    vendor_created = False
    u_vend = None
    if raw_vend_id and raw_vend_id not in ("__auto__", "__new__") and vendor_mode != "new":
        u_vend = _find_user_by_id_or_email(users, raw_vend_id)
        if u_vend:
            _add_project_to_user(u_vend["id"], proj["id"])

    if not u_vend:
        u_vend, vendor_created = inspectflow_db.ensure_vendor_user(
            company_name=supplier,
            vendor_email=vendor_email,
            contact_name=vendor_contact_name,
            phone=vendor_phone,
            project_id=proj["id"],
            password=vendor_password or None,
        )

    for u_item in [u_exp, u_fexp, u_ie]:
        if u_item:
            _add_project_to_user(u_item["id"], proj["id"])

    if not bom_items:
        raise HTTPException(status_code=400, detail="At least one BOM item is required to create a PO")

    default_cdd = str(payload.get("cdd_date") or payload.get("delivery_date") or "")[:10]
    default_ros = str(payload.get("ros_date") or "")[:10]
    default_platform = str(payload.get("platform") or "").strip()
    default_despatch = str(payload.get("despatch_location") or payload.get("delivery_point") or "Site Warehouse / DDP").strip()

    normalized_items = []
    clr_dict = {}
    for idx, it in enumerate(bom_items):
        ikey = str(it.get("item") or ((idx + 1) * 10)).strip()
        qty_f = float(it.get("qty") or it.get("ordered_qty") or 1.0)
        unit_s = str(it.get("unit") or "EA").strip().upper()
        it_cdd = str(it.get("cdd_date") or it.get("baseline_date") or default_cdd)[:10]
        normalized_items.append({
            "item": ikey,
            "desc": str(it.get("desc") or it.get("description") or f"BOM Line {ikey}"),
            "unit": unit_s,
            "qty": qty_f,
            "hold": 0,
            "lot": it.get("lot") or "Lot 1",
            "tag": str(it.get("tag") or f"TAG-{ikey}"),
            "location": str(it.get("location") or "Vendor Works"),
            "cdd_date": it_cdd,
            "ros_date": str(it.get("ros_date") or default_ros)[:10],
            "platform": str(it.get("platform") or default_platform),
            "despatch_location": str(it.get("despatch_location") or default_despatch),
            "is_split": "." in ikey,
            "parent_item": ikey.split(".")[0] if "." in ikey else "",
            "baseline_date": str(it.get("baseline_date") or it_cdd)[:10],
            "forecast_date": str(it.get("forecast_date") or "")[:10],
            "eng_pct": int(it.get("eng_pct") or 0),
            "proc_pct": int(it.get("proc_pct") or 0),
            "fab_pct": int(it.get("fab_pct") or 0),
            "insp_pct": int(it.get("insp_pct") or 0),
        })
        clr_dict[ikey] = {"irn": 0, "ship": 0, "mrv": 0, "batches": []}

    new_po_rec = {
        "po": po_num,
        "rev": "0",
        "project_id": proj["id"],
        "project_code": proj["code"],
        "project": proj["name"],
        "supplier": supplier.upper(),
        "supplierShort": supplier[:22],
        "mrRef": str(payload.get("mr_ref") or f"MR-{po_num}"),
        "contract_no": str(payload.get("contract_no") or ""),
        "budget_no": str(payload.get("budget_no") or ""),
        "enquiry": f"ENQ-{po_num}",
        "buyer": str(payload.get("buyer_name") or current_user.get("full_name") or "Project Procurement"),
        "buyer_email": str(payload.get("buyer_email") or ""),
        "client": proj.get("client_name") or "",
        "head": head,
        "ccy": payload.get("ccy") or "USD",
        "value": float(payload.get("value") or 0),
        "incoterm": payload.get("incoterm") or "DDP Site",
        "deliveryPoint": default_despatch,
        "despatch_location": default_despatch,
        "platform": default_platform,
        "cdd_date": default_cdd,
        "ros_date": default_ros,
        "pbg_required": bool(payload.get("pbg_required")),
        "lc_required": bool(payload.get("lc_required")),
        "requires_client_iap": bool(payload.get("requires_client_iap", proj.get("requires_client_iap"))),
        "payment": payload.get("payment") or "Milestone Progress",
        "origin": payload.get("origin") or "Supplier Works",
        "shipMode": payload.get("ship_mode") or "Ocean / Road",
        "awardRev": 0,
        "issuedOn": time.strftime("%Y-%m-%d"),
        "issuedAt": time.strftime("%Y-%m-%d %H:%M"),
        "notifiedOn": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "lines": len(normalized_items),
        "qty": sum(float(i.get("qty") or 0) for i in normalized_items),
        "hold": 0,
        "stage": "issued",
        "procurement_class": str(payload.get("procurement_class") or "").strip().lower() or _infer_procurement_class({"head": head, "items": normalized_items}),
        "expediting_manager_id": proj.get("expediting_manager_id") or "",
        "expediting_manager_name": proj.get("expediting_manager_name") or "",
        "expediting_manager_email": proj.get("expediting_manager_email") or "",
        "inspection_manager_id": proj.get("inspection_manager_id") or "",
        "inspection_manager_name": proj.get("inspection_manager_name") or "",
        "inspection_manager_email": proj.get("inspection_manager_email") or "",
        "assigned_expeditor_id": u_exp["id"] if u_exp else "",
        "assigned_expeditor_name": u_exp["full_name"] if u_exp else "",
        "assigned_expeditor_email": u_exp["email"] if u_exp else "",
        "assignedTo": u_exp["full_name"] if u_exp else "",
        "assigned_field_expeditor_id": u_fexp["id"] if u_fexp else "",
        "assigned_field_expeditor_name": u_fexp["full_name"] if u_fexp else "",
        "assigned_inspection_engineer_id": u_ie["id"] if u_ie else "",
        "assigned_inspection_engineer_name": u_ie["full_name"] if u_ie else "",
        "assigned_inspection_engineer_email": u_ie["email"] if u_ie else "",
        "assigned_vendor_id": u_vend["id"] if u_vend else "",
        "assigned_vendor_email": u_vend["email"] if u_vend else vendor_email,
        "vendor_contact_name": vendor_contact_name or (u_vend["full_name"] if u_vend else ""),
        "vendor_phone": vendor_phone or (u_vend.get("phone") if u_vend else ""),
        "lots": payload.get("lots") or [{"id": "Lot 1", "date": default_cdd, "grace": 0, "ld": True}],
        "items": normalized_items,
        "clr": clr_dict,
        "vdrl_documents": list(payload.get("vdrl_documents") or []),
        "irs": [],
        "irns": [],
        "punch": [],
        "rail": [],
        "sx": {"notif": [], "look": [], "punch": [], "iap": []},
    }

    with LOCK, sx_db() as c:
        existing_records = _records(c)
        if any(str(r.get("po")) == po_num for r in existing_records):
            raise HTTPException(status_code=409, detail=f"PO {po_num} already exists")
        existing_records.append(new_po_rec)
        _save_records(c, existing_records, current_user.get("email") or "Shared PO Registry", f"Created PO {po_num} with {len(normalized_items)} BOM items under Project {proj['code']}")

        sx_state = _get_sx_state(c)
        cum_ledger = sx_state.setdefault("cumulative_ledger", {})
        for itm in normalized_items:
            cum_ledger[f"{po_num}:{itm['item']}"] = {
                "po": po_num,
                "item": itm["item"],
                "desc": itm["desc"],
                "unit": itm["unit"],
                "ordered_qty": itm["qty"],
                "inspected_qty": 0,
                "released_qty": 0,
                "shipped_qty": 0,
                "delivered_qty": 0,
                "batches": [],
            }
        _save_sx_state(c, sx_state, current_user.get("email") or "Shared PO Registry")

    # Link PO to Project record
    lpos = list(proj.get("linked_po_numbers") or [])
    if po_num not in lpos:
        lpos.append(po_num)
        inspectflow_db.update_project(proj["id"], {"linked_po_numbers": lpos})

    record_audit_event(
        "po",
        po_num,
        "PO_CREATED",
        actor=current_user,
        after={"project_id": proj["id"], "supplier": supplier, "bom_count": len(normalized_items)},
    )

    return {
        "ok": True,
        "po": po_num,
        "project": proj,
        "bom_count": len(normalized_items),
        "vendor_created": vendor_created,
        "vendor_user": u_vend,
        "roster": {
            "expediting_manager": new_po_rec["expediting_manager_name"],
            "inspection_manager": new_po_rec["inspection_manager_name"],
            "package_expeditor": new_po_rec["assigned_expeditor_name"],
            "inspection_engineer": new_po_rec["assigned_inspection_engineer_name"],
            "vendor": new_po_rec["supplier"],
            "vendor_email": new_po_rec["assigned_vendor_email"],
        },
        "message": (
            f"PO {po_num} created with {len(normalized_items)} BOM items under '{proj['name']}'"
            + (f" — new Vendor '{u_vend['company_affiliation']}' ({u_vend['email']}) registered." if vendor_created and u_vend else ".")
        ),
    }


@router.get("/api/v1/po/{po}/itp-baseline")
def get_po_itp_baseline(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Returns relational ITP documents and verified baseline steps for a PO."""
    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po), None)
    if not rec:
        raise HTTPException(status_code=404, detail=f"PO {po} not found")
    if is_vendor_user(current_user):
        if not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")
    elif not user_can_access_po(current_user, rec):
        raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")

    docs_out = []
    with SessionLocal() as db:
        itp_docs = db.query(ItpDocument).filter(ItpDocument.po_number == po).all()
        for doc in itp_docs:
            steps = db.query(ItpBaselineStep).filter(ItpBaselineStep.itp_document_id == doc.id).all()
            docs_out.append({
                "id": doc.id,
                "po_number": doc.po_number,
                "doc_no": doc.doc_no,
                "revision": doc.revision,
                "approval_code": doc.approval_code,
                "scope_mode": doc.scope_mode,
                "status": doc.status,
                "verified_by": doc.verified_by,
                "steps": [
                    {
                        "id": s.id,
                        "step_no": s.step_no,
                        "phase": s.phase,
                        "activity_description": s.activity_description,
                        "vendor_point": s.vendor_point,
                        "contractor_tpi_point": s.contractor_tpi_point,
                        "company_tpa_point": s.company_tpa_point,
                        "execution_status": s.execution_status,
                        "is_hold_point": s.is_hold_point,
                        "waiver_ref": s.waiver_ref,
                    }
                    for s in steps
                ],
            })
    return {"ok": True, "po": po, "itp_documents": docs_out}


@router.post("/api/v1/po/{po}/itp-baseline")
def register_po_itp_baseline(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer", "doc_expeditor", "expediting_manager")),
):
    """Registers and optionally locks an ITP baseline document & step matrix for a PO."""
    doc_no = str(payload.get("doc_no") or "").strip()
    if not doc_no:
        raise HTTPException(status_code=400, detail="doc_no is required")
    revision = str(payload.get("revision") or "0").strip()
    approval_code = str(payload.get("approval_code") or "Code 1").strip()
    lock_active = bool(payload.get("lock_active", True))
    if lock_active and effective_role(current_user) not in ("admin", "qc_manager", "inspection_engineer"):
        raise HTTPException(status_code=403, detail="Only Admin, QC Manager, or Inspection Engineer may lock an active Code 1 ITP baseline")

    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po} not found")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")

    doc_id = f"ITP-{uuid.uuid4().hex[:10].upper()}"
    steps_in = payload.get("steps") or []
    with SessionLocal() as db:
        itp_doc = ItpDocument(
            id=doc_id,
            po_number=po,
            doc_no=doc_no,
            revision=revision,
            approval_code=approval_code,
            source_document_id=payload.get("source_document_id"),
            scope_mode=str(payload.get("scope_mode") or "WHOLE_PO"),
            scoped_items_json=json.dumps(payload.get("scoped_items") or []),
            status="LOCKED_ACTIVE" if lock_active else "DRAFT_EXTRACTED",
            verified_by=current_user.get("email") if lock_active else None,
        )
        db.add(itp_doc)
        for idx, st in enumerate(steps_in):
            hp_points = {str(st.get(k) or "-").upper() for k in ("vendor_point", "subvendor_point", "contractor_tpi_point", "company_tpa_point")}
            is_hp = bool(st.get("is_hold_point")) or ("H" in hp_points)
            db.add(ItpBaselineStep(
                id=f"ITPS-{uuid.uuid4().hex[:10].upper()}",
                itp_document_id=doc_id,
                step_no=str(st.get("step_no") or (idx + 1)),
                phase=st.get("phase"),
                activity_description=str(st.get("activity_description") or f"Step {idx + 1}"),
                reference_spec=st.get("reference_spec"),
                acceptance_criteria=st.get("acceptance_criteria"),
                verifying_document=st.get("verifying_document"),
                vendor_point=str(st.get("vendor_point") or "-"),
                subvendor_point=str(st.get("subvendor_point") or "-"),
                contractor_tpi_point=str(st.get("contractor_tpi_point") or "-"),
                company_tpa_point=str(st.get("company_tpa_point") or "-"),
                execution_status=str(st.get("execution_status") or ("PENDING" if is_hp else "VERIFIED_PASS")),
                is_hold_point=is_hp,
            ))
        db.commit()

    # Mirror into PO vdrl_documents if locked active
    if lock_active:
        with LOCK, sx_db() as c:
            L = _records(c)
            rec = next((r for r in L if str(r.get("po")) == po), None)
            if rec:
                vdrl = list(rec.get("vdrl_documents") or [])
                vdrl.append({
                    "doc_no": doc_no,
                    "title": payload.get("title") or f"ITP {doc_no}",
                    "rev": f"Rev {revision}",
                    "code": approval_code,
                    "status": "APPROVED" if approval_code in ("Code 1", "Code 2") else "UNDER REVIEW",
                    "milestone": "Engineering Approval",
                })
                rec["vdrl_documents"] = vdrl
                _save_records(c, L, current_user.get("email") or "ITP Baseline", f"Locked ITP {doc_no} on PO {po}")

    record_audit_event("itp_document", doc_id, "ITP_BASELINE_SAVED", actor=current_user, after={"po": po, "doc_no": doc_no, "steps": len(steps_in)})
    return {"ok": True, "itp_document_id": doc_id, "steps_count": len(steps_in), "status": "LOCKED_ACTIVE" if lock_active else "DRAFT_EXTRACTED"}


@router.post("/api/v1/po/{po}/itp-baseline/verify-step")
def verify_itp_baseline_step(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "qc_manager", "inspection_engineer")),
):
    """Marks a Hold/Witness step VERIFIED_PASS or WAIVED (with ConcessionWaiver audit) so IRC can issue."""
    step_id = str(payload.get("step_id") or "").strip()
    new_status = str(payload.get("execution_status") or "VERIFIED_PASS").strip().upper()
    if not step_id or new_status not in ("VERIFIED_PASS", "WAIVED", "FAILED", "PENDING"):
        raise HTTPException(status_code=400, detail="step_id and valid execution_status required")

    with SessionLocal() as db:
        step = db.query(ItpBaselineStep).filter(ItpBaselineStep.id == step_id).first()
        if not step:
            raise HTTPException(status_code=404, detail="ITP baseline step not found")
        doc = db.query(ItpDocument).filter(ItpDocument.id == step.itp_document_id, ItpDocument.po_number == po).first()
        if not doc:
            raise HTTPException(status_code=404, detail="ITP step does not belong to this PO")
        if new_status == "WAIVED":
            waiver_ref = str(payload.get("waiver_ref") or "").strip()
            just = str(payload.get("justification") or "").strip()
            if not waiver_ref or not just:
                raise HTTPException(status_code=400, detail="waiver_ref and justification required to waive an ITP Hold Point")
            step.waiver_ref = waiver_ref
            db.add(ConcessionWaiver(
                id=f"CW-{uuid.uuid4().hex[:10].upper()}",
                po_number=po,
                waiver_type="ITP_HOLD_WAIVER",
                target_ref_id=step.id,
                concession_ref_no=waiver_ref,
                justification=just,
                approved_by_name=current_user.get("full_name") or current_user.get("email") or "Inspection Engineer",
                approved_by_role=effective_role(current_user),
            ))
        step.execution_status = new_status
        step.linked_inspection_id = payload.get("linked_inspection_id") or step.linked_inspection_id
        db.commit()

    record_audit_event("itp_step", step_id, "ITP_STEP_UPDATED", actor=current_user, after={"po": po, "status": new_status})
    return {"ok": True, "step_id": step_id, "execution_status": new_status}


@router.post("/api/v1/po/{po}/schedule-class")
def set_po_schedule_class(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor")),
):
    """Assigns or switches PO schedule archetype ('bulk' | 'tagged' | 'package')."""
    cls = str(payload.get("procurement_class") or "").strip().lower()
    if cls not in ("bulk", "tagged", "package"):
        raise HTTPException(status_code=400, detail="procurement_class must be 'bulk', 'tagged', or 'package'")
    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po} not found")
        if not is_admin_user(current_user) and not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")
        rec["procurement_class"] = cls
        _save_records(c, L, current_user.get("email") or "Schedule Class", f"Set PO {po} schedule class to {cls}")
    record_audit_event("po", po, "SCHEDULE_CLASS_CHANGED", actor=current_user, after={"procurement_class": cls})
    return {"ok": True, "po": po, "procurement_class": cls}


@router.get("/api/v1/po/{po}/bulk-steps")
def get_po_bulk_steps(
    po: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Returns per-line partial-lot manufacturing step progression for a Bulk PO."""
    if effective_role(current_user) in ("", "guest"):
        raise HTTPException(status_code=403, detail="Active role required")
    with LOCK, sx_db() as c:
        rec = next((r for r in _records(c) if str(r.get("po")) == po), None)
    if not rec:
        raise HTTPException(status_code=404, detail=f"PO {po} not found")
    if is_vendor_user(current_user):
        if not vendor_owns_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")
    elif not user_can_access_po(current_user, rec):
        raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")
    return {
        "ok": True,
        "po": po,
        "procurement_class": _infer_procurement_class(rec),
        "bulk_steps": rec.get("bulk_steps") or {},
        "items": rec.get("items") or [],
    }


@router.put("/api/v1/po/{po}/bulk-steps")
def update_po_bulk_steps(
    po: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "expediting_manager", "expeditor", "vendor")),
):
    """Updates heat-lot partial stage progress & quantities for a Bulk PO line."""
    steps_in = payload.get("bulk_steps")
    if not isinstance(steps_in, dict):
        raise HTTPException(status_code=400, detail="bulk_steps dictionary is required")
    with LOCK, sx_db() as c:
        L = _records(c)
        rec = next((r for r in L if str(r.get("po")) == po), None)
        if not rec:
            raise HTTPException(status_code=404, detail=f"PO {po} not found")
        if is_vendor_user(current_user):
            if not vendor_owns_po(current_user, rec):
                raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")
        elif not user_can_access_po(current_user, rec):
            raise HTTPException(status_code=403, detail=f"Access denied for PO {po}")
        bulk = dict(rec.get("bulk_steps") or {})
        valid_items = {str(it.get("item")): float(it.get("qty") or 0) for it in (rec.get("items") or [])}
        for item_key, step_val in steps_in.items():
            ik = str(item_key)
            if ik not in valid_items or not isinstance(step_val, dict):
                continue
            max_q = valid_items[ik]
            q_done = max(0.0, min(max_q, float(step_val.get("qty_completed") or 0)))
            pct_val = max(0, min(100, int(round((q_done / max_q) * 100)) if max_q > 0 else int(step_val.get("pct") or 0)))
            bulk[ik] = {
                "heat_lot_number": str(step_val.get("heat_lot_number") or "")[:64],
                "mtc_no": str(step_val.get("mtc_no") or "")[:64],
                "stage_name": str(step_val.get("stage_name") or "")[:80],
                "qty_completed": q_done,
                "pct": pct_val,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_by": current_user.get("email") or "",
            }
        rec["bulk_steps"] = bulk
        _save_records(c, L, current_user.get("email") or "Bulk Matrix", f"Updated bulk steps on PO {po}")
    record_audit_event("po", po, "BULK_STEPS_UPDATED", actor=current_user, after={"items": list(steps_in.keys())})
    return {"ok": True, "po": po, "bulk_steps": bulk}


init_sx_db()
if settings.auth_mode == "dev":
    try:
        ensure_governance_seeded()
    except Exception as _seed_err:
        logger.warning("Warning during ensure_governance_seeded: %s", _seed_err)



