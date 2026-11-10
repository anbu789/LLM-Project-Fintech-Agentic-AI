"""
FinTech Agent — Application Configuration
Loaded from environment variables and .env file using Pydantic Settings.
Includes security validation, timeout constraints, and dual-database credential isolation.
"""

import urllib.parse
from typing import List, Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.core.exceptions import DatabaseCredentialsError


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

    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
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
    LLM_PROVIDER: str = Field(default="anthropic", description="LLM provider: mock, anthropic, openai, gemini, groq")
    LLM_MODEL: str = Field(default="claude-3-5-sonnet-20241022", description="LLM model identifier")
    LLM_API_KEY: Optional[str] = Field(default=None, description="LLM provider API key")
    LLM_API_BASE_URL: Optional[str] = Field(default=None, description="Custom base URL for OpenAI-compatible APIs")
    LLM_TIMEOUT_SECONDS: int = Field(default=30, description="LLM API timeout in seconds")

    # Chat API Limits
    MAX_MESSAGE_LENGTH: int = Field(default=2000, description="Maximum allowed chat message characters")

    # Query Execution & Safety Defaults
    QUERY_TIMEOUT_MS: int = Field(default=15000, description="Server-side query timeout in ms (maxTimeMS)")
    RESULT_DOC_LIMIT: int = Field(default=1000, description="Maximum documents returned to caller")
    DRY_RUN_RESULT_LIMIT: int = Field(default=10, description="Maximum documents returned for schedule dry-run")
    MAX_PIPELINE_STAGES: int = Field(default=20, description="Maximum allowed pipeline stages")
    MAX_PIPELINE_DEPTH: int = Field(default=10, description="Maximum allowed expression nesting depth")
    MAX_RETRY_ATTEMPTS: int = Field(default=3, description="Maximum agent retry attempts")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=30, description="Overall request deadline in seconds")

    # ChromaDB & Schema Vector Store Configuration (Phase 3)
    CHROMA_PERSIST_DIR: str = Field(default="./chroma_data", description="ChromaDB persistence directory")
    CHROMA_COLLECTION_NAME: str = Field(default="fintech_schema_catalog", description="ChromaDB collection name")
    EMBEDDING_PROVIDER: str = Field(default="mock", description="Embedding provider: mock, sentence-transformers, openai")
    EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2", description="Embedding model identifier")
    EMBEDDING_API_KEY: Optional[str] = Field(default=None, description="API key for external embedding provider")
    EMBEDDING_BATCH_SIZE: int = Field(default=32, description="Batch size for embedding generation")
    EMBEDDING_DIMENSION: int = Field(default=384, description="Expected embedding dimension (384 for MiniLM, 1536 for OpenAI)")
    SCHEMA_CATALOG_PATH: str = Field(default="backend/data/generated/schema_catalog.json", description="Path to generated schema catalog JSON")
    RETRIEVAL_TOP_K: int = Field(default=5, description="Default top-k documents to retrieve")

    # Scheduler (Placeholders for Phase 6)
    SCHEDULER_TIMEZONE: str = Field(default="Asia/Kolkata", description="Scheduler timezone")
    SCHEDULER_RECONCILE_INTERVAL_SECONDS: int = Field(default=30, description="Job reconciliation interval")

    @model_validator(mode="after")
    def validate_security_and_timeouts(self) -> "Settings":
        """Enforces timeout ranges, retry bounds, and credential isolation."""
        if self.QUERY_TIMEOUT_MS <= 0 or self.QUERY_TIMEOUT_MS > 120000:
            raise ValueError(f"QUERY_TIMEOUT_MS must be between 1 and 120000 ms, got {self.QUERY_TIMEOUT_MS}")

        if self.REQUEST_TIMEOUT_SECONDS <= 0 or self.REQUEST_TIMEOUT_SECONDS > 300:
            raise ValueError(f"REQUEST_TIMEOUT_SECONDS must be between 1 and 300 seconds, got {self.REQUEST_TIMEOUT_SECONDS}")

        if self.MAX_RETRY_ATTEMPTS < 0 or self.MAX_RETRY_ATTEMPTS > 10:
            raise ValueError(f"MAX_RETRY_ATTEMPTS must be between 0 and 10, got {self.MAX_RETRY_ATTEMPTS}")

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
