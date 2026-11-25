import json
import urllib.request
import urllib.error
import time

BASE_URL = "http://localhost:5214"
AUTH_TOKEN = ""


def request_json(method, endpoint, data=None, token=None):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    use_token = AUTH_TOKEN if token is None else token
    if use_token:
        headers["Authorization"] = f"Bearer {use_token}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def post(endpoint, data, token=None):
    return request_json("POST", endpoint, data, token=token)


def get(endpoint, token=None):
    return request_json("GET", endpoint, None, token=token)


def run_tests():
    global AUTH_TOKEN
    print("======================================================================")
    print("RUNNING PHASE 1 PRODUCTION SECURITY & WORKFLOW VERIFICATION SUITE")
    print("======================================================================")

    # 0A. Verify Unauthenticated Request Is Blocked (401)
    print("\n--- Test 0A: Backend Authentication Gate (401 on anonymous access) ---")
    try:
        get("/api/Inspections", token="")
        assert False, "Expected 401 for unauthenticated /api/Inspections"
    except urllib.error.HTTPError as e:
        assert e.code == 401
        print(f"Correctly blocked unauthenticated access: HTTP {e.code}")

    # 0B. Sign in via /api/v2/auth/login with PBKDF2 password verification & JWT
    print("\n--- Test 0B: Signed JWT Login & RBAC Enforcement ---")
    login_res = post("/api/v2/auth/login", {"email": "admin@inspectflow.com", "password": "Admin@123"}, token="")
    AUTH_TOKEN = login_res["access_token"]
    assert AUTH_TOKEN and login_res["user"]["email"] == "admin@inspectflow.com"
    print(f"Authenticated Admin JWT acquired (role={login_res['user']['inspection_role']})")

    vendor_login = post("/api/v2/auth/dev-login", {"email": "vendor@petronash.com"}, token="")
    vendor_token = vendor_login["access_token"]
    # Verify Vendor cannot spoof user_role in issue-irc (must get 403 Forbidden)
    try:
        post("/api/v1/issue-irc", {"po_number": "710001", "user_role": "admin"}, token=vendor_token)
        assert False, "Expected 403 when vendor attempts to issue IRC"
    except urllib.error.HTTPError as e:
        assert e.code == 403
        print(f"Correctly blocked Vendor IRC role-spoofing attempt: HTTP {e.code}")

    # 1. Test VDMS Documents & Real Date-Driven Countdowns
    print("\n--- Test 1: VDMS Documents Fetch & Real Date Countdowns ---")
    vdms_res = get("/api/v1/vdms/documents?po=710001")
    assert vdms_res["ok"] is True
    print(f"VDMS returned {vdms_res['count']} documents.")
    for d in vdms_res["documents"][:2]:
        print(f"  * Doc: {d['doc_no']} | Code: {d['code']} | SLA: {d['days_remaining']}d remaining (overdue={d['is_overdue']})")

    # 2. Test Vendor NOI Callout
    print("\n--- Test 2: Vendor NOI Callout ---")
    notif_no = f"NOI-TEST-{int(time.time())}"
    noi_res = post("/api/v1/vendor-noi", {
        "po_number": "710001",
        "notification_number": notif_no,
        "item_number": "10.1",
        "item_description": "Skid Base Sub-Assembly",
        "item_qty": 10,
        "item_unit": "EA",
        "milestone_name": "Hydrostatic Pressure Test",
        "start_date": "2026-12-05",
        "inspection_location": "Shop Yard B",
        "scope": "100% witness hydrotest",
    })
    assert noi_res["ok"] is True
    insp_id = noi_res["inspection_id"]
    print(f"Created NOI {notif_no} (Inspection ID: {insp_id})")

    # 3. Test NOI Revision (Rev 01)
    print("\n--- Test 3: NOI Revision (Rev 01 Increment) ---")
    rev_res = post(f"/api/v1/vendor-noi/{insp_id}/revise", {
        "scheduled_date": "2026-12-10",
        "location": "Shop Yard B - Bay 2",
        "scope": "Revised hydrotest scope to include high pressure manifold",
        "revision_notes": "Added high pressure manifold to test scope",
    })
    assert rev_res["ok"] is True
    assert "Rev 1" in rev_res["revision"]
    print(f"NOI successfully revised: {rev_res['revision']} (Status: {rev_res['message']})")

    # 4. Test NOI Cancellation (Without assigned inspector -> Clean cancel)
    print("\n--- Test 4: NOI Clean Cancellation (No Inspector) ---")
    cancel_res = post(f"/api/v1/vendor-noi/{insp_id}/cancel", {
        "reason": "Shop crane maintenance delayed preparation",
        "requested_by": "Vendor Quality Lead",
    })
    assert cancel_res["ok"] is True
    assert cancel_res["abortive_inspection"] is False
    print(f"NOI cancelled cleanly: {cancel_res['message']}")

    # 5. Test Vendor Schedule Update with Baseline Slip & Mandatory Recovery Plan
    print("\n--- Test 5: Vendor Schedule Update with Slip Validation ---")
    try:
        post("/api/v1/vendor/schedule-update", {
            "po_number": "710001",
            "items": [{
                "item_id": "10.1",
                "baseline_date": "2026-12-01",
                "forecast_date": "2026-12-20",
            }]
        })
        assert False, "Expected validation failure for missing delay reason!"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        print(f"Correctly caught baseline slip without recovery plan: HTTP {e.code}")

    sched_res = post("/api/v1/vendor/schedule-update", {
        "po_number": "710001",
        "items": [{
            "item_id": "10.1",
            "baseline_date": "2026-12-01",
            "forecast_date": "2026-12-20",
            "delay_reason_code": "RAW_MATERIAL_DELAY",
            "recovery_plan": "Adding second shift to compress welding from 14d to 8d.",
            "eng_pct": 100,
            "proc_pct": 95,
            "fab_pct": 80,
            "insp_pct": 40,
        }]
    })
    assert sched_res["ok"] is True
    print(f"Schedule update accepted with recovery plan: {sched_res['message']}")

    # 6. Test Differentiated Finding Resolution + Real Inspection Sync Bug Fix
    print("\n--- Test 6: 3-Stage Vendor NCR Sync Into inspection_reports[].findings ---")
    noi_for_ncr = post("/api/v1/vendor-noi", {
        "po_number": "710001",
        "notification_number": f"NOI-NCR-{int(time.time())}",
        "item_number": "10.1",
        "item_description": "Vessel Shell",
        "milestone_name": "Final Witness",
    })
    ncr_insp_id = noi_for_ncr["inspection_id"]
    finding_add = post(f"/api/v1/inspections/{ncr_insp_id}/add-finding", {
        "severity": "CRITICAL",
        "type": "NCR",
        "description": "Excessive weld root undercut on Shell Seam W-04",
        "code": "ASME-SEC-VIII-UNDERCUT",
    })
    finding_id = finding_add["finding"]["id"]
    print(f"Injected finding: {finding_id} ({finding_add['finding']['description']})")

    rca_res = post(f"/api/v1/vendor/ncr/{finding_id}/submit-resolution", {
        "containment_action": "Shell spool W-04 segregated in quarantine hold bay.",
        "root_cause": "Welder travel speed too high on GTAW root pass.",
        "capa_plan": "Welder re-qualified on PQR-08; calibrated wire feeder installed.",
        "target_closure_date": "2026-12-08",
        "rework_evidence_files": ["UT_Report_Rework_W04.pdf", "Welder_Cert_PQR08.pdf"]
    })
    assert rca_res["ok"] is True
    assert rca_res["inspection_synced"] is True
    # Confirm finding inside inspection record actually transitioned to pending_ie_review
    insp_after = get(f"/api/Inspections/{ncr_insp_id}")
    matched_f = next((f for f in insp_after.get("findings", []) if f.get("id") == finding_id), None)
    assert matched_f and matched_f.get("status") == "pending_ie_review" and matched_f.get("vendor_response")
    print(f"Verified finding synced inside Inspection record -> status={matched_f['status']}")

    # Complete Stage 1 Technical Close & Stage 2 Schedule Close on the injected finding
    post("/api/v1/rail/technical-close", {
        "po": "710001",
        "item_id": finding_id,
        "inspector": "Omar Farooq",
        "remarks": "UT NDE post-rework passed.",
    })
    s2_res = post("/api/v1/rail/schedule-close", {
        "po": "710001",
        "item_id": finding_id,
        "expeditor": "Ali Al-Rashid",
        "recovery_impact": "2-day rework absorbed inside existing shop float; no CDD impact.",
    })
    assert s2_res["ok"] is True

    # 7. Test Dispatch Request Invariant + Double-Dispatch Reservation Lock
    print("\n--- Test 7: Vendor Dispatch Request Invariant & Double-Dispatch Prevention ---")
    try:
        post("/api/v1/vendor/dispatch-request", {
            "po_number": "710001",
            "item_id": "10.1",
            "irc_number": "",
            "dispatch_qty": 9999,
            "packing_list_ref": "PL-710001-OVER",
            "crate_dimensions": "5m x 2m x 2m",
        })
        assert False, "Expected dispatch over-release block!"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        print(f"Correctly caught over-dispatch block: HTTP {e.code}")

    # Release 5 units on 710001 / item 10.1 using a valid inspection_id (and verify missing report is blocked)
    try:
        post("/api/v1/issue-irc", {"po_number": "710001", "item_id": "10.1", "released_qty": 5.0})
        assert False, "Expected 400 when issue-irc omits mandatory inspection_id"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        print(f"Correctly enforced mandatory inspection_id on issue-irc: HTTP {e.code}")

    noi_for_irc = post("/api/v1/vendor-noi", {
        "po_number": "710001",
        "notification_number": f"NOI-IRC-{int(time.time())}",
        "item_number": "10.1",
        "item_description": "Skid Base Sub-Assembly",
        "item_qty": 5,
        "item_unit": "EA",
        "milestone_name": "Final Release Witness",
    })
    irc_insp_id = noi_for_irc["inspection_id"]

    try:
        post("/api/v1/issue-irc", {
            "inspection_id": irc_insp_id,
            "po_number": "710001",
            "item_id": "10.1",
            "released_qty": 5.0,
        })
        assert False, "Expected 400 when issue-irc is called with zero uploaded inspection reports"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        print(f"Correctly enforced Mandatory Report Gate on issue-irc: HTTP {e.code}")

    # Upload an inspection report + obtain IE endorsement before releasing IRC
    request_json("PUT", f"/api/Inspections/{irc_insp_id}", {
        "status": "completed",
        "inspection_reports": [{
            "id": f"rep-{int(time.time())}",
            "name": "Final_Release_Flash_Report.pdf",
            "category": "inspection",
            "report_type": "Final",
            "approval_status": "pending",
            "findings": [],
        }],
    })
    ie_end = post(f"/api/v1/inspections/{irc_insp_id}/ie-approve", {"comments": "Verified clean"})
    assert ie_end["ok"] is True

    ctx_before = get("/api/v1/po/710001/context")
    item_before = next((it for it in ctx_before.get("items", []) if it["item"] == "10.1"), None)
    rel_qty = 5.0
    irc_res = post("/api/v1/issue-irc", {
        "inspection_id": irc_insp_id,
        "po_number": "710001",
        "item_id": "10.1",
        "irc_number": f"IRC-TEST-{int(time.time())}",
        "released_qty": rel_qty,
        "po_revision_override": True,
        "po_revision_justification": "Automated test batch release",
        "concession_granted": True,
        "concession_reason": "Prior historical test punch reviewed for batch test",
        "remarks": "Witnessed and cleared",
    })
    assert irc_res["ok"] is True
    issued_irc_no = irc_res["irc_number"]
    ctx_mid = get("/api/v1/po/710001/context")
    item_mid = next((it for it in ctx_mid.get("items", []) if it["item"] == "10.1"), None)
    avail_after_irc = float(item_mid["available_to_dispatch"])
    assert avail_after_irc >= rel_qty

    dispatch_res = post("/api/v1/vendor/dispatch-request", {
        "po_number": "710001",
        "item_id": "10.1",
        "irc_number": issued_irc_no,
        "dispatch_qty": avail_after_irc,
        "packing_list_ref": "PL-710001-VALID",
        "gross_weight_kg": 1500,
        "net_weight_kg": 1300,
        "crate_dimensions": "3.5m x 1.8m x 1.6m",
        "invoice_draft_ref": "INV-2026-001",
    })
    assert dispatch_res["ok"] is True
    assert dispatch_res["remaining_available_qty"] == 0.0
    print(f"Dispatch request authorized & reserved {avail_after_irc} unit(s): {dispatch_res['dispatch_id']}")

    # Attempt a duplicate dispatch against the now-reserved balance -> MUST FAIL with 400
    try:
        post("/api/v1/vendor/dispatch-request", {
            "po_number": "710001",
            "item_id": "10.1",
            "irc_number": "IRC-710001-01",
            "dispatch_qty": 1,
            "packing_list_ref": "PL-710001-DUPLICATE",
        })
        assert False, "Expected double-dispatch block!"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        print(f"Correctly prevented double-dispatch race on reserved batch: HTTP {e.code}")

    # 8. Test Executive IRC Blocker Diagnostics
    print("\n--- Test 8: Executive IRC Blocker Diagnostics ---")
    diag_res = get("/api/v1/executive/irc-blockers")
    assert diag_res["ok"] is True
    print(f"Active IRC Blockers Detected: {diag_res['count']}")
    for b in diag_res["blockers"][:3]:
        print(f"  * PO #{b['po']} | {b['status_badge']} | Next: {b['action_required']}")

    # 9. Test 2-Tier Project & PO Paired Ownership Governance
    print("\n--- Test 9: 2-Tier Project & PO Paired Ownership Governance ---")
    gov = get("/api/v1/governance/overview")
    assert gov["ok"] is True
    assert len(gov["projects"]) >= 3
    for p in gov["projects"]:
        print(f"  * [{p['code']}] {p['name']} | Exp Mgr: {p['expediting_manager_name']} | QC Mgr: {p['inspection_manager_name']} | POs: {p['po_count']}")

    ctx88 = get("/api/v1/po/PO-88001/context")
    assert ctx88["ok"] is True
    roster = ctx88["roster"]
    print(f"  * PO-88001 Paired Roster: Project={roster['project_code']} | Expeditor={roster['assigned_expeditor_name']} | IE={roster['assigned_inspection_engineer_name']}")
    assert roster["project_id"] != ""
    assert roster["assigned_expeditor_name"] != ""
    assert roster["assigned_inspection_engineer_name"] != ""

    noi88 = post("/api/v1/vendor-noi", {
        "po_number": "PO-88001",
        "notification_number": f"NOI-88001-HYDRO-{int(time.time())}",
        "item_number": "10.1",
        "item_description": "Structural Skid Base Frame with Drip Pan",
        "item_qty": 10,
        "item_unit": "EA",
        "start_date": "2026-12-10",
        "inspection_location": "Fabrication Yard A (Milan)",
        "scope": "Witness Hydrotest & Dimensional Inspection",
    })
    assert noi88["ok"] is True
    insp88 = get(f"/api/Inspections/{noi88['inspection_id']}")
    assert insp88["project_id"] == roster["project_id"]
    assert insp88["assigned_inspection_engineer_name"] == roster["assigned_inspection_engineer_name"]
    print(f"  * NOI {insp88['notification_number']} inherited ProjectId={insp88['project_id']} & Paired IE={insp88['assigned_inspection_engineer_name']}")

    re_res = post("/api/v1/governance/po-assign", {
        "po_number": "PO-88001",
        "project_id": roster["project_id"],
        "assigned_expeditor_id": "expeditor@inspectflow.com",
        "assigned_inspection_engineer_id": "engineer@inspectflow.com",
        "assigned_vendor_id": "vendor@petronash.com",
    })
    assert re_res["ok"] is True
    print(f"  * Tier-2 PO Reassignment cascaded to {re_res['updated_inspections']} inspection(s)")

    # 10. Test Strict Project Isolation & Zero-PO Project Empty State + Manager Scoping
    print("\n--- Test 10: Strict Project Isolation & Zero-PO Empty State ---")
    zero_proj = next((p for p in gov["projects"] if p.get("po_count", 0) == 0), None)
    zero_pid = zero_proj["id"] if zero_proj else "PRJ-ISOLATION-ZERO-PO"
    zero_label = f"{zero_proj['code']} ({zero_pid})" if zero_proj else zero_pid
    print(f"  * Testing 0-PO Project isolation against: {zero_label}")

    r_risk_zero = get(f"/api/v1/executive/risk-summary?project_id={zero_pid}")
    assert r_risk_zero["ok"] is True
    assert r_risk_zero["counts"]["total_alerts"] == 0, f"Expected 0 alerts for {zero_pid}, got {r_risk_zero['counts']}"

    r_blk_zero = get(f"/api/v1/executive/irc-blockers?project_id={zero_pid}")
    assert r_blk_zero["ok"] is True and r_blk_zero["count"] == 0 and r_blk_zero["blockers"] == []

    r_vdms_zero = get(f"/api/v1/vdms/documents?project_id={zero_pid}")
    assert r_vdms_zero["ok"] is True and r_vdms_zero["count"] == 0

    r_edms_zero = get(f"/api/v1/edms/documents?project_id={zero_pid}")
    assert r_edms_zero["ok"] is True and r_edms_zero["count"] == 0

    r_insp_zero = get(f"/api/Inspections?project_id={zero_pid}")
    assert isinstance(r_insp_zero, list) and len(r_insp_zero) == 0

    r_gov_zero = get(f"/api/v1/governance/overview?project_id={zero_pid}")
    assert r_gov_zero["ok"] is True and len(r_gov_zero["pos"]) == 0

    r_tpi_zero = get(f"/api/TpiAgencies/performance?project_id={zero_pid}")
    assert all((a.get("total_inspections") or 0) == 0 for a in r_tpi_zero)

    # Verify non-zero project PRJ-TRAIN3 strictly returns PRJ-TRAIN3 POs only
    r_gov_train3 = get(f"/api/v1/governance/overview?project_id={roster['project_id']}")
    assert r_gov_train3["ok"] is True
    assert len(r_gov_train3["pos"]) >= 1
    assert all(p["project_id"].lower() == roster["project_id"].lower() for p in r_gov_train3["pos"])

    # Verify SmartExpedit iframe HTML injects initial project_id + wrappers + server KV sync (auth required)
    try:
        urllib.request.urlopen(f"{BASE_URL}/smartexpedit-app?project_id={zero_pid}")
        assert False, "Expected 401 for anonymous /smartexpedit-app"
    except urllib.error.HTTPError as e:
        assert e.code == 401
    _sx_req = urllib.request.Request(
        f"{BASE_URL}/smartexpedit-app?project_id={zero_pid}",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )
    with urllib.request.urlopen(_sx_req) as resp:
        sx_html = resp.read().decode("utf-8")
    assert f'window.__IF_INIT_PROJECT_ID = "{zero_pid.lower()}"' in sx_html
    assert "_ifInstallProjectWrappers" in sx_html
    assert "SX_SET_PROJECT" in sx_html
    assert "inspectflow-sx-auth-bridge" in sx_html
    assert "window.__IF_SERVER_USER" in sx_html

    kv_res = get("/api/kv")
    assert "items" in kv_res and "ep_exp_records" in kv_res["items"]
    kv_recs = json.loads(kv_res["items"]["ep_exp_records"]["value"])
    assert any(str(r.get("po")) == "PO-88001" and "notifiedOn" in r and "lines" in r for r in kv_recs)

    # Verify Manager project access scoping (pexm@inspectflow.com)
    pexm_login = post("/api/v2/auth/dev-login", {"email": "pexm@inspectflow.com"}, token="")
    pexm_token = pexm_login["access_token"]
    pexm_projects = get("/api/Projects", token=pexm_token)
    pexm_id = str(pexm_login["user"].get("id") or "").lower()
    pexm_email = str(pexm_login["user"].get("email") or "").lower()
    pexm_pids = {str(pid).lower() for pid in (pexm_login["user"].get("project_ids") or [])}
    for proj in pexm_projects:
        team = {str(t).lower() for t in (proj.get("team_member_ids") or [])}
        allowed = (
            str(proj.get("id") or "").lower() in pexm_pids
            or str(proj.get("expediting_manager_id") or "").lower() == pexm_id
            or str(proj.get("expediting_manager_email") or "").lower() == pexm_email
            or pexm_id in team
        )
        assert allowed, f"Unauthorized project leaked to expediting_manager: {proj.get('code')}"
    print(f"  * 0-PO Project returned strictly 0 alerts/blockers/docs/inspections/POs/TPI rows; pexm scoped to {len(pexm_projects)} assigned project(s).")

    # 11. Test Auto-Provisioned Vendor Creation on PO Onboarding & Governance Vendor Endpoint
    print("\n--- Test 11: Auto-Provisioned Vendor Master on PO Creation ---")
    ts_v = int(time.time())
    test_po = f"PO-VEND-{ts_v}"
    test_email = f"vendor.sny.{ts_v}@snytest.com"
    v_po_res = post("/api/v1/governance/create-po-with-bom", {
        "po_number": test_po,
        "project_id": roster["project_id"],
        "supplier": f"SNY Valves {ts_v}",
        "description": "Test Cryogenic Control Valves",
        "vendor_mode": "auto",
        "vendor_contact_name": "SNY Coordinator",
        "vendor_email": test_email,
        "vendor_phone": "+971-50-555-0199",
        "items": [
            {"item": "10", "desc": "Control Valve Body", "qty": 5, "unit": "EA", "tag": "CV-10", "location": "Dubai Shop"}
        ],
    })
    assert v_po_res["ok"] is True
    assert v_po_res["vendor_created"] is True
    assert v_po_res["vendor_user"]["email"] == test_email
    assert v_po_res["roster"]["vendor_email"] == test_email
    print(f"  * PO {test_po} created + auto-registered Vendor user: {v_po_res['vendor_user']['full_name']} ({test_email})")

    # Verify new vendor appears in governance overview & can register/update via /api/v1/governance/vendors
    v_gov = get(f"/api/v1/governance/overview?project_id={roster['project_id']}")
    assert any(v["email"] == test_email for v in v_gov["users_by_role"]["vendors"])
    v_upd = post("/api/v1/governance/vendors", {
        "company_affiliation": f"SNY Valves {ts_v}",
        "email": test_email,
        "phone": "+971-50-555-0200",
        "project_ids": [roster["project_id"]],
    })
    assert v_upd["ok"] is True and v_upd["created"] is False
    print("  * Verified vendor deduplication & governance vendor management endpoint.")

    # Verify newly registered vendor is strictly isolated to ONLY their PO in /api/kv and /api/v1/governance/overview
    sny_login = post("/api/v2/auth/dev-login", {"email": test_email}, token="")
    sny_token = sny_login["access_token"]
    sny_kv = get("/api/kv", token=sny_token)
    sny_recs = json.loads(sny_kv["items"]["ep_exp_records"]["value"])
    assert [r.get("po") for r in sny_recs] == [test_po], f"Vendor leaked other POs in /api/kv: {[r.get('po') for r in sny_recs]}"
    sny_gov = get("/api/v1/governance/overview", token=sny_token)
    assert [p.get("po") for p in sny_gov["pos"]] == [test_po]
    print(f"  * Verified Vendor ({test_email}) is strictly isolated to ONLY PO {test_po} across /api/kv & governance.")

    # 12. Test Hybrid PDF + OCR Extraction Endpoint (/api/v1/pdf/ocr) on Scanned Image-Only PDF
    print("\n--- Test 12: Universal Scanned PDF OCR (/api/v1/pdf/ocr) ---")
    import pymupdf as _fitz
    import io as _io
    from PIL import Image as _PilImg, ImageDraw as _PilDraw, ImageFont as _PilFont
    try:
        _fnt = _PilFont.truetype("arial.ttf", 28)
    except Exception:
        _fnt = _PilFont.load_default()
    _img = _PilImg.new("RGB", (1400, 500), "white")
    _drw = _PilDraw.Draw(_img)
    _drw.text((40, 40), "PO ACKNOWLEDGEMENT & SCHEDULE RECEIPT", fill="black", font=_fnt)
    _drw.text((40, 110), "10 Engineering Drawings   01-Dec-2026   15-Dec-2026   100%", fill="black", font=_fnt)
    _drw.text((40, 180), "20 Final FAT Inspection   10-Feb-2027   15-Feb-2027   0%", fill="black", font=_fnt)
    _buf_png = _io.BytesIO()
    _img.save(_buf_png, format="PNG")
    _pdoc = _fitz.open()
    _ppg = _pdoc.new_page(width=1400, height=500)
    _ppg.insert_image(_ppg.rect, stream=_buf_png.getvalue())
    _scanned_pdf_bytes = _pdoc.tobytes()

    _ocr_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/pdf/ocr",
        data=_scanned_pdf_bytes,
        headers={"Content-Type": "application/pdf", "Authorization": f"Bearer {AUTH_TOKEN}"},
        method="POST",
    )
    with urllib.request.urlopen(_ocr_req) as _ocr_resp:
        _ocr_out = json.loads(_ocr_resp.read().decode("utf-8"))
    assert _ocr_out["ok"] is True
    assert _ocr_out["ocr_used"] is True and _ocr_out["ocr_pages"] == [1]
    assert _ocr_out["readable"] is True and len(_ocr_out["lines"]) >= 2
    assert any("2026" in ln["t"] or "2027" in ln["t"] or "Drawing" in ln["t"] or "FAT" in ln["t"] for ln in _ocr_out["lines"])
    print(f"  * Scanned PDF OCR succeeded ({_ocr_out['engine']}), extracted {len(_ocr_out['lines'])} structured lines with coordinates.")

    # 13. Test System Connections (/api/v1/connections/status) & AI Schedule Extraction (/api/v1/pdf/ai-schedule)
    print("\n--- Test 13: Connections Status & AI Schedule PDF Parser (/api/v1/pdf/ai-schedule) ---")
    conn_stat = get("/api/v1/connections/status", token=AUTH_TOKEN)
    assert conn_stat["gemini_ai"]["configured"] is True, f"GEMINI_API_KEY not configured: {conn_stat}"
    assert conn_stat["pdf_ocr"]["ready"] is True, f"PDF OCR engine not ready: {conn_stat}"
    print(f"  * Connections OK: Gemini={conn_stat['gemini_ai']['model']} (configured), OCR={conn_stat['pdf_ocr']['engine']}")
    import os as _os
    _sny_blob = "SmartExpedit/server/data/blobs/38aa9b39f5de429fb670ef8d4f99ce13"
    _sample_pdf = open(_sny_blob, "rb").read() if _os.path.exists(_sny_blob) else _scanned_pdf_bytes
    _ai_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/pdf/ai-schedule?filename=sny_schedule.pdf",
        data=_sample_pdf,
        headers={"Content-Type": "application/pdf", "Authorization": f"Bearer {AUTH_TOKEN}"},
        method="POST",
    )
    with urllib.request.urlopen(_ai_req, timeout=120) as _ai_resp:
        _ai_out = json.loads(_ai_resp.read().decode("utf-8"))
    assert _ai_out["ok"] is True and len(_ai_out["activities"]) >= 2, f"AI schedule failed: {_ai_out}"
    print(f"  * Gemini AI Schedule Extraction OK ({_ai_out['engine']}): extracted {len(_ai_out['activities'])} activity rows.")

    # 14. Security & Option A Hardening Regression Checks
    print("\n--- Test 14: Option A Security, Upload, Privilege Escalation & Duplicate PO Gates ---")
    # 14a: Signup stays pending and yields NO JWT token
    reg_email = f"pending.user.{ts_v}@example.com"
    reg_res = post("/api/v2/auth/register", {
        "email": reg_email,
        "password": "StrongPassword!99",
        "full_name": "Pending User",
    }, token="")
    assert reg_res.get("access_token") in (None, "") and reg_res.get("pending_approval") is True and reg_res.get("user", {}).get("user_status") == "pending"
    try:
        post("/api/v2/auth/login", {"email": reg_email, "password": "StrongPassword!99"}, token="")
        assert False, "Pending user should not be allowed to log in"
    except urllib.error.HTTPError as e:
        assert e.code in (401, 403)
    print("  * Verified pending signup issues no token and cannot log in until approved.")

    # 14b: Non-admin user cannot escalate company_affiliation / role via PUT /users/{id}
    sny_uid = sny_login["user"]["id"]
    upd_sny = request_json("PUT", f"/api/v2/auth/users/{sny_uid}", {
        "company_affiliation": "Competitor Hijack Corp",
        "inspection_role": "admin",
        "role": "admin",
        "phone": "+971-50-999-0001",
    }, token=sny_token)
    assert upd_sny.get("inspection_role") != "admin"
    assert upd_sny.get("company_affiliation") != "Competitor Hijack Corp"
    print("  * Verified non-admin PUT /users/{id} blocks role & company_affiliation hijacking.")

    # 14c: Duplicate PO creation returns 409 Conflict
    try:
        post("/api/v1/governance/create-po-with-bom", {
            "po_number": test_po,
            "project_id": roster["project_id"],
            "supplier": f"SNY Valves {ts_v}",
            "items": [{"item": "10", "desc": "Valve", "qty": 1, "unit": "EA"}],
        })
        assert False, "Expected 409 on duplicate PO creation"
    except urllib.error.HTTPError as e:
        assert e.code == 409
    print("  * Verified duplicate PO returns HTTP 409 Conflict.")

    # 15. Logistics Fail-Closed Guard & Relational ITP Baseline + Step Waiver Verification
    print("\n--- Test 15: Logistics Chain-of-Custody & Relational ITP Baseline Verification ---")
    try:
        post("/api/v1/delivery/update-stage", {
            "po": test_po,
            "item": "10",
            "stage": "ex_works",
            "qty": 1,
        })
        assert False, "Expected 400 when shipping without IRN release"
    except urllib.error.HTTPError as e:
        assert e.code == 400
    print("  * Verified delivery/update-stage blocks ex_works without IRN clearance (HTTP 400).")

    itp_save = post(f"/api/v1/po/{test_po}/itp-baseline", {
        "doc_no": f"ITP-{test_po}-001",
        "revision": "0",
        "approval_code": "Code 1",
        "lock_active": True,
        "steps": [
            {"step_no": "1.1", "phase": "Test", "activity_description": "Hydrostatic Test", "contractor_tpi_point": "H", "company_tpa_point": "H"}
        ],
    })
    assert itp_save["ok"] is True and itp_save["status"] == "LOCKED_ACTIVE"
    itp_get = get(f"/api/v1/po/{test_po}/itp-baseline")
    step_id = itp_get["itp_documents"][0]["steps"][0]["id"]
    waive_res = post(f"/api/v1/po/{test_po}/itp-baseline/verify-step", {
        "step_id": step_id,
        "execution_status": "VERIFIED_PASS",
    })
    assert waive_res["ok"] is True and waive_res["execution_status"] == "VERIFIED_PASS"
    print("  * Verified relational ITP baseline registration, Hold-point tracking, and step verification.")

    # 16. EPC Schedule Archetypes (bulk / tagged / package) & Bulk Partial-Lot Matrix
    print("\n--- Test 16: EPC Schedule Archetypes (bulk / tagged / package) ---")
    ctx_sny = get(f"/api/v1/po/{test_po}/context")
    assert ctx_sny.get("procurement_class") == "tagged"
    cls_upd = post(f"/api/v1/po/{test_po}/schedule-class", {"procurement_class": "bulk"})
    assert cls_upd["ok"] is True and cls_upd["procurement_class"] == "bulk"
    bulk_upd = request_json("PUT", f"/api/v1/po/{test_po}/bulk-steps", {
        "bulk_steps": {
            "10": {"heat_lot_number": "HEAT-901", "mtc_no": "MTC-3.1-A", "stage_name": "Hydro Testing", "qty_completed": 3}
        }
    })
    assert bulk_upd["ok"] is True and bulk_upd["bulk_steps"]["10"]["pct"] == 60
    bulk_get = get(f"/api/v1/po/{test_po}/bulk-steps")
    assert bulk_get["procurement_class"] == "bulk" and bulk_get["bulk_steps"]["10"]["qty_completed"] == 3.0
    print("  * Verified archetype switching & Bulk partial-lot weighted step computation (3/5 -> 60%).")

    # 17. Issue 2: Registered Active Inspector Enforcement
    print("\n--- Test 17: Registered Active Inspector Requirement ---")
    all_inspectors = get("/api/Inspectors")
    active_reg = next((i for i in all_inspectors if str(i.get("status") or "active").lower() == "active"), None)
    assert active_reg is not None, "Expected at least one registered active inspector"
    try:
        request_json("PUT", f"/api/Inspections/{noi88['inspection_id']}", {
            "assigned_inspector_name": "Unregistered Ghost Inspector",
            "assigned_inspector_email": "ghost.unregistered@example.com",
        })
        assert False, "Expected 400 when assigning an unregistered inspector"
    except urllib.error.HTTPError as e:
        assert e.code == 400
    try:
        post("/api/InspectionAttendances", {
            "inspection_id": noi88["inspection_id"],
            "inspector_id": "UNREGISTERED-ID-999",
            "check_in_time": "2026-12-10T08:00:00Z",
        })
        assert False, "Expected 400 when checking in unregistered inspector"
    except urllib.error.HTTPError as e:
        assert e.code == 400
    request_json("PUT", f"/api/Inspections/{noi88['inspection_id']}", {
        "assigned_inspector_id": active_reg["id"],
        "status": "scheduled",
    })
    insp88_assigned = get(f"/api/Inspections/{noi88['inspection_id']}")
    assert insp88_assigned["assigned_inspector_id"] == active_reg["id"]
    print(f"  * Blocked unregistered inspector assignment/attendance (400) and verified canonical registered assignment ({active_reg.get('email')}).")

    # 18. Issues 4 & 5: NOI Deletion Cross-Portal Cascade + Finalized IRC Guard
    print("\n--- Test 18: NOI Deletion Cross-Portal Sync & Finalized Guard ---")
    # Confirm finalized NOI with issued IRC cannot be accidentally deleted
    try:
        request_json("DELETE", f"/api/Inspections/{irc_insp_id}")
        assert False, "Expected 400 blocking deletion of finalized NOI with issued IRC"
    except urllib.error.HTTPError as e:
        assert e.code == 400
    print(f"  * Verified finalized NOI ({irc_insp_id[:8]}) cannot be deleted once IRC/IRN is issued (HTTP 400).")

    # Delete unfinalized NOI88 via real REST endpoint and verify removal from Inspection + SmartExpedit KV (Vendor & Expediting)
    request_json("DELETE", f"/api/Inspections/{noi88['inspection_id']}")
    try:
        get(f"/api/Inspections/{noi88['inspection_id']}")
        assert False, "Expected 404 after DELETE /api/Inspections"
    except urllib.error.HTTPError as e:
        assert e.code == 404
    kv_after_del = get("/api/kv")
    recs_after_del = json.loads(kv_after_del["items"]["ep_exp_records"]["value"])
    rec88 = next((r for r in recs_after_del if str(r.get("po")) == "PO-88001"), None)
    assert rec88 is not None
    assert not any(str(n.get("id") or "") == noi88["inspection_id"] for n in (rec88.get("sx", {}).get("notif") or [])), "Deleted NOI leaked into SmartExpedit notif list"
    assert not any(str(a.get("notif_no") or "") == noi88["notification_number"] for a in (rec88.get("sx", {}).get("iap") or [])), "Deleted NOI leaked into SmartExpedit iap list"
    print(f"  * Verified DELETE /api/Inspections/{noi88['inspection_id'][:8]} removed NOI cleanly from Inspection, Vendor Portal & Expediting.")

    # 19. Option B Phase 1: NEAS Fields & 9-Column Minimum Schedule + Freeze + ITP W/H + Sub-Orders
    print("\n--- Test 19: NEAS Fields & 9-Col Minimum Schedule Engine ---")
    meas_po = f"PO-NEAS-{ts_v}"
    post("/api/v1/governance/create-po-with-bom", {
        "po_number": meas_po,
        "project_id": roster["project_id"],
        "supplier": f"SNY Valves {ts_v}",
        "description": "Offshore Gas Scrubber Package",
        "contract_no": "4700026176",
        "budget_no": "14001-10222",
        "mr_ref": "MR-2820-900",
        "incoterm": "DDP Site",
        "cdd_date": "2026-12-28",
        "ros_date": "2027-01-15",
        "platform": "LZ Platform-4",
        "delivery_point": "Mussafah Marine Base",
        "assigned_vendor_id": sny_uid,
        "items": [
            {"item": "10", "desc": "Scrubber Vessel", "qty": 2, "unit": "EA", "tag": "V-401", "ros_date": "2027-01-15", "platform": "LZ Platform-4", "despatch_location": "Mussafah Marine Base"}
        ],
    })
    post(f"/api/v1/po/{meas_po}/itp-baseline", {
        "doc_no": f"ITP-{meas_po}-001",
        "revision": "0",
        "approval_code": "Code 1",
        "lock_active": True,
        "steps": [
            {"step_no": "2.1", "phase": "Test", "activity_description": "Shell NDT & Hydrotest Witness", "contractor_tpi_point": "H", "company_tpa_point": "H"}
        ],
    })
    post("/api/v1/vendor/sub-orders", {
        "po_number": meas_po,
        "vendor": "Forged Flanges Europe",
        "material": "Duplex Alloy Plates & Nozzles",
        "sub_po_no": f"SUB-{ts_v}",
        "unpriced_po_ref": "UNPRICED-PO-01.pdf",
        "req_delivery": "2026-11-30",
        "forecast_delivery": "2026-12-10",
        "critical": True,
    })
    sch9 = get(f"/api/v1/po/{meas_po}/schedule")
    assert sch9["ok"] is True and len(sch9["rows"]) >= 25
    assert sch9["neas"]["platform"] == "LZ Platform-4" and sch9["neas"]["ros_date"] == "2027-01-15"
    assert any(r["source_kind"] == "itp_witness_hold" for r in sch9["rows"]), "ITP Hold step not expanded into 9-col schedule"
    assert any(r["source_kind"] == "suborder" for r in sch9["rows"]), "Critical sub-order not expanded into 9-col schedule"

    # Freeze baseline and confirm unauthorized baseline date edit is rejected with 400 (Rule 2)
    frz = post(f"/api/v1/po/{meas_po}/schedule", {"rows": [sch9["rows"][0]], "freeze_baseline": True})
    assert frz["frozen"] is True
    try:
        bad_row = dict(frz["rows"][1], bE="2027-03-01")
        post(f"/api/v1/po/{meas_po}/schedule", {"rows": [bad_row]})
        assert False, "Expected 400 when modifying frozen baseline end date"
    except urllib.error.HTTPError as e:
        assert e.code == 400
    _sch_xlsx_req = urllib.request.Request(f"{BASE_URL}/api/v1/po/{meas_po}/schedule/export-xlsx", headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
    with urllib.request.urlopen(_sch_xlsx_req) as resp:
        assert resp.read(2) == b"PK"
    print(f"  * Verified NEAS fields, 9-Col Schedule ({len(sch9['rows'])} rows incl. ITP H/W & Sub-Order), Rule 2 Freeze (400), & .xlsx export.")

    # 20. Option B Phase 2A: PO Ack Buyer Escalation, NMDC 7-Sec Progress Report & Exports (.docx / .pdf)
    print("\n--- Test 20: Unified Vendor Portal (PO Ack, 7-Section Progress Report, MRB/SPIR) ---")
    ack_c = post("/api/v1/vendor/po-acknowledgement", {"po_number": meas_po, "status": "With comments", "open_points": "Clarify LD cap %"}, token=sny_token)
    assert ack_c["ack"]["buyer_escalation_required"] is True
    ack_u = post("/api/v1/vendor/po-acknowledgement", {"po_number": meas_po, "status": "Unconditional"}, token=sny_token)
    assert ack_u["ack"]["buyer_escalation_required"] is False and ack_u["ack"]["st"] == "Unconditional"

    try:
        post(f"/api/v1/po/{meas_po}/progress-reports", {
            "submit": True,
            "report_no": "01",
            "attachments": {"schedule_attached": False, "suborder_status_attached": False},
        }, token=sny_token)
        assert False, "Expected 400 enforcing Section 7 mandatory attachments"
    except urllib.error.HTTPError as e:
        assert e.code == 400

    vpr_res = post(f"/api/v1/po/{meas_po}/progress-reports", {
        "submit": True,
        "report_no": "01",
        "period_from": "2026-10-01",
        "period_to": "2026-10-31",
        "po_summary": {
            "engineering": {"planned": 80, "actual": 75},
            "procurement": {"planned": 60, "actual": 55},
            "manufacturing": {"planned": 30, "actual": 25},
            "delivery": {"planned": 0, "actual": 0},
            "overall": {"planned": 45, "actual": 40},
        },
        "areas_of_concern": "Forged nozzle lead time closely monitored.",
        "attachments": {"schedule_attached": True, "suborder_status_attached": True},
    }, token=sny_token)
    assert vpr_res["ok"] is True
    rep_id = vpr_res["report"]["id"]
    rev_vpr = post(f"/api/v1/po/{meas_po}/progress-reports/{rep_id}/review", {"decision": "Agreed", "comments": "Verified clean"})
    assert rev_vpr["report"]["status"] == "Agreed"

    for fmt, magic in [("export-docx", b"PK"), ("export-pdf", b"%PDF-")]:
        _r = urllib.request.Request(f"{BASE_URL}/api/v1/po/{meas_po}/progress-reports/{rep_id}/{fmt}", headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
        with urllib.request.urlopen(_r) as resp:
            assert resp.read(len(magic)) == magic, f"Invalid {fmt} output"
    mrb_res = post("/api/v1/vendor/mrb-spir", {"po_number": meas_po, "mrb_submitted_on": "2026-12-20", "spir_submitted_on": "2026-12-21"}, token=sny_token)
    assert mrb_res["ok"] is True
    print("  * Verified PO Ack buyer escalation, NMDC 7-Section Progress Report + Section 7 gate, .docx & .pdf export, and MRB/SPIR tracking.")

    # 21. Option B Phase 2B: Consolidated Project Weekly MSSR & 4-Sheet Excel Export
    print("\n--- Test 21: Project-Wide Consolidated Weekly MSSR ---")
    mssr_con = get(f"/api/v1/expediting/mssr/consolidated?project_id={roster['project_id']}")
    assert mssr_con["ok"] is True and any(r["po"] == meas_po and r["platform"] == "LZ Platform-4" for r in mssr_con["po_rows"])
    _mssr_req = urllib.request.Request(f"{BASE_URL}/api/v1/expediting/mssr/export-xlsx?project_id={roster['project_id']}", headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
    with urllib.request.urlopen(_mssr_req) as resp:
        assert resp.read(2) == b"PK"
    print(f"  * Verified Consolidated MSSR ({mssr_con['kpis']['total_pos']} POs) & 4-sheet Weekly MSSR .xlsx export.")

    # 22. Option B Phase 3: AI Agents (Action #2 PO/MR Review & Action #3 First Expediting Contact)
    print("\n--- Test 22: AI Agents (PO/MR Review & First Expediting Contact) ---")
    ai_mr = post(f"/api/v1/po/{meas_po}/ai-review-mr", {"notes": "HAZOP SIL-2 scrubber valves with PBG 10% and PIM required."})
    assert ai_mr["ok"] is True and len(ai_mr["review"].get("holds") or []) > 0
    ai_fc = post(f"/api/v1/po/{meas_po}/ai-first-contact", {"mark_sent": True, "issue_vdms_access": True})
    assert ai_fc["ok"] is True and ai_fc["sent"] is True and ai_fc["vdms_issued"] is True
    assert meas_po in (ai_fc["draft"].get("subject") or "") and "LZ Platform-4" in (ai_fc["draft"].get("body") or "")
    print(f"  * Verified AI Agent #2 ({ai_mr['review'].get('engine')}) & AI Agent #3 First Contact + VDMS Access.")

    # 23. Vendor Schedule Upload Parsing (.xlsx + .csv) & Multi-Item NOI Submission
    print("\n--- Test 23: Vendor Schedule Upload Parsing (.xlsx/.csv) & Multi-Item NOI ---")
    import io, openpyxl
    wb_up = openpyxl.Workbook()
    ws_up = wb_up.active
    ws_up.append(["Sr.", "Activity", "Duration (days)", "Baseline Start Date", "Baseline End Date", "Forecast / Actual Start Date", "Forecast/Actual End Date", "Dependency", "Percentage complete"])
    ws_up.append([1, "PO date", 0, "2026-10-01", "2026-10-01", "2026-10-01", "2026-10-01", "", "100%"])
    ws_up.append([10, "Start Fabrication", 25, "2026-11-01", "2026-11-26", "2026-11-03", "2026-11-28", "FS 5", "45%"])
    ws_up.append([15, "FAT / Inspection", 3, "2026-12-10", "2026-12-13", "2026-12-12", "2026-12-15", "FS 14", "0%"])
    xl_buf = io.BytesIO()
    wb_up.save(xl_buf)
    boundary = "----InspectFlowBoundaryTest23"
    mp_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="vendor_rev_sched.xlsx"\r\n'
        f"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    ).encode("utf-8") + xl_buf.getvalue() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    up_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/po/{meas_po}/schedule/upload",
        data=mp_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {sny_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(up_req) as resp:
        up_json = json.loads(resp.read().decode("utf-8"))
    assert up_json["ok"] is True and up_json["matched_count"] >= 3 and up_json["engine"] == "openpyxl"
    fab_r = next((r for r in up_json["rows"] if "start fabrication" in r["act"].lower()), None)
    assert fab_r and fab_r["fE"] == "2026-11-28" and fab_r["pct"] == "45"

    # CSV upload check
    csv_bytes = b"Sr.,Activity,Forecast/Actual End Date,Percentage complete\n11,End Fabrication,2026-12-05,80%\n"
    csv_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="vendor_rev.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + csv_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    csv_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/po/{meas_po}/schedule/upload",
        data=csv_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {sny_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(csv_req) as resp:
        csv_json = json.loads(resp.read().decode("utf-8"))
    assert csv_json["ok"] is True and csv_json["engine"] == "csv-parser"
    end_fab_r = next((r for r in csv_json["rows"] if "end fabrication" in r["act"].lower()), None)
    assert end_fab_r and end_fab_r["fE"] == "2026-12-05" and end_fab_r["pct"] == "80"

    # Multi-item NOI submission by Vendor
    multi_noi = post("/api/v1/vendor-noi", {
        "po_number": meas_po,
        "notification_number": f"NOI-MULTI-{ts_v}",
        "items": [
            {"item_number": "10", "description": "Scrubber Vessel", "qty": 2, "unit": "EA"},
            {"item_number": "20", "description": "Nozzle Internals Kit", "qty": 4, "unit": "SET"},
        ],
        "start_date": "2026-12-12",
        "scope": "Combined Multi-Item Witness FAT",
    }, token=sny_token)
    assert multi_noi["ok"] is True and multi_noi["items_count"] == 2
    multi_insp = get(f"/api/Inspections/{multi_noi['inspection_id']}")
    assert len(multi_insp.get("items_being_offered") or []) == 2
    print("  * Verified Vendor Excel/CSV Schedule Upload parsing into live 9-col table & Multi-Item NOI submission (2 items).")

    # 24. Phase 4: Client IAP Gate, KOM/PIM MOM + Auto-RAIL, Sub-Order NOI & Look-Ahead Schedule
    print("\n--- Test 24: Phase 4 (Client IAP Gate, MOM + Auto-RAIL, Sub-Order NOI & Look-Ahead) ---")
    from datetime import date as _dt, timedelta as _td
    iap_tog = post(f"/api/v1/po/{meas_po}/iap", {"action": "toggle_required", "requires_client_iap": True, "doc_no": f"IAP-{meas_po}-01"})
    assert iap_tog["ok"] is True and iap_tog["requires_client_iap"] is True

    # Ensure a sub-order exists on meas_po and issue Sub-Order Material NOI BEFORE IAP approval -> expect iap_warning
    sub_add = post("/api/v1/vendor/sub-orders", {
        "po_number": meas_po,
        "vendor": "ForgeTech Italia",
        "material": "Forged Flange Set",
        "sub_po_no": f"SUB-{ts_v}",
        "req_delivery": (_dt.today() + _td(days=20)).isoformat(),
        "forecast_delivery": (_dt.today() + _td(days=18)).isoformat(),
        "unpriced_po_ref": f"UNP-{ts_v}",
        "critical": True,
    }, token=sny_token)
    assert sub_add["ok"] is True
    ctx_sub = get(f"/api/v1/po/{meas_po}/context")
    sub_id = (sub_add.get("sub_order") or ctx_sub["sub_orders"][-1])["id"]
    look_date = (_dt.today() + _td(days=10)).isoformat()
    sub_noi = post("/api/v1/vendor-noi", {
        "po_number": meas_po,
        "notification_number": f"NOI-SUB-{ts_v}",
        "inspection_scope": "Sub-Order Material",
        "sub_order_id": sub_id,
        "item_number": f"SUB-{ts_v}",
        "item_description": "Forged Flange Set (ForgeTech Italia)",
        "milestone_name": "Sub-Order Material Inspection",
        "start_date": look_date,
        "inspection_location": "Milan Works",
        "scope": "Ultrasonic & Dimensional Sub-Order Witness",
    }, token=sny_token)
    assert sub_noi["ok"] is True and bool(sub_noi.get("iap_warning")) is True
    ctx_after_sub = get(f"/api/v1/po/{meas_po}/context")
    linked_row = next((s for s in (ctx_after_sub.get("sub_orders") or []) if s["id"] == sub_id), None)
    assert linked_row and linked_row.get("linked_noi") == sub_noi["notification_number"]

    # PMT submits and records Client IAP approval
    iap_sub = post(f"/api/v1/po/{meas_po}/iap", {"action": "submit", "dossier_ref": "DOSS-IAP-99"})
    assert iap_sub["iap_package"]["client_status"] == "SUBMITTED_TO_CLIENT"
    iap_app = post(f"/api/v1/po/{meas_po}/iap", {"action": "approve", "comments": "Client PMT Approved"})
    assert iap_app["iap_package"]["client_status"] == "APPROVED"
    assert get(f"/api/v1/po/{meas_po}/iap")["iap_cleared"] is True

    # KOM / PIM MOM with auto-spawned RAIL action items
    meet_res = post(f"/api/v1/po/{meas_po}/meetings", {
        "meeting_type": "PIM",
        "meeting_date": _dt.today().isoformat(),
        "mode": "TEAMS",
        "location": "MS Teams",
        "attendees": "PMT, BV TPIA, Vendor QA",
        "dossier_ref": "PIM-DOSS-01",
        "mom_summary": "Hold points and NDE matrix aligned.",
        "action_items": ["Submit NDE UT Procedure Rev 2 prior to FAT"],
        "spawn_rail": True,
    })
    assert meet_res["ok"] is True and len(meet_res["spawned_rail_ids"]) == 1
    assert get(f"/api/v1/po/{meas_po}/meetings")["pim_done_on"] == _dt.today().isoformat()

    # Client Inspection Look-Ahead + .xlsx Export
    look_res = get(f"/api/v1/expediting/look-ahead?project_id={roster['project_id']}&days=28")
    assert look_res["ok"] is True and any(
        ev["po"] == meas_po and ev["scope"] == "Sub-Order Material" and ev["reference"] == sub_noi["notification_number"]
        for ev in look_res["events"]
    )
    _la_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/expediting/look-ahead/export-xlsx?project_id={roster['project_id']}&days=28",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )
    with urllib.request.urlopen(_la_req) as resp:
        assert resp.read(2) == b"PK"
    print("  * Verified Phase 4: Client IAP Gate, Sub-Order NOI linkage, PIM MOM + Auto-RAIL, and Look-Ahead .xlsx.")

    # 25. Phase 5A: Stores MRV / Stamped Delivery Note & MNCR Return->Rectify->Close Loop
    print("\n--- Test 25: Phase 5A Stores MNCR & Stamped Delivery Note Loop ---")
    mncr_cr = post(f"/api/v1/po/{meas_po}/mncr", {
        "mrv_no": f"MRV-{ts_v}",
        "stamped_delivery_note_ref": f"DN-STAMP-{ts_v}",
        "item_no": "10",
        "description": "Missing 2x Spiral Wound Gasket Kits at Stores Receiving",
    })
    assert mncr_cr["ok"] is True and mncr_cr["mncr"]["status"] == "RAISED_BY_STORES"
    mncr_id = mncr_cr["mncr"]["id"]
    ret_res = post(f"/api/v1/po/{meas_po}/mncr/{mncr_id}/return-to-vendor", {"instructions": "Air-freight replacement gaskets immediately"})
    assert ret_res["mncr"]["status"] == "RETURNED_TO_VENDOR"
    rect_res = post(f"/api/v1/po/{meas_po}/mncr/{mncr_id}/vendor-rectify", {"rectification_details": "Replacement dispatched via DHL AWB-8812"}, token=sny_token)
    assert rect_res["mncr"]["status"] == "VENDOR_RECTIFIED_PENDING_PMT"
    cls_res = post(f"/api/v1/po/{meas_po}/mncr/{mncr_id}/close", {"closure_remarks": "Stores confirmed replacement accepted"})
    assert cls_res["mncr"]["status"] == "CLOSED"
    mncr_list = get(f"/api/v1/po/{meas_po}/mncr")
    assert any(dn["ref"] == f"DN-STAMP-{ts_v}" for dn in mncr_list["stamped_delivery_notes"])
    print("  * Verified Stores Stamped DN & full MNCR Raised -> Return -> Vendor Rectify -> PMT Close lifecycle.")

    # 26. Phase 5B: Two-Stage Commercial Closeout — LD Waiver Memo (.docx) & Final Invoice
    print("\n--- Test 26: Phase 5B Commercial Closeout LD Settlement & .docx Memo ---")
    import urllib.error as _uerr
    try:
        post(f"/api/v1/po/{meas_po}/closeout/ld", {"mode": "PARTIAL_WAIVER", "settled_amount": 1000})
        raise AssertionError("Expected 400 when waiver_justification missing for PARTIAL_WAIVER")
    except _uerr.HTTPError as he:
        assert he.code == 400
    ld_res = post(f"/api/v1/po/{meas_po}/closeout/ld", {
        "mode": "PARTIAL_WAIVER",
        "rate_per_day": 500,
        "cap_pct": 10,
        "settled_amount": 1500,
        "waiver_justification": "Port customs clearance delay outside vendor control (3 days waived).",
        "final_invoice_no": f"INV-FIN-{ts_v}",
        "final_invoice_paid_on": "2026-12-28",
        "mark_intimated": True,
        "mark_settled": True,
        "issue_memo": True,
    })
    assert ld_res["ok"] is True and ld_res["ld"]["mode"] == "PARTIAL_WAIVER" and ld_res["ld"]["final_invoice_no"] == f"INV-FIN-{ts_v}"
    _ld_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/po/{meas_po}/closeout/ld-memo-docx",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )
    with urllib.request.urlopen(_ld_req) as resp:
        assert resp.read(2) == b"PK"
    print("  * Verified LD Waiver justification gate, settlement, Final Invoice clearance & Waiver Memo .docx export.")

    # 27. Phase 5C: Governance Registers (TPIA Billing, TPI Credentials Pre-Mob Approval)
    print("\n--- Test 27: Phase 5C Governance Registers ---")
    reg_bill = post("/api/v1/governance/registers/tpia-billing", {
        "project_id": roster["project_id"],
        "po": meas_po,
        "title": f"BV Witness Timesheet {ts_v}",
        "party": "Bureau Veritas",
        "ref_no": f"INV-BV-{ts_v}",
        "notes": "2 mandays @ $950",
    })
    assert reg_bill["ok"] is True
    reg_tpi = post("/api/v1/governance/registers/tpi-credentials", {
        "project_id": roster["project_id"],
        "po": meas_po,
        "title": f"Inspector Test CV & CSWIP 3.1 ({ts_v})",
        "party": "SGS",
        "ref_no": f"CSWIP-{ts_v}",
    })
    assert reg_tpi["ok"] is True and reg_tpi["item"]["status"] == "PENDING_APPROVAL"
    dec_res = post(f"/api/v1/governance/registers/tpi-credentials/{reg_tpi['item']['id']}/decision", {
        "decision": "APPROVED",
        "comments": "Verified valid certificates",
    })
    assert dec_res["item"]["status"] == "APPROVED"
    reg_list = get(f"/api/v1/governance/registers/tpi-credentials?project_id={roster['project_id']}")
    assert any(x["id"] == reg_tpi["item"]["id"] for x in reg_list["items"])
    print("  * Verified Governance Registers (TPIA Billing & TPI Credential Approval).")

    # Full Self-Cleaning Teardown so automated runs leave ZERO test NOIs/IRNs/POs/concerns/users behind
    from python_app import database as _db_cleanup
    from python_app.smartexpedit_server import (
        LOCK as _SX_LOCK,
        sx_db as _sx_db,
        _records as _sx_recs,
        _save_records as _sx_save,
        _get_sx_state as _sx_state_get,
        _save_sx_state as _sx_state_save,
    )
    for _iid in (insp_id, ncr_insp_id, irc_insp_id, multi_noi["inspection_id"], sub_noi["inspection_id"]):
        _db_cleanup.delete_inspection(_iid)
    with _SX_LOCK, _sx_db() as _c:
        _recs = [r for r in _sx_recs(_c) if str(r.get("po")) not in (test_po, meas_po)]
        _test_notif_ids = {insp_id, ncr_insp_id, irc_insp_id, noi88["inspection_id"], multi_noi["inspection_id"], sub_noi["inspection_id"]}
        _test_notif_nos = {notif_no, noi_for_ncr["notification_number"], noi_for_irc["notification_number"], noi88["notification_number"], multi_noi["notification_number"], sub_noi["notification_number"]}
        for _r in _recs:
            _sxo = _r.setdefault("sx", {})
            _sxo["notif"] = [
                n for n in (_sxo.get("notif") or [])
                if str(n.get("id") or "") not in _test_notif_ids
                and not any(str(n.get("Activity") or "").startswith(nn) for nn in _test_notif_nos)
            ]
            _sxo["iap"] = [
                a for a in (_sxo.get("iap") or [])
                if str(a.get("id") or "") not in _test_notif_ids and str(a.get("notif_no") or "") not in _test_notif_nos
            ]
            if str(_r.get("po")) == "710001":
                _r["irns"] = [ir for ir in (_r.get("irns") or []) if str(ir.get("irn_no") or "") != issued_irc_no]
                _r["rail"] = [rl for rl in (_r.get("rail") or []) if str(rl.get("id") or "") != finding_id]
                _r["punch"] = [p for p in (_r.get("punch") or []) if str(p.get("id") or "") != finding_id]
                _sxo["punch"] = [p for p in (_sxo.get("punch") or []) if str(p.get("id") or "") != finding_id]
        _st = _sx_state_get(_c)
        _extra_concern_ids = {finding_id, mncr_id, *(meet_res.get("spawned_rail_ids") or [])}
        _st["concerns"] = [
            cn for cn in (_st.get("concerns") or [])
            if str(cn.get("id") or "") not in _extra_concern_ids
            and str(cn.get("insp_id") or "") not in _test_notif_ids
        ]
        _test_reg_ids = {reg_bill["item"]["id"], reg_tpi["item"]["id"]}
        for _rk, _rlist in (_st.get("erp_registers") or {}).items():
            if isinstance(_rlist, list):
                _st["erp_registers"][_rk] = [x for x in _rlist if str(x.get("id") or "") not in _test_reg_ids]
        _st["dispatch_requests"] = [
            dp for dp in (_st.get("dispatch_requests") or [])
            if str(dp.get("id") or "") != dispatch_res.get("dispatch_id")
        ]
        _sx_save(_c, _recs, "Test Cleanup", f"Removed {test_po} & temporary test NOIs")
        _sx_state_save(_c, _st, "Test Cleanup")
    with _db_cleanup.get_connection() as _conn:
        _conn.execute("DELETE FROM Users WHERE Email IN (?, ?)", (test_email, reg_email))
        _conn.commit()
    try:
        from backend_v2.core.database import SessionLocal as _SL
        from backend_v2.models.epc_models import ItpDocument as _ItpDoc, ItpBaselineStep as _ItpStep
        with _SL() as _sdb:
            _dids = [d.id for d in _sdb.query(_ItpDoc).filter(_ItpDoc.po_number.in_([test_po, meas_po])).all()]
            if _dids:
                _sdb.query(_ItpStep).filter(_ItpStep.itp_document_id.in_(_dids)).delete(synchronize_session=False)
                _sdb.query(_ItpDoc).filter(_ItpDoc.id.in_(_dids)).delete(synchronize_session=False)
                _sdb.commit()
    except Exception:
        pass
    p_clean = _db_cleanup.get_project(roster["project_id"])
    if p_clean and any(x in (test_po, meas_po) for x in (p_clean.get("linked_po_numbers") or [])):
        _db_cleanup.update_project(roster["project_id"], {"linked_po_numbers": [x for x in p_clean["linked_po_numbers"] if x not in (test_po, meas_po)]})

    print("\n======================================================================")
    print("ALL OPTION A SECURITY, QUALITY, ARCHETYPE & WORKFLOW TESTS PASSED (100%)!")
    print("======================================================================")


if __name__ == "__main__":
    run_tests()
