"""
FinTech Agent — Health Check Route
Provides basic service status without leaking configuration or credentials.
"""

from fastapi import APIRouter
from backend.app.config import settings
from backend.app.schemas.chat import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Returns application health status."""
    return HealthResponse(
        status="healthy",
        service="fintech-agent-api",
        version=settings.APP_VERSION
    )
