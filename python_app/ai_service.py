import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)


def get_gemini_api_key() -> str:
    return (
        os.environ.get("VITE_GEMINI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or ""
    ).strip()


def _repair_and_parse_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for suffix in ["]}", '"}', '"}]}', "}]}"]:
            try:
                return json.loads(text + suffix)
            except Exception:
                pass
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


def call_gemini_with_pdf(pdf_bytes: bytes, prompt: str, mime_type: str = "application/pdf") -> Dict[str, Any]:
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY / VITE_GEMINI_API_KEY is not configured in .env or .env.local")

    b64_data = base64.b64encode(pdf_bytes).decode("utf-8")
    safe_prompt = (
        prompt
        + "\n\nCRITICAL: Keep 'description' and 'remarks' fields concise to avoid exceeding response lengths. "
        "Ensure the output is well-formed JSON."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"inlineData": {"mimeType": mime_type, "data": b64_data}},
                    {"text": safe_prompt},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.95,
            "topK": 40,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }

    delay = 1.5
    last_err = None
    for attempt in range(4):
        resp = requests.post(url, json=payload, timeout=90)
        if resp.status_code in (429, 503) and attempt < 3:
            time.sleep(delay)
            delay *= 2
            continue
        if not resp.ok:
            last_err = f"Gemini API Error {resp.status_code}: {resp.text}"
            break
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("No candidates returned from Gemini API")
        parts = candidates[0].get("content", {}).get("parts") or []
        text = parts[0].get("text", "") if parts else ""
        if not text:
            raise RuntimeError("Empty response text from Gemini API")
        return _repair_and_parse_json(text)

    raise RuntimeError(last_err or "Failed to call Gemini API")


def extract_inspection_notification(pdf_bytes: bytes, filename: str = "notification.pdf") -> Dict[str, Any]:
    prompt = """You are an expert at extracting information from industrial inspection notification documents.

Extract ALL the following information from this Inspection Notification PDF and return it as a JSON object.
Be EXTREMELY thorough and detailed. Extract every piece of information, even if it seems minor.

{
  "po_number": "Purchase Order number",
  "notification_number": "Notification/Inspection reference number",
  "notification_revision": "Revision or version number of the notification (e.g., Rev 0, Rev A, V1.2)",
  "notification_receipt_date": "CRITICAL: This is ALWAYS the FIRST DATE that appears on the TOP LEFT of the document (usually labeled 'Date'). Extract this date in ISO format YYYY-MM-DD. This is NOT an inspection date.",
  "supplier_name": "Name of the supplier to whom the PO is issued",
  "subsupplier_name": "Manufacturer or sub-supplier name (may be same as supplier)",
  "vendor_contact_name": "Contact person name at vendor/manufacturer",
  "vendor_contact_phone": "Contact phone number",
  "vendor_contact_email": "Contact email address",
  "country": "Country where inspection will take place",
  "inspection_location": "Complete address or location for the inspection",
  "latitude": "Latitude coordinate if mentioned (decimal format)",
  "longitude": "Longitude coordinate if mentioned (decimal format)",
  "start_date": "Earliest inspection date in ISO format (YYYY-MM-DD)",
  "end_date": "Latest inspection date in ISO format (YYYY-MM-DD)",
  "all_inspection_dates": "Consolidated string of ALL inspection dates mentioned, including from tables/schedules",
  "inspection_time": "General time of inspection (e.g., '10:00 AM', '09:00-17:00')",
  "po_description": "Description of the Purchase Order",
  "inspection_type": "Type of inspection (e.g., Building, Fire Safety, Health, Pre-shipment, Final, etc.)",
  "items_being_offered": [
    {
      "itemNumber": "PO item number",
      "description": "Full item description with specifications",
      "quantity": "Quantity with unit (e.g., '5 EA', '100 KG', '50 meters')"
    }
  ],
  "inspection_activities": [
    {
      "date": "Date of the activity (YYYY-MM-DD)",
      "time": "Time of the activity",
      "itp_step": "ITP Step Number or reference",
      "activity": "Description of the activity or test",
      "supplier": "Supplier intervention (W=Witness, H=Hold, R=Review, or blank)",
      "contractor": "Contractor intervention (W/H/R or blank)",
      "company_tpa": "Company/TPA intervention (W/H/R or blank)",
      "remarks": "Any remarks or notes for this activity"
    }
  ],
  "notes": "Any additional relevant notes, special instructions, or requirements from the notification"
}

CRITICAL EXTRACTION RULES:
1. Return ONLY valid JSON, no markdown or code blocks
2. Use null for fields that don't exist in the document
3. All dates MUST be in YYYY-MM-DD format
4. If table has more than 20 items, ONLY extract the first 20 items.
5. For inspection_activities, extract up to the first 20 rows from ITP (Inspection Test Plan) tables.
6. Include intervention points exactly as shown (W, H, R, or combinations like W/H)
7. Keep all "description" text concise (under 15 words).
"""
    return call_gemini_with_pdf(pdf_bytes, prompt)


