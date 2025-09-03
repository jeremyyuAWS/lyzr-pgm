import os
import json
import logging
import pytz
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import httpx

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


STUDIO_API_BASE = os.getenv("STUDIO_API_URL", "https://agent-prod.studio.lyzr.ai")
DEFAULT_API_KEY = os.getenv("STUDIO_API_KEY")


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
async def root():
    return {"status": "ok", "service": "lyzr-agent-api"}


@app.post("/create-agents/")
async def create_agents(
    request: Request,
    user: UserClaims = Depends(get_current_user),
):
    """
    Create manager + role agents from incoming JSON.
    """
    try:
        body = await request.json()
        trace("📥 Incoming JSON body keys", {"keys": list(body.keys())})

        manager_json = body.get("manager_json")
        tz_name = body.get("tz_name", "America/Los_Angeles")
        studio_api_key = body.get("studio_api_key") or DEFAULT_API_KEY

        if not manager_json:
            raise HTTPException(status_code=400, detail="manager_json is required")
        if not studio_api_key:
            raise HTTPException(status_code=400, detail="studio_api_key is required")

        trace("🔑 Authenticated user", {"user": user.dict()})

        async with LyzrAPIClient(base_url=STUDIO_API_BASE, api_key=studio_api_key) as client:
            result = await create_manager_with_roles(client, manager_json)

        if not result or not result.get("ok"):
            trace("❌ Manager creation failed", {"error": result})
            raise HTTPException(status_code=500, detail="Manager creation failed")

        manager = result.get("manager", {})
        trace("✅ Manager created", {"id": manager.get("id")})

        return {
            "ok": True,
            "timestamp": _timestamp_str(tz_name),
            "manager": manager,
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


@app.post("/run-inference/")
async def run_inference(
    request: Request,
    user: UserClaims = Depends(get_current_user),
):
    """
    Proxy inference requests to Studio.
    Supports both /chat/ (default) and /stream/ modes.
    """
    try:
        body = await request.json()
        trace("📥 Inference request body", {"keys": list(body.keys())})

        agent_id = body.get("agent_id")
        message = body.get("message")
        studio_api_key = body.get("studio_api_key") or DEFAULT_API_KEY
        use_stream = body.get("stream", False)

        if not agent_id or not message:
            raise HTTPException(status_code=400, detail="agent_id and message are required")
        if not studio_api_key:
            raise HTTPException(status_code=400, detail="studio_api_key is required")

        endpoint = "/v3/inference/stream/" if use_stream else "/v3/inference/chat/"

        payload = {
            "user_id": user.email,
            "agent_id": agent_id,
            "session_id": f"{agent_id}-{user.sub}",
            "message": message,
            "system_prompt_variables": body.get("system_prompt_variables", {}),
            "filter_variables": body.get("filter_variables", {}),
            "features": body.get("features", []),
            "assets": body.get("assets", []),
        }

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.post(
                f"{STUDIO_API_BASE}{endpoint}",
                headers={"x-api-key": studio_api_key, "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    except HTTPException:
        raise
    except Exception as e:
        trace("❌ Inference error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")
