"""
SmartExpedit Deterministic Excel & AI Schedule / Sub-Order Parsers
===================================================================
Implements §9 of the SmartExpedit Functional & Technical Guide:
- parse_excel_schedule(file_bytes): Deterministic openpyxl parser supporting:
  1. Cable / Tag Status Mode (`tagnumber` + `complitiondate`/`completiondate` or `tentativeinspectiondate`)
  2. Activity Schedule Mode (`activityname`/`taskname` + baseline/current/actual start & finish)
- parse_vendor_schedule_file(...): Excel first, PDF/other fallback via Gemini AI, upserts on (po_id, activity_code)
- parse_suborder_report_file(...): Sub-order status extraction + calc_float() + save_suborder()
"""

import io
import re
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

import openpyxl

from python_app.epc_constants import WBS_CATEGORIES, calc_float
from python_app import expediting_db
from python_app.ai_service import call_gemini_with_pdf


MAX_SHEETS = 20
MAX_ROWS_PER_SHEET = 5000
MAX_ACTIVITIES = 500

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _norm_header(val: Any) -> str:
    """Strip non-alphanumeric characters and lowercase."""
    if val is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(val).lower())


def parse_flexible_date(val: Any) -> Optional[str]:
    """
    Accepts datetime/date objects, Excel serial numbers, ISO strings YYYY-MM-DD,
    D/M/YYYY or M/D/YYYY, and DD-Mon-YYYY or DD Mon YYYY.
    Returns YYYY-MM-DD or None. Out-of-range years (<1990 or >2100) are rejected.
    """
    if val is None or val == "" or str(val).strip() in ("-", "—", "N/A", "TBA", "TBD", "None"):
        return None

    if isinstance(val, datetime):
        d = val.date()
        return d.isoformat() if 1990 <= d.year <= 2100 else None
    if isinstance(val, date):
        return val.isoformat() if 1990 <= val.year <= 2100 else None

    # Excel serial number
    if isinstance(val, (int, float)):
        if 32874 <= val <= 76700:  # roughly 1990 to 2100
            try:
                base = date(1899, 12, 30)
                d = base + timedelta(days=int(val))
                if 1990 <= d.year <= 2100:
                    return d.isoformat()
            except Exception:
                return None
        return None

    s = str(val).strip()
    if not s:
        return None

    # ISO YYYY-MM-DD (or YYYY-MM-DDTHH:MM:SS)
    m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m_iso:
        y, mo, da = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if 1990 <= y <= 2100:
            try:
                return date(y, mo, da).isoformat()
            except ValueError:
                return None

    # DD-Mon-YYYY or DD Mon YYYY or DD-Mon-YY
    m_mon = re.match(r"^(\d{1,2})[\s\-/]+([A-Za-z]{3,9})[\s\-/,]+(\d{2,4})$", s)
    if m_mon:
        da = int(m_mon.group(1))
        mon_str = m_mon.group(2)[:3].lower()
        y = int(m_mon.group(3))
        if y < 100:
            y += 2000
        mo = MONTH_MAP.get(mon_str)
        if mo and 1990 <= y <= 2100:
            try:
                return date(y, mo, da).isoformat()
            except ValueError:
                return None

    # D/M/YYYY or M/D/YYYY
    m_slash = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", s)
    if m_slash:
        a, b, y = int(m_slash.group(1)), int(m_slash.group(2)), int(m_slash.group(3))
        if y < 100:
            y += 2000
        if 1990 <= y <= 2100:
            # Prefer D/M/YYYY unless b > 12 and a <= 12
            if a > 12 and b <= 12:
                da, mo = a, b
            elif b > 12 and a <= 12:
                mo, da = a, b
            else:
                da, mo = a, b
            try:
                return date(y, mo, da).isoformat()
            except ValueError:
                return None

    return None


def _is_excel_bytes(file_bytes: bytes, filename: str = "") -> bool:
    """Detect .xlsx (PK\\x03\\x04) vs unsupported legacy .xls binary."""
    if file_bytes[:4] == b"\xd0\xcf\x11\xe0":
        raise ValueError("Legacy binary .xls files are not supported. Please save the workbook as .xlsx and upload again.")
    if file_bytes[:4] == b"PK\x03\x04":
        return True
    lower = (filename or "").lower()
    if lower.endswith(".xls"):
        raise ValueError("Legacy binary .xls files are not supported. Please save the workbook as .xlsx and upload again.")
    return lower.endswith(".xlsx") or lower.endswith(".xlsm")


