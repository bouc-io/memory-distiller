"""
Minimal bouc.io platform-admin gate for the prompt-inspection endpoints.

This service had no authentication at all: ``/v1/distill``, ``/health`` and ``/metrics``
are open, and the ``Authorization`` header is only ever passed through to downstream APIs.
Those endpoints are unchanged. This module exists solely so the new prompt endpoints are
not open, because prompt text includes the injection-defense and worthiness rules.

Mirrors memory-api-server's ``auth.middleware.ts``: the token is **decoded, not verified**.
Signature validation happens at the edge (Istio + oauth2-proxy), which is the same trust
assumption the other services make. This is therefore a defence-in-depth check, not the
primary boundary.

Gate is any bouc.io staff role. Deliberately not the wider admin-portal set, which also
includes ``org_admin`` and ``org_admin_enterprise``: those are customer administrators, and
prompt text carries the worthiness and injection-defense rules.
"""

import logging

import jwt
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

# Mirrors BOUC_ROLES in the Node services' src/lib/roles.ts. Kept as a literal list rather
# than imported, because this service shares no code with them by design.
BOUC_ROLES = (
    "bouc_admin",
    "bouc_finance",
    "bouc_ops",
    "bouc_engineer",
    "bouc_sre",
    "bouc_user",
)


def _extract_bearer(authorization: str | None) -> str | None:
    """Pull the bearer token out, tolerating a comma-joined Authorization header."""
    if not authorization:
        return None
    for part in (p.strip() for p in authorization.split(",")):
        if part.startswith("Bearer "):
            token = part[len("Bearer ") :].strip()
            return token or None
    return None


def require_bouc_staff(
    authorization: str | None = Header(None),
    x_auth_request_roles: str | None = Header(None),
) -> str:
    """
    FastAPI dependency. Returns the caller's username, or raises 401/403.

    Roles come from the JWT's ``realm_access.roles``, falling back to the
    ``x-auth-request-roles`` header injected by oauth2-proxy, matching the other services.
    """
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "UNAUTHORIZED",
                "message": "Missing or invalid bearer token.",
            },
        )

    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:  # noqa: BLE001 - any decode failure is a 401
        logger.warning(f"Failed to decode bearer token: {exc}")
        raise HTTPException(
            status_code=401,
            detail={"error_code": "UNAUTHORIZED", "message": "Malformed bearer token."},
        ) from exc

    username = claims.get("preferred_username") or claims.get("sub")
    if not username:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "UNAUTHORIZED",
                "message": "Token carries no subject.",
            },
        )

    roles = (claims.get("realm_access") or {}).get("roles")
    if not roles:
        roles = [r for r in (x_auth_request_roles or "").split(",") if r]

    if not any(r in BOUC_ROLES for r in roles):
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "FORBIDDEN",
                "message": "Requires a bouc.io staff role.",
            },
        )

    return str(username)
