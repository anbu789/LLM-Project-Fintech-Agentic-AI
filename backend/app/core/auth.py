"""
FinTech Agent — Cryptographic Authentication & Tenant Isolation Module
Provides HMAC-SHA256 signed Bearer token generation, verification, and FastAPI
dependencies to establish trusted authenticated principals and enforce strict
server-side tenant isolation, eliminating caller-controlled identity spoofing.
"""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, List, Optional
from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.core.logging import logger

_http_bearer_scheme = HTTPBearer(auto_error=False)


def _b64_encode(data: bytes) -> str:
    """Encodes bytes to unpadded URL-safe base64 string."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_decode(data: str) -> bytes:
    """Decodes unpadded URL-safe base64 string to bytes."""
    pad = len(data) % 4
    if pad:
        data += "=" * (4 - pad)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


class AuthenticatedUser(BaseModel):
    """Immutable trusted principal extracted from validated cryptographic token."""
    user_id: str = Field(..., description="Unique authenticated user identifier")
    role: str = Field(default="analyst", description="User authorization role (analyst, compliance, admin)")
    scopes: List[str] = Field(default_factory=lambda: ["schedules:read", "schedules:write"])
    issued_at: int = Field(..., description="UTC epoch seconds when token was issued")
    expires_at: int = Field(..., description="UTC epoch seconds when token expires")


class TokenManager:
    """Issues and verifies cryptographically signed HMAC-SHA256 tokens."""

    def __init__(self, secret_key: Optional[str] = None):
        self._secret = secret_key or getattr(settings, "JWT_SECRET_KEY", None) or "fintech_agent_secure_hmac_default_secret_key_32bytes"

    def create_access_token(
        self,
        user_id: str,
        role: str = "analyst",
        expires_delta: Optional[timedelta] = None,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """Constructs an HMAC-SHA256 signed Bearer token."""
        if not user_id or not user_id.strip():
            raise ValueError("user_id cannot be empty.")

        now = int(time.time())
        if expires_delta:
            exp = now + int(expires_delta.total_seconds())
        else:
            exp_minutes = getattr(settings, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 60)
            exp = now + (exp_minutes * 60)

        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": user_id.strip(),
            "role": role,
            "scopes": scopes or ["schedules:read", "schedules:write"],
            "iat": now,
            "exp": exp,
            "nonce": secrets.token_hex(8),
        }

        h_b64 = _b64_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        p_b64 = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{h_b64}.{p_b64}"

        signature = hmac.new(self._secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
        sig_b64 = _b64_encode(signature)

        return f"{signing_input}.{sig_b64}"

    def verify_token(self, token: str) -> AuthenticatedUser:
        """Verifies HMAC signature, checks expiration, and extracts trusted principal."""
        if not token or not token.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is missing or empty.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        parts = token.strip().split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed authentication token structure.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        h_b64, p_b64, sig_b64 = parts
        signing_input = f"{h_b64}.{p_b64}"
        expected_sig = hmac.new(self._secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
        expected_sig_b64 = _b64_encode(expected_sig)

        if not hmac.compare_digest(expected_sig_b64, sig_b64):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature. Token has been tampered with or revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload_bytes = _b64_decode(p_b64)
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not parse token payload.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        now = int(time.time())
        exp = payload.get("exp", 0)
        if now > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token has expired at {exp} (current time {now}).",
                headers={"WWW-Authenticate": "Bearer"},
            )

        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing 'sub' subject claim.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return AuthenticatedUser(
            user_id=sub,
            role=payload.get("role", "analyst"),
            scopes=payload.get("scopes", []),
            issued_at=payload.get("iat", now),
            expires_at=exp,
        )


auth_manager = TokenManager()


async def get_current_authenticated_user(
    auth_creds: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer_scheme),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    user_id_query: Optional[str] = Query(None, alias="user_id"),
) -> AuthenticatedUser:
    """Enforces authentication and prevents caller-controlled identity impersonation.

    Rules:
      1. A valid cryptographic Bearer token MUST be provided.
      2. If caller also sends 'X-User-ID' or 'user_id' query, it MUST match the token principal.
         Any mismatch is immediately flagged and rejected as an identity spoofing attack (403).
      3. No fallback to a default user or unauthenticated caller.
    """
    token = auth_creds.credentials if auth_creds else None

    # In development/test mode, if no bearer token is sent but dev credentials or mock headers are used:
    if not token:
        # Check if caller tried to spoof identity via header alone without a token
        if x_user_id or user_id_query:
            logger.warning(
                f"Unauthorized identity assertion rejected: Caller attempted to use "
                f"header/query user '{x_user_id or user_id_query}' without a valid Bearer token."
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication credentials required. Unsigned identity headers are rejected.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials. Please provide 'Authorization: Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate cryptographic signature and expiration
    user = auth_manager.verify_token(token)

    # Identity Spoofing Defense: If caller passed X-User-ID or query user_id, ensure it matches token!
    caller_asserted = (x_user_id or user_id_query or "").strip()
    if caller_asserted and caller_asserted != user.user_id:
        logger.error(
            f"SECURITY ALERT — Identity spoofing attempt detected! Authenticated principal '{user.user_id}' "
            f"attempted to impersonate '{caller_asserted}' via request header/query."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Identity spoofing violation: Asserted user '{caller_asserted}' does not match "
                f"authenticated token principal '{user.user_id}'."
            ),
        )

    return user
