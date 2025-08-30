from jose import jwt, JWTError
import os
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
JWT_ALGO = "HS256"

async def get_current_user(token: str = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        # ✅ Optional: enforce audience & issuer
        if payload.get("aud") != "authenticated":
            raise HTTPException(status_code=401, detail="Invalid audience")
        return {
            "user_id": payload.get("sub"),
            "claims": payload
        }
    except JWTError as e:
        print("❌ JWT decode failed:", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")
