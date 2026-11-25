import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 11 * inch - 36, "SmartExpedit & InspectFlow | Integrated Operational Workflow & Vendor Specification")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, 11 * inch - 42, 8.5 * inch - 54, 11 * inch - 42)
            
        # Footer
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 46, 8.5 * inch - 54, 46)
        
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * inch - 54, 34, page_str)
        self.drawString(54, 34, "CONFIDENTIAL & PROPRIETARY — INTEGRATED QUALITY, EXPEDITING & VENDOR GOVERNANCE")
        self.restoreState()


def build_pdf(filename="Expediting_and_Inspection_Workflow_Guide.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=50,
        rightMargin=50,
        topMargin=50,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    c_primary = colors.HexColor("#0F172A")
    c_brand = colors.HexColor("#0284C7")
    c_dark = colors.HexColor("#1E293B")
    c_border = colors.HexColor("#CBD5E1")
    c_bg_light = colors.HexColor("#F8FAFC")
    c_callout_bg = colors.HexColor("#F0F9FF")
    c_callout_border = colors.HexColor("#BAE6FD")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=c_primary,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=c_brand,
        spaceAfter=10
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=c_primary,
        spaceBefore=12,
        spaceAfter=5,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=c_brand,
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=c_dark,
        spaceAfter=4
    )

    body_bold = ParagraphStyle(
        'Body_Bold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11.5,
        textColor=c_dark,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=2
    )

    table_header = ParagraphStyle(
        'TH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white
    )

    table_body = ParagraphStyle(
        'TB',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        textColor=c_dark
    )

    table_body_bold = ParagraphStyle(
        'TBB',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=c_dark
    )

    story = []

    # ── HEADER & TITLE ─────────────────────────────────────────────────────────
    story.append(Paragraph("SMARTEXPEDIT & INSPECTFLOW ARCHITECTURE", subtitle_style))
    story.append(Paragraph("Integrated Expediting, Inspection & Vendor Portal Specification", title_style))
    story.append(Paragraph("End-to-End Operational Lifecycle: PO Placement, Vendor Portal, VDMS, Quality Gates to Site Receipt (MRV)", body_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_brand, spaceBefore=3, spaceAfter=8))

    meta_data = [
        [
            Paragraph("<b>Version:</b> 2.1 (Phase 2 Hardened + Vendor Portal)", table_body),
            Paragraph("<b>Platform Scope:</b> SmartExpedit + InspectFlow + Vendor Portal", table_body),
            Paragraph("<b>Target Roles:</b> Expeditors, Inspectors, IE, QC, Logistics & Vendors", table_body)
        ],
        [
            Paragraph("<b>Status:</b> Approved Technical Standard", table_body),
            Paragraph("<b>Integration:</b> Bidirectional REST API + VDMS Integration", table_body),
            Paragraph("<b>Security:</b> Strict RBAC & PO Role Isolation", table_body)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6))

    # ── SECTION 1: ARCHITECTURE & CUMULATIVE QUANTITY LEDGER ───────────────────
    story.append(Paragraph("1. System Architecture & The Cumulative Ledger Invariant", h1_style))
    story.append(Paragraph(
        "The end-to-end platform integrates three critical execution tiers: <b>SmartExpedit</b> (governing baseline schedules, "
        "split BOMs, shop floor surveillance, and 4-stage logistics), <b>InspectFlow</b> (managing quality gates, ITP compliance, "
        "witness points, finding remediation, and IRC releases), and the <b>Dedicated Vendor Portal</b> (enabling secure, role-isolated "
        "vendor interaction for NOI callouts, VDMS tracking, schedule updates, and dispatch requests).", body_style))

    story.append(Paragraph(
        "Every line item and sub-split is governed by the <b>Cumulative Quantity Ledger Matrix</b>. The platform strictly enforces "
        "the mathematical invariant at every transition:", body_style))

    eq_box = [
        [Paragraph("<font color='#0284C7' size='8.5'><b>Total PO Ordered Qty &ge; Inspected Qty &ge; Released Qty (IRC) &ge; Shipped Qty (BL/AWB) &ge; Delivered Site Qty (MRV)</b></font>", body_bold)]
    ]
    t_eq = Table(eq_box, colWidths=[7.5*inch])
    t_eq.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_callout_bg),
        ('BOX', (0,0), (-1,-1), 1, c_callout_border),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_eq)
    story.append(Spacer(1, 6))

    # ── SECTION 2: DEDICATED VENDOR PORTAL REQUIREMENTS & WORKFLOW ─────────────
    story.append(Paragraph("2. Dedicated Vendor Portal & Workflow Requirements", h1_style))

    vendor_topics = [
        ("2.1 Role-Based PO Isolation & Portal Hub", [
            "<b>Secure Authentication:</b> Dedicated vendor login credentials with strict tenant isolation. Vendors only access awarded POs and line items.",
            "<b>Dedicated Functional Tabs:</b> Vendor dashboard provides 5 specialized modules: (1) <i>VDMS Documents</i>, (2) <i>Schedule & Progress</i>, (3) <i>Notice of Inspection (NOI)</i>, (4) <i>NCR Actions</i>, and (5) <i>Dispatch Requests</i>."
        ]),
        ("2.2 Notice of Inspection (NOI) Full Lifecycle & Edge Cases", [
            "<b>Advance Notice Lead-Time SLA:</b> System enforces contractual rules (Domestic &ge; 5 business days, Overseas &ge; 14 business days). Short-notice submissions trigger a prominent <i>'SHORT NOTICE CALLOUT'</i> high-priority banner for Coordinator clearance.",
            "<b>Cancellation Before Assignment:</b> Inspection status moves directly to <i>'Cancelled'</i>, clears the milestone in the expediting schedule, and logs no abortive charges.",
            "<b>Cancellation After Assignment:</b> Mandates entry of formal cancellation reason, transitions status to <i>'Cancelled (Vendor Request)'</i>, records an <b>Abortive Inspection</b> entry (standby/travel billing), and fires instant SMS/Email alerts to the Inspector, Coordinator, and Expeditor.",
            "<b>NOI Revisions (Scope & Date Changes):</b> System creates versioned revisions (e.g. <i>NOI-2026-004 Rev 1</i>). Runs automated ITP checks in VDMS for newly added items. For scope additions, inspector receives a scope-update alert; for date/location changes, inspector status switches to <i>'Pending Re-confirmation'</i> with a 24h timer before reassignment."
        ]),
        ("2.3 Differentiated Vendor NCR Resolution & Rework Handling", [
            "<b>Critical / Major NCRs (3-Stage Structured Form):</b> Vendor must submit: (1) Immediate Containment Action, (2) Root Cause Analysis (RCA) & CAPA with committed target dates, and (3) Physical Rework Evidence (photos, NDE reports, calibrated charts) &rarr; moves to <i>'Pending IE Technical Review'</i>.",
            "<b>Minor Findings & Punch Items (Direct Submission):</b> Formal RCA/CAPA is NOT required. Vendor submits direct correction or missing document (e.g. updated MTC, calibration cert, paint touch-up photo) for immediate IE closeout without bureaucratic delays."
        ]),
        ("2.4 Real-Time Expeditor 'IRC Blocker Diagnostics' Ribbon", [
            "<b>Live Blocker Transparency:</b> When an inspection is completed but an IRC is unissued, the Expeditor Workbench displays real-time diagnostic status: <i>'IRC BLOCKED: Major NCR #3 awaiting Vendor RCA'</i>, <i>'IRC ON HOLD: Vendor submitted rework, awaiting IE Technical Review'</i>, or <i>'IRC READY: Minor Punch only, eligible for conditional release'</i>.",
            "<b>Diagnostic Drawer:</b> Clicking the badge opens a slide-over panel displaying open findings, vendor response timelines, and IE review history."
        ]),
        ("2.5 Schedule Updates & VDMS Document Integration", [
            "<b>Dual-Input Progress Tracking:</b> Vendor updates milestone dates and % complete (Engineering, Procurement, Fabrication, Inspection) via interactive Web Grid or Excel Template upload.",
            "<b>Baseline Slip Enforcement:</b> If any Forecast date slips past the Contractual Baseline, the system enforces a mandatory <i>Delay Reason Code</i> and <i>Recovery Plan</i> submission.",
            "<b>VDMS Integration:</b> Fetches document metadata, revisions, and review status (Code 1/2/3) from VDMS. Displays live countdown SLA timers for pending reviews and resubmissions across Vendor, Expeditor, and Inspection dashboards."
        ]),
        ("2.6 Post-IRC Dispatch Request & Logistics Handover", [
            "<b>Vendor Dispatch Request:</b> Following IRC issuance, vendor submits Dispatch Request attaching Final Packing List (net/gross weights, crate dimensions L&times;W&times;H, draft commercial invoice).",
            "<b>Chain of Custody Validation:</b> System verifies <i>Packing List Qty &le; IRC Released Qty</i> before Logistics Coordinator issues Movement Authority and records the BL/AWB."
        ])
    ]

    for title, items in vendor_topics:
        story.append(Paragraph(title, h2_style))
        for item in items:
            story.append(Paragraph(f"• {item}", bullet_style))
        story.append(Spacer(1, 2))

    story.append(PageBreak())

    # ── SECTION 3: 7-PHASE OPERATIONAL LIFECYCLE ──────────────────────────────
    story.append(Paragraph("3. End-to-End Operational Lifecycle Walkthrough", h1_style))

    phases = [
        ("Phase 1: PO Ingestion, Baseline Freeze & Package Line Decomposition", [
            "<b>PO Line Ingestion:</b> PO data is ingested, creating baseline BOM line items, tags, quantities, and delivery milestones.",
            "<b>Package Splitting (POST /api/v1/po/split-item):</b> For packages fabricated in separate vendor shops, the Expeditor splits items (e.g. Item 10 into 10.1 Skid Base, 10.2 Pressure Vessel) with distinct locations, enabling independent inspection calls and partial releases."
        ]),
        ("Phase 2: Engineering Deliverables & ITP Quality Gate (VDMS / EDMS)", [
            "<b>VDMS Document Sync:</b> Connects to VDMS to track ITPs, WPS/PQR, NDE procedures, and MTCs. Displays review codes (Code 1, 2, 3) and overdue countdown timers.",
            "<b>Mandatory ITP Gate:</b> If an NOI is issued while an ITP is missing or Code 3, InspectFlow flags an immediate quality hold warning."
        ]),
        ("Phase 3: Shop Fabrication & Field Surveillance", [
            "<b>Dual-Track Surveillance:</b> Compares Vendor Self-Reported Progress against Field Expeditor Audited Physical Progress.",
            "<b>Variance Alert:</b> Reported % exceeding Audited % by >10% triggers an automated S-Curve fabrication delay alert and creates a recovery action in Expediting RAIL."
        ]),
        ("Phase 4: Notice of Inspection (NOI) Callout & Sync", [
            "<b>Vendor Portal Submission:</b> Vendor issues NOI specifying PO, Item/Split, milestone, date, and yard location.",
            "<b>Bidirectional Auto-Sync:</b> Instantly creates the inspection assignment in InspectFlow and notifies the Expeditor Workbench under 'Upcoming & Active Inspections'."
        ]),
        ("Phase 5: Inspection Execution, IE Deliverable Review & RAIL Escalation", [
            "<b>Field Report Upload:</b> Inspector completes visit and uploads Inspection Report + MTCs. Status moves to <i>'completed (Under IE Review)'</i> — never premature finalized.",
            "<b>IE Review & Missed Finding Injection:</b> IE reviews deliverables. Can inject missed findings via <i>'+ Add Missed Finding / IE Comment'</i> and endorse report for IRC.",
            "<b>2-Stage Closeout:</b> Stage 1 (Technical Verification) is signed off by IE upon verified rework; Stage 2 (Schedule Closeout) is signed off by Expeditor in RAIL."
        ]),
        ("Phase 6: Strict Quality Gate & Inspection Release Certificate (IRC)", [
            "<b>Quality Gate Rules:</b> Open Major NCRs strictly block release. Allowed with Concession/Conditional release (QC Manager approved) or with Minor Punch (issued as <i>'Released with Minor Punch'</i>).",
            "<b>Ledger Lock:</b> Releasing updates cumulative ledger (<i>Released Qty += Qty</i>). Over-release is blocked without formal PO revision override.",
            "<b>3-Tier Dispatch:</b> Automated email with signed PDF to Vendor, TPI, Expeditor, and Logistics; in-app notification banner; immutable PO audit log entry."
        ]),
        ("Phase 7: 4-Stage Logistics Pipeline & Site Material Receipt (MRV)", [
            "<b>Stage 1 (Ready for Dispatch):</b> Packing list, crate dimensions, preservation check, and IRC attachment.",
            "<b>Stage 2 (Ex-Works Pickup):</b> Logistics records BL/AWB and carrier details. Invariant check: <i>Shipped Qty &le; Released Qty</i>.",
            "<b>Stage 3 (Port & Customs):</b> Marine/Air freight tracking, duty clearance, and domestic transit to site.",
            "<b>Stage 4 (Site Receipt & MRV):</b> Joint site inspection. Invariant check: <i>Delivered Qty &le; Shipped Qty</i>. Shortage or transit damage flags OS&D and auto-spawns Material NCR (MNCR) in RAIL. Clean receipt executes final MRV."
        ])
    ]

    for title, items in phases:
        story.append(Paragraph(title, h2_style))
        for item in items:
            story.append(Paragraph(f"• {item}", bullet_style))
        story.append(Spacer(1, 2))

    story.append(Spacer(1, 6))

    # ── SECTION 4: OPERATIONAL SCENARIOS MATRIX ───────────────────────────────
    story.append(Paragraph("4. Comprehensive Operational Scenario Matrix", h1_style))

    scenarios = [
        ("A: Standard Happy Path", "Clean fabrication, Code 1 ITP, zero findings during inspection witness points.", "All 7 phases proceed cleanly. Release is clean; 100% quantity delivered to site with clean MRV."),
        ("B: Package Line Decomposition", "Single PO line item fabricated across multiple separate vendor yards (Skid vs Vessel).", "Expeditor executes split (POST /api/v1/po/split-item) into 10.1 and 10.2. Enables independent NOIs, inspections, and IRCs."),
        ("C: Unapproved / Code 3 ITP", "Vendor triggers NOI callout while ITP is missing or rejected in VDMS.", "POST /api/v1/vendor-noi triggers immediate inspection hold warning. Assignment blocked until VDMS reflects Code 1/2."),
        ("D: Fabrication Progress Variance", "Vendor reports 70% progress; Field Expeditor physical audit verifies 45% (>10% delta).", "S-Curve variance alert triggers. Auto-creates corrective recovery action item in Expediting RAIL with expediter escalation."),
        ("E: Critical/Major NCR on Report", "Hydrotest burst or flange crack identified during witness point.", "Report upload sets status to 'Under IE Review'. Release button is HARD BLOCKED. Requires Stage 1 Tech Closeout before IRC unblock."),
        ("F: Fast-Track Concession Release", "Critical shutdown milestone; minor surface defect with open NCR.", "QC Manager evaluates technical justification and grants Concession. System allows Conditional Release with permit number."),
        ("G: Minor Punch Items", "Cosmetic paint scratch or missing valve nameplate at final inspection.", "IE categorizes finding as MINOR. IRC issued as 'APPROVED (WITH MINOR PUNCH)'. Punch list transfers to Site MRV team."),
        ("H: Partial Batch Releases", "100 ordered valves released in 3 partial batches (30 -> 40 -> 30).", "Cumulative ledger tracks batches independently (Released += Qty). Generates 3 separate IRCs and 3 linked BL shipments."),
        ("I: Over-Release Prevention", "User attempts to release 60 units when remaining balance is only 40.", "Hard validation rejects submission ('Release exceeds unreleased balance'). Override strictly requires PO Revision entry."),
        ("J: Logistics Over-Shipment Block", "Logistics team attempts to enter Ex-Works shipment of 50 units when only 30 were released.", "Chain of custody check prevents shipment ('Shipped > Released'). Entry rejected; shipment capped at 30."),
        ("K: Site OS&D Shortage / Damage", "Site uncrates 40 units: 2 damaged in transit, 3 missing.", "Receiver logs OS&D flag. System auto-spawns Material NCR (MNCR) in RAIL. Expeditor triggers replacement; clean MRV for 35 units."),
        ("L: Departmental Role Segregation", "Expeditor attempts to issue IRC or Inspector attempts to edit PO contracts.", "Strict department lockouts prevent cross-functional unauthorized edits. Shared read-only visibility maintained via PO Context.")
    ]

    table_data = [
        [
            Paragraph("<b>Scenario</b>", table_header),
            Paragraph("<b>Trigger Condition</b>", table_header),
            Paragraph("<b>System Quality Gate & Resolution</b>", table_header)
        ]
    ]

    for sc_title, sc_trigger, sc_res in scenarios:
        table_data.append([
            Paragraph(f"<b>{sc_title}</b>", table_body_bold),
            Paragraph(sc_trigger, table_body),
            Paragraph(sc_res, table_body)
        ])

    scenario_table = Table(table_data, colWidths=[1.8*inch, 2.5*inch, 3.2*inch])
    scenario_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_primary),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(scenario_table)

    story.append(PageBreak())

    # ── SECTION 5: API ENDPOINTS & UI CONTROLS ────────────────────────────────
    story.append(Paragraph("5. API Endpoints & UI Controls Mapping", h1_style))

    api_data = [
        [
            Paragraph("<b>Workflow Action</b>", table_header),
            Paragraph("<b>Frontend UI Component & Location</b>", table_header),
            Paragraph("<b>Backend API Endpoint & Method</b>", table_header)
        ],
        [
            Paragraph("Vendor Authentication & PO Scope", table_body_bold),
            Paragraph("Dedicated Vendor Portal &rarr; Login View", table_body),
            Paragraph("POST /api/v1/vendor/login", table_body)
        ],
        [
            Paragraph("VDMS Document Sync & Countdown", table_body_bold),
            Paragraph("Expediting & Vendor Portal &rarr; VDMS Tab", table_body),
            Paragraph("GET /api/v1/edms/documents<br/>POST /api/v1/edms/sync", table_body)
        ],
        [
            Paragraph("Vendor Schedule & Progress Update", table_body_bold),
            Paragraph("Vendor Portal &rarr; Schedule Tab (Grid / Excel)", table_body),
            Paragraph("POST /api/v1/vendor/schedule-update", table_body)
        ],
        [
            Paragraph("Vendor NOI Callout", table_body_bold),
            Paragraph("Vendor Portal &rarr; NOI Tab &rarr; 'Issue NOI'", table_body),
            Paragraph("POST /api/v1/vendor-noi", table_body)
        ],
        [
            Paragraph("Vendor NOI Cancellation", table_body_bold),
            Paragraph("Vendor Portal &rarr; NOI Tab &rarr; 'Cancel Callout'", table_body),
            Paragraph("POST /api/v1/vendor-noi/{id}/cancel", table_body)
        ],
        [
            Paragraph("Vendor NOI Revision (Rev 01)", table_body_bold),
            Paragraph("Vendor Portal &rarr; NOI Tab &rarr; 'Revise Callout'", table_body),
            Paragraph("POST /api/v1/vendor-noi/{id}/revise", table_body)
        ],
        [
            Paragraph("Vendor NCR RCA/CAPA Submission", table_body_bold),
            Paragraph("Vendor Portal &rarr; NCR Actions &rarr; 'Submit RCA/CAPA'", table_body),
            Paragraph("POST /api/v1/vendor/ncr/{id}/submit-resolution", table_body)
        ],
        [
            Paragraph("Vendor Minor Correction Upload", table_body_bold),
            Paragraph("Vendor Portal &rarr; NCR Actions &rarr; 'Submit Correction'", table_body),
            Paragraph("POST /api/v1/vendor/ncr/{id}/quick-close", table_body)
        ],
        [
            Paragraph("Split Package Line Item", table_body_bold),
            Paragraph("Expediting &rarr; PO Details &rarr; 'Split Package Line Item'", table_body),
            Paragraph("POST /api/v1/po/split-item", table_body)
        ],
        [
            Paragraph("IE Add Missed Finding", table_body_bold),
            Paragraph("Inspection Modal &rarr; Findings Tab &rarr; '+ Add Missed Finding'", table_body),
            Paragraph("POST /api/v1/inspections/{id}/add-finding", table_body)
        ],
        [
            Paragraph("IE Report Endorsement", table_body_bold),
            Paragraph("Inspection Modal &rarr; Reports Tab &rarr; 'Endorse Report for IRC'", table_body),
            Paragraph("POST /api/v1/inspections/{id}/ie-approve", table_body)
        ],
        [
            Paragraph("Stage 1 Technical Closeout", table_body_bold),
            Paragraph("Inspection Modal &rarr; Findings Tab &rarr; 'Verify Tech Closeout'", table_body),
            Paragraph("POST /api/v1/rail/technical-close", table_body)
        ],
        [
            Paragraph("Stage 2 Schedule Closeout", table_body_bold),
            Paragraph("Expediting &rarr; RAIL Tab &rarr; 'Verify Schedule Recovery'", table_body),
            Paragraph("POST /api/v1/rail/schedule-close", table_body)
        ],
        [
            Paragraph("Strict Quality Gate IRC Issuance", table_body_bold),
            Paragraph("Inspection Modal &rarr; Overview Tab &rarr; 'Issue IRC' Dialog", table_body),
            Paragraph("POST /api/v1/issue-irc", table_body)
        ],
        [
            Paragraph("Vendor Dispatch Request", table_body_bold),
            Paragraph("Vendor Portal &rarr; Dispatch Tab &rarr; 'Submit Dispatch Request'", table_body),
            Paragraph("POST /api/v1/vendor/dispatch-request", table_body)
        ],
        [
            Paragraph("4-Stage Logistics & Site MRV", table_body_bold),
            Paragraph("Expediting &rarr; Logistics Tab &rarr; 'Update Shipment / Delivery'", table_body),
            Paragraph("POST /api/v1/delivery/update-stage", table_body)
        ],
        [
            Paragraph("Executive Risk Ribbon & Diagnostics", table_body_bold),
            Paragraph("Expediting Workbench Header Banner & Blocker Drawer", table_body),
            Paragraph("GET /api/v1/executive/risk-summary", table_body)
        ]
    ]

    api_table = Table(api_data, colWidths=[1.8*inch, 2.7*inch, 3.0*inch])
    api_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_brand),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(api_table)
    story.append(Spacer(1, 10))

    # ── SECTION 6: ROLES & RBAC MATRIX ────────────────────────────────────────
    story.append(Paragraph("6. Security, Governance & Role-Based Access Control (RBAC)", h1_style))
    story.append(Paragraph(
        "<b>Segregation of Duties:</b> The architecture establishes strict operational boundaries. Vendors operate only on "
        "their awarded POs (NOI, schedule updates, rework submissions, dispatch requests). Package Expeditors manage schedules, "
        "BOM splits, physical fabrication surveillance, and logistics stages without altering technical quality assessments. "
        "Inspectors and Inspection Engineers retain exclusive authority over technical evaluations, deliverable endorsements, "
        "and IRC releases. All milestones, submissions, and releases generate an immutable cryptographically hashed audit trail.", body_style))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF: {filename}")

if __name__ == "__main__":
    out_name = sys.argv[1] if len(sys.argv) > 1 else "Expediting_and_Inspection_Workflow_Guide.pdf"
    build_pdf(out_name)
