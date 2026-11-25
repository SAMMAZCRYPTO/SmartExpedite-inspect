import sqlite3
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from python_app import database as base_db
from python_app import epc_constants as epc


def get_conn() -> sqlite3.Connection:
    return base_db.get_connection()


def now_iso() -> str:
    return base_db.now_iso()


def init_expediting_db() -> None:
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS EpcProjects (
                id TEXT PRIMARY KEY,
                project_code TEXT UNIQUE NOT NULL,
                project_name TEXT NOT NULL,
                client_name TEXT,
                contractor_name TEXT,
                status TEXT DEFAULT 'ACTIVE',
                start_date TEXT,
                planned_completion TEXT,
                overall_progress_pct REAL DEFAULT 0,
                created_date TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS EpcVendors (
                id TEXT PRIMARY KEY,
                vendor_name TEXT NOT NULL,
                vendor_code TEXT,
                contact_person TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                country TEXT,
                city TEXT,
                vendor_type TEXT DEFAULT 'PACKAGED_EQUIPMENT',
                approved INTEGER DEFAULT 1,
                created_date TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS PurchaseOrders (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                project_code TEXT,
                po_number TEXT UNIQUE NOT NULL,
                po_title TEXT NOT NULL,
                vendor_id TEXT,
                vendor_name TEXT,
                expeditor_id TEXT,
                expeditor_name TEXT,
                po_type TEXT DEFAULT 'PACKAGED',
                po_award_date TEXT,
                contractual_delivery_date TEXT,
                required_on_site_date TEXT,
                incoterms TEXT DEFAULT 'DDP',
                delivery_destination TEXT DEFAULT 'Mussafah Yard',
                platform TEXT,
                budget_ref TEXT,
                po_value REAL DEFAULT 0,
                overall_status TEXT DEFAULT 'ACTIVE',
                overall_progress_pct REAL DEFAULT 0,
                ld_applicable INTEGER DEFAULT 1,
                ld_rate_per_day REAL DEFAULT 0.1,
                ld_max_pct REAL DEFAULT 10.0,
                kom_date TEXT,
                baseline_approved INTEGER DEFAULT 0,
                notes TEXT,
                created_date TEXT,
                updated_date TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ScheduleActivities (
                id TEXT PRIMARY KEY,
                po_id TEXT NOT NULL,
                po_number TEXT,
                activity_code TEXT NOT NULL,
                activity_name TEXT NOT NULL,
                wbs_category TEXT DEFAULT 'FABRICATION',
                sequence INTEGER DEFAULT 1,
                baseline_start TEXT,
                baseline_finish TEXT,
                current_start TEXT,
                current_finish TEXT,
                actual_start TEXT,
                actual_finish TEXT,
                duration_days INTEGER DEFAULT 14,
                percent_complete REAL DEFAULT 0,
                is_critical INTEGER DEFAULT 0,
                predecessors TEXT,
                status TEXT DEFAULT 'NOT_STARTED',
                created_date TEXT,
                updated_date TEXT,
                UNIQUE(po_id, activity_code)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS SubOrders (
                id TEXT PRIMARY KEY,
                po_id TEXT NOT NULL,
                po_number TEXT,
                main_vendor TEXT,
                sub_vendor_name TEXT NOT NULL,
                mfg_location TEXT,
                sub_order_number TEXT NOT NULL,
                item_description TEXT,
                po_placed_forecast TEXT,
                po_placed_actual TEXT,
                mfg_clearance_forecast TEXT,
                mfg_clearance_actual TEXT,
                lead_time_weeks INTEGER DEFAULT 12,
                contractual_delivery_date TEXT,
                forecast_delivery_date TEXT,
                transit_time_days INTEGER DEFAULT 0,
                expected_arrival_workshop TEXT,
                raw_date TEXT,
                float_days INTEGER,
                delay_status TEXT DEFAULT 'ON_TRACK',
                delay_reasons TEXT,
                contact_details TEXT,
                unpriced_po_file_uri TEXT,
                unpriced_po_file_name TEXT,
                created_date TEXT,
                updated_date TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS POLineItems (
                id TEXT PRIMARY KEY,
                po_id TEXT NOT NULL,
                po_number TEXT,
                item_no TEXT,
                tag_number TEXT NOT NULL,
                description TEXT,
                quantity REAL DEFAULT 1,
                uom TEXT DEFAULT 'EA',
                size TEXT,
                pressure_rating TEXT,
                moc_body TEXT,
                moc_trim TEXT,
                release_qty REAL DEFAULT 0,
                hold_qty REAL DEFAULT 0,
                dispatched_qty REAL DEFAULT 0,
                cdd_date TEXT,
                ros_date TEXT,
                platform TEXT,
                heat_lot_number TEXT,
                created_date TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS BulkManufacturingSteps (
                id TEXT PRIMARY KEY,
                line_item_id TEXT NOT NULL,
                po_id TEXT NOT NULL,
                po_number TEXT,
                tag_number TEXT,
                heat_lot_number TEXT,
                stage_name TEXT NOT NULL,
                stage_label TEXT,
                planned_date TEXT,
                forecast_date TEXT,
                actual_date TEXT,
                status TEXT DEFAULT 'PENDING',
                inspection_cert_32_no TEXT,
                inspection_cert_date TEXT,
                remarks TEXT,
                created_date TEXT,
                UNIQUE(line_item_id, stage_name)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS VDRLDocuments (
                id TEXT PRIMARY KEY,
                po_id TEXT NOT NULL,
                po_number TEXT,
                doc_number TEXT NOT NULL,
                doc_title TEXT NOT NULL,
                discipline TEXT DEFAULT 'MECHANICAL',
                revision TEXT DEFAULT 'A',
                planned_submission_date TEXT,
                forecast_submission_date TEXT,
                actual_submission_date TEXT,
                epc_review_due_date TEXT,
                actual_return_date TEXT,
                approval_code TEXT DEFAULT 'UNDER_REVIEW',
                delay_days INTEGER DEFAULT 0,
                remarks TEXT,
                created_date TEXT,
                updated_date TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS RAILItems (
                id TEXT PRIMARY KEY,
                po_id TEXT,
                po_number TEXT DEFAULT 'ALL',
                action_item_no TEXT NOT NULL,
                category TEXT DEFAULT 'ENGINEERING',
                platform_unit TEXT,
                issue_description TEXT NOT NULL,
                originator TEXT,
                date_origin TEXT,
                action_by TEXT DEFAULT 'VENDOR',
                target_date TEXT,
                schedule_impact TEXT DEFAULT 'MAJOR',
                followup_remarks TEXT,
                status TEXT DEFAULT 'OPEN',
                closure_date TEXT,
                created_date TEXT,
                updated_date TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS EpcInspectionNotifications (
                id TEXT PRIMARY KEY,
                po_id TEXT NOT NULL,
                po_number TEXT,
                vendor_name TEXT,
                activity_id TEXT,
                activity_code TEXT,
                activity_name TEXT,
                planned_date TEXT,
                requested_date TEXT,
                inspection_type TEXT DEFAULT 'WITNESS',
                location TEXT,
                scope TEXT,
                status TEXT DEFAULT 'SUBMITTED',
                notified_date TEXT,
                inspector_remarks TEXT,
                created_date TEXT
            )
            """
        )
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS IX_PurchaseOrders_ProjectId ON PurchaseOrders(project_id)",
            "CREATE INDEX IF NOT EXISTS IX_ScheduleActivities_PoId ON ScheduleActivities(po_id)",
            "CREATE INDEX IF NOT EXISTS IX_SubOrders_PoId ON SubOrders(po_id)",
            "CREATE INDEX IF NOT EXISTS IX_POLineItems_PoId ON POLineItems(po_id)",
            "CREATE INDEX IF NOT EXISTS IX_BulkSteps_PoId ON BulkManufacturingSteps(po_id)",
            "CREATE INDEX IF NOT EXISTS IX_VDRL_PoId ON VDRLDocuments(po_id)",
            "CREATE INDEX IF NOT EXISTS IX_RAIL_PoId ON RAILItems(po_id)",
            "CREATE INDEX IF NOT EXISTS IX_EpcNOI_PoId ON EpcInspectionNotifications(po_id)",
        ]:
            cur.execute(idx_sql)
        conn.commit()

    _seed_expediting_data_if_empty()


def _seed_expediting_data_if_empty() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cnt = cur.execute("SELECT COUNT(*) FROM PurchaseOrders").fetchone()[0]
        if cnt > 0:
            return

        ts = now_iso()

        # 1. Seed 2 EPC Projects (§9)
        projects = [
            (
                "epc-proj-1",
                "ADNOC-UZ750",
                "Upper Zakum 750K EPC Surface Facilities",
                "ADNOC Offshore",
                "NPCC / Technip Energies JV",
                "ACTIVE",
                "2026-01-15",
                "2027-06-30",
                62.0,
                ts,
            ),
            (
                "epc-proj-2",
                "DALMA-GAS-02",
                "Dalma Gas Development Package B",
                "ADNOC Sour Gas",
                "Petrofac Emirates",
                "ACTIVE",
                "2026-03-01",
                "2027-09-15",
                44.0,
                ts,
            ),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO EpcProjects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            projects,
        )

        # 2. Seed 6 Approved Vendors (§9)
        vendors = [
            ("vend-1", "Petronash FZE", "VND-PET-01", "Rajesh Menon", "rmenon@petronash.com", "+971-4-8861200", "UAE", "Jebel Ali, Dubai", "PACKAGED_EQUIPMENT", 1, ts),
            ("vend-2", "Fangzheng Valve Group Co., Ltd", "VND-FZV-02", "Vivian Jin", "sales9@fzvgroup.com", "+86-577-67356515", "China", "Wenzhou", "BULK_MATERIAL", 1, ts),
            ("vend-3", "Sulzer Pumps Wastewater UK", "VND-SUL-03", "David Clark", "d.clark@sulzer.com", "+44-113-2701234", "UK", "Leeds", "PACKAGED_EQUIPMENT", 1, ts),
            ("vend-4", "Ducab High Voltage", "VND-DUC-04", "Tariq Al Mansoori", "tariq@ducab.com", "+971-2-5027777", "UAE", "Abu Dhabi", "BULK_MATERIAL", 1, ts),
            ("vend-5", "Atlas Copco Energas GmbH", "VND-ATC-05", "Klaus Weber", "k.weber@atlascopco.com", "+49-2236-96500", "Germany", "Cologne", "PACKAGED_EQUIPMENT", 1, ts),
            ("vend-6", "Frames Energy Systems B.V.", "VND-FRM-06", "Jan de Vries", "j.devries@frames-group.com", "+31-172-461800", "Netherlands", "Alphen aan den Rijn", "BOTH", 1, ts),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO EpcVendors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            vendors,
        )

        # 3. Seed 4 Purchase Orders (§9: 3 Packaged, 1 Bulk)
        pos = [
            (
                "po-1",
                "epc-proj-1",
                "ADNOC-UZ750",
                "4500018920",
                "Chemical Injection Skid Packages (6 Sets)",
                "vend-1",
                "Petronash FZE",
                "00000000-0000-0000-0000-000000000003",
                "QC Engineer",
                "PACKAGED",
                "2026-05-01",
                "2026-12-15",
                "2027-01-10",
                "DDP",
                "Mussafah Yard",
                "UZ-WP4",
                "BDG-ME-104",
                2850000.0,
                "ACTIVE",
                58.0,
                1,
                0.15,
                10.0,
                "2026-11-20",
                1,
                "Critical chemical dosing skids for UZ750 wellhead platforms.",
                ts,
                ts,
            ),
            (
                "po-2",
                "epc-proj-1",
                "ADNOC-UZ750",
                "1061008122",
                "High-Pressure Trunnion Mounted Ball Valves (CF8M)",
                "vend-2",
                "Fangzheng Valve Group Co., Ltd",
                "00000000-0000-0000-0000-000000000003",
                "QC Engineer",
                "BULK",
                "2026-04-10",
                "2026-11-30",
                "2026-12-20",
                "CFR",
                "Khalifa Port",
                "UZ-CPP",
                "BDG-PV-212",
                1420000.0,
                "ACTIVE",
                70.0,
                1,
                0.10,
                10.0,
                "2026-11-18",
                1,
                "Bulk valve supply linked with InspectFlow Notification 1061008122-FAN-NOI-029.",
                ts,
                ts,
            ),
            (
                "po-3",
                "epc-proj-2",
                "DALMA-GAS-02",
                "4500021405",
                "Multistage Centrifugal Export Pumps (API 610 BB3)",
                "vend-3",
                "Sulzer Pumps Wastewater UK",
                None,
                None,
                "PACKAGED",
                "2026-06-15",
                "2027-02-28",
                "2027-03-20",
                "FOB",
                "Mussafah Yard",
                "DLM-P1",
                "BDG-ROT-08",
                4100000.0,
                "CRITICAL_DELAY",
                36.0,
                1,
                0.20,
                10.0,
                "2026-11-25",
                1,
                "Sub-vendor casing casting delay impacting assembly.",
                ts,
                ts,
            ),
            (
                "po-4",
                "epc-proj-2",
                "DALMA-GAS-02",
                "4500023990",
                "Instrument Air Compressor Package",
                "vend-5",
                "Atlas Copco Energas GmbH",
                "00000000-0000-0000-0000-000000000001",
                "System Administrator",
                "PACKAGED",
                "2026-07-01",
                "2027-03-15",
                "2027-04-01",
                "DAP",
                "Mussafah Yard",
                "DLM-UTIL",
                "BDG-ROT-19",
                1980000.0,
                "ACTIVE",
                45.0,
                1,
                0.10,
                10.0,
                "2026-11-28",
                0,
                "Awaiting baseline schedule approval.",
                ts,
                ts,
            ),
        ]
        cur.executemany(
            """
            INSERT OR IGNORE INTO PurchaseOrders VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            pos,
        )

        # 4. Seed 4 SubOrders with Float calculations (§8.1 & §9)
        suborders_raw = [
            (
                "so-1",
                "po-1",
                "4500018920",
                "Petronash FZE",
                "Milton Roy Europe",
                "Pont-Saint-Pierre, France",
                "SO-PET-881",
                "API 675 Plunger Metering Pumps (12 Nos)",
                "2026-06-01",
                "2026-06-05",
                "2026-07-01",
                "2026-07-10",
                16,
                "2026-10-15",
                "2026-11-18",
                12,
                "2026-11-20",
                "Diaphragm forging batch re-heat treatment",
                "p.laurent@miltonroy.com",
            ),
            (
                "so-2",
                "po-1",
                "4500018920",
                "Petronash FZE",
                "WIKA Alexander Wiegand SE",
                "Klingenberg, Germany",
                "SO-PET-884",
                "Inconel 625 Pressure Transmitters & Gauges",
                "2026-06-10",
                "2026-06-10",
                "2026-06-25",
                "2026-06-25",
                10,
                "2026-09-30",
                "2026-10-25",
                7,
                "2026-11-12",
                "On schedule",
                "export@wika.de",
            ),
            (
                "so-3",
                "po-1",
                "4500018920",
                "Petronash FZE",
                "Swagelok Manufacturing",
                "Solon, Ohio, USA",
                "SO-PET-892",
                "Super Duplex 2507 Tubing & Manifolds",
                "2026-06-15",
                "2026-06-15",
                "2026-07-01",
                "2026-07-01",
                12,
                "2026-09-15",
                "2026-09-20",
                10,
                "2026-11-05",
                "Delivered to Jebel Ali workshop",
                "orders@swagelok.com",
            ),
            (
                "so-4",
                "po-3",
                "4500021405",
                "Sulzer Pumps Wastewater UK",
                "Goodwin Steel Castings Ltd",
                "Stoke-on-Trent, UK",
                "SO-SUL-309",
                "ASTM A995 Gr. 5A Super Duplex Pump Casings",
                "2026-07-10",
                "2026-07-18",
                "2026-08-01",
                "2026-08-12",
                20,
                "2026-11-15",
                "2026-12-18",
                5,
                "2026-12-01",
                "Upgrade weld repair after RT examination",
                "foundry@goodwinsteel.co.uk",
            ),
        ]
        for s in suborders_raw:
            flt, arr, dstat = epc.calc_float(s[14], s[15], s[16])
            cur.execute(
                """
                INSERT OR IGNORE INTO SubOrders VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?
                )
                """,
                (
                    s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7],
                    s[8], s[9], s[10], s[11], s[12], s[13], s[14], s[15],
                    arr, s[16], flt, dstat, s[17], s[18], ts, ts
                ),
            )

        # 5. Seed 3 POLineItems + 30 BulkManufacturingSteps for PO-2 (Bulk Valves)
        line_items = [
            ("li-1", "po-2", "1061008122", "154", "BV-154-CF8M", "Ball Valve Flanged Long Pattern Reduced Bore 4\" 600#", 12, "PCS", "4 inch", "Class 600", "ASTM A351 CF8M", "316SS", 8, 2, 4, "2026-11-30", "2026-12-20", "UZ-CPP", "HT-2026-8821", ts),
            ("li-2", "po-2", "1061008122", "587", "BV-587-TRUN", "Ball Valve Trunnion Mounted 8\" 900# RJ", 6, "PCS", "8 inch", "Class 900", "ASTM A351 CF8M", "F51 Duplex", 4, 2, 0, "2026-11-30", "2026-12-20", "UZ-CPP", "HT-2026-8845", ts),
            ("li-3", "po-2", "1061008122", "773", "BV-773-GEAR", "Ball Valve Full Bore Gear Operated 12\" 1500#", 4, "PCS", "12 inch", "Class 1500", "ASTM A351 CF8M", "Inconel 625", 0, 4, 0, "2026-11-30", "2026-12-20", "UZ-CPP", "HT-2026-8902", ts),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO POLineItems VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            line_items,
        )

        completed_counts = {"li-1": 8, "li-2": 6, "li-3": 4}
        for li in line_items:
            li_id, po_id, po_num, _, tag, *_, heat, _ = li
            comp_n = completed_counts[li_id]
            for st_idx, stg in enumerate(epc.BULK_STAGES):
                is_done = st_idx < comp_n
                cur.execute(
                    """
                    INSERT OR IGNORE INTO BulkManufacturingSteps VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        f"bms-{li_id}-{st_idx+1}",
                        li_id,
                        po_id,
                        po_num,
                        tag,
                        heat,
                        stg["name"],
                        stg["label"],
                        "2026-09-01",
                        "2026-10-15",
                        "2026-10-12" if is_done else None,
                        "COMPLETED" if is_done else "PENDING",
                        "CERT-3.2-089" if (is_done and stg["name"] == "CERT_32_ISSUANCE") else None,
                        "2026-10-12" if is_done else None,
                        None,
                        ts,
                    ),
                )

        # 6. Seed 4 VDRLDocuments (§8.2 & §9)
        vdrl_docs = [
            ("vdrl-1", "po-1", "4500018920", "UZ750-PET-GA-001", "General Arrangement & Skid Layout Drawing", "MECHANICAL", "B", "2026-06-15", "2026-06-15", "2026-06-16", "2026-06-30", "2026-06-28", "CODE_1", 0, "Approved with minor nozzle orientation comments", ts, ts),
            ("vdrl-2", "po-1", "4500018920", "UZ750-PET-ITP-002", "Inspection & Test Plan (ITP) — Chemical Injection Skid", "MECHANICAL", "A", "2026-07-01", "2026-07-01", "2026-07-02", "2026-07-16", "2026-07-15", "APPROVED", 0, "Final approved for construction", ts, ts),
            ("vdrl-3", "po-1", "4500018920", "UZ750-PET-EL-009", "Hazardous Area Junction Box Wiring Diagram", "ELECTRICAL", "0", "2026-10-01", "2026-10-05", "2026-10-05", "2026-10-19", None, "UNDER_REVIEW", 26, "Awaiting E&I Lead Engineer review — Past 14d SLA", ts, ts),
            ("vdrl-4", "po-3", "4500021405", "DLM-SUL-CALC-004", "API 610 Rotor Lateral & Torsional Critical Speed Analysis", "MECHANICAL", "A", "2026-09-20", "2026-09-25", "2026-09-25", "2026-10-09", None, "CODE_2", 36, "Resubmission overdue from vendor", ts, ts),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO VDRLDocuments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            vdrl_docs,
        )

        # 7. Seed 4 RAILItems (§8.3 & §9)
        rail_items = [
            ("rail-1", "po-1", "4500018920", "RAIL-4500018920-001", "SUB_VENDOR", "UZ-WP4", "Milton Roy metering pump diaphragm forging heat-treatment retest delay (Float -10d)", "QC Engineer", "2026-10-20", "VENDOR", "2026-11-22", "CRITICAL", "Air-freight option requested from France to Jebel Ali", "OPEN", None, ts, ts),
            ("rail-2", "po-1", "4500018920", "RAIL-4500018920-002", "ENGINEERING", "UZ-WP4", "Close out E&I junction box wiring review UZ750-PET-EL-009 (overdue SLA)", "Package Expeditor", "2026-10-25", "ENGINEERING", "2026-11-18", "MAJOR", "Expedited with Lead Electrical Engineer", "PENDING_REVIEW", None, ts, ts),
            ("rail-3", "po-2", "1061008122", "RAIL-1061008122-001", "QUALITY", "UZ-CPP", "Gear handwheel turns exceeded 80-turn ITP Step 4.8 limit during torque test", "Fulkrum Inspector", "2026-08-24", "VENDOR", "2026-09-15", "MAJOR", "Bevel gear ratio modified and re-witnessed satisfactorily", "CLOSED", "2026-09-14", ts, ts),
            ("rail-4", "po-3", "4500021405", "RAIL-4500021405-001", "SUB_VENDOR", "DLM-P1", "Goodwin Steel pump casing RT upgrade weld repair schedule recovery plan", "PExM", "2026-11-01", "VENDOR", "2026-11-25", "CRITICAL", "Weekly foundry progress audit scheduled", "OPEN", None, ts, ts),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO RAILItems VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rail_items,
        )
        conn.commit()

    # Generate standard 23-activity baselines for PO-1, PO-2, PO-3
    generate_standard_baseline("po-1", progress_override=58)
    generate_standard_baseline("po-2", progress_override=70)
    generate_standard_baseline("po-3", progress_override=36)


# ── CRUD & Business Logic Functions ──────────────────────────────────────────

def list_epc_projects() -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM EpcProjects ORDER BY created_date DESC").fetchall()]
        for r in rows:
            r["po_count"] = conn.execute(
                "SELECT COUNT(*) FROM PurchaseOrders WHERE project_code = ?", (r["project_code"],)
            ).fetchone()[0]
        return rows


def create_epc_project(data: Dict[str, Any]) -> Dict[str, Any]:
    init_expediting_db()
    pid = str(uuid.uuid4())
    code = (data.get("project_code") or data.get("code") or f"PRJ-{pid[:4].upper()}").strip().upper()
    name = (data.get("project_name") or data.get("name") or "New EPC Project").strip()
    start_d = data.get("start_date") or date.today().isoformat()
    end_d = data.get("planned_completion") or data.get("end_date") or (date.today() + timedelta(days=365)).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO EpcProjects (
                id, project_code, project_name, client_name, contractor_name,
                status, start_date, planned_completion, overall_progress_pct, created_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                code,
                name,
                data.get("client_name") or "",
                data.get("contractor_name") or data.get("location") or "",
                data.get("status", "ACTIVE"),
                start_d,
                end_d,
                float(data.get("overall_progress_pct") or 0),
                now_iso(),
            ),
        )
        conn.commit()
    res = next((p for p in list_epc_projects() if p["id"] == pid), {"id": pid, "project_code": code, "project_name": name})
    return _norm_project(res)


def list_epc_vendors() -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM EpcVendors ORDER BY vendor_name ASC").fetchall()]


def create_epc_vendor(data: Dict[str, Any]) -> Dict[str, Any]:
    init_expediting_db()
    vid = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO EpcVendors (
                id, vendor_name, vendor_code, contact_person, contact_email,
                contact_phone, country, city, vendor_type, approved, created_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                vid,
                (data.get("vendor_name") or data.get("name") or "").strip(),
                data.get("vendor_code") or f"VND-{vid[:5].upper()}",
                data.get("contact_person"),
                data.get("contact_email"),
                data.get("contact_phone"),
                data.get("country"),
                data.get("city"),
                data.get("vendor_type") or data.get("categories") or "PACKAGED_EQUIPMENT",
                now_iso(),
            ),
        )
        conn.commit()
    return _norm_vendor(next(v for v in list_epc_vendors() if v["id"] == vid))


def list_purchase_orders() -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM PurchaseOrders ORDER BY created_date DESC").fetchall()]


def get_purchase_order(po_id: str) -> Optional[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM PurchaseOrders WHERE id = ?", (po_id,)).fetchone()
        return dict(row) if row else None


def create_purchase_order(data: Dict[str, Any]) -> Dict[str, Any]:
    init_expediting_db()
    poid = str(uuid.uuid4())
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO PurchaseOrders (
                id, project_id, project_code, po_number, po_title,
                vendor_id, vendor_name, expeditor_id, expeditor_name,
                po_type, po_award_date, contractual_delivery_date, required_on_site_date,
                incoterms, delivery_destination, platform, budget_ref, po_value,
                overall_status, overall_progress_pct, ld_applicable, ld_rate_per_day,
                ld_max_pct, kom_date, baseline_approved, notes, created_date, updated_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0.1, 10.0, ?, 0, ?, ?, ?)
            """,
            (
                poid,
                data.get("project_id"),
                data.get("project_code") or data.get("project_name"),
                data.get("po_number", "").strip(),
                (data.get("po_title") or data.get("description") or "").strip(),
                data.get("vendor_id"),
                data.get("vendor_name"),
                data.get("expeditor_id"),
                data.get("expeditor_name") or data.get("assigned_expeditor"),
                data.get("po_type", "PACKAGED"),
                data.get("po_award_date") or date.today().isoformat(),
                data.get("contractual_delivery_date") or data.get("contract_delivery_date"),
                data.get("required_on_site_date") or data.get("required_at_site_date"),
                data.get("incoterms") or data.get("incoterm") or "DDP",
                data.get("delivery_destination", "Mussafah Yard"),
                data.get("platform"),
                data.get("budget_ref"),
                float(data.get("po_value") or 0),
                data.get("overall_status", "ACTIVE"),
                float(data.get("overall_progress_pct") or 0),
                data.get("kom_date"),
                data.get("notes"),
                ts,
                ts,
            ),
        )
        conn.commit()
    return _norm_po(get_purchase_order(poid) or {})


def assign_po_expeditor(po_id: str, expeditor_id: Optional[str], expeditor_name: Optional[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE PurchaseOrders SET expeditor_id = ?, expeditor_name = ?, updated_date = ? WHERE id = ?",
            (expeditor_id, expeditor_name, now_iso(), po_id),
        )
        conn.commit()


# ── Schedule Activities & Standard 23-Activity Baseline (§6.5 & §8.7) ────────

def list_schedule_activities(po_id: Optional[str] = None) -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        if po_id:
            rows = conn.execute(
                "SELECT * FROM ScheduleActivities WHERE po_id = ? ORDER BY sequence ASC", (po_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ScheduleActivities ORDER BY sequence ASC").fetchall()
        return [dict(r) for r in rows]


def generate_standard_baseline(po_id: str, progress_override: Any = None, force: bool = False) -> List[Dict[str, Any]]:
    po = get_purchase_order(po_id)
    if not po:
        return []
    if po.get("baseline_approved") and not force:
        # Frozen baseline invariant: return existing activities without mutating baseline dates
        return list_schedule_activities(po_id)
    award = epc.parse_iso_date(po.get("po_award_date")) or date.today()
    ts = now_iso()
    if isinstance(progress_override, str):
        progress_override = None

    with get_conn() as conn:
        for i, act in enumerate(epc.STANDARD_ACTIVITIES):
            seq = i + 1
            start_d = award + timedelta(days=i * 7)
            finish_d = start_d + timedelta(days=14)
            is_crit = 1 if seq in epc.CRITICAL_BASELINE_SEQUENCES else 0

            if progress_override is not None:
                cutoff = int((progress_override / 100.0) * len(epc.STANDARD_ACTIVITIES))
                if i < cutoff:
                    pct = 100.0
                    st_val = "COMPLETED"
                elif i == cutoff:
                    pct = 50.0
                    st_val = "IN_PROGRESS"
                else:
                    pct = 0.0
                    st_val = "NOT_STARTED"
            else:
                pct = 100.0 if i == 0 else 0.0
                st_val = "COMPLETED" if i == 0 else "NOT_STARTED"

            conn.execute(
                """
                INSERT INTO ScheduleActivities (
                    id, po_id, po_number, activity_code, activity_name,
                    wbs_category, sequence, baseline_start, baseline_finish,
                    current_start, current_finish, actual_start, actual_finish,
                    duration_days, percent_complete, is_critical, status,
                    created_date, updated_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 14, ?, ?, ?, ?, ?)
                ON CONFLICT(po_id, activity_code) DO UPDATE SET
                    baseline_start = excluded.baseline_start,
                    baseline_finish = excluded.baseline_finish,
                    updated_date = excluded.updated_date
                """,
                (
                    str(uuid.uuid4()),
                    po_id,
                    po["po_number"],
                    act["code"],
                    act["name"],
                    act["category"],
                    seq,
                    start_d.isoformat(),
                    finish_d.isoformat(),
                    start_d.isoformat(),
                    finish_d.isoformat(),
                    start_d.isoformat() if pct == 100 else None,
                    finish_d.isoformat() if pct == 100 else None,
                    pct,
                    is_crit,
                    st_val,
                    ts,
                    ts,
                ),
            )
        conn.execute(
            "UPDATE PurchaseOrders SET baseline_approved = 1, updated_date = ? WHERE id = ?",
            (ts, po_id),
        )
        conn.commit()
    return list_schedule_activities(po_id)


def upsert_schedule_activities(
    po_id: str, po_number_or_activities: Any, activities: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """Idempotent upsert on (po_id, activity_code) (§9.1 step 8)."""
    if activities is None and isinstance(po_number_or_activities, list):
        activities = po_number_or_activities
        po = get_purchase_order(po_id)
        po_number = po["po_number"] if po else ""
    else:
        po_number = str(po_number_or_activities or "")
        activities = activities or []
    added = 0
    updated = 0
    ts = now_iso()
    with get_conn() as conn:
        for idx, a in enumerate(activities):
            code = (a.get("activity_code") or f"PARSED-{idx+1}").strip()
            name = (a.get("activity_name") or "").strip()
            if not name:
                continue
            wbs = (a.get("wbs_category") or "FABRICATION").strip().upper()
            if wbs not in epc.WBS_CATEGORIES:
                wbs = "FABRICATION"

            b_start = a.get("baseline_start") or a.get("current_start")
            b_fin = a.get("baseline_finish") or a.get("current_finish")
            c_start = a.get("current_start") or b_start
            c_fin = a.get("current_finish") or b_fin
            pct = max(0.0, min(100.0, float(a.get("percent_complete") or 0.0)))
            status = "COMPLETED" if pct >= 100.0 else ("IN_PROGRESS" if pct > 0.0 else "NOT_STARTED")
            is_crit = 1 if (a.get("is_critical") or a.get("is_critical_path")) else 0

            existing = conn.execute(
                "SELECT id FROM ScheduleActivities WHERE po_id = ? AND activity_code = ?",
                (po_id, code),
            ).fetchone()
            if existing:
                updated += 1
                conn.execute(
                    """
                    UPDATE ScheduleActivities
                    SET activity_name = ?, wbs_category = ?,
                        current_start = ?, current_finish = ?,
                        actual_start = COALESCE(?, actual_start),
                        actual_finish = COALESCE(?, actual_finish),
                        percent_complete = ?, is_critical = ?, status = ?, updated_date = ?
                    WHERE po_id = ? AND activity_code = ?
                    """,
                    (
                        name,
                        wbs,
                        c_start,
                        c_fin,
                        a.get("actual_start"),
                        a.get("actual_finish"),
                        pct,
                        is_crit,
                        status,
                        ts,
                        po_id,
                        code,
                    ),
                )
            else:
                added += 1
                conn.execute(
                    """
                    INSERT INTO ScheduleActivities (
                        id, po_id, po_number, activity_code, activity_name,
                        wbs_category, sequence, baseline_start, baseline_finish,
                        current_start, current_finish, actual_start, actual_finish,
                        duration_days, percent_complete, is_critical, status,
                        created_date, updated_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        po_id,
                        po_number,
                        code,
                        name,
                        wbs,
                        int(a.get("sequence") or (idx + 1)),
                        b_start,
                        b_fin,
                        c_start,
                        c_fin,
                        a.get("actual_start"),
                        a.get("actual_finish"),
                        int(a.get("duration_days") or 0),
                        pct,
                        is_crit,
                        status,
                        ts,
                        ts,
                    ),
                )
        conn.commit()
    return get_schedule_activities(po_id)


# ── Sub-Orders & Float (§8.1) ────────────────────────────────────────────────

def list_suborders(po_id: Optional[str] = None) -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        if po_id:
            rows = conn.execute("SELECT * FROM SubOrders WHERE po_id = ? ORDER BY raw_date ASC", (po_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM SubOrders ORDER BY raw_date ASC").fetchall()
        return [dict(r) for r in rows]


def save_suborder(data: Dict[str, Any]) -> Dict[str, Any]:
    init_expediting_db()
    sid = data.get("id") or str(uuid.uuid4())
    f_date = data.get("forecast_delivery_date") or data.get("sub_vendor_eta_date")
    r_date = data.get("raw_date") or data.get("required_at_workshop_date")
    sub_no = data.get("sub_order_number") or data.get("sub_po_number") or f"SO-{int(datetime.now().timestamp()) % 100000}"
    item_desc = data.get("item_description") or data.get("material_description")
    mfg_loc = data.get("mfg_location") or data.get("country_of_origin")
    flt, arr, dstat = epc.calc_float(
        f_date,
        data.get("transit_time_days"),
        r_date,
    )
    ts = now_iso()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM SubOrders WHERE id = ?", (sid,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE SubOrders
                SET sub_vendor_name = ?, mfg_location = ?, sub_order_number = ?,
                    item_description = ?, forecast_delivery_date = ?, transit_time_days = ?,
                    expected_arrival_workshop = ?, raw_date = ?, float_days = ?,
                    delay_status = ?, delay_reasons = ?, unpriced_po_file_uri = COALESCE(?, unpriced_po_file_uri),
                    unpriced_po_file_name = COALESCE(?, unpriced_po_file_name), updated_date = ?
                WHERE id = ?
                """,
                (
                    data.get("sub_vendor_name", "Unknown"),
                    mfg_loc,
                    sub_no,
                    item_desc,
                    f_date,
                    int(data.get("transit_time_days") or 0),
                    arr,
                    r_date,
                    flt,
                    dstat,
                    data.get("delay_reasons"),
                    data.get("unpriced_po_file_uri"),
                    data.get("unpriced_po_file_name"),
                    ts,
                    sid,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO SubOrders (
                    id, po_id, po_number, main_vendor, sub_vendor_name, mfg_location,
                    sub_order_number, item_description, forecast_delivery_date,
                    transit_time_days, expected_arrival_workshop, raw_date,
                    float_days, delay_status, delay_reasons,
                    unpriced_po_file_uri, unpriced_po_file_name, created_date, updated_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    data.get("po_id"),
                    data.get("po_number"),
                    data.get("main_vendor"),
                    data.get("sub_vendor_name", "Unknown"),
                    mfg_loc,
                    sub_no,
                    item_desc,
                    f_date,
                    int(data.get("transit_time_days") or 0),
                    arr,
                    r_date,
                    flt,
                    dstat,
                    data.get("delay_reasons"),
                    data.get("unpriced_po_file_uri"),
                    data.get("unpriced_po_file_name"),
                    ts,
                    ts,
                ),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM SubOrders WHERE id = ?", (sid,)).fetchone()
        return _norm_suborder(dict(row))


def delete_suborder(suborder_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM SubOrders WHERE id = ?", (suborder_id,))
        conn.commit()


# ── Bulk Line Items & 10-Stage Manufacturing Matrix (§8.4 & §8.8) ────────────

def list_po_line_items(po_id: str) -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute("SELECT * FROM POLineItems WHERE po_id = ? ORDER BY item_no ASC", (po_id,)).fetchall()
        ]


def list_bulk_steps(po_id: str) -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute("SELECT * FROM BulkManufacturingSteps WHERE po_id = ?", (po_id,)).fetchall()
        ]


def toggle_bulk_stage(
    line_item_id: str,
    po_id: str,
    po_number: str,
    tag_number: str,
    heat_lot: str = "",
    stage_name: str = "",
    stage_label: str = "",
    stage_sequence: int = 1,
) -> None:
    """
    §8.4: Clicking a stage with no record creates it as COMPLETED with actual_date = today;
    clicking a completed stage flips it to PENDING and clears the date.
    """
    if not stage_label:
        stage_label = next((s["label"] for s in epc.BULK_STAGES if s["name"] == stage_name), stage_name)
    stage_order = [s["name"] for s in epc.BULK_STAGES]
    today_iso = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, status FROM BulkManufacturingSteps WHERE line_item_id = ? AND stage_name = ?",
            (line_item_id, stage_name),
        ).fetchone()
        all_rows = {
            r["stage_name"]: r["status"]
            for r in conn.execute(
                "SELECT stage_name, status FROM BulkManufacturingSteps WHERE line_item_id = ?",
                (line_item_id,),
            ).fetchall()
        }
        next_status = "PENDING" if (row and row["status"] == "COMPLETED") else "COMPLETED"
        if next_status == "COMPLETED" and stage_name in stage_order:
            idx = stage_order.index(stage_name)
            missing_prev = [
                stage_order[i] for i in range(idx) if all_rows.get(stage_order[i]) != "COMPLETED"
            ]
            if missing_prev:
                raise ValueError(
                    f"Cannot mark '{stage_name}' completed before prerequisite stage(s): {', '.join(missing_prev)}"
                )
        if next_status == "PENDING" and stage_name in ("DISPATCH", "CERT_32_ISSUANCE"):
            raise ValueError(f"Completed '{stage_name}' milestone is locked and cannot be reverted directly.")
        if not row:
            conn.execute(
                """
                INSERT INTO BulkManufacturingSteps (
                    id, line_item_id, po_id, po_number, tag_number, heat_lot_number,
                    stage_name, stage_label, actual_date, status, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?)
                """,
                (
                    str(uuid.uuid4()),
                    line_item_id,
                    po_id,
                    po_number,
                    tag_number,
                    heat_lot,
                    stage_name,
                    stage_label,
                    today_iso,
                    now_iso(),
                ),
            )
        else:
            new_st = "PENDING" if row["status"] == "COMPLETED" else "COMPLETED"
            new_dt = None if new_st == "PENDING" else today_iso
            conn.execute(
                "UPDATE BulkManufacturingSteps SET status = ?, actual_date = ? WHERE id = ?",
                (new_st, new_dt, row["id"]),
            )
        conn.commit()


# ── VDRL Documents & 14-Day SLA (§8.2) ───────────────────────────────────────

def list_vdrl_documents(po_id: Optional[str] = None) -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        if po_id:
            rows = conn.execute("SELECT * FROM VDRLDocuments WHERE po_id = ? ORDER BY doc_number ASC", (po_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM VDRLDocuments ORDER BY doc_number ASC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            due_iso, delay_days, is_overdue = epc.calc_vdrl_sla(
                d.get("actual_submission_date"),
                d.get("planned_submission_date"),
                d.get("epc_review_due_date"),
                d.get("actual_return_date"),
            )
            d["epc_review_due_date"] = due_iso
            d["delay_days"] = delay_days
            d["is_overdue"] = is_overdue
            result.append(d)
        return result


def save_vdrl_document(data: Dict[str, Any]) -> Dict[str, Any]:
    init_expediting_db()
    did = data.get("id") or str(uuid.uuid4())
    doc_no = data.get("doc_number") or data.get("document_code") or "VDRL-NEW"
    doc_t = data.get("doc_title") or data.get("document_title") or "Engineering Document"
    today = date.today()
    planned = data.get("planned_submission_date") or today.isoformat()
    due_default = (epc.parse_iso_date(planned) or today) + timedelta(days=14)
    due_iso, delay_days, _ = epc.calc_vdrl_sla(
        data.get("actual_submission_date"),
        planned,
        data.get("epc_review_due_date") or due_default.isoformat(),
        data.get("actual_return_date"),
    )
    ts = now_iso()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM VDRLDocuments WHERE id = ?", (did,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE VDRLDocuments
                SET doc_number = ?, doc_title = ?, discipline = ?, revision = ?,
                    planned_submission_date = ?, actual_submission_date = ?,
                    epc_review_due_date = ?, actual_return_date = ?,
                    approval_code = ?, delay_days = ?, remarks = ?, updated_date = ?
                WHERE id = ?
                """,
                (
                    doc_no,
                    doc_t,
                    data.get("discipline", "MECHANICAL"),
                    data.get("revision", "A"),
                    planned,
                    data.get("actual_submission_date"),
                    due_iso,
                    data.get("actual_return_date"),
                    data.get("approval_code", "UNDER_REVIEW"),
                    delay_days,
                    data.get("remarks"),
                    ts,
                    did,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO VDRLDocuments (
                    id, po_id, po_number, doc_number, doc_title, discipline, revision,
                    planned_submission_date, forecast_submission_date, actual_submission_date,
                    epc_review_due_date, actual_return_date, approval_code, delay_days,
                    remarks, created_date, updated_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    did,
                    data.get("po_id"),
                    data.get("po_number"),
                    doc_no,
                    doc_t,
                    data.get("discipline", "MECHANICAL"),
                    data.get("revision", "A"),
                    planned,
                    planned,
                    data.get("actual_submission_date"),
                    due_iso,
                    data.get("actual_return_date"),
                    data.get("approval_code", "UNDER_REVIEW"),
                    delay_days,
                    data.get("remarks"),
                    ts,
                    ts,
                ),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM VDRLDocuments WHERE id = ?", (did,)).fetchone()
    if not row:
        raise ValueError(f"VDRL document {did} not found after save")
    return _norm_vdrl(dict(row))


def delete_vdrl_document(doc_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM VDRLDocuments WHERE id = ?", (doc_id,))
        conn.commit()


# ── RAIL Items (§8.3) ────────────────────────────────────────────────────────

def list_rail_items(po_id: Optional[str] = None) -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        if po_id:
            rows = conn.execute("SELECT * FROM RAILItems WHERE po_id = ? ORDER BY created_date DESC", (po_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM RAILItems ORDER BY created_date DESC").fetchall()
        return [dict(r) for r in rows]


def create_rail_item(data: Dict[str, Any]) -> Dict[str, Any]:
    init_expediting_db()
    rid = str(uuid.uuid4())
    po_num = data.get("po_number") or "ALL"
    seg = po_num.split("/")[0] if "/" in po_num else po_num
    with get_conn() as conn:
        seq = conn.execute("SELECT COUNT(*) FROM RAILItems").fetchone()[0] + 1
        item_no = data.get("action_item_no") or f"RAIL-{seg}-{seq:03d}"
        ts = now_iso()
        conn.execute(
            """
            INSERT INTO RAILItems (
                id, po_id, po_number, action_item_no, category, platform_unit,
                issue_description, originator, date_origin, action_by,
                target_date, schedule_impact, followup_remarks, status,
                closure_date, created_date, updated_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', NULL, ?, ?)
            """,
            (
                rid,
                data.get("po_id"),
                po_num,
                item_no,
                data.get("category", "ENGINEERING"),
                data.get("platform_unit"),
                data.get("issue_description") or data.get("action_description") or "",
                data.get("originator", "Expeditor"),
                date.today().isoformat(),
                data.get("action_by") or data.get("owner_name") or "VENDOR",
                data.get("target_date") or data.get("due_date"),
                data.get("schedule_impact") or data.get("impact") or "MAJOR",
                data.get("followup_remarks"),
                ts,
                ts,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM RAILItems WHERE id = ?", (rid,)).fetchone()
    return _norm_rail(dict(row)) if row else {"id": rid}


def advance_rail_item(rail_id: str) -> None:
    """§8.3: OPEN -> PENDING_REVIEW -> CLOSED -> OPEN; stamps/clears closure_date."""
    cycle = {"OPEN": "PENDING_REVIEW", "PENDING_REVIEW": "CLOSED", "CLOSED": "OPEN"}
    with get_conn() as conn:
        row = conn.execute("SELECT status FROM RAILItems WHERE id = ?", (rail_id,)).fetchone()
        if not row:
            return
        next_st = cycle.get(row["status"], "OPEN")
        c_date = date.today().isoformat() if next_st == "CLOSED" else None
        conn.execute(
            "UPDATE RAILItems SET status = ?, closure_date = ?, updated_date = ? WHERE id = ?",
            (next_st, c_date, now_iso(), rail_id),
        )
        conn.commit()


def delete_rail_item(rail_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM RAILItems WHERE id = ?", (rail_id,))
        conn.commit()


# ── EPC Inspection Notifications (§8.5) ──────────────────────────────────────

def list_epc_inspection_notifications(po_id: Optional[str] = None) -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        if po_id:
            rows = conn.execute(
                "SELECT * FROM EpcInspectionNotifications WHERE po_id = ? ORDER BY created_date DESC", (po_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM EpcInspectionNotifications ORDER BY created_date DESC").fetchall()
        return [dict(r) for r in rows]


def create_epc_inspection_notification(data: Dict[str, Any]) -> Dict[str, Any]:
    init_expediting_db()
    nid = str(uuid.uuid4())
    ts = now_iso()
    today_iso = date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO EpcInspectionNotifications (
                id, po_id, po_number, vendor_name, activity_id, activity_code,
                activity_name, planned_date, requested_date, inspection_type,
                location, scope, status, notified_date, inspector_remarks, created_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED', ?, ?, ?)
            """,
            (
                nid,
                data.get("po_id"),
                data.get("po_number"),
                data.get("vendor_name"),
                data.get("activity_id"),
                data.get("activity_code"),
                data.get("activity_name"),
                data.get("planned_date") or data.get("proposed_date") or today_iso,
                data.get("requested_date") or data.get("proposed_date") or today_iso,
                data.get("inspection_type", "WITNESS"),
                data.get("location"),
                data.get("scope") or data.get("notes"),
                today_iso,
                data.get("inspector_remarks") or data.get("contact_person"),
                ts,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM EpcInspectionNotifications WHERE id = ?", (nid,)).fetchone()
    return _norm_insp(dict(row)) if row else {"id": nid}


def update_epc_inspection_notification_status(
    notif_id: str, status: str, remarks: Optional[str] = None
) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE EpcInspectionNotifications SET status = ?, inspector_remarks = COALESCE(?, inspector_remarks) WHERE id = ?",
            (status, remarks, notif_id),
        )
        conn.commit()


# ── Unified Normalized Adapter Layer for UI & Parsers ────────────────────────

def init_expediting_tables() -> None:
    init_expediting_db()


def _norm_project(p: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(p)
    out.setdefault("name", out.get("project_name", ""))
    out.setdefault("code", out.get("project_code", ""))
    out.setdefault("location", out.get("contractor_name") or "")
    out.setdefault("project_manager", "")
    return out


def _norm_vendor(v: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(v)
    out.setdefault("name", out.get("vendor_name", ""))
    out.setdefault("categories", out.get("vendor_type", "PACKAGED_EQUIPMENT"))
    out.setdefault("rating", None)
    return out


def _norm_po(p: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(p)
    out["description"] = out.get("description") or out.get("po_title") or ""
    out["project_name"] = out.get("project_name") or out.get("project_code") or ""
    out["contract_delivery_date"] = out.get("contract_delivery_date") or out.get("contractual_delivery_date") or ""
    out["current_delivery_date"] = out.get("current_delivery_date") or out.get("contractual_delivery_date") or ""
    out["required_at_site_date"] = out.get("required_at_site_date") or out.get("required_on_site_date") or ""
    out["incoterm"] = out.get("incoterm") or out.get("incoterms") or "DDP"
    out["progress_percent"] = float(out.get("progress_percent") if out.get("progress_percent") is not None else (out.get("overall_progress_pct") or 0.0))
    out["assigned_expeditor"] = out.get("assigned_expeditor") if out.get("assigned_expeditor") is not None else (out.get("expeditor_name") or "")
    out.setdefault("vendor_email", "")
    return out


def _norm_activity(a: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    out["is_critical_path"] = bool(out.get("is_critical") or out.get("is_critical_path"))
    return out


def _norm_suborder(s: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(s)
    out["sub_po_number"] = out.get("sub_po_number") or out.get("sub_order_number") or ""
    out["material_description"] = out.get("material_description") or out.get("item_description") or ""
    out["country_of_origin"] = out.get("country_of_origin") or out.get("mfg_location") or "UAE"
    out["required_at_workshop_date"] = out.get("required_at_workshop_date") or out.get("raw_date") or ""
    out["sub_vendor_eta_date"] = out.get("sub_vendor_eta_date") or out.get("expected_arrival_workshop") or out.get("forecast_delivery_date") or ""
    return out


def _norm_line_item(li: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(li)
    out["item_number"] = out.get("item_number") or out.get("item_no") or "0010"
    return out


def _norm_vdrl(d: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(d)
    out["document_code"] = out.get("document_code") or out.get("doc_number") or ""
    out["document_title"] = out.get("document_title") or out.get("doc_title") or ""
    out["review_delay_days"] = out.get("review_delay_days") if out.get("review_delay_days") is not None else (out.get("delay_days") or 0)
    return out


def _norm_rail(r: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(r)
    out["item_number"] = out.get("item_number") or out.get("action_item_no") or ""
    out["action_description"] = out.get("action_description") or out.get("issue_description") or ""
    out["owner_name"] = out.get("owner_name") or out.get("action_by") or "VENDOR"
    out["due_date"] = out.get("due_date") or out.get("target_date") or ""
    out["impact"] = out.get("impact") or out.get("schedule_impact") or "MAJOR"
    return out


def _norm_insp(n: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(n)
    out["proposed_date"] = out.get("proposed_date") or out.get("requested_date") or out.get("planned_date") or ""
    out["notes"] = out.get("notes") or out.get("scope") or out.get("inspector_remarks") or ""
    out["contact_person"] = out.get("contact_person") or out.get("vendor_name") or "QA Manager"
    if out.get("status") == "SUBMITTED":
        out["status"] = "PENDING"
    return out


def get_epc_projects() -> List[Dict[str, Any]]:
    init_expediting_db()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM EpcProjects ORDER BY created_date DESC").fetchall()
        return [_norm_project(dict(r)) for r in rows]


def get_epc_vendors() -> List[Dict[str, Any]]:
    return [_norm_vendor(v) for v in list_epc_vendors()]


def get_purchase_orders() -> List[Dict[str, Any]]:
    return [_norm_po(p) for p in list_purchase_orders()]


def get_schedule_activities(po_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return [_norm_activity(a) for a in list_schedule_activities(po_id)]


def get_expeditors() -> List[Dict[str, Any]]:
    users = base_db.list_users()
    return [
        {"id": u["id"], "full_name": u["full_name"], "email": u["email"], "role": u.get("inspection_role") or u.get("role")}
        for u in users
        if (u.get("inspection_role") or u.get("role")) in ("admin", "expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "qc_manager")
        and str(u.get("user_status") or "active").lower() == "active"
    ]


def update_purchase_order(po_id: str, updates: Dict[str, Any]) -> None:
    existing = get_purchase_order(po_id)
    if not existing:
        raise ValueError(f"Purchase order '{po_id}' not found")
    allowed_map = {
        "assigned_expeditor": "expeditor_name",
        "expeditor_name": "expeditor_name",
        "expeditor_id": "expeditor_id",
        "overall_status": "overall_status",
        "po_title": "po_title",
        "description": "po_title",
        "contractual_delivery_date": "contractual_delivery_date",
        "required_on_site_date": "required_on_site_date",
        "notes": "notes",
    }
    sets = []
    params: List[Any] = []
    for k, col in allowed_map.items():
        if k in updates and updates[k] is not None:
            sets.append(f"{col} = ?")
            params.append(updates[k])
    if sets:
        sets.append("updated_date = ?")
        params.append(now_iso())
        params.append(po_id)
        with get_conn() as conn:
            conn.execute(f"UPDATE PurchaseOrders SET {', '.join(sets)} WHERE id = ?", params)
            conn.commit()


def update_schedule_activity(act_id: str, updates: Dict[str, Any]) -> None:
    with get_conn() as conn:
        pct = max(0.0, min(100.0, float(updates.get("percent_complete", 0))))
        st_val = "COMPLETED" if pct >= 100 else ("IN_PROGRESS" if pct > 0 else "NOT_STARTED")
        is_crit = 1 if updates.get("is_critical_path") else 0
        conn.execute(
            """
            UPDATE ScheduleActivities
            SET current_finish = COALESCE(?, current_finish),
                percent_complete = ?,
                is_critical = ?,
                actual_finish = ?,
                status = ?,
                updated_date = ?
            WHERE id = ?
            """,
            (
                updates.get("current_finish"),
                pct,
                is_crit,
                updates.get("actual_finish"),
                st_val,
                now_iso(),
                act_id,
            ),
        )
        # Recompute PO progress
        row = conn.execute("SELECT po_id FROM ScheduleActivities WHERE id = ?", (act_id,)).fetchone()
        if row:
            po_id = row["po_id"]
            avg_row = conn.execute("SELECT AVG(percent_complete) as avg_p FROM ScheduleActivities WHERE po_id = ?", (po_id,)).fetchone()
            if avg_row and avg_row["avg_p"] is not None:
                conn.execute("UPDATE PurchaseOrders SET overall_progress_pct = ? WHERE id = ?", (round(float(avg_row["avg_p"]), 1), po_id))
        conn.commit()


def create_bulk_line_item(data: Dict[str, Any]) -> Dict[str, Any]:
    lid = str(uuid.uuid4())
    po_id = str(data.get("po_id") or "").strip()
    if not po_id:
        raise ValueError("po_id is required")
    po_number = data.get("po_number", "")
    tag = data.get("tag_number", "TAG-01")
    heat = data.get("heat_lot_number", "HT-001")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO POLineItems (
                id, po_id, po_number, item_no, tag_number, description,
                quantity, uom, heat_lot_number, created_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lid,
                po_id,
                po_number,
                data.get("item_number", "0010"),
                tag,
                data.get("description", ""),
                float(data.get("quantity") or 1),
                data.get("uom", "EA"),
                heat,
                now_iso(),
            ),
        )
        for stg in epc.BULK_STAGES:
            conn.execute(
                """
                INSERT OR IGNORE INTO BulkManufacturingSteps (
                    id, line_item_id, po_id, po_number, tag_number, heat_lot_number,
                    stage_name, stage_label, status, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (str(uuid.uuid4()), lid, po_id, po_number, tag, heat, stg["name"], stg["label"], now_iso()),
            )
        conn.commit()
    return {"id": lid}


def get_rail_items(po_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return [_norm_rail(r) for r in list_rail_items(po_id)]


def update_epc_inspection_status(notif_id: str, status: str) -> None:
    update_epc_inspection_notification_status(notif_id, status)


def get_executive_dashboard_metrics() -> Dict[str, Any]:
    pos = get_purchase_orders()
    expeditors = get_expeditors()
    sub_orders = [_norm_suborder(s) for s in list_suborders()]
    vdrl_docs = [_norm_vdrl(d) for d in list_vdrl_documents()]
    all_activities = get_schedule_activities()

    active_pos_count = sum(1 for p in pos if p.get("overall_status") == "ACTIVE")
    critical_suborders_count = sum(1 for s in sub_orders if s.get("delay_status") == "CRITICAL_DELAY")
    unassigned_pos_count = sum(1 for p in pos if not p.get("assigned_expeditor"))
    overdue_vdrl_count = sum(1 for d in vdrl_docs if d.get("is_overdue"))

    today = date.today()
    in_14d = today + timedelta(days=14)
    upcoming_inspections_14d = 0
    for a in all_activities:
        if a.get("activity_code") in epc.INSPECTION_ACTIVITY_CODES and float(a.get("percent_complete") or 0) < 100:
            cf = epc.parse_iso_date(a.get("current_finish") or a.get("baseline_finish"))
            if cf and today <= cf <= in_14d:
                upcoming_inspections_14d += 1

    return {
        "pos": pos,
        "expeditors": expeditors,
        "all_activities": all_activities,
        "active_pos_count": active_pos_count,
        "critical_suborders_count": critical_suborders_count,
        "unassigned_pos_count": unassigned_pos_count,
        "overdue_vdrl_count": overdue_vdrl_count,
        "upcoming_inspections_14d": upcoming_inspections_14d,
    }


def get_workbench_detail(po_id: str) -> Dict[str, Any]:
    po_raw = get_purchase_order(po_id)
    po = _norm_po(po_raw) if po_raw else {}
    return {
        "po": po,
        "activities": get_schedule_activities(po_id),
        "sub_orders": [_norm_suborder(s) for s in list_suborders(po_id)],
        "line_items": [_norm_line_item(li) for li in list_po_line_items(po_id)],
        "bulk_steps": list_bulk_steps(po_id),
        "vdrl_docs": [_norm_vdrl(d) for d in list_vdrl_documents(po_id)],
        "rail_items": get_rail_items(po_id),
        "inspections": [_norm_insp(n) for n in list_epc_inspection_notifications(po_id)],
    }