def extract_inspection_report(
    pdf_bytes: bytes, filename: str = "report.pdf", report_type: str = "Flash"
) -> Dict[str, Any]:
    prompt = f"""You are an expert at analyzing industrial inspection reports and quality control documents.

MISSION: Extract ALL findings, non-conformances (NCRs), observations, defects, issues, problems, concerns, and test results from this {report_type} report PDF.

Return the information as a JSON object with this EXACT structure:

{{
  "report_summary": "Brief summary of the inspection report",
  "inspection_date": "Date of inspection in YYYY-MM-DD format",
  "inspector_name": "Name of inspector who conducted the inspection",
  "overall_result": "Overall result: PASS, FAIL, or CONDITIONAL",
  "findings": [
    {{
      "id": "Unique identifier from document (e.g., NCR-001, OBS-001, Finding #1)",
      "type": "Classification: Non-conformance, NCR, Observation, Concern, Defect, etc.",
      "severity": "Impact level: Critical, Major, Minor, or null if not specified",
      "description": "Detailed description of what was found",
      "item_reference": "Specific item number, clause, section, or ITP step reference",
      "location": "Location/area where finding was observed",
      "requirement_reference": "Reference to requirement/standard/specification violated",
      "corrective_action_required": "Required corrective action or remediation",
      "status": "Open or Closed"
    }}
  ],
  "test_results": [
    {{
      "test_name": "Name of test performed",
      "result": "Result value or outcome",
      "unit": "Unit of measurement",
      "specification": "Required specification/acceptance criteria",
      "status": "pass or fail"
    }}
  ],
  "recommendations": "General recommendations from inspector",
  "next_steps": "Recommended next steps or follow-up actions"
}}
"""
    return call_gemini_with_pdf(pdf_bytes, prompt)


def chat_with_assistant(
    user_message: str,
    inspections: List[Dict[str, Any]],
    inspectors: List[Dict[str, Any]],
    agencies: List[Dict[str, Any]],
) -> str:
    api_key = get_gemini_api_key()
    if not api_key:
        return "⚠️ Gemini API key is not configured in `.env` / `.env.local`."

    summary_context = {
        "total_inspections": len(inspections),
        "total_inspectors": len(inspectors),
        "total_agencies": len(agencies),
        "inspections": [
            {
                "notification_number": i.get("notification_number"),
                "po_number": i.get("po_number"),
                "supplier_name": i.get("supplier_name"),
                "country": i.get("country"),
                "status": i.get("status"),
                "start_date": i.get("start_date"),
                "end_date": i.get("end_date"),
                "assigned_inspector": i.get("assigned_inspector_name"),
                "tpi_agency": i.get("tpi_agency"),
                "open_ncrs": i.get("open_ncrs_count"),
                "total_findings": i.get("total_findings_count"),
                "po_description": i.get("po_description"),
            }
            for i in inspections[:50]
        ],
        "inspectors": [
            {
                "name": insp.get("full_name"),
                "email": insp.get("email"),
                "specialization": insp.get("specialization"),
                "company": insp.get("company"),
                "status": insp.get("status"),
            }
            for insp in inspectors[:30]
        ],
    }

    system_prompt = (
        "You are InspectFlow AI, an intelligent Quality Control & Inspection Management assistant.\n"
        "Use the live database context below to answer the user's question accurately, concisely, "
        "and formatted in clean Markdown.\n\n"
        f"LIVE DATABASE CONTEXT:\n{json.dumps(summary_context, indent=2)}\n\n"
        f"USER QUESTION: {user_message}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": system_prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }
    try:
        resp = requests.post(url, json=payload, timeout=45)
        if not resp.ok:
            return f"⚠️ Gemini API Error ({resp.status_code}): {resp.text}"
        data = resp.json()
        return (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "No response generated.")
        )
    except Exception as exc:
        return f"⚠️ Error contacting Gemini AI: {exc}"


