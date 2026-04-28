"""
Firebase auth dependency for the FastAPI server.

The Firebase Admin SDK is initialized lazily using Application Default
Credentials, so IT/infra can plug in a real Firebase deployment by pointing
GOOGLE_APPLICATION_CREDENTIALS at a service-account JSON (or by relying on
workload identity in GKE). No credential paths are hardcoded here.

Env vars:
- AUTH_DISABLED=true       Skip verification entirely. Local dev only.
- AUTH_ALLOWED_DOMAIN      Required email domain (default: temporal.io).
- FIREBASE_PROJECT_ID      Firebase project ID. Required for token verification
                           when running without a service-account JSON (local dev).
                           In prod with GOOGLE_APPLICATION_CREDENTIALS set, the
                           project ID is read from the JSON automatically.
- GOOGLE_APPLICATION_CREDENTIALS  Picked up by firebase_admin automatically.
"""

import os
from pathlib import Path
from typing import Optional

import firebase_admin
from fastapi import Header, HTTPException, status
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials as firebase_credentials

_initialized = False


def _ensure_firebase_initialized() -> None:
    """
    Initialize the Firebase Admin SDK.

    Two supported modes:
    1. Service-account credentials: GOOGLE_APPLICATION_CREDENTIALS points at a
       readable JSON file. Project ID is read from the JSON. (Production.)
    2. Anonymous (token verification only): FIREBASE_PROJECT_ID is set.
       The SDK fetches Google's public signing keys to verify ID tokens; no
       credentials file required. (Local dev.)

    A misconfigured GOOGLE_APPLICATION_CREDENTIALS (path doesn't exist) is
    treated as "not set" so we can fall through to mode 2.
    """
    global _initialized
    if _initialized:
        return
    if firebase_admin._apps:
        _initialized = True
        return

    raw_cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    project_id = os.getenv("FIREBASE_PROJECT_ID")

    print(
        f"[auth] env: GOOGLE_APPLICATION_CREDENTIALS={raw_cred_path!r} "
        f"FIREBASE_PROJECT_ID={project_id!r} cwd={os.getcwd()!r}"
    )

    # Resolve a relative cred path against the project root so the file is
    # found regardless of where uvicorn was launched from. Project root is
    # the parent of `ui/` (this file lives at ui/backend/auth.py).
    cred_path: Optional[str] = None
    if raw_cred_path:
        p = Path(raw_cred_path)
        if not p.is_absolute():
            project_root = Path(__file__).resolve().parent.parent.parent
            p = project_root / p
        cred_path = str(p)

    if cred_path and Path(cred_path).is_file():
        cred = firebase_credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print(f"[auth] Firebase initialized with service account: {cred_path}")
    elif project_id:
        if raw_cred_path:
            print(
                f"[auth] WARNING: GOOGLE_APPLICATION_CREDENTIALS={raw_cred_path!r} "
                f"resolved to {cred_path!r} but no such file. "
                f"Falling back to project-ID-only verification."
            )
        firebase_admin.initialize_app(options={"projectId": project_id})
        print(f"[auth] Firebase initialized with project ID only: {project_id}")
    else:
        raise RuntimeError(
            f"Firebase auth is not configured. "
            f"GOOGLE_APPLICATION_CREDENTIALS={raw_cred_path!r} "
            f"(resolved to {cred_path!r}) and FIREBASE_PROJECT_ID is unset. "
            f"Set one, or set AUTH_DISABLED=true to bypass."
        )

    _initialized = True


async def verify_firebase_user(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """FastAPI dependency. Returns the decoded Firebase token on success."""
    if os.getenv("AUTH_DISABLED", "").lower() == "true":
        return {"email": "dev@local", "uid": "dev", "auth_disabled": True}

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1].strip()

    try:
        _ensure_firebase_initialized()
        decoded = firebase_auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Firebase ID token: {exc}",
        )

    if not decoded.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified",
        )

    email = (decoded.get("email") or "").lower()
    allowed_domain = os.getenv("AUTH_ALLOWED_DOMAIN", "temporal.io").lower()
    if not email.endswith("@" + allowed_domain):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access restricted to @{allowed_domain} accounts",
        )

    return decoded
