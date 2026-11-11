"""
FinTech Agent — FastAPI Application Entry Point
Configures middleware (CORS, RequestBodyLimit), exception handlers, API routing,
and graceful lifespan management (MongoDB verification, ChromaDB readiness, clean shutdown).
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.routes import api_router
from backend.app.config import settings
from backend.app.core.execution_monitor import execution_monitor
from backend.app.core.logging import logger, sanitize_error_message
from backend.app.core.middleware import RequestBodyLimitMiddleware
from backend.app.schemas.chat import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application lifecycle: startup verification and graceful shutdown."""
    logger.info("Initializing FinTech Agent backend services...")
    execution_monitor.start()

    mongo_status = "unknown"
    mongo_version = None
    chroma_count = 0

    # 1. MongoDB connectivity verification
    try:
        from backend.app.db.mongo_client import check_mongo_connection
        conn_status = check_mongo_connection(timeout_ms=5000)
        mongo_status = conn_status.get("status", "unknown")
        mongo_version = conn_status.get("version")
        logger.info(f"MongoDB connection: status={mongo_status}, version={mongo_version}")
    except Exception as e:
        mongo_status = "error"
        logger.warning(f"MongoDB startup check warning: {e}")

    # 2. ChromaDB RAG store verification & auto-indexing
    try:
        from backend.app.rag.chroma_store import chroma_store
        from backend.app.rag.indexer import schema_indexer
        stats = chroma_store.get_stats()
        doc_count = stats.get("document_count", 0)
        chroma_count = doc_count
        logger.info(f"ChromaDB schema vector index: collection='{stats.get('collection_name')}', count={doc_count}")
        if doc_count == 0 and stats.get("status") != "error":
            logger.info("ChromaDB index is empty; triggering initial schema indexing...")
            schema_indexer.index_schema(force=False)
    except Exception as e:
        logger.warning(f"ChromaDB startup check warning: {e}")

    execution_monitor.emit(
        "BACKEND_STARTED",
        status="ONLINE",
        details={
            "port": settings.APP_PORT,
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "mongo_status": mongo_status,
            "mongo_version": mongo_version,
            "chroma_entries": chroma_count,
            "phase6_live_execution_enabled": settings.PHASE6_LIVE_EXECUTION_ENABLED,
            "phase7_scheduler_enabled": settings.PHASE7_SCHEDULER_ENABLED,
            "phase7_live_registration_enabled": settings.PHASE7_LIVE_REGISTRATION_ENABLED,
        },
    )

    yield

    # 3. Graceful shutdown
    logger.info("Shutting down FinTech Agent backend services...")
    execution_monitor.emit("BACKEND_SHUTDOWN", status="OFFLINE", details={"port": settings.APP_PORT})
    execution_monitor.shutdown(timeout=2.0)
    try:
        from backend.app.db.mongo_client import mongo_manager
        mongo_manager.close()
        logger.info("Closed MongoDB client connections.")
    except Exception as e:
        logger.warning(f"Error during shutdown: {e}")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Natural Language to Sandboxed MongoDB Query Agent for Banking Operations",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 1. Request Body Size Limiter Middleware
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_bytes=settings.MAX_REQUEST_BODY_BYTES
)

# 2. CORS Middleware with credentials safety
origins = settings.cors_origins_list
has_wildcard = "*" in origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if not has_wildcard else ["*"],
    allow_credentials=not has_wildcard,  # Wildcard cannot be used with credentials
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Formats validation errors into standardized ErrorResponse structure."""
    errors = exc.errors()
    first_error = errors[0] if errors else {}
    field = ".".join(str(loc) for loc in first_error.get("loc", []))
    msg = first_error.get("msg", "Invalid request payload.")
    error_msg = f"Validation error on '{field}': {msg}" if field else msg

    logger.warning(f"Validation failure on {request.url.path}: {sanitize_error_message(error_msg)}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": error_msg,
            "request_id": None,
        },
    )


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def root_health():
    """Top-level health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="fintech-agent-api",
        version=settings.APP_VERSION,
    )


@app.get("/")
async def root():
    """Root metadata endpoint."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "phase": "FinTech Agent Production-Hardened Agentic System",
        "documentation": "/docs",
        "health": "/api/v1/health",
        "root_health": "/health",
    }


# Mount API Routes
app.include_router(api_router)