def _sanitize_prompt_name(val: str, default: str = "document.pdf") -> str:
    clean = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(val or default).name)
    return clean[:120] or default


def extract_schedule_with_gemini(
    pdf_bytes: bytes,
    filename: str = "schedule.pdf",
    procurement_class: str = "tagged",
) -> Dict[str, Any]:
    """Extract structured manufacturing/execution schedule milestones from any PDF (text, Gantt, or scanned)."""
    safe_fname = _sanitize_prompt_name(filename, "schedule.pdf")
    cls_norm = str(procurement_class or "tagged").strip().lower()
    archetype_note = {
        "bulk": "This PO is BULK MATERIALS: capture commodity batch/heat-lot milestones (Raw Material Mill Receipt, Forming/Threading, Heat Treatment, Lab/3.1 MTC, Coating, Final Inspection/IRN, Packing/EXW).",
        "package": "This PO is an ENGINEERED PACKAGE: capture Master Package WBS activities, Sub-Assembly fabrication splits, Bought-Out Sub-Orders, Integration/Skid Assembly, and Integrated FAT (IFAT).",
        "tagged": "This PO is TAGGED EQUIPMENT: capture per-Tag engineering/VDRL approvals, PIM, castings/forgings, Hydro/NDT, FAT, IRN, and Ex-Works Delivery.",
    }.get(cls_norm, "")
    prompt = f"""You are an expert EPC expediting and project controls planner.
{archetype_note}
Read EVERY schedule activity / milestone row in this attached vendor manufacturing or execution schedule PDF ("{safe_fname}").
It may be a scanned image, rotated landscape table, MS Project / Primavera P6 printout, or Excel-exported PDF with multi-line wrapped cells or N/A rows.

Return ONLY a valid JSON object matching this exact schema:
{{
  "po_date": "YYYY-MM-DD or null",
  "target_delivery": "YYYY-MM-DD or null",
  "activities": [
    {{
      "id": "Sr or task ID string (e.g. '1', '2')",
      "act": "Clean activity/milestone description (without responsible party or numbers)",
      "bS": "Baseline Start date in YYYY-MM-DD, or empty string '' if N/A/missing",
      "bE": "Baseline Finish/End date in YYYY-MM-DD, or empty string '' if N/A/missing",
      "fS": "Forecast Start date in YYYY-MM-DD, or empty string '' if N/A/missing",
      "fE": "Forecast Finish/End date in YYYY-MM-DD, or empty string '' if N/A/missing",
      "pct": "Completion percentage as integer string 0..100 (e.g. '100', '0'), or '' if missing"
    }}
  ]
}}

RULES:
1. Convert ALL dates (e.g., 21/11/2026, 21-Nov-26) strictly to YYYY-MM-DD (DD/MM/YYYY interpretation when day > 12 or standard EPC international dates; verify consistency across rows!).
2. Keep EVERY dated activity row (do not skip any activity that has baseline or forecast dates). Skip purely N/A rows with no dates.
3. Combine multi-line activity descriptions cleanly (e.g. "Drg, Datasheet, ITP, SVL, Schedule submission", "Delivered at destination (for DDP/DDU/DAP)").
4. Do NOT include Responsible/Vendor/NMDC/Duration/Dependency columns inside "act".
5. If only Forecast OR only Baseline dates are given, populate fS/fE from whichever pair is available.
"""
    raw = call_gemini_with_pdf(pdf_bytes, prompt)
    activities_out: List[Dict[str, str]] = []
    for item in raw.get("activities") or []:
        if not isinstance(item, dict):
            continue
        act = str(item.get("act") or "").strip()
        bS = str(item.get("bS") or "").strip()[:10]
        bE = str(item.get("bE") or "").strip()[:10]
        fS = str(item.get("fS") or bS or "").strip()[:10]
        fE = str(item.get("fE") or bE or fS or "").strip()[:10]
        if not act or not (bS or bE or fS or fE):
            continue
        pct_raw = str(item.get("pct") or "").replace("%", "").strip()
        activities_out.append(
            {
                "id": str(item.get("id") or "").strip(),
                "act": act,
                "duration_days": str(item.get("duration_days") or item.get("dur") or "").strip(),
                "bS": bS,
                "bE": bE,
                "fS": fS,
                "fE": fE,
                "dependency": str(item.get("dependency") or item.get("dep") or "").strip(),
                "pct": pct_raw,
            }
        )
    return {
        "po_date": raw.get("po_date"),
        "target_delivery": raw.get("target_delivery"),
        "activities": activities_out,
    }


