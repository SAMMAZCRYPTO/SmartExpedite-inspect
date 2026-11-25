import json
import os
import re
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend_v2.core.config import settings
from backend_v2.core.passwords import hash_password, is_password_hashed, verify_password

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "backend" / "inspectflow.db"
UPLOADS_DIR = BASE_DIR / "backend" / "wwwroot" / "uploads"
_DB_INITIALIZED = False
_DB_WRITE_LOCK = threading.RLock()

INSPECTION_STATUS_INT_TO_STR = {
    0: "received",
    1: "scheduled",
    2: "in_progress",
    3: "completed",
    4: "finalized",
    5: "cancelled",
}
INSPECTION_STATUS_STR_TO_INT = {v: k for k, v in INSPECTION_STATUS_INT_TO_STR.items()}
INSPECTION_STATUS_STR_TO_INT["inprogress"] = 2
INSPECTION_STATUS_STR_TO_INT["canceled"] = 5

INSPECTOR_STATUS_INT_TO_STR = {
    0: "active",
    1: "inactive",
    2: "suspended",
    3: "on_leave",
}
INSPECTOR_STATUS_STR_TO_INT = {v: k for k, v in INSPECTOR_STATUS_INT_TO_STR.items()}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(force: bool = False) -> None:
    global _DB_INITIALIZED
    if _DB_INITIALIZED and not force:
        return
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                Id TEXT PRIMARY KEY,
                Email TEXT UNIQUE NOT NULL,
                Password TEXT NOT NULL,
                FullName TEXT NOT NULL,
                Role TEXT NOT NULL DEFAULT 'guest',
                InspectionRole TEXT,
                CompanyAffiliation TEXT,
                Department TEXT,
                Phone TEXT,
                UserStatus TEXT NOT NULL DEFAULT 'active',
                ProjectIds TEXT DEFAULT '[]',
                TokenVersion INTEGER NOT NULL DEFAULT 1,
                CreatedAt TEXT NOT NULL,
                UpdatedAt TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS RevokedTokens (
                Jti TEXT PRIMARY KEY,
                ExpiresAt INTEGER NOT NULL,
                RevokedAt TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Projects (
                Id TEXT PRIMARY KEY,
                Name TEXT NOT NULL DEFAULT '',
                Code TEXT UNIQUE NOT NULL DEFAULT '',
                Description TEXT,
                ClientName TEXT,
                StartDate TEXT,
                EndDate TEXT,
                Status TEXT NOT NULL DEFAULT 'active',
                ExpeditingManagerId TEXT,
                ExpeditingManagerName TEXT,
                ExpeditingManagerEmail TEXT,
                InspectionManagerId TEXT,
                InspectionManagerName TEXT,
                InspectionManagerEmail TEXT,
                TeamMemberIds TEXT DEFAULT '[]',
                LinkedPoNumbers TEXT DEFAULT '[]',
                RequiresClientIap INTEGER NOT NULL DEFAULT 0,
                CreatedAt TEXT NOT NULL,
                UpdatedAt TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS TpiAgencies (
                Id TEXT PRIMARY KEY,
                Name TEXT NOT NULL DEFAULT '',
                CompanyCode TEXT UNIQUE,
                ManagerName TEXT,
                ManagerEmail TEXT,
                ManagerPhone TEXT,
                Address TEXT,
                City TEXT,
                Country TEXT,
                CertificationInfo TEXT,
                Status TEXT NOT NULL DEFAULT 'active',
                CreatedAt TEXT NOT NULL,
                UpdatedAt TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Inspectors (
                Id TEXT PRIMARY KEY,
                UserId TEXT,
                TpiAgencyId TEXT REFERENCES TpiAgencies(Id) ON DELETE SET NULL,
                FullName TEXT NOT NULL DEFAULT '',
                Email TEXT UNIQUE NOT NULL DEFAULT '',
                Phone TEXT,
                Specialization TEXT,
                Certifications TEXT,
                ExperienceYears INTEGER,
                CvUrl TEXT,
                PhotoUrl TEXT,
                Status INTEGER NOT NULL DEFAULT 0,
                CreatedAt TEXT NOT NULL,
                UpdatedAt TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Inspections (
                Id TEXT PRIMARY KEY,
                PoNumber TEXT NOT NULL DEFAULT '',
                NotificationNumber TEXT NOT NULL DEFAULT '',
                NotificationRevision TEXT,
                SupplierName TEXT NOT NULL DEFAULT '',
                SubsupplierName TEXT,
                SupplierAddress TEXT,
                Country TEXT,
                PoDescription TEXT,
                InspectionType TEXT,
                VendorContactName TEXT,
                VendorContactPhone TEXT,
                VendorContactEmail TEXT,
                ProjectId TEXT REFERENCES Projects(Id) ON DELETE SET NULL,
                AssignedInspectorId TEXT REFERENCES Inspectors(Id) ON DELETE SET NULL,
                TpiAgencyId TEXT REFERENCES TpiAgencies(Id) ON DELETE SET NULL,
                AssignedBy TEXT,
                NotificationDate TEXT,
                NotificationReceiptDate TEXT,
                StartDate TEXT,
                EndDate TEXT,
                ExpectedCompletionDate TEXT,
                ActualCompletionDate TEXT,
                AllInspectionDates TEXT,
                InspectionTime TEXT,
                LocationName TEXT,
                LocationAddress TEXT,
                LocationLatitude REAL,
                LocationLongitude REAL,
                Status INTEGER NOT NULL DEFAULT 0,
                ItemsBeingOffered TEXT DEFAULT '[]',
                InspectionReports TEXT DEFAULT '[]',
                InspectionActivities TEXT DEFAULT '[]',
                TestReportsJson TEXT DEFAULT '[]',
                AdditionalReportsJson TEXT DEFAULT '[]',
                DocumentUrl TEXT,
                Notes TEXT,
                ReleaseNoteUrl TEXT,
                CreatedAt TEXT NOT NULL,
                UpdatedAt TEXT NOT NULL,
                CreatedBy TEXT,
                AssignedInspectionEngineerId TEXT,
                AssignedInspectionEngineerName TEXT,
                AssignedInspectionEngineerEmail TEXT,
                AssignedExpeditorId TEXT,
                AssignedExpeditorName TEXT,
                AssignedExpeditorEmail TEXT,
                ExpeditingManagerName TEXT,
                InspectionManagerName TEXT,
                CancellationReason TEXT,
                CancelledBy TEXT,
                CancelledAt TEXT,
                AbortiveInspection INTEGER DEFAULT 0,
                InspectorConfirmationStatus TEXT DEFAULT 'confirmed',
                ReconfirmationDeadline TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS InspectionAttendances (
                Id TEXT PRIMARY KEY,
                InspectionId TEXT NOT NULL REFERENCES Inspections(Id) ON DELETE CASCADE,
                InspectorId TEXT NOT NULL REFERENCES Inspectors(Id) ON DELETE CASCADE,
                CheckInTime TEXT,
                CheckOutTime TEXT,
                CheckInLatitude REAL,
                CheckInLongitude REAL,
                CheckOutLatitude REAL,
                CheckOutLongitude REAL,
                LocationVerified INTEGER NOT NULL DEFAULT 0,
                DistanceFromSiteMeters REAL,
                CheckInNotes TEXT,
                CheckOutNotes TEXT,
                CreatedAt TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS InspectionReviews (
                Id TEXT PRIMARY KEY,
                InspectionId TEXT NOT NULL REFERENCES Inspections(Id) ON DELETE CASCADE,
                InspectorId TEXT NOT NULL REFERENCES Inspectors(Id) ON DELETE CASCADE,
                ReviewedBy TEXT,
                ReportQualityScore INTEGER,
                TimelinessScore INTEGER,
                CommunicationScore INTEGER,
                SpecificationComplianceScore INTEGER,
                FirstTimeAcceptance INTEGER,
                ItpHoldPointCompliance INTEGER,
                ValueAddedObservations INTEGER DEFAULT 0,
                OverallScore INTEGER,
                MissedNcrCount INTEGER DEFAULT 0,
                FalseNcrCount INTEGER DEFAULT 0,
                Strengths TEXT,
                AreasForImprovement TEXT,
                AdditionalComments TEXT,
                ReviewDate TEXT,
                CreatedAt TEXT NOT NULL
            )
            """
        )

        # Ensure secondary indexes exist
        for stmt in [
            "CREATE INDEX IF NOT EXISTS IX_Inspections_ProjectId ON Inspections(ProjectId)",
            "CREATE INDEX IF NOT EXISTS IX_Inspections_Status ON Inspections(Status)",
            "CREATE INDEX IF NOT EXISTS IX_Inspections_NotificationNumber ON Inspections(NotificationNumber)",
            "CREATE INDEX IF NOT EXISTS IX_Inspections_AssignedInspectorId ON Inspections(AssignedInspectorId)",
            "CREATE INDEX IF NOT EXISTS IX_Inspections_TpiAgencyId ON Inspections(TpiAgencyId)",
            "CREATE INDEX IF NOT EXISTS IX_Inspectors_TpiAgencyId ON Inspectors(TpiAgencyId)",
            "CREATE INDEX IF NOT EXISTS IX_InspectionAttendances_InspectionId ON InspectionAttendances(InspectionId)",
            "CREATE INDEX IF NOT EXISTS IX_InspectionAttendances_InspectorId ON InspectionAttendances(InspectorId)",
            "CREATE INDEX IF NOT EXISTS IX_InspectionReviews_InspectionId ON InspectionReviews(InspectionId)",
            "CREATE INDEX IF NOT EXISTS IX_InspectionReviews_InspectorId ON InspectionReviews(InspectorId)",
            "CREATE INDEX IF NOT EXISTS IX_RevokedTokens_ExpiresAt ON RevokedTokens(ExpiresAt)",
        ]:
            cur.execute(stmt)

        # Safe column migrations for existing databases
        proj_cols = {r[1] for r in cur.execute("PRAGMA table_info(Projects)").fetchall()}
        if "RequiresClientIap" not in proj_cols:
            cur.execute("ALTER TABLE Projects ADD COLUMN RequiresClientIap INTEGER NOT NULL DEFAULT 0")

        count = cur.execute("SELECT COUNT(*) FROM Users").fetchone()[0]
        if count == 0 and settings.auth_mode == "dev":
            default_users = [
                (
                    "00000000-0000-0000-0000-000000000001",
                    "admin@inspectflow.com",
                    hash_password(os.environ.get("DEV_ADMIN_PASSWORD") or "Admin@123"),
                    "System Administrator",
                    "admin",
                    "admin",
                    "InspectFlow",
                    "Administration",
                    "",
                    "active",
                    "[]",
                    now_iso(),
                    now_iso(),
                ),
                (
                    "00000000-0000-0000-0000-000000000002",
                    "inspector@inspectflow.com",
                    hash_password(os.environ.get("DEV_USER_PASSWORD") or "Inspector@123"),
                    "Fulkrum Inspector",
                    "inspector",
                    "inspector",
                    "Fulkrum",
                    "Inspection",
                    "",
                    "active",
                    "[]",
                    now_iso(),
                    now_iso(),
                ),
                (
                    "00000000-0000-0000-0000-000000000003",
                    "qc@inspectflow.com",
                    hash_password(os.environ.get("DEV_USER_PASSWORD") or "QC@123456"),
                    "QC Engineer",
                    "qc_manager",
                    "qc_manager",
                    "InspectFlow",
                    "Quality Control",
                    "",
                    "active",
                    "[]",
                    now_iso(),
                    now_iso(),
                ),
                (
                    "00000000-0000-0000-0000-000000000004",
                    "tpi@inspectflow.com",
                    hash_password(os.environ.get("DEV_USER_PASSWORD") or "TPI@123456"),
                    "TPI Agency",
                    "inspection_agency",
                    "inspection_agency",
                    "Fulkrum",
                    "TPI",
                    "",
                    "active",
                    "[]",
                    now_iso(),
                    now_iso(),
                ),
            ]
            cur.executemany(
                """
                INSERT INTO Users (
                    Id, Email, Password, FullName, Role, InspectionRole,
                    CompanyAffiliation, Department, Phone, UserStatus, ProjectIds,
                    CreatedAt, UpdatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                default_users,
            )
        elif count == 0 and settings.auth_mode == "production":
            admin_pw = os.environ.get("INITIAL_ADMIN_PASSWORD", "").strip()
            if admin_pw:
                cur.execute(
                    """
                    INSERT INTO Users (
                        Id, Email, Password, FullName, Role, InspectionRole,
                        CompanyAffiliation, Department, Phone, UserStatus, ProjectIds,
                        CreatedAt, UpdatedAt
                    ) VALUES (?, ?, ?, 'System Administrator', 'admin', 'admin', 'InspectFlow', 'Administration', '', 'active', '[]', ?, ?)
                    """,
                    (
                        "00000000-0000-0000-0000-000000000001",
                        os.environ.get("INITIAL_ADMIN_EMAIL", "admin@inspectflow.com").strip().lower(),
                        hash_password(admin_pw),
                        now_iso(),
                        now_iso(),
                    ),
                )
        else:
            # One-time transparent migration: hash any legacy plaintext passwords in Users table
            rows = cur.execute("SELECT Id, Password FROM Users").fetchall()
            for row in rows:
                pw = row["Password"]
                if pw and not is_password_hashed(pw):
                    cur.execute(
                        "UPDATE Users SET Password = ?, UpdatedAt = ? WHERE Id = ?",
                        (hash_password(pw), now_iso(), row["Id"]),
                    )

        user_cols = {r[1] for r in cur.execute("PRAGMA table_info(Users)").fetchall()}
        if "TokenVersion" not in user_cols:
            cur.execute("ALTER TABLE Users ADD COLUMN TokenVersion INTEGER NOT NULL DEFAULT 1")

        # Ensure extended governance columns on Projects, Inspections, and InspectionReviews
        proj_cols = {r[1] for r in cur.execute("PRAGMA table_info(Projects)").fetchall()}
        for col_name, col_def in [
            ("ExpeditingManagerId", "TEXT"),
            ("ExpeditingManagerName", "TEXT"),
            ("ExpeditingManagerEmail", "TEXT"),
            ("InspectionManagerId", "TEXT"),
            ("InspectionManagerName", "TEXT"),
            ("InspectionManagerEmail", "TEXT"),
            ("TeamMemberIds", "TEXT DEFAULT '[]'"),
            ("LinkedPoNumbers", "TEXT DEFAULT '[]'"),
        ]:
            if col_name not in proj_cols:
                cur.execute(f"ALTER TABLE Projects ADD COLUMN {col_name} {col_def}")

        insp_cols = {r[1] for r in cur.execute("PRAGMA table_info(Inspections)").fetchall()}
        for col_name, col_def in [
            ("AssignedInspectionEngineerId", "TEXT"),
            ("AssignedInspectionEngineerName", "TEXT"),
            ("AssignedInspectionEngineerEmail", "TEXT"),
            ("AssignedExpeditorId", "TEXT"),
            ("AssignedExpeditorName", "TEXT"),
            ("AssignedExpeditorEmail", "TEXT"),
            ("ExpeditingManagerName", "TEXT"),
            ("InspectionManagerName", "TEXT"),
            ("CancellationReason", "TEXT"),
            ("CancelledBy", "TEXT"),
            ("CancelledAt", "TEXT"),
            ("AbortiveInspection", "INTEGER DEFAULT 0"),
            ("InspectorConfirmationStatus", "TEXT DEFAULT 'confirmed'"),
            ("ReconfirmationDeadline", "TEXT"),
            ("DocumentUrl", "TEXT"),
            ("TestReportsJson", "TEXT DEFAULT '[]'"),
            ("AdditionalReportsJson", "TEXT DEFAULT '[]'"),
        ]:
            if col_name not in insp_cols:
                cur.execute(f"ALTER TABLE Inspections ADD COLUMN {col_name} {col_def}")

        rev_cols = {r[1] for r in cur.execute("PRAGMA table_info(InspectionReviews)").fetchall()}
        for col_name, col_def in [
            ("SpecificationComplianceScore", "INTEGER"),
            ("FirstTimeAcceptance", "INTEGER"),
            ("ItpHoldPointCompliance", "INTEGER"),
            ("ValueAddedObservations", "INTEGER DEFAULT 0"),
        ]:
            if col_name not in rev_cols:
                cur.execute(f"ALTER TABLE InspectionReviews ADD COLUMN {col_name} {col_def}")

        conn.commit()
    _DB_INITIALIZED = True


def _parse_json_safe(val: Any, default: Any = None) -> Any:
    if default is None:
        default = []
    if val is None or val == "":
        return default
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


def _to_json_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val)


def _fmt_date(val: Any) -> Optional[str]:
    if not val:
        return None
    s = str(val).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s


def _norm_id(val: Any) -> Optional[str]:
    if not val:
        return None
    s = str(val).strip()
    return s.lower() if s else None


# ── Projects ─────────────────────────────────────────────────────────────────

def _map_project(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    return {
        "id": _norm_id(d.get("Id")),
        "name": d.get("Name") or "",
        "code": d.get("Code") or "",
        "description": d.get("Description"),
        "client_name": d.get("ClientName"),
        "start_date": _fmt_date(d.get("StartDate")),
        "end_date": _fmt_date(d.get("EndDate")),
        "status": d.get("Status") or "active",
        "expediting_manager_id": _norm_id(d.get("ExpeditingManagerId")),
        "expediting_manager_name": d.get("ExpeditingManagerName") or "",
        "expediting_manager_email": d.get("ExpeditingManagerEmail") or "",
        "inspection_manager_id": _norm_id(d.get("InspectionManagerId")),
        "inspection_manager_name": d.get("InspectionManagerName") or "",
        "inspection_manager_email": d.get("InspectionManagerEmail") or "",
        "team_member_ids": _parse_json_safe(d.get("TeamMemberIds"), []),
        "linked_po_numbers": _parse_json_safe(d.get("LinkedPoNumbers"), []),
        "requires_client_iap": bool(d.get("RequiresClientIap")),
        "created_at": d.get("CreatedAt"),
        "updated_at": d.get("UpdatedAt"),
    }


def list_projects() -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM Projects ORDER BY CreatedAt DESC").fetchall()
        return [_map_project(r) for r in rows]


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    if not project_id:
        return None
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Projects WHERE UPPER(Id) = UPPER(?)", (project_id,)
        ).fetchone()
        return _map_project(row) if row else None


def _sync_project_to_user_assignments(conn: sqlite3.Connection, project_id: str, exp_mgr_id: Optional[str], insp_mgr_id: Optional[str], team_ids: List[str]) -> None:
    norm_pid = _norm_id(project_id)
    if not norm_pid:
        return
    assigned_user_ids = {_norm_id(uid) for uid in ([exp_mgr_id, insp_mgr_id] + list(team_ids or [])) if uid}
    # Sync additions AND removals across all Users so revoking a user from a project persists
    all_users = conn.execute("SELECT Id, Role, InspectionRole, ProjectIds FROM Users").fetchall()
    for row in all_users:
        uid = _norm_id(row["Id"])
        if not uid:
            continue
        curr_pids = [_norm_id(p) for p in _parse_json_safe(row["ProjectIds"], []) if p]
        should_have = uid in assigned_user_ids
        if should_have and norm_pid not in curr_pids:
            curr_pids.append(norm_pid)
            conn.execute(
                "UPDATE Users SET ProjectIds = ?, UpdatedAt = ? WHERE UPPER(Id) = UPPER(?)",
                (_to_json_str(curr_pids), now_iso(), row["Id"]),
            )
        elif not should_have and norm_pid in curr_pids:
            eff_role = str(row["InspectionRole"] or row["Role"] or "").lower()
            if eff_role != "admin":
                new_pids = [p for p in curr_pids if p != norm_pid]
                conn.execute(
                    "UPDATE Users SET ProjectIds = ?, UpdatedAt = ? WHERE UPPER(Id) = UPPER(?)",
                    (_to_json_str(new_pids), now_iso(), row["Id"]),
                )


def _resolve_user_summary(conn: sqlite3.Connection, user_id: Optional[str], fallback_name: Optional[str] = None, fallback_email: Optional[str] = None):
    if not user_id:
        return None, fallback_name or "", fallback_email or ""
    row = conn.execute("SELECT Id, FullName, Email FROM Users WHERE UPPER(Id) = UPPER(?)", (str(user_id),)).fetchone()
    if row:
        return _norm_id(row["Id"]), row["FullName"] or "", row["Email"] or ""
    return _norm_id(user_id), fallback_name or "", fallback_email or ""


def create_project(data: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    pid = str(data.get("id") or uuid.uuid4()).upper()
    ts = now_iso()
    team_ids = [_norm_id(x) for x in (data.get("team_member_ids") or []) if x]
    linked_pos = [str(x) for x in (data.get("linked_po_numbers") or []) if x]
    with get_connection() as conn:
        em_id, em_name, em_email = _resolve_user_summary(
            conn, data.get("expediting_manager_id"), data.get("expediting_manager_name"), data.get("expediting_manager_email")
        )
        im_id, im_name, im_email = _resolve_user_summary(
            conn, data.get("inspection_manager_id"), data.get("inspection_manager_name"), data.get("inspection_manager_email")
        )
        conn.execute(
            """
            INSERT INTO Projects (
                Id, Name, Code, Description, ClientName, StartDate, EndDate, Status,
                ExpeditingManagerId, ExpeditingManagerName, ExpeditingManagerEmail,
                InspectionManagerId, InspectionManagerName, InspectionManagerEmail,
                TeamMemberIds, LinkedPoNumbers, RequiresClientIap, CreatedAt, UpdatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                data.get("name", ""),
                data.get("code", ""),
                data.get("description"),
                data.get("client_name"),
                data.get("start_date"),
                data.get("end_date"),
                data.get("status", "active"),
                em_id,
                em_name,
                em_email,
                im_id,
                im_name,
                im_email,
                _to_json_str(team_ids),
                _to_json_str(linked_pos),
                1 if data.get("requires_client_iap") else 0,
                ts,
                ts,
            ),
        )
        _sync_project_to_user_assignments(conn, pid, em_id, im_id, team_ids)
        conn.commit()
    return get_project(pid)  # type: ignore


def update_project(project_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_project(project_id)
    if not existing:
        return None
    ts = now_iso()
    team_ids = data.get("team_member_ids") if "team_member_ids" in data else existing.get("team_member_ids", [])
    team_ids = [_norm_id(x) for x in (team_ids or []) if x]
    linked_pos = data.get("linked_po_numbers") if "linked_po_numbers" in data else existing.get("linked_po_numbers", [])
    linked_pos = [str(x) for x in (linked_pos or []) if x]

    with get_connection() as conn:
        raw_em_id = data["expediting_manager_id"] if "expediting_manager_id" in data else existing.get("expediting_manager_id")
        em_id, em_name, em_email = _resolve_user_summary(
            conn, raw_em_id, data.get("expediting_manager_name", existing.get("expediting_manager_name")), data.get("expediting_manager_email", existing.get("expediting_manager_email"))
        )
        raw_im_id = data["inspection_manager_id"] if "inspection_manager_id" in data else existing.get("inspection_manager_id")
        im_id, im_name, im_email = _resolve_user_summary(
            conn, raw_im_id, data.get("inspection_manager_name", existing.get("inspection_manager_name")), data.get("inspection_manager_email", existing.get("inspection_manager_email"))
        )

        conn.execute(
            """
            UPDATE Projects
            SET Name = ?, Code = ?, Description = ?, ClientName = ?,
                StartDate = ?, EndDate = ?, Status = ?,
                ExpeditingManagerId = ?, ExpeditingManagerName = ?, ExpeditingManagerEmail = ?,
                InspectionManagerId = ?, InspectionManagerName = ?, InspectionManagerEmail = ?,
                TeamMemberIds = ?, LinkedPoNumbers = ?, RequiresClientIap = ?, UpdatedAt = ?
            WHERE UPPER(Id) = UPPER(?)
            """,
            (
                data.get("name", existing["name"]),
                data.get("code", existing["code"]),
                data.get("description", existing["description"]),
                data.get("client_name", existing["client_name"]),
                data.get("start_date", existing["start_date"]),
                data.get("end_date", existing["end_date"]),
                data.get("status", existing["status"]),
                em_id,
                em_name,
                em_email,
                im_id,
                im_name,
                im_email,
                _to_json_str(team_ids),
                _to_json_str(linked_pos),
                1 if data.get("requires_client_iap", existing.get("requires_client_iap")) else 0,
                ts,
                project_id,
            ),
        )
        _sync_project_to_user_assignments(conn, project_id, em_id, im_id, team_ids)
        conn.commit()
    return get_project(project_id)


def delete_project(project_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM Projects WHERE UPPER(Id) = UPPER(?)", (project_id,))
        conn.commit()
        return cur.rowcount > 0


# ── TPI Agencies ─────────────────────────────────────────────────────────────

def _map_agency(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    return {
        "id": _norm_id(d.get("Id")),
        "name": d.get("Name") or "",
        "company_code": d.get("CompanyCode"),
        "manager_name": d.get("ManagerName"),
        "manager_email": d.get("ManagerEmail"),
        "manager_phone": d.get("ManagerPhone"),
        "email": d.get("ManagerEmail"),
        "phone": d.get("ManagerPhone"),
        "address": d.get("Address"),
        "city": d.get("City"),
        "country": d.get("Country"),
        "certification_info": d.get("CertificationInfo"),
        "status": d.get("Status") or "active",
        "created_at": d.get("CreatedAt"),
        "updated_at": d.get("UpdatedAt"),
    }


def list_agencies() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM TpiAgencies ORDER BY CreatedAt DESC").fetchall()
        return [_map_agency(r) for r in rows]


def get_agency(agency_id: str) -> Optional[Dict[str, Any]]:
    if not agency_id:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM TpiAgencies WHERE UPPER(Id) = UPPER(?)", (agency_id,)
        ).fetchone()
        return _map_agency(row) if row else None


def create_agency(data: Dict[str, Any]) -> Dict[str, Any]:
    aid = str(data.get("id") or uuid.uuid4()).upper()
    ts = now_iso()
    code = data.get("company_code") or f"TPI-{aid[:6]}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO TpiAgencies (
                Id, Name, CompanyCode, ManagerName, ManagerEmail, ManagerPhone,
                Address, City, Country, CertificationInfo, Status, CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                data.get("name", ""),
                code,
                data.get("manager_name"),
                data.get("manager_email") or data.get("email"),
                data.get("manager_phone") or data.get("phone"),
                data.get("address"),
                data.get("city"),
                data.get("country"),
                data.get("certification_info"),
                data.get("status", "active"),
                ts,
                ts,
            ),
        )
        conn.commit()
    return get_agency(aid)  # type: ignore


def update_agency(agency_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_agency(agency_id)
    if not existing:
        return None
    ts = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE TpiAgencies
            SET Name = ?, CompanyCode = ?, ManagerName = ?, ManagerEmail = ?,
                ManagerPhone = ?, Address = ?, City = ?, Country = ?,
                CertificationInfo = ?, Status = ?, UpdatedAt = ?
            WHERE UPPER(Id) = UPPER(?)
            """,
            (
                data.get("name", existing["name"]),
                data.get("company_code", existing["company_code"]),
                data.get("manager_name", existing["manager_name"]),
                data.get("manager_email") or data.get("email") or existing["manager_email"],
                data.get("manager_phone") or data.get("phone") or existing["manager_phone"],
                data.get("address", existing["address"]),
                data.get("city", existing["city"]),
                data.get("country", existing["country"]),
                data.get("certification_info", existing["certification_info"]),
                data.get("status", existing["status"]),
                ts,
                agency_id,
            ),
        )
        conn.commit()
    return get_agency(agency_id)


def delete_agency(agency_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM TpiAgencies WHERE UPPER(Id) = UPPER(?)", (agency_id,))
        conn.commit()
        return cur.rowcount > 0


# ── Inspectors ───────────────────────────────────────────────────────────────

def _parse_inspector_status_to_str(val: Any) -> str:
    if isinstance(val, int):
        return INSPECTOR_STATUS_INT_TO_STR.get(val, "active")
    if isinstance(val, str):
        if val.isdigit():
            return INSPECTOR_STATUS_INT_TO_STR.get(int(val), "active")
        return val.lower()
    return "active"


def _parse_inspector_status_to_int(val: Any) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.isdigit():
            return int(val)
        return INSPECTOR_STATUS_STR_TO_INT.get(val.lower(), 0)
    return 0


def _map_inspector(row: sqlite3.Row, agencies_map: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = dict(row)
    agency_id = _norm_id(d.get("TpiAgencyId"))
    agency_obj = agencies_map.get(agency_id) if (agencies_map and agency_id) else get_agency(agency_id) if agency_id else None
    return {
        "id": _norm_id(d.get("Id")),
        "user_id": _norm_id(d.get("UserId")),
        "tpi_agency_id": agency_id,
        "tpi_agency": agency_obj,
        "company": agency_obj["name"] if agency_obj else None,
        "full_name": d.get("FullName") or "",
        "email": d.get("Email") or "",
        "phone": d.get("Phone"),
        "specialization": d.get("Specialization"),
        "certifications": d.get("Certifications"),
        "certification_number": d.get("Certifications"),
        "experience_years": d.get("ExperienceYears"),
        "years_of_experience": d.get("ExperienceYears"),
        "cv_url": d.get("CvUrl"),
        "photo_url": d.get("PhotoUrl"),
        "qualification_url": d.get("PhotoUrl"),
        "status": _parse_inspector_status_to_str(d.get("Status")),
        "created_at": d.get("CreatedAt"),
        "updated_at": d.get("UpdatedAt"),
    }


def list_inspectors() -> List[Dict[str, Any]]:
    agencies = {a["id"]: a for a in list_agencies()}
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM Inspectors ORDER BY CreatedAt DESC").fetchall()
        return [_map_inspector(r, agencies) for r in rows]


def get_inspector(inspector_id: str) -> Optional[Dict[str, Any]]:
    if not inspector_id:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Inspectors WHERE UPPER(Id) = UPPER(?)", (inspector_id,)
        ).fetchone()
        return _map_inspector(row) if row else None


def _resolve_agency_id(data: Dict[str, Any]) -> Optional[str]:
    aid = data.get("tpi_agency_id")
    if aid:
        return str(aid).upper()
    company = data.get("company") or data.get("tpi_agency")
    if isinstance(company, str) and company.strip():
        for a in list_agencies():
            if a["name"].lower() == company.strip().lower():
                return a["id"].upper()
    return None


def create_inspector(data: Dict[str, Any]) -> Dict[str, Any]:
    iid = str(data.get("id") or uuid.uuid4()).upper()
    ts = now_iso()
    agency_id = _resolve_agency_id(data)
    spec = data.get("specialization")
    if isinstance(spec, list):
        spec = ", ".join(str(x) for x in spec)
    exp = data.get("experience_years") if data.get("experience_years") is not None else data.get("years_of_experience")
    try:
        exp = int(exp) if exp not in (None, "") else None
    except Exception:
        exp = None

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO Inspectors (
                Id, UserId, TpiAgencyId, FullName, Email, Phone,
                Specialization, Certifications, ExperienceYears,
                CvUrl, PhotoUrl, Status, CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                iid,
                str(data["user_id"]).upper() if data.get("user_id") else None,
                agency_id,
                data.get("full_name", ""),
                data.get("email", ""),
                data.get("phone"),
                spec,
                data.get("certifications") or data.get("certification_number"),
                exp,
                data.get("cv_url"),
                data.get("photo_url") or data.get("qualification_url"),
                _parse_inspector_status_to_int(data.get("status", "active")),
                ts,
                ts,
            ),
        )
        conn.commit()
    return get_inspector(iid)  # type: ignore


def update_inspector(inspector_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_inspector(inspector_id)
    if not existing:
        return None
    ts = now_iso()
    agency_id = _resolve_agency_id(data)
    if agency_id is None and "tpi_agency_id" not in data and "company" not in data:
        agency_id = existing["tpi_agency_id"].upper() if existing.get("tpi_agency_id") else None

    spec = data.get("specialization", existing["specialization"])
    if isinstance(spec, list):
        spec = ", ".join(str(x) for x in spec)

    exp = data.get("experience_years", data.get("years_of_experience", existing["experience_years"]))
    try:
        exp = int(exp) if exp not in (None, "") else None
    except Exception:
        exp = existing["experience_years"]

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE Inspectors
            SET TpiAgencyId = ?, FullName = ?, Email = ?, Phone = ?,
                Specialization = ?, Certifications = ?, ExperienceYears = ?,
                CvUrl = ?, PhotoUrl = ?, Status = ?, UpdatedAt = ?
            WHERE UPPER(Id) = UPPER(?)
            """,
            (
                agency_id,
                data.get("full_name") or existing["full_name"],
                data.get("email") or existing["email"],
                data.get("phone", existing["phone"]),
                spec,
                data.get("certifications", data.get("certification_number", existing["certifications"])),
                exp,
                data.get("cv_url", existing["cv_url"]),
                data.get("photo_url", data.get("qualification_url", existing["photo_url"])),
                _parse_inspector_status_to_int(data.get("status", existing["status"])),
                ts,
                inspector_id,
            ),
        )
        conn.commit()
    return get_inspector(inspector_id)


def delete_inspector(inspector_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM Inspectors WHERE UPPER(Id) = UPPER(?)", (inspector_id,))
        conn.commit()
        return cur.rowcount > 0


# ── Inspections ──────────────────────────────────────────────────────────────

def _parse_inspection_status_to_str(val: Any) -> str:
    if isinstance(val, int):
        return INSPECTION_STATUS_INT_TO_STR.get(val, "received")
    if isinstance(val, str):
        if val.isdigit():
            return INSPECTION_STATUS_INT_TO_STR.get(int(val), "received")
        return val.lower()
    return "received"


def _parse_inspection_status_to_int(val: Any) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.isdigit():
            return int(val)
        return INSPECTION_STATUS_STR_TO_INT.get(val.lower(), 0)
    return 0


def _map_inspection(
    row: sqlite3.Row,
    projects_map: Optional[Dict[str, Dict[str, Any]]] = None,
    inspectors_map: Optional[Dict[str, Dict[str, Any]]] = None,
    agencies_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    d = dict(row)
    proj_id = _norm_id(d.get("ProjectId"))
    insp_id = _norm_id(d.get("AssignedInspectorId"))
    agency_id = _norm_id(d.get("TpiAgencyId"))

    project_obj = projects_map.get(proj_id) if (projects_map and proj_id) else (get_project(proj_id) if proj_id else None)
    inspector_obj = inspectors_map.get(insp_id) if (inspectors_map and insp_id) else (get_inspector(insp_id) if insp_id else None)
    agency_obj = agencies_map.get(agency_id) if (agencies_map and agency_id) else (get_agency(agency_id) if agency_id else None)
    if not agency_obj and inspector_obj and inspector_obj.get("tpi_agency"):
        agency_obj = inspector_obj["tpi_agency"]

    reports = _parse_json_safe(d.get("InspectionReports"), [])
    activities = _parse_json_safe(d.get("InspectionActivities"), [])
    items = _parse_json_safe(d.get("ItemsBeingOffered"), [])
    test_reports = _parse_json_safe(d.get("TestReportsJson"), [])
    additional_reports = _parse_json_safe(d.get("AdditionalReportsJson"), [])

    release_notes = []
    if d.get("ReleaseNoteUrl"):
        parsed_rn = _parse_json_safe(d.get("ReleaseNoteUrl"), None)
        if isinstance(parsed_rn, list):
            release_notes = parsed_rn
        elif isinstance(d.get("ReleaseNoteUrl"), str) and d.get("ReleaseNoteUrl").startswith("http"):
            release_notes = [{"name": "Release Note", "url": d.get("ReleaseNoteUrl"), "uploaded_date": d.get("UpdatedAt")}]

    # Compute helper counts & consolidated findings list for quick filters / Vendor Portal
    total_findings = 0
    open_ncrs = 0
    consolidated_findings = []
    for rep in reports:
        if isinstance(rep, dict):
            rep_url = rep.get("url") or ""
            rep_name = rep.get("name") or "Inspection Report"
            for idx, f in enumerate(rep.get("findings", []) or []):
                if isinstance(f, dict):
                    total_findings += 1
                    ftype = (f.get("type") or "").lower()
                    fstatus = (f.get("closure_status") or f.get("status") or "open").lower()
                    if ("ncr" in ftype or "non-conformance" in ftype or "nonconformance" in ftype) and fstatus != "closed":
                        open_ncrs += 1
                    f_id = f.get("id") or f"{rep_url}_{idx}"
                    consolidated_findings.append({
                        **f,
                        "id": f_id,
                        "report_name": rep_name,
                        "report_url": rep_url,
                    })

    return {
        "id": _norm_id(d.get("Id")),
        "po_number": d.get("PoNumber") or "",
        "notification_number": d.get("NotificationNumber") or "",
        "notification_revision": d.get("NotificationRevision"),
        "supplier_name": d.get("SupplierName") or "",
        "subsupplier_name": d.get("SubsupplierName"),
        "supplier_address": d.get("SupplierAddress"),
        "country": d.get("Country"),
        "po_description": d.get("PoDescription"),
        "inspection_type": d.get("InspectionType"),
        "vendor_contact_name": d.get("VendorContactName"),
        "vendor_contact_phone": d.get("VendorContactPhone"),
        "vendor_contact_email": d.get("VendorContactEmail"),
        "project_id": proj_id,
        "project": project_obj,
        "assigned_inspector_id": insp_id,
        "inspector": inspector_obj,
        "assigned_inspector_name": inspector_obj["full_name"] if inspector_obj else None,
        "assigned_inspector_email": inspector_obj["email"] if inspector_obj else None,
        "assigned_inspector_phone": inspector_obj["phone"] if inspector_obj else None,
        "tpi_agency_id": agency_id,
        "tpi_agency_obj": agency_obj,
        "tpi_agency": agency_obj["name"] if agency_obj else None,
        "assigned_by": _norm_id(d.get("AssignedBy")),
        "assigned_inspection_engineer_id": _norm_id(d.get("AssignedInspectionEngineerId")),
        "assigned_inspection_engineer_name": d.get("AssignedInspectionEngineerName") or (project_obj.get("inspection_manager_name") if project_obj else ""),
        "assigned_inspection_engineer_email": d.get("AssignedInspectionEngineerEmail") or (project_obj.get("inspection_manager_email") if project_obj else ""),
        "assigned_expeditor_id": _norm_id(d.get("AssignedExpeditorId")),
        "assigned_expeditor_name": d.get("AssignedExpeditorName") or "",
        "assigned_expeditor_email": d.get("AssignedExpeditorEmail") or "",
        "expediting_manager_name": d.get("ExpeditingManagerName") or (project_obj.get("expediting_manager_name") if project_obj else ""),
        "inspection_manager_name": d.get("InspectionManagerName") or (project_obj.get("inspection_manager_name") if project_obj else ""),
        "cancellation_reason": d.get("CancellationReason") or "",
        "cancelled_by": d.get("CancelledBy") or "",
        "cancelled_at": d.get("CancelledAt") or "",
        "abortive_inspection": bool(d.get("AbortiveInspection")),
        "inspector_confirmation_status": d.get("InspectorConfirmationStatus") or "confirmed",
        "reconfirmation_deadline": d.get("ReconfirmationDeadline"),
        "notification_date": _fmt_date(d.get("NotificationDate")),
        "notification_receipt_date": _fmt_date(d.get("NotificationReceiptDate")),
        "start_date": _fmt_date(d.get("StartDate")),
        "end_date": _fmt_date(d.get("EndDate")),
        "expected_completion_date": _fmt_date(d.get("ExpectedCompletionDate")),
        "actual_completion_date": _fmt_date(d.get("ActualCompletionDate")),
        "all_inspection_dates": d.get("AllInspectionDates"),
        "inspection_time": d.get("InspectionTime"),
        "location_name": d.get("LocationName"),
        "location_address": d.get("LocationAddress") or d.get("SupplierAddress"),
        "inspection_location": d.get("LocationAddress") or d.get("LocationName") or d.get("SupplierAddress"),
        "location_latitude": d.get("LocationLatitude"),
        "location_longitude": d.get("LocationLongitude"),
        "status": _parse_inspection_status_to_str(d.get("Status")),
        "items_being_offered": items,
        "inspection_reports": reports,
        "test_reports": test_reports,
        "additional_reports": additional_reports,
        "document_url": d.get("DocumentUrl"),
        "findings": consolidated_findings,
        "inspection_activities": activities,
        "release_notes": release_notes,
        "release_note_url": d.get("ReleaseNoteUrl"),
        "notes": d.get("Notes"),
        "created_by": d.get("CreatedBy"),
        "created_at": d.get("CreatedAt"),
        "updated_at": d.get("UpdatedAt"),
        "total_findings_count": total_findings,
        "open_ncrs_count": open_ncrs,
    }


def list_inspections() -> List[Dict[str, Any]]:
    projects = {p["id"]: p for p in list_projects()}
    agencies = {a["id"]: a for a in list_agencies()}
    inspectors = {i["id"]: i for i in list_inspectors()}
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM Inspections ORDER BY CreatedAt DESC").fetchall()
        return [_map_inspection(r, projects, inspectors, agencies) for r in rows]


def get_inspection(inspection_id: str) -> Optional[Dict[str, Any]]:
    if not inspection_id:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Inspections WHERE UPPER(Id) = UPPER(?)", (inspection_id,)
        ).fetchone()
        if not row:
            return None
        item = _map_inspection(row)
        item["reviews"] = list_reviews(inspection_id=inspection_id)
        item["attendances"] = list_attendances(inspection_id=inspection_id)
        return item


def create_inspection(data: Dict[str, Any]) -> Dict[str, Any]:
    iid = str(data.get("id") or uuid.uuid4()).upper()
    ts = now_iso()
    agency_id = _resolve_agency_id(data)
    proj_id = str(data["project_id"]).upper() if data.get("project_id") else None
    insp_id = str(data["assigned_inspector_id"]).upper() if data.get("assigned_inspector_id") else None

    lat = data.get("location_latitude") if data.get("location_latitude") not in (None, "") else data.get("latitude")
    lng = data.get("location_longitude") if data.get("location_longitude") not in (None, "") else data.get("longitude")
    try:
        lat = float(lat) if lat not in (None, "") else None
        lng = float(lng) if lng not in (None, "") else None
    except Exception:
        lat, lng = None, None

    rn_val = data.get("release_note_url")
    if data.get("release_notes") is not None:
        rn_val = _to_json_str(data.get("release_notes"))

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO Inspections (
                Id, PoNumber, NotificationNumber, NotificationRevision,
                SupplierName, SubsupplierName, SupplierAddress, Country,
                PoDescription, InspectionType, VendorContactName, VendorContactPhone, VendorContactEmail,
                ProjectId, AssignedInspectorId, TpiAgencyId, AssignedBy,
                NotificationDate, NotificationReceiptDate, StartDate, EndDate,
                ExpectedCompletionDate, ActualCompletionDate, AllInspectionDates, InspectionTime,
                LocationName, LocationAddress, LocationLatitude, LocationLongitude,
                Status, ItemsBeingOffered, InspectionReports, InspectionActivities,
                TestReportsJson, AdditionalReportsJson, DocumentUrl,
                Notes, ReleaseNoteUrl, CreatedAt, UpdatedAt, CreatedBy,
                AssignedInspectionEngineerId, AssignedInspectionEngineerName, AssignedInspectionEngineerEmail,
                AssignedExpeditorId, AssignedExpeditorName, AssignedExpeditorEmail,
                ExpeditingManagerName, InspectionManagerName,
                CancellationReason, CancelledBy, CancelledAt, AbortiveInspection,
                InspectorConfirmationStatus, ReconfirmationDeadline
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                iid,
                data.get("po_number", ""),
                data.get("notification_number", ""),
                data.get("notification_revision"),
                data.get("supplier_name", ""),
                data.get("subsupplier_name"),
                data.get("supplier_address") or data.get("inspection_location"),
                data.get("country"),
                data.get("po_description"),
                data.get("inspection_type"),
                data.get("vendor_contact_name") or data.get("inspector_name"),
                data.get("vendor_contact_phone") or data.get("contact_phone"),
                data.get("vendor_contact_email") or data.get("contact_email"),
                proj_id,
                insp_id,
                agency_id,
                str(data["assigned_by"]).upper() if data.get("assigned_by") else None,
                _fmt_date(data.get("notification_date")),
                _fmt_date(data.get("notification_receipt_date")),
                _fmt_date(data.get("start_date")),
                _fmt_date(data.get("end_date")),
                _fmt_date(data.get("expected_completion_date")),
                _fmt_date(data.get("actual_completion_date")),
                data.get("all_inspection_dates"),
                data.get("inspection_time"),
                data.get("location_name"),
                data.get("location_address") or data.get("inspection_location"),
                lat,
                lng,
                _parse_inspection_status_to_int(data.get("status", "received")),
                _to_json_str(data.get("items_being_offered", [])),
                _to_json_str(data.get("inspection_reports", [])),
                _to_json_str(data.get("inspection_activities", [])),
                _to_json_str(data.get("test_reports", [])),
                _to_json_str(data.get("additional_reports", [])),
                data.get("document_url"),
                data.get("notes"),
                rn_val,
                ts,
                ts,
                data.get("created_by"),
                _norm_id(data.get("assigned_inspection_engineer_id")),
                data.get("assigned_inspection_engineer_name"),
                data.get("assigned_inspection_engineer_email"),
                _norm_id(data.get("assigned_expeditor_id")),
                data.get("assigned_expeditor_name"),
                data.get("assigned_expeditor_email"),
                data.get("expediting_manager_name"),
                data.get("inspection_manager_name"),
                data.get("cancellation_reason"),
                data.get("cancelled_by"),
                data.get("cancelled_at"),
                1 if data.get("abortive_inspection") else 0,
                data.get("inspector_confirmation_status", "confirmed"),
                data.get("reconfirmation_deadline"),
            ),
        )
        conn.commit()
    return get_inspection(iid)  # type: ignore


def update_inspection(inspection_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_inspection(inspection_id)
    if not existing:
        return None
    ts = now_iso()

    agency_id = _resolve_agency_id(data)
    if agency_id is None and "tpi_agency_id" not in data and "tpi_agency" not in data:
        agency_id = existing["tpi_agency_id"].upper() if existing.get("tpi_agency_id") else None

    proj_id = (
        str(data["project_id"]).upper()
        if data.get("project_id")
        else (existing["project_id"].upper() if existing.get("project_id") and "project_id" not in data else None)
    )
    insp_id = (
        str(data["assigned_inspector_id"]).upper()
        if data.get("assigned_inspector_id")
        else (
            existing["assigned_inspector_id"].upper()
            if existing.get("assigned_inspector_id") and "assigned_inspector_id" not in data
            else None
        )
    )

    items = data.get("items_being_offered") if "items_being_offered" in data else existing["items_being_offered"]
    reports = data.get("inspection_reports") if "inspection_reports" in data else existing["inspection_reports"]
    activities = data.get("inspection_activities") if "inspection_activities" in data else existing["inspection_activities"]
    test_reports = data.get("test_reports") if "test_reports" in data else existing.get("test_reports", [])
    additional_reports = data.get("additional_reports") if "additional_reports" in data else existing.get("additional_reports", [])
    doc_url = data.get("document_url", existing.get("document_url"))

    rn_val = existing.get("release_note_url")
    if "release_notes" in data:
        rn_val = _to_json_str(data["release_notes"])
    elif "release_note_url" in data:
        rn_val = data["release_note_url"]

    lat = data.get("location_latitude", existing.get("location_latitude"))
    lng = data.get("location_longitude", existing.get("location_longitude"))
    try:
        lat = float(lat) if lat not in (None, "") else None
        lng = float(lng) if lng not in (None, "") else None
    except Exception:
        lat, lng = existing.get("location_latitude"), existing.get("location_longitude")

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE Inspections
            SET PoNumber = ?, NotificationNumber = ?, NotificationRevision = ?,
                SupplierName = ?, SubsupplierName = ?, SupplierAddress = ?, Country = ?,
                PoDescription = ?, InspectionType = ?,
                VendorContactName = ?, VendorContactPhone = ?, VendorContactEmail = ?,
                ProjectId = ?, AssignedInspectorId = ?, TpiAgencyId = ?,
                NotificationDate = ?, NotificationReceiptDate = ?, StartDate = ?, EndDate = ?,
                ExpectedCompletionDate = ?, ActualCompletionDate = ?,
                AllInspectionDates = ?, InspectionTime = ?,
                LocationName = ?, LocationAddress = ?, LocationLatitude = ?, LocationLongitude = ?,
                Status = ?, ItemsBeingOffered = ?, InspectionReports = ?, InspectionActivities = ?,
                TestReportsJson = ?, AdditionalReportsJson = ?, DocumentUrl = ?,
                Notes = ?, ReleaseNoteUrl = ?, UpdatedAt = ?,
                AssignedInspectionEngineerId = ?, AssignedInspectionEngineerName = ?, AssignedInspectionEngineerEmail = ?,
                AssignedExpeditorId = ?, AssignedExpeditorName = ?, AssignedExpeditorEmail = ?,
                ExpeditingManagerName = ?, InspectionManagerName = ?,
                CancellationReason = ?, CancelledBy = ?, CancelledAt = ?, AbortiveInspection = ?,
                InspectorConfirmationStatus = ?, ReconfirmationDeadline = ?
            WHERE UPPER(Id) = UPPER(?)
            """,
            (
                data.get("po_number") or existing["po_number"],
                data.get("notification_number") or existing["notification_number"],
                data.get("notification_revision", existing["notification_revision"]),
                data.get("supplier_name") or existing["supplier_name"],
                data.get("subsupplier_name", existing["subsupplier_name"]),
                data.get("supplier_address", existing["supplier_address"]),
                data.get("country", existing["country"]),
                data.get("po_description", existing["po_description"]),
                data.get("inspection_type", existing["inspection_type"]),
                data.get("vendor_contact_name", existing["vendor_contact_name"]),
                data.get("vendor_contact_phone", existing["vendor_contact_phone"]),
                data.get("vendor_contact_email", existing["vendor_contact_email"]),
                proj_id,
                insp_id,
                agency_id,
                _fmt_date(data.get("notification_date", existing["notification_date"])),
                _fmt_date(data.get("notification_receipt_date", existing["notification_receipt_date"])),
                _fmt_date(data.get("start_date", existing["start_date"])),
                _fmt_date(data.get("end_date", existing["end_date"])),
                _fmt_date(data.get("expected_completion_date", existing["expected_completion_date"])),
                _fmt_date(data.get("actual_completion_date", existing["actual_completion_date"])),
                data.get("all_inspection_dates", existing["all_inspection_dates"]),
                data.get("inspection_time", existing["inspection_time"]),
                data.get("location_name", existing["location_name"]),
                data.get("location_address", data.get("inspection_location", existing["location_address"])),
                lat,
                lng,
                _parse_inspection_status_to_int(data.get("status", existing["status"])),
                _to_json_str(items),
                _to_json_str(reports),
                _to_json_str(activities),
                _to_json_str(test_reports),
                _to_json_str(additional_reports),
                doc_url,
                data.get("notes", existing["notes"]),
                rn_val,
                ts,
                _norm_id(data.get("assigned_inspection_engineer_id", existing.get("assigned_inspection_engineer_id"))),
                data.get("assigned_inspection_engineer_name", existing.get("assigned_inspection_engineer_name")),
                data.get("assigned_inspection_engineer_email", existing.get("assigned_inspection_engineer_email")),
                _norm_id(data.get("assigned_expeditor_id", existing.get("assigned_expeditor_id"))),
                data.get("assigned_expeditor_name", existing.get("assigned_expeditor_name")),
                data.get("assigned_expeditor_email", existing.get("assigned_expeditor_email")),
                data.get("expediting_manager_name", existing.get("expediting_manager_name")),
                data.get("inspection_manager_name", existing.get("inspection_manager_name")),
                data.get("cancellation_reason", existing.get("cancellation_reason")),
                data.get("cancelled_by", existing.get("cancelled_by")),
                data.get("cancelled_at", existing.get("cancelled_at")),
                1 if data.get("abortive_inspection", existing.get("abortive_inspection")) else 0,
                data.get("inspector_confirmation_status", existing.get("inspector_confirmation_status")),
                data.get("reconfirmation_deadline", existing.get("reconfirmation_deadline")),
                inspection_id,
            ),
        )
        conn.commit()
    return get_inspection(inspection_id)


def delete_inspection(inspection_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM Inspections WHERE UPPER(Id) = UPPER(?)", (inspection_id,))
        conn.commit()
        return cur.rowcount > 0


# ── Attendances ──────────────────────────────────────────────────────────────

def _map_attendance(row: sqlite3.Row, inspectors_map: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = dict(row)
    insp_id = _norm_id(d.get("InspectorId"))
    inspector_obj = inspectors_map.get(insp_id) if (inspectors_map and insp_id) else (get_inspector(insp_id) if insp_id else None)
    ci_lat = d.get("CheckInLatitude")
    ci_lng = d.get("CheckInLongitude")
    co_lat = d.get("CheckOutLatitude")
    co_lng = d.get("CheckOutLongitude")
    return {
        "id": _norm_id(d.get("Id")),
        "inspection_id": _norm_id(d.get("InspectionId")),
        "inspector_id": insp_id,
        "inspector": inspector_obj,
        "inspector_name": inspector_obj["full_name"] if inspector_obj else None,
        "check_in_time": d.get("CheckInTime"),
        "check_out_time": d.get("CheckOutTime"),
        "check_in_latitude": ci_lat,
        "check_in_longitude": ci_lng,
        "check_out_latitude": co_lat,
        "check_out_longitude": co_lng,
        "check_in_coordinates_text": f"POINT({ci_lng} {ci_lat})" if (ci_lat is not None and ci_lng is not None) else None,
        "check_out_coordinates_text": f"POINT({co_lng} {co_lat})" if (co_lat is not None and co_lng is not None) else None,
        "location_verified": bool(d.get("LocationVerified")),
        "distance_from_site_meters": d.get("DistanceFromSiteMeters"),
        "check_in_notes": d.get("CheckInNotes"),
        "check_out_notes": d.get("CheckOutNotes"),
        "created_at": d.get("CreatedAt"),
    }


def list_attendances(inspection_id: Optional[str] = None, inspector_id: Optional[str] = None) -> List[Dict[str, Any]]:
    inspectors = {i["id"]: i for i in list_inspectors()}
    query = "SELECT * FROM InspectionAttendances WHERE 1=1"
    params: List[Any] = []
    if inspection_id:
        query += " AND UPPER(InspectionId) = UPPER(?)"
        params.append(inspection_id)
    if inspector_id:
        query += " AND UPPER(InspectorId) = UPPER(?)"
        params.append(inspector_id)
    query += " ORDER BY CheckInTime DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_map_attendance(r, inspectors) for r in rows]


def get_attendance(attendance_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM InspectionAttendances WHERE UPPER(Id) = UPPER(?)", (attendance_id,)
        ).fetchone()
        return _map_attendance(row) if row else None


def create_attendance(data: Dict[str, Any]) -> Dict[str, Any]:
    aid = str(data.get("id") or uuid.uuid4()).upper()
    ts = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO InspectionAttendances (
                Id, InspectionId, InspectorId, CheckInTime, CheckOutTime,
                CheckInLatitude, CheckInLongitude, CheckOutLatitude, CheckOutLongitude,
                LocationVerified, DistanceFromSiteMeters, CheckInNotes, CheckOutNotes, CreatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                str(data.get("inspection_id", "")).upper(),
                str(data.get("inspector_id", "")).upper(),
                data.get("check_in_time") or ts,
                data.get("check_out_time"),
                data.get("check_in_latitude"),
                data.get("check_in_longitude"),
                data.get("check_out_latitude"),
                data.get("check_out_longitude"),
                1 if data.get("location_verified") else 0,
                data.get("distance_from_site_meters"),
                data.get("check_in_notes"),
                data.get("check_out_notes"),
                ts,
            ),
        )
        conn.commit()
    return get_attendance(aid)  # type: ignore


def update_attendance(attendance_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_attendance(attendance_id)
    if not existing:
        return None
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE InspectionAttendances
            SET CheckInTime = ?, CheckOutTime = ?,
                CheckInLatitude = ?, CheckInLongitude = ?,
                CheckOutLatitude = ?, CheckOutLongitude = ?,
                LocationVerified = ?, DistanceFromSiteMeters = ?,
                CheckInNotes = ?, CheckOutNotes = ?
            WHERE UPPER(Id) = UPPER(?)
            """,
            (
                data.get("check_in_time", existing["check_in_time"]),
                data.get("check_out_time", existing["check_out_time"]),
                data.get("check_in_latitude", existing["check_in_latitude"]),
                data.get("check_in_longitude", existing["check_in_longitude"]),
                data.get("check_out_latitude", existing["check_out_latitude"]),
                data.get("check_out_longitude", existing["check_out_longitude"]),
                1 if data.get("location_verified", existing["location_verified"]) else 0,
                data.get("distance_from_site_meters", existing["distance_from_site_meters"]),
                data.get("check_in_notes", existing["check_in_notes"]),
                data.get("check_out_notes", existing["check_out_notes"]),
                attendance_id,
            ),
        )
        conn.commit()
    return get_attendance(attendance_id)


def delete_attendance(attendance_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM InspectionAttendances WHERE UPPER(Id) = UPPER(?)", (attendance_id,))
        conn.commit()
        return cur.rowcount > 0


# ── Reviews ──────────────────────────────────────────────────────────────────

def _map_review(row: sqlite3.Row, inspectors_map: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    d = dict(row)
    insp_id = _norm_id(d.get("InspectorId"))
    inspector_obj = inspectors_map.get(insp_id) if (inspectors_map and insp_id) else (get_inspector(insp_id) if insp_id else None)
    overall = d.get("OverallScore") or 0
    spec_score = d.get("SpecificationComplianceScore")
    if spec_score is None:
        spec_score = d.get("ReportQualityScore")
    fta = d.get("FirstTimeAcceptance")
    itp_comp = d.get("ItpHoldPointCompliance")
    return {
        "id": _norm_id(d.get("Id")),
        "inspection_id": _norm_id(d.get("InspectionId")),
        "inspector_id": insp_id,
        "inspector": inspector_obj,
        "reviewed_by": _norm_id(d.get("ReviewedBy")),
        "report_quality_score": d.get("ReportQualityScore"),
        "timeliness_score": d.get("TimelinessScore"),
        "communication_score": d.get("CommunicationScore"),
        "specification_compliance_score": spec_score,
        "first_time_acceptance": bool(fta) if fta is not None else None,
        "itp_hold_point_compliance": bool(itp_comp) if itp_comp is not None else None,
        "value_added_observations": d.get("ValueAddedObservations") or 0,
        "overall_score": overall,
        "client_rating": round(overall / 20.0, 1) if overall else 5.0,
        "missed_ncr_count": d.get("MissedNcrCount") or 0,
        "false_ncr_count": d.get("FalseNcrCount") or 0,
        "strengths": d.get("Strengths"),
        "areas_for_improvement": d.get("AreasForImprovement"),
        "additional_comments": d.get("AdditionalComments"),
        "review_date": d.get("ReviewDate"),
        "created_at": d.get("CreatedAt"),
    }


def list_reviews(inspection_id: Optional[str] = None, inspector_id: Optional[str] = None) -> List[Dict[str, Any]]:
    inspectors = {i["id"]: i for i in list_inspectors()}
    query = "SELECT * FROM InspectionReviews WHERE 1=1"
    params: List[Any] = []
    if inspection_id:
        query += " AND UPPER(InspectionId) = UPPER(?)"
        params.append(inspection_id)
    if inspector_id:
        query += " AND UPPER(InspectorId) = UPPER(?)"
        params.append(inspector_id)
    query += " ORDER BY ReviewDate DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_map_review(r, inspectors) for r in rows]


def get_review(review_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM InspectionReviews WHERE UPPER(Id) = UPPER(?)", (review_id,)
        ).fetchone()
        return _map_review(row) if row else None


def create_review(data: Dict[str, Any]) -> Dict[str, Any]:
    rid = str(data.get("id") or uuid.uuid4()).upper()
    ts = now_iso()
    q_score = data.get("report_quality_score")
    t_score = data.get("timeliness_score")
    c_score = data.get("communication_score")
    spec_score = data.get("specification_compliance_score")
    fta = data.get("first_time_acceptance")
    itp_comp = data.get("itp_hold_point_compliance")
    val_obs = int(data.get("value_added_observations") or 0)
    o_score = data.get("overall_score")
    if o_score is None:
        vals = [int(x) for x in (q_score, t_score, c_score, spec_score) if x is not None]
        o_score = round(sum(vals) / len(vals)) if vals else 85

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO InspectionReviews (
                Id, InspectionId, InspectorId, ReviewedBy,
                ReportQualityScore, TimelinessScore, CommunicationScore,
                SpecificationComplianceScore, FirstTimeAcceptance, ItpHoldPointCompliance, ValueAddedObservations,
                OverallScore, MissedNcrCount, FalseNcrCount, Strengths, AreasForImprovement,
                AdditionalComments, ReviewDate, CreatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                str(data.get("inspection_id", "")).upper(),
                str(data.get("inspector_id", "")).upper(),
                str(data["reviewed_by"]).upper() if data.get("reviewed_by") else None,
                q_score,
                t_score,
                c_score,
                spec_score,
                (1 if fta else 0) if fta is not None else None,
                (1 if itp_comp else 0) if itp_comp is not None else None,
                val_obs,
                o_score,
                int(data.get("missed_ncr_count") or 0),
                int(data.get("false_ncr_count") or 0),
                data.get("strengths"),
                data.get("areas_for_improvement"),
                data.get("additional_comments"),
                data.get("review_date") or ts,
                ts,
            ),
        )
        conn.commit()
    return get_review(rid)  # type: ignore


def update_review(review_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_review(review_id)
    if not existing:
        return None
    q_score = data.get("report_quality_score", existing.get("report_quality_score"))
    t_score = data.get("timeliness_score", existing.get("timeliness_score"))
    c_score = data.get("communication_score", existing.get("communication_score"))
    spec_score = data.get("specification_compliance_score", existing.get("specification_compliance_score"))
    fta = data.get("first_time_acceptance", existing.get("first_time_acceptance"))
    itp_comp = data.get("itp_hold_point_compliance", existing.get("itp_hold_point_compliance"))
    val_obs = data.get("value_added_observations", existing.get("value_added_observations") or 0)
    o_score = data.get("overall_score")
    if o_score is None:
        vals = [int(x) for x in (q_score, t_score, c_score, spec_score) if x is not None]
        o_score = round(sum(vals) / len(vals)) if vals else existing.get("overall_score", 85)

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE InspectionReviews
            SET ReportQualityScore = ?, TimelinessScore = ?, CommunicationScore = ?,
                SpecificationComplianceScore = ?, FirstTimeAcceptance = ?, ItpHoldPointCompliance = ?, ValueAddedObservations = ?,
                OverallScore = ?, MissedNcrCount = ?, FalseNcrCount = ?, Strengths = ?,
                AreasForImprovement = ?, AdditionalComments = ?
            WHERE UPPER(Id) = UPPER(?)
            """,
            (
                q_score,
                t_score,
                c_score,
                spec_score,
                (1 if fta else 0) if fta is not None else None,
                (1 if itp_comp else 0) if itp_comp is not None else None,
                int(val_obs or 0),
                o_score,
                int(data.get("missed_ncr_count", existing.get("missed_ncr_count") or 0)),
                int(data.get("false_ncr_count", existing.get("false_ncr_count") or 0)),
                data.get("strengths", existing.get("strengths")),
                data.get("areas_for_improvement", existing.get("areas_for_improvement")),
                data.get("additional_comments", existing.get("additional_comments")),
                review_id,
            ),
        )
        conn.commit()
    return get_review(review_id)


def delete_review(review_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM InspectionReviews WHERE UPPER(Id) = UPPER(?)", (review_id,))
        conn.commit()
        return cur.rowcount > 0


def user_has_project_access(user: Optional[Dict[str, Any]], project: Dict[str, Any]) -> bool:
    if not user or not project:
        return False
    eff_role = str(user.get("effective_role") or user.get("inspection_role") or user.get("role") or "").lower()
    base_role = str(user.get("role") or "").lower()
    if eff_role == "admin" or base_role == "admin":
        return True

    uid = str(user.get("id") or "").strip().lower()
    uemail = str(user.get("email") or "").strip().lower()
    pid = str(project.get("id") or "").strip().lower()
    user_pids = {str(x).strip().lower() for x in (user.get("project_ids") or []) if x}
    team_ids = {str(x).strip().lower() for x in (project.get("team_member_ids") or []) if x}

    if pid and pid in user_pids:
        return True
    if uid and uid in team_ids:
        return True
    if uid and uid in {
        str(project.get("expediting_manager_id") or "").strip().lower(),
        str(project.get("inspection_manager_id") or "").strip().lower(),
    }:
        return True
    if uemail and uemail in {
        str(project.get("expediting_manager_email") or "").strip().lower(),
        str(project.get("inspection_manager_email") or "").strip().lower(),
    }:
        return True
    return False


# ── TPI Performance Aggregation ──────────────────────────────────────────────

def get_tpi_performance(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    agencies = list_agencies()
    inspectors = list_inspectors()
    inspections = list_inspections()
    if project_id and str(project_id).strip().lower() != "all":
        norm_pid = str(project_id).strip().lower()
        inspections = [i for i in inspections if str(i.get("project_id") or "").strip().lower() == norm_pid]
    insp_ids_scope = {i["id"] for i in inspections}
    reviews = list_reviews()
    if project_id and str(project_id).strip().lower() != "all":
        reviews = [r for r in reviews if r.get("inspection_id") in insp_ids_scope]

    result = []
    for a in agencies:
        aid = a["id"]
        a_inspectors = [i for i in inspectors if i.get("tpi_agency_id") == aid]
        a_inspector_ids = {i["id"] for i in a_inspectors}
        a_inspections = [
            insp
            for insp in inspections
            if insp.get("tpi_agency_id") == aid or insp.get("assigned_inspector_id") in a_inspector_ids
        ]
        a_inspection_ids = {insp["id"] for insp in a_inspections}
        a_reviews = [
            r
            for r in reviews
            if r.get("inspection_id") in a_inspection_ids or r.get("inspector_id") in a_inspector_ids
        ]

        def _avg(key: str) -> float:
            vals = [float(r[key]) for r in a_reviews if r.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else 0.0

        completed_with_dates = [
            i for i in a_inspections if i.get("actual_completion_date") and i.get("expected_completion_date")
        ]
        on_time_rate = 0.0
        if completed_with_dates:
            on_time = sum(
                1 for i in completed_with_dates if i["actual_completion_date"] <= i["expected_completion_date"]
            )
            on_time_rate = round((on_time / len(completed_with_dates)) * 100.0, 1)

        total_findings = sum(i.get("total_findings_count", 0) for i in a_inspections)
        total_ncrs = sum(i.get("open_ncrs_count", 0) for i in a_inspections)
        fta_vals = [100.0 if r.get("first_time_acceptance") else 0.0 for r in a_reviews if r.get("first_time_acceptance") is not None]
        itp_vals = [100.0 if r.get("itp_hold_point_compliance") else 0.0 for r in a_reviews if r.get("itp_hold_point_compliance") is not None]
        val_obs_total = sum(int(r.get("value_added_observations") or 0) for r in a_reviews)

        result.append(
            {
                "agency_id": aid,
                "agency_name": a["name"],
                "company_code": a.get("company_code"),
                "manager_name": a.get("manager_name"),
                "manager_email": a.get("manager_email"),
                "agency_status": a.get("status", "active"),
                "total_inspections": len(a_inspections),
                "completed_inspections": sum(1 for i in a_inspections if i.get("status") in ("completed", "finalized")),
                "reviewed_inspections": len(a_reviews),
                "received_inspections": sum(1 for i in a_inspections if i.get("status") == "received"),
                "in_progress_inspections": sum(1 for i in a_inspections if i.get("status") == "in_progress"),
                "scheduled_inspections": sum(1 for i in a_inspections if i.get("status") == "scheduled"),
                "avg_overall_score": _avg("overall_score"),
                "avg_quality_score": _avg("report_quality_score"),
                "avg_timeliness_score": _avg("timeliness_score"),
                "avg_communication_score": _avg("communication_score"),
                "avg_spec_compliance_score": _avg("specification_compliance_score"),
                "first_time_acceptance_rate": round(sum(fta_vals) / len(fta_vals), 1) if fta_vals else 0.0,
                "itp_hold_point_compliance_rate": round(sum(itp_vals) / len(itp_vals), 1) if itp_vals else 0.0,
                "total_value_added_observations": val_obs_total,
                "active_inspectors": sum(1 for i in a_inspectors if i.get("status") == "active"),
                "total_inspectors": len(a_inspectors),
                "on_time_completion_rate": on_time_rate,
                "total_ncrs": total_ncrs,
                "total_findings": total_findings,
                "total_missed_ncrs": sum(int(r.get("missed_ncr_count") or 0) for r in a_reviews),
                "total_false_ncrs": sum(int(r.get("false_ncr_count") or 0) for r in a_reviews),
            }
        )
    return result


# ── Users & Auth ─────────────────────────────────────────────────────────────

def _map_user(row: sqlite3.Row, include_password: bool = False) -> Dict[str, Any]:
    d = dict(row)
    res = {
        "id": _norm_id(d.get("Id")),
        "email": d.get("Email") or "",
        "full_name": d.get("FullName") or "",
        "role": d.get("Role") or "guest",
        "inspection_role": d.get("InspectionRole"),
        "company_affiliation": d.get("CompanyAffiliation") or "",
        "company": d.get("CompanyAffiliation") or "",
        "department": d.get("Department") or "",
        "phone": d.get("Phone") or "",
        "user_status": d.get("UserStatus") or "active",
        "project_ids": _parse_json_safe(d.get("ProjectIds"), []),
        "token_version": int(d.get("TokenVersion") or 1),
        "created_at": d.get("CreatedAt"),
        "updated_at": d.get("UpdatedAt"),
    }
    if include_password:
        res["password"] = d.get("Password")
    return res


def revoke_token(jti: str, expires_at: int) -> None:
    if not jti:
        return
    init_db()
    with _DB_WRITE_LOCK, get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO RevokedTokens (Jti, ExpiresAt, RevokedAt) VALUES (?, ?, ?)",
            (jti, int(expires_at or 0), now_iso()),
        )
        conn.execute("DELETE FROM RevokedTokens WHERE ExpiresAt < ?", (int(datetime.now(timezone.utc).timestamp()),))
        conn.commit()


def is_token_revoked(jti: str) -> bool:
    if not jti:
        return False
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM RevokedTokens WHERE Jti = ?", (jti,)).fetchone()
        return row is not None


def bump_user_token_version(user_id: str) -> None:
    if not user_id:
        return
    init_db()
    with _DB_WRITE_LOCK, get_connection() as conn:
        conn.execute(
            "UPDATE Users SET TokenVersion = COALESCE(TokenVersion, 1) + 1, UpdatedAt = ? WHERE UPPER(Id) = UPPER(?)",
            (now_iso(), user_id),
        )
        conn.commit()


def list_users() -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM Users ORDER BY CreatedAt ASC").fetchall()
        return [_map_user(r) for r in rows]


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Users WHERE LOWER(Email) = LOWER(?)", (email.strip(),)
        ).fetchone()
        if not row:
            return None
        user = _map_user(row, include_password=True)
        stored_pw = user.get("password") or ""
        if not verify_password(password, stored_pw):
            return None
        if not is_password_hashed(stored_pw):
            conn.execute(
                "UPDATE Users SET Password = ?, UpdatedAt = ? WHERE Id = ?",
                (hash_password(password), now_iso(), row["Id"]),
            )
            conn.commit()
        if user.get("user_status") == "deactivated":
            raise ValueError("This account has been deactivated. Please contact your administrator.")
        user.pop("password", None)
        return user


def register_user(email: str, password: str, full_name: str) -> Dict[str, Any]:
    init_db()
    uid = str(uuid.uuid4())
    ts = now_iso()
    hashed_pw = password if is_password_hashed(password) else hash_password(password)
    with _DB_WRITE_LOCK, get_connection() as conn:
        existing = conn.execute(
            "SELECT Id FROM Users WHERE LOWER(Email) = LOWER(?)", (email.strip(),)
        ).fetchone()
        if existing:
            raise ValueError("An account with this email already exists.")
        conn.execute(
            """
            INSERT INTO Users (
                Id, Email, Password, FullName, Role, InspectionRole,
                CompanyAffiliation, Department, Phone, UserStatus, ProjectIds,
                TokenVersion, CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, 'guest', NULL, '', '', '', 'pending', '[]', 1, ?, ?)
            """,
            (uid, email.strip().lower(), hashed_pw, full_name.strip() or email.split("@")[0], ts, ts),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM Users WHERE Id = ?", (uid,)).fetchone()
        return _map_user(row)


def update_user(user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_WRITE_LOCK, get_connection() as conn:
        row = conn.execute("SELECT * FROM Users WHERE UPPER(Id) = UPPER(?)", (user_id,)).fetchone()
        if not row:
            return None
        existing = _map_user(row, include_password=True)
        irole = data.get("inspection_role", existing["inspection_role"])
        role = data.get("role") or irole or existing["role"]
        new_status = data.get("user_status", existing["user_status"])
        new_pw = existing["password"]
        invalidate_sessions = False
        if data.get("password"):
            new_pw = data["password"] if is_password_hashed(data["password"]) else hash_password(str(data["password"]))
            invalidate_sessions = True
        if role != existing["role"] or irole != existing["inspection_role"] or new_status != existing["user_status"]:
            invalidate_sessions = True
        next_tv = int(existing.get("token_version") or 1) + (1 if invalidate_sessions else 0)
        conn.execute(
            """
            UPDATE Users
            SET FullName = ?, Role = ?, InspectionRole = ?, CompanyAffiliation = ?,
                Department = ?, Phone = ?, UserStatus = ?, ProjectIds = ?, Password = ?, TokenVersion = ?, UpdatedAt = ?
            WHERE UPPER(Id) = UPPER(?)
            """,
            (
                data.get("full_name", existing["full_name"]),
                role,
                irole,
                data.get("company_affiliation", existing["company_affiliation"]),
                data.get("department", existing["department"]),
                data.get("phone", existing["phone"]),
                new_status,
                _to_json_str(data.get("project_ids", existing["project_ids"])),
                new_pw,
                next_tv,
                now_iso(),
                user_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM Users WHERE UPPER(Id) = UPPER(?)", (user_id,)).fetchone()
        return _map_user(updated)


def ensure_vendor_user(
    company_name: str,
    vendor_email: str = "",
    contact_name: str = "",
    phone: str = "",
    project_id: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Finds an existing Vendor Portal user matching email or supplier company name,
    or creates a new active Vendor Portal account linked to the project.
    Returns (user_dict, created_bool).
    """
    init_db()
    company = str(company_name or "").strip() or "Vendor"
    raw_email = str(vendor_email or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "", company.lower()) or "vendor"
    target_email = raw_email or f"vendor@{slug}.com"
    norm_company = re.sub(r"[^a-z0-9]+", "", company.lower())

    users = list_users()
    matched = next(
        (u for u in users if str(u.get("email") or "").strip().lower() == target_email),
        None,
    )
    if not matched and not raw_email and norm_company and norm_company != "vendor":
        matched = next(
            (
                u
                for u in users
                if (u.get("inspection_role") or u.get("role")) == "vendor"
                and re.sub(r"[^a-z0-9]+", "", str(u.get("company_affiliation") or "").lower()) == norm_company
            ),
            None,
        )

    if matched:
        pids = list(matched.get("project_ids") or [])
        updates: Dict[str, Any] = {}
        if project_id and all(str(p).lower() != str(project_id).lower() for p in pids):
            pids.append(project_id)
            updates["project_ids"] = pids
        if company and not matched.get("company_affiliation"):
            updates["company_affiliation"] = company
        if contact_name and contact_name.strip() and not matched.get("full_name"):
            updates["full_name"] = contact_name.strip()
        if phone and phone.strip() and not matched.get("phone"):
            updates["phone"] = phone.strip()
        if updates:
            updated = update_user(matched["id"], updates)
            return (updated or matched, False)
        return (matched, False)

    uid = str(uuid.uuid4())
    ts = now_iso()
    full_name = str(contact_name or "").strip() or f"{company} (Vendor Portal)"
    raw_pw = str(password or "").strip() or secrets.token_urlsafe(16)
    hashed_pw = raw_pw if is_password_hashed(raw_pw) else hash_password(raw_pw)
    proj_list = [project_id] if project_id else []

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO Users (
                Id, Email, Password, FullName, Role, InspectionRole,
                CompanyAffiliation, Department, Phone, UserStatus, ProjectIds,
                CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, 'vendor', 'vendor', ?, 'Supplier Quality & Dispatch', ?, 'active', ?, ?, ?)
            """,
            (
                uid,
                target_email,
                hashed_pw,
                full_name,
                company,
                str(phone or "").strip(),
                _to_json_str(proj_list),
                ts,
                ts,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM Users WHERE Id = ?", (uid,)).fetchone()
        return (_map_user(row), True)


def find_and_update_finding(
    finding_id: str, mutator: Callable[[Dict[str, Any], Dict[str, Any]], None]
) -> Optional[Dict[str, Any]]:
    """
    Finds a finding across all Inspections' `inspection_reports[].findings`
    (matching either explicit `id` or deterministic fallback `{report.url}_{idx}`),
    applies `mutator(finding, inspection)`, persists back to `InspectionReports`,
    and returns the updated Inspection record under an atomic write lock.
    """
    target_fid = str(finding_id or "").strip()
    with _DB_WRITE_LOCK:
        for insp in list_inspections():
            reports = insp.get("inspection_reports") or []
            matched = False
            for rep in reports:
                if not isinstance(rep, dict):
                    continue
                rep_url = rep.get("url") or ""
                findings = rep.get("findings") or []
                for idx, f in enumerate(findings):
                    if not isinstance(f, dict):
                        continue
                    curr_id = str(f.get("id") or f"{rep_url}_{idx}")
                    if curr_id == target_fid or str(f.get("id") or "") == target_fid:
                        f["id"] = curr_id
                        mutator(f, insp)
                        matched = True
                        break
                if matched:
                    break
            if matched:
                return update_inspection(insp["id"], {"inspection_reports": reports})
    return None


# ── File Storage ─────────────────────────────────────────────────────────────

def save_uploaded_file(
    file_bytes: bytes,
    filename: str,
    bucket: str = "inspection-documents",
    subpath: Optional[str] = None,
    base_url: str = "http://localhost:5214",
) -> str:
    safe_bucket = "".join(c if c.isalnum() or c in "-_" else "_" for c in (bucket or "inspection-documents"))
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in (filename or "document.pdf"))
    ext = Path(safe_name).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise ValueError(f"Extension '{ext}' is not permitted")
    rel_path = f"uploads/{uuid.uuid4().hex}_{safe_name}"
    target_path = (UPLOADS_DIR / safe_bucket / Path(rel_path)).resolve()
    root_resolved = UPLOADS_DIR.resolve()
    if root_resolved not in target_path.parents:
        raise ValueError("Invalid upload target path")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(file_bytes)
    return f"{base_url.rstrip('/')}/uploads/{safe_bucket}/{rel_path}"