def build_sample_schedule_excel(po_number: str) -> bytes:
    """Generates a ready-to-upload sample Excel workbook with both Activity & Cable/Tag sheets."""
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Level3_Schedule"
    ws1.append([
        "Activity Code", "Activity Name", "WBS Category",
        "Baseline Start", "Baseline Finish",
        "Current Start", "Current Finish",
        "Percent Complete", "Critical"
    ])
    base = date.today() - timedelta(days=30)
    sample_rows = [
        ("STD-01", "Kick-Off Meeting (KOM)", "ENGINEERING", -25, -24, -25, -24, 100, "Yes"),
        ("STD-02", "GAD & Datasheet Submission", "ENGINEERING", -20, -10, -18, -8, 100, "Yes"),
        ("STD-05", "Sub-PO Placement (Forgings & Body)", "PROCUREMENT", -10, 0, -5, 5, 90, "Yes"),
        ("STD-10", "Raw Material Receipt & Mill Cert Review (NOI)", "PROCUREMENT", 1, 8, 5, 12, 50, "Yes"),
        ("STD-11", "Machining & Body Assembly", "FABRICATION", 9, 25, 13, 30, 25, "Yes"),
        ("STD-16", "Hydrostatic & Seat Leakage Test - FAT (NOI)", "TESTING", 26, 32, 31, 37, 0, "Yes"),
        ("STD-18", "Final Inspection & Release Note - IRN (NOI)", "TESTING", 33, 38, 38, 42, 0, "Yes"),
        ("STD-22", "Ex-Works Dispatch & Shipping", "SHIPPING", 39, 48, 43, 52, 0, "Yes"),
    ]
    for code, name, cat, bs, bf, cs, cf, pct, crit in sample_rows:
        ws1.append([
            code, name, cat,
            (base + timedelta(days=bs)).isoformat(),
            (base + timedelta(days=bf)).isoformat(),
            (base + timedelta(days=cs)).isoformat(),
            (base + timedelta(days=cf)).isoformat(),
            pct, crit
        ])

    ws2 = wb.create_sheet("Cable_Tag_Status")
    ws2.append(["SAP Code", "Tag Number", "Description", "Completion Date", "Tentative Inspection Date"])
    ws2.append(["SAP-8801", f"{po_number}-TAG-01", "8-inch Ball Valve Assembly", (base + timedelta(days=20)).isoformat(), (base + timedelta(days=28)).isoformat()])
    ws2.append(["SAP-8802", f"{po_number}-TAG-02", "12-inch Check Valve Assembly", (base + timedelta(days=26)).isoformat(), (base + timedelta(days=34)).isoformat()])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_excel_schedule(file_bytes: bytes) -> Dict[str, Any]:
    """
    Deterministic Excel schedule parser (§9.2 of SmartExpedit Guide).
    Returns:
      {
        "activities": [...],
        "warnings": [...],
        "sheetSummary": [...]
      }
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet_names = wb.sheetnames[:MAX_SHEETS]
    warnings: List[str] = []
    if len(wb.sheetnames) > MAX_SHEETS:
        warnings.append(f"Workbook has {len(wb.sheetnames)} sheets; only the first {MAX_SHEETS} were scanned.")

    activities: List[Dict[str, Any]] = []
    sheet_summary: List[Dict[str, Any]] = []
    seq_counter = 1

    for sheet_idx, sheet_name in enumerate(sheet_names, start=1):
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))[:MAX_ROWS_PER_SHEET]
        if not rows:
            sheet_summary.append({"sheet": sheet_name, "mode": "EMPTY", "extracted": 0})
            continue

        # Scan first 30 rows to locate header row
        header_row_idx = None
        header_map: Dict[str, int] = {}
        mode = None

        for r_idx, row in enumerate(rows[:30]):
            norm_cols = { _norm_header(val): c_idx for c_idx, val in enumerate(row) if _norm_header(val) }
            if "tagnumber" in norm_cols and (
                "complitiondate" in norm_cols
                or "completiondate" in norm_cols
                or "tentativeinspectiondate" in norm_cols
            ):
                header_row_idx = r_idx
                header_map = norm_cols
                mode = "CABLE_TAG"
                break
            if any(
                k in norm_cols
                for k in (
                    "activityname",
                    "taskname",
                    "activitydescription",
                    "milestonename",
                    "activity",
                )
            ):
                header_row_idx = r_idx
                header_map = norm_cols
                mode = "ACTIVITY"
                break

        if header_row_idx is None or mode is None:
            sheet_summary.append({"sheet": sheet_name, "mode": "SKIPPED", "extracted": 0})
            continue

        extracted_in_sheet = 0
        today_iso = date.today().isoformat()

        if mode == "CABLE_TAG":
            tag_col = header_map.get("tagnumber")
            sap_col = header_map.get("sapcode") or header_map.get("itemcode")
            desc_col = header_map.get("description") or header_map.get("cabledescription")
            comp_col = header_map.get("complitiondate") if "complitiondate" in header_map else header_map.get("completiondate")
            insp_col = header_map.get("tentativeinspectiondate")

            for r_idx in range(header_row_idx + 1, len(rows)):
                if len(activities) >= MAX_ACTIVITIES:
                    warnings.append(f"Reached {MAX_ACTIVITIES} milestone cap; remaining rows truncated.")
                    break
                row = rows[r_idx]
                tag_val = str(row[tag_col]).strip() if tag_col is not None and tag_col < len(row) and row[tag_col] is not None else ""
                if not tag_val or tag_val.lower() in ("none", "total", "grand total"):
                    continue
                sap_val = str(row[sap_col]).strip() if sap_col is not None and sap_col < len(row) and row[sap_col] is not None else "NOSAP"
                desc_val = str(row[desc_col]).strip() if desc_col is not None and desc_col < len(row) and row[desc_col] is not None else ""

                comp_date = parse_flexible_date(row[comp_col]) if comp_col is not None and comp_col < len(row) else None
                insp_date = parse_flexible_date(row[insp_col]) if insp_col is not None and insp_col < len(row) else None

                if comp_date and insp_date and insp_date < comp_date:
                    warnings.append(
                        f"[{sheet_name} row {r_idx + 1}] Tag {tag_val}: Inspection date ({insp_date}) is earlier than Completion date ({comp_date})."
                    )

                suffix_desc = f" ({desc_val})" if desc_val else ""

                if comp_date:
                    pct = 100 if comp_date <= today_iso else 0
                    activities.append({
                        "activity_code": f"XLS-{sheet_idx}-{sap_val}-{tag_val}-COMP",
                        "activity_name": f"{tag_val}{suffix_desc} — Completion",
                        "wbs_category": "FABRICATION",
                        "sequence": seq_counter,
                        "baseline_start": comp_date,
                        "baseline_finish": comp_date,
                        "current_start": comp_date,
                        "current_finish": comp_date,
                        "actual_start": comp_date if pct == 100 else None,
                        "actual_finish": comp_date if pct == 100 else None,
                        "percent_complete": pct,
                        "is_critical_path": False,
                        "is_milestone": True,
                    })
                    seq_counter += 1
                    extracted_in_sheet += 1

                if insp_date and len(activities) < MAX_ACTIVITIES:
                    pct = 100 if insp_date <= today_iso else 0
                    activities.append({
                        "activity_code": f"XLS-{sheet_idx}-{sap_val}-{tag_val}-INSP",
                        "activity_name": f"{tag_val}{suffix_desc} — Tentative inspection",
                        "wbs_category": "TESTING",
                        "sequence": seq_counter,
                        "baseline_start": insp_date,
                        "baseline_finish": insp_date,
                        "current_start": insp_date,
                        "current_finish": insp_date,
                        "actual_start": insp_date if pct == 100 else None,
                        "actual_finish": insp_date if pct == 100 else None,
                        "percent_complete": pct,
                        "is_critical_path": True,
                        "is_milestone": True,
                    })
                    seq_counter += 1
                    extracted_in_sheet += 1

        elif mode == "ACTIVITY":
            code_col = (
                header_map.get("activitycode")
                or header_map.get("activityid")
                or header_map.get("taskid")
                or header_map.get("code")
                or header_map.get("sr")
                or header_map.get("srno")
            )
            name_col = (
                header_map.get("activityname")
                or header_map.get("taskname")
                or header_map.get("activitydescription")
                or header_map.get("milestonename")
                or header_map.get("activity")
                or header_map.get("description")
            )
            cat_col = header_map.get("wbscategory") or header_map.get("category") or header_map.get("phase") or header_map.get("wbs")
            dur_col = header_map.get("durationdays") or header_map.get("duration") or header_map.get("dur")
            dep_col = header_map.get("dependency") or header_map.get("predecessor") or header_map.get("dep")
            bs_col = header_map.get("baselinestartdate") or header_map.get("baselinestart") or header_map.get("plannedstart") or header_map.get("start")
            bf_col = header_map.get("baselineenddate") or header_map.get("baselinefinish") or header_map.get("baselineend") or header_map.get("plannedfinish") or header_map.get("finish")
            cs_col = header_map.get("forecastactualstartdate") or header_map.get("forecaststartdate") or header_map.get("currentstart") or header_map.get("forecaststart")
            cf_col = header_map.get("forecastactualenddate") or header_map.get("forecastfinishdate") or header_map.get("forecastenddate") or header_map.get("currentfinish") or header_map.get("forecastfinish") or header_map.get("forecastend")
            as_col = header_map.get("actualstart") or header_map.get("actualstartdate")
            af_col = header_map.get("actualfinish") or header_map.get("actualenddate")
            pct_col = header_map.get("percentagecomplete") or header_map.get("percentcomplete") or header_map.get("pctcomplete") or header_map.get("progress") or header_map.get("complete") or header_map.get("pct")
            crit_col = header_map.get("iscriticalpath") or header_map.get("critical")
            rem_col = header_map.get("remarks") or header_map.get("notes")

            for r_idx in range(header_row_idx + 1, len(rows)):
                if len(activities) >= MAX_ACTIVITIES:
                    warnings.append(f"Reached {MAX_ACTIVITIES} milestone cap; remaining rows truncated.")
                    break
                row = rows[r_idx]
                if name_col is None or name_col >= len(row) or row[name_col] is None:
                    continue
                act_name = str(row[name_col]).strip()
                if not act_name or act_name.lower() in ("none", "total", "notes", "notes :"):
                    continue
                if re.match(r"^\d+\.\s*the\s+", act_name.lower()):
                    continue

                act_code = (
                    str(row[code_col]).strip()
                    if code_col is not None and code_col < len(row) and row[code_col] is not None
                    else f"ACT-{seq_counter:03d}"
                )
                raw_cat = (
                    str(row[cat_col]).strip().upper()
                    if cat_col is not None and cat_col < len(row) and row[cat_col] is not None
                    else "FABRICATION"
                )
                wbs_cat = raw_cat if raw_cat in WBS_CATEGORIES else "FABRICATION"

                dur_raw = str(row[dur_col]).strip() if dur_col is not None and dur_col < len(row) and row[dur_col] is not None else ""
                dep_raw = str(row[dep_col]).strip() if dep_col is not None and dep_col < len(row) and row[dep_col] is not None else ""
                rem_raw = str(row[rem_col]).strip() if rem_col is not None and rem_col < len(row) and row[rem_col] is not None else ""
                bs = parse_flexible_date(row[bs_col]) if bs_col is not None and bs_col < len(row) else None
                bf = parse_flexible_date(row[bf_col]) if bf_col is not None and bf_col < len(row) else bs
                cs = parse_flexible_date(row[cs_col]) if cs_col is not None and cs_col < len(row) else None
                cf = parse_flexible_date(row[cf_col]) if cf_col is not None and cf_col < len(row) else cs
                a_start = parse_flexible_date(row[as_col]) if as_col is not None and as_col < len(row) else None
                a_fin = parse_flexible_date(row[af_col]) if af_col is not None and af_col < len(row) else None

                # Parse percent complete
                pct_val = 0
                pct_explicit = False
                if pct_col is not None and pct_col < len(row) and row[pct_col] is not None and str(row[pct_col]).strip() != "":
                    try:
                        raw_p = str(row[pct_col]).replace("%", "").strip()
                        num_p = float(raw_p)
                        if 0 < num_p <= 1.0 and "%" not in str(row[pct_col]):
                            num_p *= 100.0
                        pct_val = max(0, min(100, int(round(num_p))))
                        pct_explicit = True
                    except Exception:
                        pct_val = 0
                elif a_fin:
                    pct_val = 100
                    pct_explicit = True

                is_crit = False
                if crit_col is not None and crit_col < len(row) and row[crit_col] is not None:
                    is_crit = str(row[crit_col]).strip().lower() in ("true", "yes", "1", "y", "critical")

                activities.append({
                    "activity_code": act_code,
                    "activity_name": act_name,
                    "wbs_category": wbs_cat,
                    "sequence": seq_counter,
                    "duration_days": dur_raw,
                    "dependency": dep_raw,
                    "remarks": rem_raw,
                    "raw_bS": bs or "",
                    "raw_bE": bf or "",
                    "raw_fS": (a_start or cs or ""),
                    "raw_fE": (a_fin or cf or ""),
                    "raw_pct": str(pct_val) if pct_explicit else "",
                    "baseline_start": bs or cf or today_iso,
                    "baseline_finish": bf or bs or today_iso,
                    "current_start": cs or bs or today_iso,
                    "current_finish": cf or bf or today_iso,
                    "actual_start": a_start,
                    "actual_finish": a_fin,
                    "percent_complete": pct_val,
                    "is_critical_path": is_crit,
                    "is_milestone": (bs == bf) and bs is not None,
                })
                seq_counter += 1
                extracted_in_sheet += 1

        sheet_summary.append({"sheet": sheet_name, "mode": mode, "extracted": extracted_in_sheet})

    return {
        "activities": activities,
        "warnings": warnings,
        "sheetSummary": sheet_summary,
    }


def parse_vendor_schedule_file(
    file_bytes: bytes,
    filename: str,
    po_id: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Implements `parse_vendor_schedule` (§9.1):
    1. Excel workbooks -> deterministic `parse_excel_schedule`
    2. PDF / other files -> Gemini AI extraction with strict schema
    3. Idempotent upsert on `(po_id, activity_code)` unless `dry_run=True`
    """
    warnings: List[str] = []
    sheet_summary: List[Dict[str, Any]] = []
    activities: List[Dict[str, Any]] = []

    if _is_excel_bytes(file_bytes, filename):
        res = parse_excel_schedule(file_bytes)
        activities = res["activities"]
        warnings = res["warnings"]
        sheet_summary = res["sheetSummary"]
    else:
        # AI extraction fallback for PDF schedules
        prompt = """
        Extract all Level-3 schedule activities/milestones from this vendor schedule document.
        Return ONLY valid JSON with key "activities" containing a list of objects with:
        - "activity_code": string (e.g. "STD-01" or "ACT-01")
        - "activity_name": string
        - "wbs_category": one of ["ENGINEERING", "PROCUREMENT", "FABRICATION", "TESTING", "SHIPPING"]
        - "baseline_start": "YYYY-MM-DD"
        - "baseline_finish": "YYYY-MM-DD"
        - "current_start": "YYYY-MM-DD"
        - "current_finish": "YYYY-MM-DD"
        - "percent_complete": number (0 to 100)
        - "is_critical_path": boolean
        """
        ai_res = call_gemini_with_pdf(file_bytes, prompt)
        raw_acts = ai_res.get("activities", []) if isinstance(ai_res, dict) else []
        for idx, r in enumerate(raw_acts, start=1):
            cat = str(r.get("wbs_category", "FABRICATION")).upper()
            if cat not in WBS_CATEGORIES:
                cat = "FABRICATION"
            activities.append({
                "activity_code": r.get("activity_code") or f"PDF-{idx:02d}",
                "activity_name": r.get("activity_name") or f"Milestone {idx}",
                "wbs_category": cat,
                "sequence": idx,
                "baseline_start": parse_flexible_date(r.get("baseline_start")) or date.today().isoformat(),
                "baseline_finish": parse_flexible_date(r.get("baseline_finish")) or date.today().isoformat(),
                "current_start": parse_flexible_date(r.get("current_start")) or date.today().isoformat(),
                "current_finish": parse_flexible_date(r.get("current_finish")) or date.today().isoformat(),
                "actual_start": parse_flexible_date(r.get("actual_start")),
                "actual_finish": parse_flexible_date(r.get("actual_finish")),
                "percent_complete": int(r.get("percent_complete") or 0),
                "is_critical_path": bool(r.get("is_critical_path", False)),
                "is_milestone": False,
            })
        sheet_summary.append({"sheet": filename, "mode": "AI_PDF_EXTRACTION", "extracted": len(activities)})

    if dry_run or not po_id:
        return {
            "status": "dry_run",
            "count": len(activities),
            "activities": activities,
            "warnings": warnings,
            "sheetSummary": sheet_summary,
        }

    saved = expediting_db.upsert_schedule_activities(po_id, activities)
    return {
        "status": "ok",
        "count": len(saved),
        "activities": saved,
        "warnings": warnings,
        "sheetSummary": sheet_summary,
    }


