# src/utils/auth.py
import os
import requests
from jose import jwt, jwk, JWTError
from jose.utils import base64url_decode
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")

class UserClaims(BaseModel):
    sub: str
    email: str
    role: str

security = HTTPBearer(auto_error=True)

def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)) -> UserClaims:
    try:
        # 1. Decode headers
        unverified_header = jwt.get_unverified_header(token.credentials)

        # 2. Fetch JWKS from Supabase
        jwks = requests.get(SUPABASE_JWKS_URL).json()

        # 3. Find the matching key
        key = next((k for k in jwks["keys"] if k["kid"] == unverified_header["kid"]), None)
        if not key:
            raise HTTPException(status_code=401, detail="No matching JWK found")

        # 4. Verify
        payload = jwt.decode(
            token.credentials,
            key,
            algorithms=[unverified_header["alg"]],
            audience=os.getenv("SUPABASE_JWT_AUDIENCE", None)
        )
        return UserClaims(**payload)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Supabase token: {str(e)}")
