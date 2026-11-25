# InspectFlow + SmartExpedit — EPC Expediting & Quality Inspection ERP

InspectFlow + SmartExpedit is a full-stack **EPC Contractor Procurement Expediting, Vendor Collaboration & Quality Inspection Platform** built with **React (Vite + Tailwind + shadcn/ui)** and **Python FastAPI + SQLite/SQLAlchemy**.

---

## Key Capabilities

- **Inspection Management (IMS):** NOI upload & AI PDF/OCR extraction, registered TPI inspector assignment & attendance check-in/check-out, IE report review & endorsement, NCR / finding tracking, and gated IRC/IRN release.
- **Vendor Portal:** Multi-item NOI submission, schedule upload & parsing (`.xlsx`, `.csv`, `.pdf` via Gemini AI + OCR fallback), PO acknowledgement, Critical Sub-Order declaration & 1-click Sub-Order NOI, 7-section NMDC Progress Reports (`.docx` / `.pdf` export), Dispatch requests, and MRB/SPIR/MNCR closeout.
- **Expediting ERP Workbench:**
  - NEAS item-level tracking & PO schedule archetypes (`bulk`, `tagged`, `package`)
  - 9-column Minimum Requirement Schedule with server baseline freeze & `.xlsx` export
  - Client IAP approval gate, KOM/Tech/PIM Meeting MOMs + Auto-RAIL action items
  - Rolling Client Inspection Look-Ahead Schedule (`14d` / `28d` / `60d`) + `.xlsx` export
  - Chain-of-custody delivery staging (Ex-Works → In-Transit → Stores MRV / Stamped DN → MNCR return/rectify/close)
  - Two-stage commercial closeout (LD assessment, Waiver Memo `.docx` export, Final Invoice)
  - Project-wide Consolidated Weekly MSSR (4-sheet `.xlsx`) & Governance Registers
  - AI Agents for PO/MR requirements review & First Expediting Contact drafting

---

## Prerequisites

- **Python** `3.10+`
- **Node.js** `18+` and **npm**
- *(Optional)* A **Google Gemini API key** (`GEMINI_API_KEY`) for AI PDF NOI/schedule extraction and PO/MR review agents (non-AI workflows, Excel/CSV parsers, and OCR fallback work without it).

---

## Quick Start (Local Development)

### 1. Clone the repository
```bash
git clone https://github.com/SAMMAZCRYPTO/SmartExpedite-inspect.git
cd SmartExpedite-inspect
```

### 2. Configure environment variables
Copy the example template (never commit `.env` or secrets):
```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```
```bash
# macOS / Linux
cp .env.example .env
```
Edit `.env` and optionally add your `GEMINI_API_KEY=...`. For local testing, `.env.example` sets `AUTH_MODE=dev`, which seeds starter demo accounts cleanly on an empty database and enables one-click role switching at `/login`.

> **Automated Windows setup:** You can run `.\setup.ps1` in PowerShell to verify Python/Node, create `.env`, install dependencies, and build `dist/` automatically.

### 3. Install dependencies & build the frontend
```bash
pip install -r requirements.txt
npm install
npm run build
```

### 4. Start the application
```bash
python -m uvicorn python_app.api_server:app --host 0.0.0.0 --port 5214
```
Open **http://localhost:5214** in your browser. On first run, the server automatically creates clean SQLite databases (`backend/inspectflow.db` and `SmartExpedit/server/data/smartexpedit.db`) with starter tables and dev demo accounts.

*(Optional — frontend hot-reload dev mode)* Run `npm run dev` on port `5173` while FastAPI runs on port `5214` (API proxy preconfigured in [vite.config.js](vite.config.js)).

---

## Automated Verification Suite

With the server running on `http://localhost:5214` in `AUTH_MODE=dev`:
```bash
python verify_vendor_portal_suite.py
```

---

## Production Deployment Notes

- Set `AUTH_MODE=production` and supply a strong random `JWT_SECRET` in `.env` (server fails closed if omitted or invalid).
- Configure `DATABASE_URL` (PostgreSQL `postgresql+psycopg://...` or SQL Server `mssql+pyodbc://...`) and run `alembic upgrade head` (`alembic.ini` / `backend_v2/alembic/`).
- Do not enable `SX_DEMO=1` or dev quick-login in production.

---

## Project Structure

```text
├── python_app/               # FastAPI server, SQLite/ERP workflows, parsers, AI/OCR services
├── backend_v2/               # JWT Auth/RBAC, SQLAlchemy models, Alembic migrations, storage & audit
├── SmartExpedit/             # Embedded Expediting Workbench UI & bridge scripts
├── src/                      # React + Vite frontend (IMS, Expediting, Vendor Portal, Governance)
├── docs/                     # Integration & extraction documentation
├── verify_vendor_portal_suite.py  # End-to-end security, workflow & Phase 1-5 verification suite
├── .env.example              # Safe environment configuration template
└── setup.ps1                 # Windows local setup script
```
