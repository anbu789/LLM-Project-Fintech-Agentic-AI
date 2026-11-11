"""
FinTech Agent — Application Configuration
Loaded from environment variables and .env file using Pydantic Settings.
Includes security validation, timeout constraints, dual-database credential isolation,
and centralized project root path resolution.
"""

from pathlib import Path
import urllib.parse
from typing import List, Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.core.exceptions import DatabaseCredentialsError

# Centralized project root resolution (independent of process CWD)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application
    APP_ENV: str = Field(default="development", description="Application environment")
    APP_NAME: str = Field(default="FinTech Agent API", description="Application name")
    APP_VERSION: str = Field(default="1.0.0", description="API version")
    APP_PORT: int = Field(default=8001, description="Application server port")

    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:8001,http://127.0.0.1:8001",
        description="Comma-separated allowed origins"
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # MongoDB Base & Security Configuration
    MONGO_URI: str = Field(default="mongodb://localhost:27017/", description="Base MongoDB connection URI")
    MONGO_BANKING_DB: str = Field(default="fintech_agent_db", description="Banking dataset database name")
    MONGO_METADATA_DB: str = Field(default="agent_metadata_db", description="Agent metadata database name")

    MONGO_AUTH_ENABLED: bool = Field(
        default=False,
        description="Whether server-side MongoDB authentication is strictly enforced"
    )
    MONGO_NATIVE_AUTH_VERIFIED: bool = Field(
        default=False,
        description="Whether native MongoDB server-side authentication has been explicitly verified"
    )
    ALLOW_UNAUTHENTICATED_DEV: bool = Field(
        default=True,
        description="Explicit flag allowing unauthenticated local development"
    )
    MONGO_AUTH_SOURCE: Optional[str] = Field(
        default=None,
        description="Target authentication database (e.g., admin or fintech_agent_db)"
    )

    # Dedicated Read-Only Banking Database Credentials
    MONGO_READONLY_USERNAME: Optional[str] = Field(
        default=None,
        description="Dedicated read-only banking DB user (role: read on fintech_agent_db)"
    )
    MONGO_READONLY_PASSWORD: Optional[str] = Field(
        default=None,
        description="Read-only banking DB user password"
    )

    # Application Metadata Database Credentials (readWrite on agent_metadata_db)
    MONGO_METADATA_USERNAME: Optional[str] = Field(
        default=None,
        description="Application metadata DB user (role: readWrite on agent_metadata_db)"
    )
    MONGO_METADATA_PASSWORD: Optional[str] = Field(
        default=None,
        description="Metadata DB user password"
    )

    # LLM Provider Configuration
    LLM_PROVIDER: str = Field(default="gemini", description="LLM provider: mock, anthropic, openai, gemini, groq, ollama")
    LLM_MODEL: str = Field(default="claude-3-5-sonnet-20241022", description="LLM model identifier")
    LLM_API_KEY: Optional[str] = Field(default=None, description="Generic fallback LLM API key")
    LLM_API_BASE_URL: Optional[str] = Field(default=None, description="Custom base URL for OpenAI-compatible APIs")
    LLM_TIMEOUT_SECONDS: int = Field(default=30, description="Legacy per-provider timeout ceiling in seconds")
    LLM_ATTEMPT_TIMEOUT_SECONDS: float = Field(default=12.0, description="Per-attempt HTTP timeout ceiling for LLM calls in seconds")
    LLM_MAX_ATTEMPTS: int = Field(default=2, description="Maximum total attempts per LLM provider call (initial attempt + at most 1 retry)")
    LLM_RETRY_BASE_DELAY_SECONDS: float = Field(default=0.8, description="Base exponential backoff delay for retryable LLM errors in seconds")
    LLM_RETRY_MAX_DELAY_SECONDS: float = Field(default=1.5, description="Maximum backoff delay between retryable LLM attempts in seconds")
    LLM_OPERATION_TIMEOUT_SECONDS: float = Field(default=24.0, description="Total deadline across all retries for one LLM operation in seconds")
    LLM_MIN_RETRY_BUDGET_SECONDS: float = Field(default=4.0, description="Minimum remaining operation budget in seconds required to permit a retry attempt")
    LLM_ATTEMPT_RESERVE_SECONDS: float = Field(default=1.0, description="Reserve buffer in seconds kept at operation deadline boundary for cleanup and error delivery")

    # Provider-Specific API Keys (Isolated Credentials)
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Dedicated Anthropic API key")
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="Dedicated OpenAI API key")
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Dedicated Gemini/Google API key")
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Dedicated Groq API key")

    # Groq Fallback Provider Configuration
    GROQ_MODEL: str = Field(default="openai/gpt-oss-120b", description="Default Groq model identifier")
    GROQ_BASE_URL: str = Field(default="https://api.groq.com/openai/v1", description="Groq API base URL")

    # Local Ollama Fallback Provider Configuration
    OLLAMA_ENABLED: bool = Field(default=True, description="Enable local Ollama fallback provider")
    OLLAMA_BASE_URL: str = Field(default="http://127.0.0.1:11434", description="Local Ollama server base URL")
    OLLAMA_MODEL: str = Field(
        default="hf.co/mradermacher/K2-Horizon-3.7B-i1-GGUF:Q3_K_M",
        description="Local Ollama model identifier",
    )

    # Multi-Provider Fallback Orchestration
    LLM_FALLBACK_ENABLED: bool = Field(default=True, description="Enable multi-provider LLM fallback chain")
    LLM_FALLBACK_ORDER: str = Field(default="groq,ollama", description="Comma-separated secondary provider fallback order")

    @property
    def llm_fallback_order_list(self) -> List[str]:
        """Parsed list of fallback providers in sequence (e.g. ['groq', 'ollama'])."""
        return [p.strip().lower() for p in self.LLM_FALLBACK_ORDER.split(",") if p.strip()]

    def get_provider_api_key(self, provider: str) -> Optional[str]:
        """Resolves provider-specific API key, falling back to LLM_API_KEY if unset."""
        prov = provider.lower().strip()
        if prov == "anthropic":
            return self.ANTHROPIC_API_KEY or self.LLM_API_KEY
        elif prov == "openai":
            return self.OPENAI_API_KEY or self.LLM_API_KEY
        elif prov in {"gemini", "google"}:
            return self.GEMINI_API_KEY or self.LLM_API_KEY
        elif prov == "groq":
            return self.GROQ_API_KEY
        elif prov == "ollama":
            return None
        return self.LLM_API_KEY

    # Chat API Limits & Security
    MAX_MESSAGE_LENGTH: int = Field(default=2000, description="Maximum allowed chat message characters")
    MAX_REQUEST_BODY_BYTES: int = Field(default=1_048_576, description="Max allowed HTTP request body in bytes (1MB)")
    USER_RATE_LIMIT: int = Field(default=60, description="Max allowed requests per minute per IP")
    USER_LLM_BUDGET: int = Field(default=100000, description="Token/character budget for LLM calls")
    MAX_CONVERSATION_HISTORY_TURNS: int = Field(default=10, description="Max conversation turns passed to LLM context")

    # Query Execution & Safety Defaults
    QUERY_TIMEOUT_MS: int = Field(default=15000, description="Server-side query timeout in ms (maxTimeMS)")
    RESULT_DOC_LIMIT: int = Field(default=1000, description="Maximum documents returned to caller")
    DRY_RUN_RESULT_LIMIT: int = Field(default=10, description="Maximum documents returned for schedule dry-run")
    MAX_PIPELINE_STAGES: int = Field(default=20, description="Maximum allowed pipeline stages")
    MAX_PIPELINE_DEPTH: int = Field(default=10, description="Maximum allowed expression nesting depth")
    MAX_LOOKUP_RESULTS_PER_DOCUMENT: int = Field(default=100, description="Max allowed documents per parent in $lookup joins")
    MAX_RESULT_BYTES: int = Field(default=5242880, description="Max allowed execution result size in bytes (5MB)")
    MAX_RESULT_NESTING_DEPTH: int = Field(default=10, description="Max allowed document/expression nesting depth")
    PHASE6_LIVE_EXECUTION_ENABLED: bool = Field(default=False, description="Fail-closed execution gate for Phase 6 live queries")
    MAX_RETRY_ATTEMPTS: int = Field(default=3, description="Maximum agent retry attempts")
    QUERY_MAX_RETRY_ATTEMPTS: int = Field(default=0, description="Maximum database execution retries for API chat requests (0 enforces at-most-once execution)")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=30, description="Overall request deadline in seconds")
    BACKEND_PROCESSING_RESERVE_SECONDS: float = Field(default=4.0, description="Time reserved inside REQUEST_TIMEOUT_SECONDS for non-LLM stages and error response delivery")

    # Execution Monitor Configuration (Local Rotating JSONL Stream)
    MONITORING_ENABLED: bool = Field(default=True, description="Enable non-blocking local JSONL execution monitoring")
    MONITORING_LOG_PATH: str = Field(
        default=str(PROJECT_ROOT / "logs" / "execution_events.jsonl"),
        description="Local filesystem path for execution monitor JSONL events",
    )
    MONITORING_QUEUE_MAX_SIZE: int = Field(default=2048, description="Bounded async-safe monitoring event queue size")
    MONITORING_LOG_MAX_BYTES: int = Field(default=5_242_880, description="Maximum size in bytes per monitor log file before rotation")
    MONITORING_LOG_BACKUP_COUNT: int = Field(default=5, description="Number of rotated monitor log backup files to retain")
    MONITORING_LOG_FULL_QUERY: bool = Field(default=False, description="When False (default), store privacy-safe redacted/truncated query summaries instead of full user text")

    # ChromaDB & Schema Vector Store Configuration (Phase 3)
    CHROMA_PERSIST_DIR: str = Field(
        default=str(PROJECT_ROOT / "chroma_data"),
        description="Absolute ChromaDB persistence directory"
    )
    CHROMA_COLLECTION_NAME: str = Field(default="fintech_schema_catalog_cosine", description="ChromaDB collection name")
    EMBEDDING_PROVIDER: str = Field(default="mock", description="Embedding provider: mock, sentence-transformers, openai")
    EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2", description="Embedding model identifier")
    EMBEDDING_API_KEY: Optional[str] = Field(default=None, description="API key for external embedding provider")
    EMBEDDING_BATCH_SIZE: int = Field(default=32, description="Batch size for embedding generation")
    EMBEDDING_DIMENSION: int = Field(default=384, description="Expected embedding dimension (384 for MiniLM, 1536 for OpenAI)")
    SCHEMA_SOURCE_PATH: str = Field(
        default=str(PROJECT_ROOT / "fintech-agent" / "data" / "schema.json"),
        description="Path to original source schema.json"
    )
    SCHEMA_CATALOG_PATH: str = Field(
        default=str(PROJECT_ROOT / "backend" / "data" / "generated" / "schema_catalog.json"),
        description="Path to generated schema catalog JSON"
    )
    RETRIEVAL_TOP_K: int = Field(default=5, description="Default top-k documents to retrieve")

    # Scheduler & Jobs (Phase 7)
    SCHEDULER_TIMEZONE: str = Field(default="Asia/Kolkata", description="Scheduler timezone")
    SCHEDULER_RECONCILE_INTERVAL_SECONDS: int = Field(default=30, description="Job reconciliation interval")
    SCHEDULER_MAX_INSTANCES: int = Field(default=1, description="Max concurrent scheduler instances")
    JOB_MAX_CONSECUTIVE_FAILURES: int = Field(default=3, description="Max consecutive job execution failures")
    PHASE7_SCHEDULER_ENABLED: bool = Field(default=False, description="Fail-closed gate for background APScheduler runner")
    PHASE7_LIVE_REGISTRATION_ENABLED: bool = Field(default=False, description="Fail-closed gate for live persistent job registration")
    PHASE7_FAILURE_THRESHOLD: int = Field(default=3, description="Consecutive failure threshold before auto-pause")
    PHASE7_DRY_RUN_RESULT_LIMIT: int = Field(default=10, description="Maximum documents returned for schedule dry-run preview")

    # Authentication & JWT Configuration
    JWT_SECRET_KEY: str = Field(default="dev_jwt_secret_key_minimum_32_chars_long_12345", description="JWT secret key")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Access token expiration minutes")
    JWT_REFRESH_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, description="Refresh token expiration minutes")

    # Notification & Delivery
    SMTP_HOST: Optional[str] = Field(default=None, description="SMTP server host")
    SMTP_PORT: int = Field(default=587, description="SMTP server port")
    SMTP_USER: Optional[str] = Field(default=None, description="SMTP username")
    SMTP_PASS: Optional[str] = Field(default=None, description="SMTP password")
    ALERT_RECIPIENT_EMAIL: Optional[str] = Field(default=None, description="Alert recipient email address")

    @model_validator(mode="after")
    def validate_security_and_timeouts(self) -> "Settings":
        """Enforces timeout ranges, retry bounds, CORS safety, credential isolation, and production safeguards."""
        if self.QUERY_TIMEOUT_MS <= 0 or self.QUERY_TIMEOUT_MS > 120000:
            raise ValueError(f"QUERY_TIMEOUT_MS must be between 1 and 120000 ms, got {self.QUERY_TIMEOUT_MS}")

        if self.REQUEST_TIMEOUT_SECONDS <= 0 or self.REQUEST_TIMEOUT_SECONDS > 300:
            raise ValueError(f"REQUEST_TIMEOUT_SECONDS must be between 1 and 300 seconds, got {self.REQUEST_TIMEOUT_SECONDS}")

        if self.MAX_RETRY_ATTEMPTS < 0 or self.MAX_RETRY_ATTEMPTS > 10:
            raise ValueError(f"MAX_RETRY_ATTEMPTS must be between 0 and 10, got {self.MAX_RETRY_ATTEMPTS}")

        if self.LLM_ATTEMPT_TIMEOUT_SECONDS <= 0 or self.LLM_ATTEMPT_TIMEOUT_SECONDS > 120:
            raise ValueError(f"LLM_ATTEMPT_TIMEOUT_SECONDS must be between 0 and 120, got {self.LLM_ATTEMPT_TIMEOUT_SECONDS}")

        if self.LLM_MAX_ATTEMPTS < 1 or self.LLM_MAX_ATTEMPTS > 10:
            raise ValueError(f"LLM_MAX_ATTEMPTS must be between 1 and 10, got {self.LLM_MAX_ATTEMPTS}")

        if self.LLM_RETRY_BASE_DELAY_SECONDS < 0 or self.LLM_RETRY_MAX_DELAY_SECONDS < self.LLM_RETRY_BASE_DELAY_SECONDS:
            raise ValueError("Invalid LLM retry backoff delay configuration.")

        if self.LLM_OPERATION_TIMEOUT_SECONDS <= 0 or self.LLM_OPERATION_TIMEOUT_SECONDS > 300:
            raise ValueError(f"LLM_OPERATION_TIMEOUT_SECONDS must be between 0 and 300, got {self.LLM_OPERATION_TIMEOUT_SECONDS}")

        if self.BACKEND_PROCESSING_RESERVE_SECONDS < 0 or self.BACKEND_PROCESSING_RESERVE_SECONDS > 60:
            raise ValueError("BACKEND_PROCESSING_RESERVE_SECONDS must be between 0 and 60.")

        if self.QUERY_MAX_RETRY_ATTEMPTS < 0 or self.QUERY_MAX_RETRY_ATTEMPTS > 5:
            raise ValueError(f"QUERY_MAX_RETRY_ATTEMPTS must be between 0 and 5, got {self.QUERY_MAX_RETRY_ATTEMPTS}")

        if self.MONITORING_QUEUE_MAX_SIZE < 16:
            raise ValueError("MONITORING_QUEUE_MAX_SIZE must be at least 16.")

        if self.MONITORING_LOG_MAX_BYTES < 1024:
            raise ValueError("MONITORING_LOG_MAX_BYTES must be at least 1024 bytes.")

        if self.MONITORING_LOG_BACKUP_COUNT < 1:
            raise ValueError("MONITORING_LOG_BACKUP_COUNT must be at least 1.")

        # Check CORS configuration
        origins = self.cors_origins_list
        if "*" in origins and len(origins) > 1:
            raise ValueError("Wildcard '*' cannot be combined with explicit origins in CORS_ORIGINS.")

        # Production Environment Enforcements
        if self.APP_ENV == "production":
            if self.ALLOW_UNAUTHENTICATED_DEV:
                raise ValueError("ALLOW_UNAUTHENTICATED_DEV must be False in production environment.")
            if not self.MONGO_AUTH_ENABLED:
                raise ValueError("MONGO_AUTH_ENABLED must be True in production environment.")
            if not (self.MONGO_READONLY_USERNAME and self.MONGO_READONLY_PASSWORD):
                raise ValueError("Dedicated read-only banking credentials are required in production environment.")
            if not (self.MONGO_METADATA_USERNAME and self.MONGO_METADATA_PASSWORD):
                raise ValueError("Application metadata DB credentials are required in production environment.")
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY.startswith("dev_"):
                raise ValueError("JWT_SECRET_KEY must be a secure production key (not dev default).")

        # Server-side authentication validation
        if self.MONGO_AUTH_ENABLED:
            ro_user = (self.MONGO_READONLY_USERNAME or "").strip()
            ro_pass = (self.MONGO_READONLY_PASSWORD or "").strip()
            meta_user = (self.MONGO_METADATA_USERNAME or "").strip()
            meta_pass = (self.MONGO_METADATA_PASSWORD or "").strip()

            if not ro_user or not ro_pass:
                raise ValueError("MONGO_AUTH_ENABLED is True, but MONGO_READONLY_USERNAME or MONGO_READONLY_PASSWORD is not configured.")

            if not meta_user or not meta_pass:
                raise ValueError("MONGO_AUTH_ENABLED is True, but MONGO_METADATA_USERNAME or MONGO_METADATA_PASSWORD is not configured.")

            if ro_user == meta_user:
                raise ValueError(
                    f"Least-privilege violation: Banking read-only user and metadata user cannot share "
                    f"the same username ('{ro_user}'). Separate identities are required."
                )
        elif not self.ALLOW_UNAUTHENTICATED_DEV:
            raise ValueError(
                "Unauthenticated MongoDB access is disallowed when ALLOW_UNAUTHENTICATED_DEV=False. "
                "Enable MONGO_AUTH_ENABLED=True or ALLOW_UNAUTHENTICATED_DEV=True for development."
            )

        return self

    def _build_authenticated_uri(self, username: Optional[str], password: Optional[str], target_db: str) -> str:
        """Constructs an authenticated connection URI with authSource parameter."""
        user = (username or "").strip()
        pwd = (password or "").strip()
        if not user or not pwd:
            raise DatabaseCredentialsError(
                f"Missing required authentication credentials for database '{target_db}'."
            )

        parsed = urllib.parse.urlsplit(self.MONGO_URI)
        host = parsed.netloc or parsed.path.lstrip("/")

        query_parts = []
        if parsed.query:
            query_parts.append(parsed.query)

        auth_source = self.MONGO_AUTH_SOURCE or target_db
        query_parts.append(f"authSource={urllib.parse.quote_plus(auth_source)}")
        qs = "&".join(query_parts)

        user_enc = urllib.parse.quote_plus(user)
        pwd_enc = urllib.parse.quote_plus(pwd)
        return f"mongodb://{user_enc}:{pwd_enc}@{host}/{target_db}?{qs}"

    def get_banking_uri(self) -> str:
        """Construct URI for banking DB, strictly using read-only credentials when configured."""
        if self.MONGO_AUTH_ENABLED:
            return self._build_authenticated_uri(
                self.MONGO_READONLY_USERNAME,
                self.MONGO_READONLY_PASSWORD,
                self.MONGO_BANKING_DB
            )
        if self.MONGO_READONLY_USERNAME and self.MONGO_READONLY_PASSWORD:
            return self._build_authenticated_uri(
                self.MONGO_READONLY_USERNAME,
                self.MONGO_READONLY_PASSWORD,
                self.MONGO_BANKING_DB
            )
        if not self.ALLOW_UNAUTHENTICATED_DEV:
            raise DatabaseCredentialsError("Unauthenticated access to banking DB is prohibited.")
        return self.MONGO_URI

    def get_metadata_uri(self) -> str:
        """Construct URI for metadata DB, using dedicated metadata credentials when configured."""
        if self.MONGO_AUTH_ENABLED:
            return self._build_authenticated_uri(
                self.MONGO_METADATA_USERNAME,
                self.MONGO_METADATA_PASSWORD,
                self.MONGO_METADATA_DB
            )
        if self.MONGO_METADATA_USERNAME and self.MONGO_METADATA_PASSWORD:
            return self._build_authenticated_uri(
                self.MONGO_METADATA_USERNAME,
                self.MONGO_METADATA_PASSWORD,
                self.MONGO_METADATA_DB
            )
        if not self.ALLOW_UNAUTHENTICATED_DEV:
            raise DatabaseCredentialsError("Unauthenticated access to metadata DB is prohibited.")
        return self.MONGO_URI


settings = Settings()
