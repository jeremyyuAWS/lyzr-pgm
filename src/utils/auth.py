# src/utils/auth.py
import os
import requests
import jwt
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# -----------------------------
# Config
# -----------------------------
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")
if not SUPABASE_JWKS_URL:
    raise RuntimeError("SUPABASE_JWKS_URL must be set in environment variables")

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

# -----------------------------
# JWKS Cache
# -----------------------------
_jwks_cache = None

def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        resp = requests.get(SUPABASE_JWKS_URL, timeout=10)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache

def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)) -> UserClaims:
    """
    Decode a Supabase JWT from Authorization: Bearer <token> header.
    Auto-detects audience: tries 'authenticated', falls back to verify_aud=False.
    """
    try:
        jwks = get_jwks()
        unverified_header = jwt.get_unverified_header(token.credentials)
        key = next((k for k in jwks["keys"] if k["kid"] == unverified_header["kid"]), None)
        if not key:
            raise HTTPException(status_code=401, detail="Auth failed: No matching JWK")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)

        # Try strict audience first
        try:
            payload = jwt.decode(
                token.credentials,
                public_key,
                algorithms=["RS256"],
                audience="authenticated"
            )
        except jwt.InvalidAudienceError:
            # Fallback: disable audience verification
            payload = jwt.decode(
                token.credentials,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False}
            )

        return UserClaims(
            sub=payload.get("sub", ""),
            email=payload.get("email", ""),
            role=payload.get("role", "authenticated"),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
