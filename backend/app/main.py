"""
FinTech Agent — FastAPI Application Entry Point
Configures middleware, exception handlers, and API routing.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.routes import api_router
from backend.app.config import settings
from backend.app.core.logging import logger

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Natural Language to Sandboxed MongoDB Query Agent for Banking Operations (Phase 2 LLM Shell)",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
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

    logger.warning(f"Validation failure on {request.url.path}: {error_msg}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": error_msg,
            "request_id": None,
        },
    )


@app.get("/")
async def root():
    """Root metadata endpoint."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "phase": "Phase 2 — LLM Connectivity & API Shell",
        "documentation": "/docs",
        "health": "/api/v1/health",
    }


# Mount API Routes
app.include_router(api_router)
