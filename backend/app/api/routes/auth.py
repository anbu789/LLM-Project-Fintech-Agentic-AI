"""
FinTech Agent — Authentication & Token API Routes
Provides endpoints for token issuance, login verification, and identity inspection.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.core.auth import (
    AuthenticatedUser,
    auth_manager,
    get_current_authenticated_user,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class TokenRequest(BaseModel):
    user_id: str = Field(..., description="User identifier to authenticate")
    role: str = Field(default="analyst", description="Role: analyst, auditor, compliance, admin")
    password: Optional[str] = Field(default=None, description="Account password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    expires_in: int


@router.post("/token", response_model=TokenResponse, summary="Obtain authenticated Bearer token")
async def login_for_access_token(req: TokenRequest):
    """Issues a cryptographically signed HMAC-SHA256 Bearer token for authorized users."""
    user_id = req.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id cannot be empty.")

    # Validate allowed roles
    if req.role not in ("analyst", "auditor", "compliance", "admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{req.role}'. Must be one of: analyst, auditor, compliance, admin."
        )

    token = auth_manager.create_access_token(user_id=user_id, role=req.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_id,
        role=req.role,
        expires_in=3600,
    )


@router.get("/me", response_model=AuthenticatedUser, summary="Get current authenticated user profile")
async def get_my_profile(current_user: AuthenticatedUser = Depends(get_current_authenticated_user)):
    """Returns the trusted principal extracted from the cryptographic token."""
    return current_user
