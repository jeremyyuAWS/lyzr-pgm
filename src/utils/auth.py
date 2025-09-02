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
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"

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

def get_jwks():
    try:
        resp = requests.get(JWKS_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch JWKS: {e}")

def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)) -> UserClaims:
    """
    Decode a Supabase JWT from Authorization: Bearer <token> header
    and return typed user claims.
    """
    try:
        jwks = get_jwks()
        unverified_header = jwt.get_unverified_header(token.credentials)
        key = next((k for k in jwks["keys"] if k["kid"] == unverified_header["kid"]), None)
        if not key:
            raise HTTPException(status_code=401, detail="Auth failed: No matching JWK")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)

        payload = jwt.decode(
            token.credentials,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False}  # 👈 ignore audience mismatch
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
