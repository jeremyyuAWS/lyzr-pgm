# src/utils/auth.py

import os
import httpx
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from jose.exceptions import JWTError

JWKS_URL = os.getenv("SUPABASE_JWKS_URL")  # https://<project>.supabase.co/auth/v1/jwks
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")  # Set in Render
ALGORITHMS = ["RS256"]

if not JWKS_URL:
    raise RuntimeError("❌ SUPABASE_JWKS_URL not set")
if not SUPABASE_ANON_KEY:
    raise RuntimeError("❌ SUPABASE_ANON_KEY not set")

_jwks_cache = None

def _get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        try:
            headers = {"apikey": SUPABASE_ANON_KEY}
            resp = httpx.get(JWKS_URL, headers=headers, timeout=10.0)  # ✅ add apikey
            resp.raise_for_status()
            _jwks_cache = resp.json()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch JWKS from {JWKS_URL}: {e}")
    return _jwks_cache

class UserClaims(BaseModel):
    sub: str
    email: str
    role: str

security = HTTPBearer(auto_error=True)

def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)) -> UserClaims:
    try:
        jwks = _get_jwks()
        payload = jwt.decode(
            token.credentials,
            jwks,
            algorithms=ALGORITHMS,
            options={"verify_aud": False},
        )
        return UserClaims(**payload)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