def parse_suborder_report_file(
    file_bytes: bytes,
    filename: str,
    po_id: str,
    po_number: str,
    main_vendor: str,
) -> Dict[str, Any]:
    """
    Implements `parse_suborder_report` (§9.3):
    Extracts sub-orders from Excel or PDF, calculates float & delay_status via `calc_float`,
    and creates/updates `SubOrder` records.
    """
    extracted_rows: List[Dict[str, Any]] = []

    if _is_excel_bytes(file_bytes, filename):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))[:MAX_ROWS_PER_SHEET]
        header_idx = None
        hmap: Dict[str, int] = {}
        for r_idx, row in enumerate(rows[:20]):
            cols = {_norm_header(v): c_idx for c_idx, v in enumerate(row) if _norm_header(v)}
            if any(k in cols for k in ("subvendorname", "subvendor", "supplier", "materialdescription", "subponumber")):
                header_idx = r_idx
                hmap = cols
                break
        if header_idx is not None:
            for r_idx in range(header_idx + 1, len(rows)):
                row = rows[r_idx]
                sv_col = hmap.get("subvendorname") or hmap.get("subvendor") or hmap.get("supplier")
                mat_col = hmap.get("materialdescription") or hmap.get("description") or hmap.get("material")
                spo_col = hmap.get("subponumber") or hmap.get("ponumber") or hmap.get("subpo")
                cnt_col = hmap.get("countryoforigin") or hmap.get("country") or hmap.get("origin")
                raw_col = hmap.get("requiredatworkshopdate") or hmap.get("rawdate") or hmap.get("needdate")
                eta_col = hmap.get("subvendoretadate") or hmap.get("etadate") or hmap.get("deliverydate")

                sv = str(row[sv_col]).strip() if sv_col is not None and sv_col < len(row) and row[sv_col] else ""
                mat = str(row[mat_col]).strip() if mat_col is not None and mat_col < len(row) and row[mat_col] else ""
                if not sv and not mat:
                    continue
                extracted_rows.append({
                    "sub_po_number": str(row[spo_col]).strip() if spo_col is not None and spo_col < len(row) and row[spo_col] else f"SUB-{r_idx:03d}",
                    "sub_vendor_name": sv or "Sub-Supplier",
                    "material_description": mat or "Sub-Vendor Component",
                    "country_of_origin": str(row[cnt_col]).strip() if cnt_col is not None and cnt_col < len(row) and row[cnt_col] else "Unknown",
                    "required_at_workshop_date": parse_flexible_date(row[raw_col]) if raw_col is not None and raw_col < len(row) else None,
                    "sub_vendor_eta_date": parse_flexible_date(row[eta_col]) if eta_col is not None and eta_col < len(row) else None,
                })
    else:
        prompt = """
        Extract all sub-vendor purchase orders / material status rows from this report.
        Return ONLY valid JSON with key "sub_orders" containing a list of objects with:
        - "sub_po_number": string
        - "sub_vendor_name": string
        - "material_description": string
        - "country_of_origin": string
        - "required_at_workshop_date": "YYYY-MM-DD"
        - "sub_vendor_eta_date": "YYYY-MM-DD"
        """
        ai_res = call_gemini_with_pdf(file_bytes, prompt)
        extracted_rows = ai_res.get("sub_orders", []) if isinstance(ai_res, dict) else []

    existing_subs = expediting_db.list_suborders(po_id) if po_id else []
    created: List[Dict[str, Any]] = []
    for item in extracted_rows:
        raw_d = parse_flexible_date(item.get("required_at_workshop_date")) or (date.today() + timedelta(days=30)).isoformat()
        eta_d = parse_flexible_date(item.get("sub_vendor_eta_date")) or (date.today() + timedelta(days=25)).isoformat()
        sub_no = str(item.get("sub_po_number") or "SUB-NEW").strip()
        mat_desc = str(item.get("material_description") or "Component").strip()
        # Idempotent match to avoid duplicating sub-orders on repeat uploads
        matched = next(
            (
                s for s in existing_subs
                if str(s.get("sub_po_number") or "").strip().lower() == sub_no.lower()
                and str(s.get("material_description") or "").strip().lower() == mat_desc.lower()
            ),
            None,
        )
        saved = expediting_db.save_suborder({
            **({"id": matched["id"]} if matched else {}),
            "po_id": po_id,
            "po_number": po_number,
            "main_vendor": main_vendor,
            "sub_po_number": sub_no,
            "sub_vendor_name": item.get("sub_vendor_name") or "Sub-Vendor",
            "material_description": mat_desc,
            "country_of_origin": item.get("country_of_origin") or "Unknown",
            "required_at_workshop_date": raw_d,
            "sub_vendor_eta_date": eta_d,
        })
        created.append(saved)

    return {
        "status": "ok",
        "count": len(created),
        "sub_orders": created,
    }

