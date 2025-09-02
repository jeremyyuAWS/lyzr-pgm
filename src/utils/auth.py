# src/utils/auth.py
import os
import jwt
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# -----------------------------
# Config
# -----------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "changeme")  # ✅ set this in Render env vars
ALGORITHM = "HS256"

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

def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)) -> UserClaims:
    """
    Decode Supabase JWT using project JWT_SECRET.
    """
    try:
        payload = jwt.decode(token.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        return UserClaims(
            sub=payload.get("sub"),
            email=payload.get("email"),
            role=payload.get("role", "authenticated")
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
