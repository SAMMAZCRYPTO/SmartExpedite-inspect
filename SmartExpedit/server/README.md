# SmartExpedit — Python server

The same SmartExpedit screens, served by Python (Flask) with one shared SQLite database.
Every user sees the same orders, uploaded files are kept on the server, and other applications
connect through the JSON API below.

## Start it
**Windows:** double-click `run.bat`. The first run installs Flask and Waitress, then shows
"SmartExpedit is running". Open http://localhost:8080 — other PCs use http://<this-PC-name>:8080.
**Linux/Mac:** `./run.sh`

Data lives in `server/data/` (`smartexpedit.db` and `blobs/`). Back up that folder to back up everything.
The first browser that opens an empty server loads the sample data.

| Setting (environment variable) | Default | What it does |
|---|---|---|
| SX_PORT | 8080 | Port |
| SX_HOST | 0.0.0.0 | 0.0.0.0 lets other PCs connect; 127.0.0.1 keeps it on this PC |
| SX_DATA | server/data | Where the database and files are kept |
| SX_API_KEY | (none) | When set, every /api/v1 call needs the header `X-API-Key: <key>` |
| SX_DEMO | 1 | 0 hides "Reset demo" (on a shared server it resets everyone's data; it asks first) |

## How the page talks to the server
- At start the page reads everything from the server; each change is sent back within half a second.
- If the server is slow or down, saves wait and retry patiently (up to every 60 s); the top bar shows
  **Saved**, **Saving…** or **Server not answering — retrying**. Nothing is lost while the page stays open.
- Uploads show **Uploading <file> — n%**.
- Every 20 seconds the page picks up other users' saves and redraws when nobody is typing.
- Two users saving different POs at the same moment are merged on the server, PO by PO.

## API for other applications
All answers are JSON. Add `X-API-Key` when SX_API_KEY is set.

| Call | Returns / does |
|---|---|
| GET /api/v1/health | server status and number of POs |
| GET /api/v1/pos | one line per PO: po, rev, supplier, title, currency, value, stage, assigned_to, issued_on, lots |
| GET /api/v1/pos/{po} | the whole PO record |
| GET /api/v1/pos/{po}?part=documents | also: schedule, plan, items, irns, shipments, inspection, reviews, submissions, mssr |
| PATCH /api/v1/pos/{po} | merge fields into the PO, e.g. `{"stage":"shipped"}` |
| POST /api/v1/pos/{po}/irns | add an IRN (IMS connector), e.g. `{"no":"IRN-10","rev":"R0","date":"2026-11-14","cat":"Final","comp":"Lot 1","lines":[{"item":"10","po":8,"now":8}]}` |
| POST /api/v1/pos/{po}/ships | add a shipment (Logistics connector): `no, mode, vessel, etd, atd, eta, ata, kg, mrv, lot` |
| POST /api/v1/pos/{po}/pls · /bls · /irs · /punch | add a packing list, bill of lading, inspection report or punch point |
| GET /api/v1/field | field expediting rows and visits |
| GET /api/v1/files?po={po} | uploaded files (id, name, size, tab, who, when) |
| GET /api/v1/files/{id} | download a file |
| GET /api/v1/audit | the last 200 API changes |

Example (PowerShell):
`Invoke-RestMethod http://localhost:8080/api/v1/pos`

## Files
| File | Role |
|---|---|
| app.py | the server and the API |
| sx_head.js / sx_tail.js | the link between the page and the server (storage, uploads, live updates, status line) |
| make_static.py | builds static/index.html from ../index.html plus the link scripts; run it after rebuilding index.html |
| static/index.html | the page the server sends |
| run.bat / run.sh, requirements.txt | start-up |
