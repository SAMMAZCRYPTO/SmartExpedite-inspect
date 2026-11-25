import json
import sqlite3
import time
import os
from pathlib import Path
from python_app import database as inspectflow_db
from python_app.smartexpedit_server import sx_db, _records, _save_records, _get_sx_state, _save_sx_state, LOCK

PO_NUM = "PO-88001"
SUPPLIER = "Flowserve & Sulzer Consortium"
PROJECT = "Offshore Gas Expansion Project (Train-3)"

def seed_dummy_bom():
    print(f"Creating comprehensive Dummy Bill of Materials for PO: {PO_NUM}...")

    with LOCK, sx_db() as c:
        L = _records(c)
        # Remove existing if any
        L = [r for r in L if str(r.get("po")) != PO_NUM]

        new_po = {
            "po": PO_NUM,
            "rev": "0",
            "supplier": SUPPLIER.upper(),
            "supplierShort": "Flowserve-Sulzer",
            "mrRef": f"MR-{PO_NUM}",
            "project": PROJECT,
            "head": "Chemical Injection Package & Cryogenic Ball Valves",
            "ccy": "USD",
            "value": 2450000,
            "incoterm": "DDP Site Warehouse",
            "issuedOn": "2026-10-01",
            "assignedTo": "Ali (Lead Expeditor)",
            "stage": "fab",
            "lots": [
                {"id": "Lot 1 (Skid Base)", "date": "2026-12-15", "grace": 0, "ld": True},
                {"id": "Lot 2 (Valves Batch 1)", "date": "2026-12-20", "grace": 0, "ld": True},
                {"id": "Lot 3 (Control Panels)", "date": "2027-01-10", "grace": 0, "ld": False},
            ],
            # Detailed Bill of Materials (BOM) Items
            "items": [
                {
                    "item": "10",
                    "desc": "Chemical Injection Package (Complete System)",
                    "unit": "LOT",
                    "qty": 1.0,
                    "hold": 0,
                    "lot": "Lot 1 (Skid Base)",
                    "tag": "03-PK-101",
                    "location": "Milan / Houston / Singapore",
                    "is_package_parent": True,
                },
                {
                    "item": "10.1",
                    "desc": "Structural Skid Base Frame with Drip Pan",
                    "unit": "EA",
                    "qty": 10.0,
                    "hold": 0,
                    "lot": "Lot 1 (Skid Base)",
                    "tag": "03-SK-101A..J",
                    "location": "Fabrication Yard A (Milan)",
                    "is_split": True,
                    "parent_item": "10",
                    "forecast_date": "2026-12-10",
                    "baseline_date": "2026-12-01",
                    "eng_pct": 100,
                    "proc_pct": 100,
                    "fab_pct": 85,
                    "insp_pct": 50,
                },
                {
                    "item": "10.2",
                    "desc": "Dosing Pressure Vessel (SS316L, 1500 psig)",
                    "unit": "EA",
                    "qty": 10.0,
                    "hold": 0,
                    "lot": "Lot 1 (Skid Base)",
                    "tag": "03-V-101A..J",
                    "location": "Vessel Shop B (Houston)",
                    "is_split": True,
                    "parent_item": "10",
                    "forecast_date": "2026-12-18",
                    "baseline_date": "2026-12-15",
                    "eng_pct": 100,
                    "proc_pct": 95,
                    "fab_pct": 70,
                    "insp_pct": 30,
                },
                {
                    "item": "10.3",
                    "desc": "Multi-Head Metering Dosing Pump & Manifold",
                    "unit": "EA",
                    "qty": 10.0,
                    "hold": 0,
                    "lot": "Lot 1 (Skid Base)",
                    "tag": "03-P-101A..J",
                    "location": "Pump Works C (Singapore)",
                    "is_split": True,
                    "parent_item": "10",
                    "forecast_date": "2026-12-22",
                    "baseline_date": "2026-12-20",
                    "eng_pct": 100,
                    "proc_pct": 90,
                    "fab_pct": 60,
                    "insp_pct": 20,
                },
                {
                    "item": "20",
                    "desc": "6\" ANSI 900# Cryogenic Top-Entry Ball Valves",
                    "unit": "EA",
                    "qty": 100.0,
                    "hold": 0,
                    "lot": "Lot 2 (Valves Batch 1)",
                    "tag": "XV-2001 to XV-2100",
                    "location": "Valve Works (Milan)",
                    "forecast_date": "2026-12-20",
                    "baseline_date": "2026-12-15",
                    "eng_pct": 100,
                    "proc_pct": 100,
                    "fab_pct": 90,
                    "insp_pct": 60,
                },
                {
                    "item": "30",
                    "desc": "Hazardous Area Local Instrument & PLC Control Panel",
                    "unit": "EA",
                    "qty": 2.0,
                    "hold": 0,
                    "lot": "Lot 3 (Control Panels)",
                    "tag": "CP-101 / CP-102",
                    "location": "Systems Yard (Houston)",
                    "forecast_date": "2027-01-10",
                    "baseline_date": "2027-01-05",
                    "eng_pct": 100,
                    "proc_pct": 85,
                    "fab_pct": 50,
                    "insp_pct": 10,
                },
            ],
            # Manufacturing Schedule Milestones
            "mfg": {
                "plan": "2026-10-15",
                "engDoc": "2026-10-30",
                "rawMat": "2026-11-15",
                "weld": "2026-12-05",
                "pressureTest": "2026-12-15",
                "extInsp": "2026-12-20",
                "irn": "2026-12-25",
                "exWorks": "2027-01-05",
                "siteDelivery": "2027-02-01",
            },
            # VDMS / VDRL Engineering Deliverables
            "vdrl_documents": [
                {
                    "doc_no": f"ITP-{PO_NUM}-001",
                    "title": "Master Inspection & Test Plan (ITP) for Chemical Injection",
                    "rev": "Rev 1",
                    "code": "Code 1",
                    "status": "APPROVED",
                    "submitted": "2026-10-10",
                    "returned": "2026-10-18",
                    "milestone": "Engineering Approval",
                },
                {
                    "doc_no": f"WPS-{PO_NUM}-002",
                    "title": "WPS / PQR for Inconel 625 Overlay Welding",
                    "rev": "Rev 0",
                    "code": "Code 2",
                    "status": "APPROVED WITH COMMENTS",
                    "submitted": "2026-10-20",
                    "returned": "2026-10-28",
                    "milestone": "Welding & Fabrication",
                },
                {
                    "doc_no": f"NDE-{PO_NUM}-003",
                    "title": "Ultrasonic & Hydrostatic Test Procedure",
                    "rev": "Rev 0",
                    "code": "Code 3",
                    "status": "REJECTED (REVISE & RESUBMIT)",
                    "submitted": "2026-11-01",
                    "returned": "2026-11-09",
                    "milestone": "Pressure Testing",
                },
                {
                    "doc_no": f"MDR-{PO_NUM}-004",
                    "title": "Manufacturing Data Report (MDR) Index & MTC Dossier",
                    "rev": "Rev 0",
                    "code": "Code 1",
                    "status": "APPROVED",
                    "submitted": "2026-11-05",
                    "returned": "2026-11-12",
                    "milestone": "Final Dossier",
                },
            ],
            # Cumulative Ledger Matrix
            "clr": {
                "10": {"irn": 0, "ship": 0, "mrv": 0, "batches": []},
                "10.1": {"irn": 0, "ship": 0, "mrv": 0, "batches": []},
                "10.2": {"irn": 0, "ship": 0, "mrv": 0, "batches": []},
                "10.3": {"irn": 0, "ship": 0, "mrv": 0, "batches": []},
                "20": {"irn": 0, "ship": 0, "mrv": 0, "batches": []},
                "30": {"irn": 0, "ship": 0, "mrv": 0, "batches": []},
            },
            "irs": [],
            "irns": [],
            "punch": [],
            "rail": [
                {
                    "id": "RAIL-88001-01",
                    "no": "ACT-01",
                    "desc": "NDE-88001-003 rejected (Code 3). Vendor must resubmit calibration procedure before hydrotest.",
                    "tier": 2,
                    "status": "OPEN",
                    "technical_status": "OPEN",
                    "days_open": 5,
                    "target_date": "2026-11-25",
                }
            ],
            "sx": {"notif": [], "look": [], "punch": [], "iap": []},
        }

        L.append(new_po)
        _save_records(c, L, "Seed Script", f"Seeded comprehensive Dummy BOM for {PO_NUM}")

        # Update sx_state cumulative_ledger
        sx_state = _get_sx_state(c)
        if "cumulative_ledger" not in sx_state:
            sx_state["cumulative_ledger"] = {}

        for itm in new_po["items"]:
            k = f"{PO_NUM}:{itm['item']}"
            sx_state["cumulative_ledger"][k] = {
                "po": PO_NUM,
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

        _save_sx_state(c, sx_state, "Seed Script")

    # Also register in InspectFlow Projects / Inspections
    print(f"Successfully seeded PO {PO_NUM} with 6 BOM line items, VDRL documents, and schedule activities.")

if __name__ == "__main__":
    seed_dummy_bom()

