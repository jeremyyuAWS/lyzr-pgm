from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt, os

bearer_scheme = HTTPBearer()
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")  # optional, only if verifying locally

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        print("🔑 Incoming JWT:", token[:50], "...")  # log first 50 chars
        payload = jwt.decode(
            token,
            os.getenv("SUPABASE_JWT_SECRET"),   # must match Supabase JWT secret
            algorithms=["HS256"]
        )
        print("✅ Decoded payload:", payload)
        return {"user_id": payload["sub"], "claims": payload}
    except Exception as e:
        print("❌ JWT decode failed:", str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")
