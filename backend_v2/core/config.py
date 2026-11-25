import os
import secrets
from pathlib import Path
from typing import List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=False)


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self) -> None:
        self.base_dir: Path = BASE_DIR
        raw_mode = os.environ.get("AUTH_MODE", "").strip().lower()
        if not raw_mode:
            # Fail closed: production unless AUTH_MODE=dev is explicitly configured
            self.auth_mode: str = "production"
        elif raw_mode in ("dev", "production"):
            self.auth_mode = raw_mode
        else:
            raise RuntimeError(
                f"Invalid AUTH_MODE='{raw_mode}'. Must be 'dev' or 'production' (fail-closed)."
            )

        # Demo reset features are disabled by default; opt-in only in dev
        self.sx_demo: bool = (
            self.auth_mode == "dev"
            and os.environ.get("SX_DEMO", "0").strip() == "1"
        )

        # Default to unified SQLite DB locally; IT swaps to postgresql+psycopg:// or mssql+pyodbc:// via DATABASE_URL
        default_sqlite = f"sqlite:///{(BASE_DIR / 'backend' / 'inspectflow.db').as_posix()}"
        self.database_url: str = os.environ.get("DATABASE_URL", default_sqlite).strip()

        # Persist a strong dev secret across restarts if none provided in env
        env_secret = os.environ.get("JWT_SECRET", "").strip()
        if env_secret:
            self.jwt_secret = env_secret
        elif self.auth_mode == "production":
            secret_file = BASE_DIR / "backend" / ".jwt_secret"
            if secret_file.exists():
                self.jwt_secret = secret_file.read_text(encoding="utf-8").strip()
            else:
                self.jwt_secret = secrets.token_urlsafe(48)
                secret_file.parent.mkdir(parents=True, exist_ok=True)
                secret_file.write_text(self.jwt_secret, encoding="utf-8")
                try:
                    os.chmod(secret_file, 0o600)
                except OSError:
                    pass
        else:
            secret_file = BASE_DIR / "backend" / ".jwt_secret"
            secret_file.parent.mkdir(parents=True, exist_ok=True)
            if secret_file.exists():
                self.jwt_secret = secret_file.read_text(encoding="utf-8").strip()
            else:
                self.jwt_secret = secrets.token_urlsafe(48)
                secret_file.write_text(self.jwt_secret, encoding="utf-8")
                try:
                    os.chmod(secret_file, 0o600)
                except OSError:
                    pass

        self.jwt_expire_hours: int = int(os.environ.get("JWT_EXPIRE_HOURS", "24"))
        self.gemini_api_key: str = (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("VITE_GEMINI_API_KEY")
            or ""
        ).strip()

        raw_origins = os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:5214,http://127.0.0.1:5214,http://localhost:5173,http://127.0.0.1:5173",
        )
        self.cors_origins: List[str] = [
            o.strip() for o in raw_origins.split(",") if o.strip()
        ]

        self.storage_root: Path = Path(
            os.environ.get("STORAGE_ROOT", str(BASE_DIR / "backend" / "wwwroot" / "uploads"))
        )
        self.upload_max_bytes: int = int(
            os.environ.get("UPLOAD_MAX_BYTES", str(50 * 1024 * 1024))
        )
        self.allowed_extensions = {
            ".pdf", ".png", ".jpg", ".jpeg", ".webp",
            ".xlsx", ".xls", ".csv", ".doc", ".docx", ".txt",
        }

        # Corporate OIDC / Entra ID placeholders (activated when AUTH_MODE=production)
        self.oidc_tenant_id: str = os.environ.get("OIDC_TENANT_ID", "").strip()
        self.oidc_client_id: str = os.environ.get("OIDC_CLIENT_ID", "").strip()


settings = Settings()
