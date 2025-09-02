# src/utils/auth.py
import os
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# -----------------------------
# Config
# -----------------------------
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")  # ✅ from Supabase Project Settings → API
JWT_ALGORITHM = "HS256"

if not JWT_SECRET:
    raise RuntimeError("Missing SUPABASE_JWT_SECRET env var — set it in Render")

# -----------------------------
# Models
# -----------------------------
class UserClaims(BaseModel):
    sub: str = ""
    email: str = ""
    role: str = "authenticated"

# -----------------------------
# Security Dependency
# -----------------------------
security = HTTPBearer(auto_error=True)

# -----------------------------
# Decoder
# -----------------------------
def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)) -> UserClaims:
    """
    Decode a Supabase JWT (HS256) from Authorization: Bearer <token> header.
    Returns typed user claims.
    """
    try:
        payload = jwt.decode(
            token.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False}  # Supabase tokens often omit audience
        )
        return UserClaims(
            sub=payload.get("sub", ""),
            email=payload.get("email", payload.get("user_metadata", {}).get("email", "")),
            role=payload.get("role", "authenticated"),
        )
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
