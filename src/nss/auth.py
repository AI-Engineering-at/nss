"""JWT authentication and role-based access control.

Provides token creation/verification, a Starlette middleware for
request authentication, and a FastAPI dependency for role enforcement.
"""

from __future__ import annotations

import enum
import time
from typing import Any

import jwt
import structlog
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


class Role(enum.StrEnum):
    """RBAC roles for NSS."""
    ADMIN = "admin"
    DATA_PROCESSOR = "data_processor"
    VIEWER = "viewer"
    AUDITOR = "auditor"


def create_token(
    user_id: str,
    role: str,
    secret: str,
    expiry_minutes: int = 15,
) -> str:
    """Create a signed JWT.

    Args:
        user_id: Subject identifier.
        role: User role (admin, data_processor, viewer, auditor).
        secret: HMAC secret for signing.
        expiry_minutes: Token lifetime in minutes.

    Returns:
        Encoded JWT string.
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + expiry_minutes * 60,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str, secret: str) -> dict[str, Any]:
    """Verify and decode a JWT.

    Args:
        token: Encoded JWT string.
        secret: HMAC secret used for verification.

    Returns:
        Decoded payload dict.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is invalid.
    """
    return jwt.decode(token, secret, algorithms=["HS256"])


class JWTMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates JWT on protected routes.

    Skips validation for /health and /metrics endpoints.
    """

    def __init__(self, app: Any, secret: str) -> None:
        super().__init__(app)
        self._secret = secret

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        # Skip auth for health/metrics/docs endpoints
        path = request.url.path
        if path in ("/health", "/metrics", "/metrics/prometheus", "/docs", "/openapi.json"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header."},
            )

        token = auth_header[7:]
        try:
            payload = verify_token(token, self._secret)
            request.state.user_id = payload["sub"]
            request.state.role = payload["role"]
        except jwt.ExpiredSignatureError:
            return JSONResponse(status_code=401, content={"detail": "Token expired."})
        except jwt.InvalidTokenError:
            return JSONResponse(status_code=401, content={"detail": "Invalid token."})

        return await call_next(request)


def require_role(required_role: str):
    """FastAPI dependency that enforces a minimum role.

    Usage::

        @app.get("/admin", dependencies=[Depends(require_role("admin"))])
        async def admin_endpoint(): ...
    """
    async def _check(
        credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    ) -> dict[str, Any]:
        if not credentials:
            raise HTTPException(status_code=401, detail="Not authenticated.")

        from nss.config import config
        try:
            payload = verify_token(credentials.credentials, config.jwt_secret)
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        # Simple hierarchy: admin > data_processor > auditor > viewer
        hierarchy = {"admin": 4, "data_processor": 3, "auditor": 2, "viewer": 1}
        user_level = hierarchy.get(payload.get("role", ""), 0)
        required_level = hierarchy.get(required_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{payload.get('role')}' insufficient. Required: '{required_role}'.",
            )
        return payload

    return _check
