# src/utils/auth.py

import os
import requests
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from jose.exceptions import JWTError

# -----------------------------
# Config
# -----------------------------
JWKS_URL = os.getenv("SUPABASE_JWKS_URL")
ALGORITHMS = ["RS256"]  # Supabase uses RS256 for signing

if not JWKS_URL:
    raise RuntimeError("❌ SUPABASE_JWKS_URL is not set in environment variables")

# Cache keys for performance
_jwks_cache = None


def _get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        try:
            resp = requests.get(JWKS_URL, timeout=10)
            resp.raise_for_status()
            _jwks_cache = resp.json()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch JWKS from {JWKS_URL}: {e}")
    return _jwks_cache


# -----------------------------
# Models
# -----------------------------
class UserClaims(BaseModel):
    sub: str
    email: str
    role: str


# -----------------------------
# Security Dependency
# -----------------------------
security = HTTPBearer(auto_error=True)


def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(security),
) -> UserClaims:
    """
    Decode and verify Supabase JWT using JWKS.
    """
    try:
        jwks = _get_jwks()
        payload = jwt.decode(
            token.credentials,
            jwks,
            algorithms=ALGORITHMS,
            options={"verify_aud": False},  # skip aud unless you enforce it
        )
        return UserClaims(**payload)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
