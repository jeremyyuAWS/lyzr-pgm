# src/utils/auth.py

import os
import jwt
from pydantic import BaseModel
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# -----------------------------
# Config
# -----------------------------
SECRET = os.getenv("JWT_SECRET", "super-secret")  # set in Render env vars
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

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
    Decode a JWT from Authorization: Bearer <token> header
    and return typed user claims.
    """
    try:
        payload = jwt.decode(token.credentials, SECRET, algorithms=[ALGORITHM])
        return UserClaims(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
