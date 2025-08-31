from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import os

bearer_scheme = HTTPBearer()
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
JWT_ALGORITHM = "HS256"

if not JWT_SECRET:
    raise RuntimeError("Missing SUPABASE_JWT_SECRET env var")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        # 👇 Do NOT require audience, just verify signature + expiry
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False}   # ✅ ignore audience
        )
        return {"user_id": claims.get("sub"), "claims": claims}
    except JWTError as e:
        print(f"❌ JWT decode failed: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid JWT: {str(e)}")
