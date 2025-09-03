# backend/main_with_auth.py

import os
import json
import logging
import pytz
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from scripts.create_manager_with_roles import create_manager_with_roles
from src.api.client_async import LyzrAPIClient
from src.utils.auth import get_current_user
from src.utils.normalize_output import normalize_inference_output

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
    allow_origins=["*"],  # 🔒 tighten later if needed
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
async def create_agents(request: Request):
    """
    Create manager + role agents from incoming JSON.
    """
    try:
        body = await request.json()
        trace("📥 Incoming JSON body keys", {"keys": list(body.keys())})

        manager_json = body.get("manager_json")
        roles_json = body.get("roles_json", [])
        tz_name = body.get("tz_name", "America/Los_Angeles")

        if not manager_json:
            raise HTTPException(status_code=400, detail="manager_json is required")

        # Validate authenticated user
        user = await get_current_user(request)
        trace("🔑 Authenticated user", {"user": user})

        # Orchestration with API client
        async with LyzrAPIClient() as client:
            result = await client.create_manager_with_roles(manager_json)

            if not result.get("ok"):
                trace("❌ Manager creation failed", {"error": result})
                raise HTTPException(status_code=500, detail=result.get("error"))

            trace("✅ Manager created", {"id": result["manager"]["id"]})
            return {
                "ok": True,
                "timestamp": _timestamp_str(tz_name),
                "manager": result["manager"],
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
