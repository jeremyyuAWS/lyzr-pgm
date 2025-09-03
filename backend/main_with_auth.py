# backend/main_with_auth.py

import os
import json
import logging
import pytz
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from scripts.create_manager_with_roles import create_manager_with_roles
from src.api.client_async import LyzrAPIClient
from src.utils.auth import get_current_user, UserClaims

# -----------------------------
# Environment
# -----------------------------
load_dotenv()

# -----------------------------
# Logging Setup
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("agent-api")


def trace(msg: str, extra: dict | None = None):
    """Helper for structured logging"""
    if extra:
        logger.info(f"{msg} | {json.dumps(extra, ensure_ascii=False)}")
    else:
        logger.info(msg)


# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(title="Lyzr Agent API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🔒 tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Helpers
# -----------------------------
def _tz(tz_name: str | None = None) -> pytz.timezone:
    tz_name = tz_name or os.getenv("APP_TZ", "America/Los_Angeles")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone("America/Los_Angeles")


def _timestamp_str(tz_name: str | None = None) -> str:
    now = datetime.now(_tz(tz_name))
    return now.strftime("%d%b%Y-%I:%M%p %Z").upper()


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
async def root():
    return {"status": "ok", "service": "lyzr-agent-api"}


@app.post("/create-agents/")
async def create_agents(
    request: Request,
    user: UserClaims = Depends(get_current_user),  # ✅ inject Supabase JWT auth
):
    """
    Create manager + role agents from incoming JSON.
    Expects: { "manager_json": {...}, "tz_name": "America/Los_Angeles", "studio_api_key": "<key>" }
    """
    try:
        body = await request.json()
        trace("📥 Incoming JSON body keys", {"keys": list(body.keys())})

        manager_json = body.get("manager_json")
        tz_name = body.get("tz_name", "America/Los_Angeles")
        studio_api_key = body.get("studio_api_key")

        if not manager_json:
            raise HTTPException(status_code=400, detail="manager_json is required")

        if not studio_api_key:
            raise HTTPException(status_code=400, detail="studio_api_key is required")

        trace("🔑 Authenticated user", {"user": user.dict()})

        # Orchestration with API client (thread the API key)
        async with LyzrAPIClient(api_key=studio_api_key) as client:
            result = await create_manager_with_roles(client, manager_json)

        if not result or not result.get("ok"):
            trace("❌ Manager creation failed", {"error": result})
            raise HTTPException(status_code=500, detail="Manager creation failed")

        manager_data = result.get("manager", {})
        manager_id = manager_data.get("id") or manager_data.get("agent_id")
        manager_name = manager_data.get("name")

        trace("✅ Manager created", {"id": manager_id, "name": manager_name})

        return {
            "ok": True,
            "timestamp": _timestamp_str(tz_name),
            "manager": {
                "id": manager_id,
                "name": manager_name,
            },
            "roles": result.get("roles", []),
        }

    except HTTPException:
        raise
    except ValueError as ve:
        trace("❌ Bad Request", {"error": str(ve)})
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        trace("❌ Internal Error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
