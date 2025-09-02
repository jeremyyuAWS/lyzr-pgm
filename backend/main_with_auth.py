# backend/main_with_auth.py
import os
import tempfile
import json
import yaml
import logging
import uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from scripts.create_manager_with_roles import create_manager_with_roles
from src.utils.normalize_output import normalize_inference_output
from src.api.client import LyzrAPIClient
from src.utils.auth import get_current_user  # ✅ JWT-based auth

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


def trace(msg: str, extra: dict = None):
    """Helper for structured trace logging with request_id."""
    rid = extra.get("request_id") if extra else None
    if rid:
        logger.info(f"[trace][rid={rid}] {msg}")
    else:
        logger.info(f"[trace] {msg}")


# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(title="Agent Orchestrator API (Supabase JWT Auth)")

# -----------------------------
# CORS (origins from .env, fallback to *)
# -----------------------------
cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "")
origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

if not origins:
    logger.warning("⚠️ No CORS origins configured, falling back to * (dev mode).")
    origins = ["*"]

logger.info(f"🔐 Allowed CORS origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True if "*" not in origins else False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# -----------------------------
# Helpers
# -----------------------------
def get_request_id() -> str:
    return uuid.uuid4().hex[:8]


# -----------------------------
# Debug + health
# -----------------------------
@app.get("/me")
async def read_me(user=Depends(get_current_user)):
    """
    Returns the full decoded Supabase JWT payload for debugging.
    """
    return {
        "status": "ok",
        "user_id": user.get("sub", ""),
        "claims": user  # 👈 full decoded JWT payload
    }


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Agent Orchestrator API (Supabase JWT Auth)"}


# -----------------------------
# Endpoints
# -----------------------------
@app.post("/create-agents/")
async def create_agents_from_file(
    file: UploadFile = File(...),
    tz_name: str = Form("America/Los_Angeles"),
    user=Depends(get_current_user)  # ✅ enforce auth
):
    """
    Create Manager + Role agents from a YAML file using the authenticated user's Supabase JWT.
    """
    rid = get_request_id()
    trace(f"Received /create-agents request tz={tz_name} by {user.get('email')}", {"request_id": rid})

    client = LyzrAPIClient(api_key=None)  # auth handled via JWT now

    yaml_path = None
    try:
        raw_bytes = await file.read()
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Uploaded file is not valid UTF-8")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
            tmp.write(text.encode("utf-8"))
            yaml_path = Path(tmp.name)

        result = create_manager_with_roles(client, yaml_path)
        return {"status": "success", "created": result, "user": user}

    except yaml.YAMLError as ye:
        logger.error(f"YAML parse failed: {ye}")
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {ye}")
    except Exception as e:
        logger.exception("❌ create_agents_from_file failed")
        raise HTTPException(status_code=500, detail=f"Create agents failed: {e}")
    finally:
        if yaml_path and yaml_path.exists():
            try:
                yaml_path.unlink()
            except Exception:
                pass


# -----------------------------
# Inference
# -----------------------------
class InferencePayload(BaseModel):
    agent_id: str
    message: str


@app.post("/run-inference/")
async def run_inference(
    req: InferencePayload,
    user=Depends(get_current_user)  # ✅ enforce auth
):
    """
    Run inference against a given agent_id for the authenticated user.
    """
    rid = get_request_id()
    trace(f"Run inference for agent_id={req.agent_id} by {user.get('email')}", {"request_id": rid})

    headers = {"Content-Type": "application/json"}

    payload = {
        "agent_id": req.agent_id,
        "session_id": f"{req.agent_id}-{os.urandom(4).hex()}",
        "message": req.message,
    }

    try:
        resp = httpx.post(
            "https://agent-prod.studio.lyzr.ai/v3/inference/chat/",
            headers=headers,
            json=payload,
            timeout=60,
        )
        trace(f"Studio response status={resp.status_code}", {"request_id": rid})

        if resp.status_code != 200:
            error_text = resp.text
            logger.error(f"Studio error response: {error_text}")
            raise HTTPException(status_code=resp.status_code, detail=error_text)

        raw = resp.json()

        out_dir = Path(f"outputs/{user.get('sub')}")
        out_dir.mkdir(parents=True, exist_ok=True)

        normalized = normalize_inference_output(json.dumps(raw), out_dir)
        return {
            "status": "success",
            "agent_id": req.agent_id,
            "raw": raw,
            "normalized": normalized,
            "user": user
        }
    except httpx.RequestError as re:
        logger.exception("❌ HTTP request to Studio failed")
        raise HTTPException(status_code=500, detail=f"Network error contacting Studio: {re}")
    except Exception as e:
        logger.exception("❌ run_inference failed")
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")


# -----------------------------
# Middleware (logs)
# -----------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    body = await request.body()
    try:
        body_text = body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = f"<{len(body)} bytes of binary>"
    print(f"📥 Incoming {request.method} {request.url} - Body: {body_text}")
    response = await call_next(request)
    print(f"📤 Response {response.status_code}")
    return response
