# SmartExpedit — After edition (latest, 13-Nov-2026)

Two ways to run it:
- **With the Python server (shared data, API):** `server/run.bat` — see `server/README.md`.
- **On its own:** open `index.html` in a browser. Data then stays in that browser only.
"Reset demo" in the top bar puts the sample data back.

## What is in it
Dashboard (with the vendor-submission inbox) · Assignment Queue (visual expeditor picker) ·
Expediting Core (Introduction Letter, Order Head, MR Study with the Saudi Aramco MR reader, Document Control VDR, Files) ·
Sub Orders (Submit Procurement Plan, Analysis) · Inspection (IAP, IRN, PIM, Inspection Report, Punch List, notifications) ·
Delivery (Delivery, Packing List, Bill of Lading, Vessel View, dispatch) ·
Order Execution (Manufacturing Schedule, MSSR internal/client, Vendor Progress Report, Close-out) · Field Expediting.
Vendor Portal: Respond to Notification, SDR Portal, Manufacturing Schedule, Submit Procurement Plan,
Vendor Progress Report — each with "Fill from a file" (PDF or Excel).

## Source (`src/`)
| File | Role |
|---|---|
| engine_libs/ | Expediting engine (register, schedule, letter, MR reader, PDF and XLSX libraries) and the expediting_detail.html it is cut from |
| shell.js | SmartExpedit shell: navigation, queue, dashboard, sub-order plan, tabs |
| ep_mr_aramco.js | MR reader fallback for Saudi Aramco MRs (ITR/NMR forms in Attachment V) |
| fix2.js | 10-Nov fixes: storage, date fields, select-all, Sub Orders stage, IR, punch list, packing list, B/L, vessel view, review loop, vendor schedule, MSSR, Vendor Progress Report, Field Expediting |
| fx3.js | "Fill from a file" on every Vendor Portal tab |
| data/ | sample records, sub-order plan rows, workflow actions, Ruwais LNG field-visit tracker data |
| build.py | rebuilds `index.html`: `python3 src/build.py` (needs Python 3 with openpyxl) |

Load order inside index.html: engine_libs → expediting_detail main script → data → shell.js → fix2.js → fx3.js.
