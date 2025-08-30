# backend/auth_middleware.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt, os

bearer_scheme = HTTPBearer()

JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")  # optional, only if verifying locally

async def get_current_user(token: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """
    Decode the Supabase JWT and normalize the user object.
    Ensures we always return `user_id` instead of raw `sub`.
    """
    try:
        # Decode JWT from Supabase Auth (default uses HS256)
        payload = jwt.decode(token.credentials, JWT_SECRET, algorithms=["HS256"])
        
        # Normalize sub → user_id
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("JWT missing 'sub' claim")
        
        return {
            "user_id": user_id,
            "claims": payload
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