def _call_gemini_text_json(prompt: str, max_tokens: int = 4096) -> Dict[str, Any]:
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.15,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    resp = requests.post(url, json=payload, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Gemini API Error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    if not text:
        raise RuntimeError("Empty response text from Gemini API")
    return _repair_and_parse_json(text)


def analyze_po_and_mr(
    pdf_bytes: Optional[bytes] = None,
    filename: str = "PO_MR.pdf",
    po_context_text: str = "",
    po_number: str = "",
    mr_ref: str = "",
) -> Dict[str, Any]:
    """
    Workflow Action #2 AI Agent: Reviews Purchase Order & Material Requisition (MR)
    to extract Technical Requirements, BOM Matrix, HOLDs, Optional Scope, Design Inputs,
    HAZOP/SIL, PIM, Document/SDRL Requirements, PBG, and LC Terms.
    Falls back gracefully to deterministic extraction if no Gemini key or PDF is provided.
    """
    safe_fn = _sanitize_prompt_name(filename, "PO_MR.pdf")
    schema_prompt = f"""You are a Senior EPC Procurement & Expediting Engineer reviewing PO '{po_number}' (MR '{mr_ref}', file '{safe_fn}').
Analyze the PO and Material Requisition (MR) requirements and extract ALL key points for Expediting and Inspection execution.
Context summary (if any):
{po_context_text[:6000]}

Return STRICT valid JSON matching this schema:
{{
  "technical_requirements": ["string"],
  "bom_summary": [{{"item": "string", "desc": "string", "qty": "string", "tag": "string"}}],
  "holds": ["Technical/Commercial/Inspection HOLD points"],
  "optional_scope": ["Optional scope items or priced options"],
  "design_inputs": ["Vendor engineering design inputs required before fabrication"],
  "hazop_sil": {{"required": true, "notes": "string"}},
  "pim_required": {{"required": true, "notes": "Pre-Inspection Meeting trigger & timing"}},
  "doc_requirements": ["Key SDRL/VDRL deliverable obligations and submission timelines"],
  "pbg_required": {{"required": true, "terms": "Performance Bank Guarantee terms or N/A"}},
  "lc_requirement": {{"required": true, "terms": "Letter of Credit / payment terms"}},
  "checklist_flags": {{
    "Technical requirements": true,
    "BOM matrix": true,
    "HOLDs": true,
    "Optional scope": false,
    "Design inputs": true,
    "HAZOP": false,
    "SIL": false,
    "PIM": true,
    "Document requirements": true,
    "PBG": false,
    "LC requirement": false
  }},
  "expeditor_risk_notes": "Concise 2-4 sentence summary of critical risks and first actions."
}}"""

    engine = "deterministic-fallback"
    parsed: Dict[str, Any] = {}
    if get_gemini_api_key():
        try:
            if pdf_bytes and len(pdf_bytes) > 50:
                parsed = call_gemini_with_pdf(pdf_bytes, schema_prompt)
            else:
                parsed = _call_gemini_text_json(schema_prompt)
            engine = "gemini-2.5-flash"
        except Exception:
            parsed = {}

    if not parsed:
        lower_txt = po_context_text.lower()
        hazop = ("hazop" in lower_txt) or ("sil" in lower_txt)
        pbg = "pbg" in lower_txt or "performance bank" in lower_txt
        lc = "letter of credit" in lower_txt or " lc " in f" {lower_txt} "
        parsed = {
            "technical_requirements": [
                f"Verify compliance with MR {mr_ref or po_number} Technical Specification, ITP, and NEAS delivery terms.",
                "Confirm positive material identification (PMI), NDT, and nameplate traceability per BOM tags.",
            ],
            "bom_summary": [],
            "holds": ["Hold fabrication release pending Code 1/Code 2 ITP, GA Drawings, and Sub-Order approval."],
            "optional_scope": ["Check PO commercial annexure for optional commissioning spares / 2-year spares (SPIR)."],
            "design_inputs": ["Verify client-furnished Foundation Loads, Utility interface data, and P&ID markups."],
            "hazop_sil": {"required": hazop, "notes": "HAZOP/SIL compliance flagged for engineered safety instrumentation." if hazop else "Confirm whether SIL/HAZOP closeout actions impact skid instrumentation."},
            "pim_required": {"required": True, "notes": "Schedule PIM at supplier works prior to sub-order release / fabrication start."},
            "doc_requirements": ["Submit SDRL/VDRL deliverables, 9-col Baseline Schedule (Z003), and Sub-Order Plan (Z002) within 14 days."],
            "pbg_required": {"required": pbg, "terms": "Verify PBG submission with Buyer/Finance before advance payment milestone." if pbg else "Confirm with Buyer if PBG applies per PO commercial terms."},
            "lc_requirement": {"required": lc, "terms": "Track LC opening/expiry vs CDD window." if lc else "Confirm payment term milestone triggers (Advance / IRN / MRV)."},
            "checklist_flags": {
                "Technical requirements": True,
                "BOM matrix": True,
                "HOLDs": True,
                "Optional scope": False,
                "Design inputs": True,
                "HAZOP": hazop,
                "SIL": hazop,
                "PIM": True,
                "Document requirements": True,
                "PBG": pbg,
                "LC requirement": lc,
            },
            "expeditor_risk_notes": f"PO {po_number} reviewed against MR {mr_ref or 'baseline'}. Prioritize unconditional PO acknowledgement, SDRL/Schedule submission, and PIM alignment.",
        }

    parsed["engine"] = engine
    return parsed


def draft_first_expediting_contact(
    po_rec: Dict[str, Any],
    mr_review: Optional[Dict[str, Any]] = None,
    project_rec: Optional[Dict[str, Any]] = None,
    expeditor_name: str = "Package Expeditor",
) -> Dict[str, Any]:
    """
    Workflow Action #3 AI Agent: Drafts the First Expediting Contact email/letter
    combining PO/NEAS metadata, Action #2 MR findings, and VDMS/Schedule expectations.
    """
    po_num = str(po_rec.get("po") or "")
    supplier = po_rec.get("supplier") or po_rec.get("supplierShort") or "Vendor"
    head = po_rec.get("head") or "Equipment / Material Supply"
    proj_name = (project_rec or {}).get("name") or po_rec.get("project") or ""
    proj_code = (project_rec or {}).get("code") or po_rec.get("project_code") or ""
    contract_no = po_rec.get("contract_no") or ""
    cdd = po_rec.get("cdd_date") or ((po_rec.get("lots") or [{}])[0].get("date") if po_rec.get("lots") else "") or "Per PO"
    ros = po_rec.get("ros_date") or "Per Project Schedule"
    platform = po_rec.get("platform") or "Project Facilities"
    despatch = po_rec.get("despatch_location") or po_rec.get("deliveryPoint") or "Site Stores"
    incoterm = po_rec.get("incoterm") or "Per PO"
    mr_ref = po_rec.get("mrRef") or ""

    highlights = []
    if isinstance(mr_review, dict):
        highlights.extend((mr_review.get("holds") or [])[:3])
        highlights.extend((mr_review.get("doc_requirements") or [])[:2])
        if (mr_review.get("pim_required") or {}).get("required"):
            highlights.append("Pre-Inspection Meeting (PIM) required prior to fabrication start.")

    engine = "template-fallback"
    if get_gemini_api_key():
        prompt = f"""You are a Lead EPC Package Expeditor ({expeditor_name}).
Draft a crisp, professional First Expediting Contact email/letter to Vendor '{supplier}' for Purchase Order '{po_num}' ({head}).
Include:
- Project: [{proj_code}] {proj_name} | Client Contract: {contract_no or 'N/A'} | MR: {mr_ref}
- Contractual Terms: Incoterm={incoterm}, CDD={cdd}, ROS={ros}, Platform={platform}, Despatch Location={despatch}
- Specific technical/MR obligations from Action #2 review: {json.dumps(highlights)}
- Mandatory immediate vendor submissions on Portal:
  1. Unconditional PO Acknowledgement
  2. Vendor Data Register / SDRL Submission & VDMS onboarding check
  3. 9-Column Manufacturing Schedule (23 Minimum Activities + ITP Witness/Hold points + Sub-Orders)
  4. Unpriced Sub-Order PO copies & Kick-Off Meeting (KOM) readiness dates

Return strict JSON:
{{
  "subject": "string",
  "body": "string (clean email text with numbered action list)",
  "action_items": ["short bullet strings"]
}}"""
        try:
            res = _call_gemini_text_json(prompt, max_tokens=2048)
            if res.get("subject") and res.get("body"):
                res["engine"] = "gemini-2.5-flash"
                return res
        except Exception:
            pass

    subject = f"First Expediting Contact — PO {po_num} ({head}) | {proj_code or 'EPC Project'}"
    bullets = [
        f"Submit unconditional PO Acknowledgement (or highlight any commercial/technical points for immediate Buyer resolution).",
        f"Submit 9-Column Baseline Schedule matching all 23 minimum milestones, including ITP Witness/Hold points and critical sub-orders.",
        f"Submit SDRL / VDRL deliverables (Drawings, Datasheets, ITP, SVL) via VDMS per schedule.",
        f"Provide Kick-Off Meeting (KOM) & Pre-Inspection Meeting (PIM) proposed dates via MS Teams / Supplier Works.",
        f"Upload unpriced PO copies for critical sub-orders and track monthly NMDC 7-section Progress Report + Sub-Order Status.",
    ]
    if highlights:
        bullets.extend(highlights[:3])
    body = (
        f"Dear {supplier} Project Team,\n\n"
        f"Congratulations on the award of Purchase Order {po_num} for {head} under Project [{proj_code}] {proj_name}.\n\n"
        f"Key Order Parameters (NEAS Reference):\n"
        f"- Material Requisition (MR): {mr_ref or 'As per PO'}\n"
        f"- Delivery Terms: {incoterm} | Despatch Location: {despatch} | Platform/Unit: {platform}\n"
        f"- Contractual Delivery Date (CDD): {cdd} | Required On Site (ROS): {ros}\n\n"
        f"Kindly prioritize the following actions within 7 calendar days:\n"
        + "\n".join(f"{idx+1}. {b}" for idx, b in enumerate(bullets))
        + f"\n\nDocument Controller is issuing your VDMS templates and portal access concurrently.\n\nBest regards,\n{expeditor_name}\nPackage Expediting"
    )
    return {
        "subject": subject,
        "body": body,
        "action_items": bullets,
        "engine": engine,
    }


