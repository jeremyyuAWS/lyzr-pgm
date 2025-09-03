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
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from httpx import TimeoutException, RequestError

from scripts.create_manager_with_roles import create_manager_with_roles
from src.utils.normalize_output import normalize_inference_output
from src.api.client import LyzrAPIClient  # now async-capable
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
# Global API client (async)
# -----------------------------
client: LyzrAPIClient | None = None


@app.on_event("startup")
async def startup_event():
    global client
    api_key = os.getenv("LYZR_API_KEY", "")
    client = LyzrAPIClient(api_key=api_key, timeout=300.0)  # 5 min timeout
    await client.__aenter__()  # open async client
    logger.info("✅ LyzrAPIClient initialized")


@app.on_event("shutdown")
async def shutdown_event():
    global client
    if client:
        await client.__aexit__(None, None, None)
        logger.info("👋 LyzrAPIClient closed")


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


def safe_user_email(user) -> str:
    return getattr(user, "email", None)


def safe_user_sub(user) -> str:
    return getattr(user, "sub", "")


def user_to_dict(user) -> dict:
    if hasattr(user, "dict"):
        return user.dict()
    elif isinstance(user, dict):
        return user
    else:
        return {"sub": safe_user_sub(user), "email": safe_user_email(user)}


def extract_api_key_from_user(user) -> str | None:
    key = None

    if isinstance(user, dict):
        key = user.get("lyzr_api_key") or user.get("encrypted_api_key")
    else:
        key = getattr(user, "lyzr_api_key", None) or getattr(user, "encrypted_api_key", None)

    if key:
        logger.info("✅ Using API key from Supabase JWT")
        return key

    env_key = os.getenv("LYZR_API_KEY")
    if env_key:
        logger.warning("⚠️ No API key in Supabase JWT — falling back to environment")
    else:
        logger.error("❌ No API key available in user claims or environment")
    return env_key


# -----------------------------
# Debug + health
# -----------------------------
@app.get("/me")
async def read_me(user=Depends(get_current_user)):
    return {
        "status": "ok",
        "user_id": safe_user_sub(user),
        "claims": user_to_dict(user),
    }


@app.get("/health")
async def health_check():
    try:
        resp = await client._request("GET", "/v3/agents/")
        ok = resp["ok"]
    except Exception as e:
        ok = False
        logger.error(f"❌ Healthcheck failed: {e}")
    return {"status": "ok" if ok else "error", "service": "Agent Orchestrator API", "studio_ok": ok}


# -----------------------------
# Endpoints
# -----------------------------
@app.post("/create-agents")
@app.post("/create-agents/")  # support both
async def create_agents_from_file(
    file: UploadFile = File(...),
    tz_name: str = Form("America/Los_Angeles"),
    user=Depends(get_current_user),
):
    rid = get_request_id()
    trace(
        f"Received /create-agents request tz={tz_name} by {safe_user_email(user)}",
        {"request_id": rid},
    )

    api_key = extract_api_key_from_user(user)
    if not api_key:
        raise HTTPException(status_code=401, detail="No API key found in user profile")

    local_client = LyzrAPIClient(api_key=api_key)
    await local_client.__aenter__()  # open

    yaml_path = None
    try:
        raw_bytes = await file.read()
        text = raw_bytes.decode("utf-8")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
            tmp.write(text.encode("utf-8"))
            yaml_path = Path(tmp.name)

        result = await create_manager_with_roles(local_client, yaml_path)
        return {"status": "success", "created": result, "user": user_to_dict(user)}

    except yaml.YAMLError as ye:
        logger.error(f"YAML parse failed: {ye}")
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {ye}")
    except Exception as e:
        logger.exception("❌ create_agents_from_file failed")
        raise HTTPException(status_code=500, detail=f"Create agents failed: {e}")
    finally:
        if yaml_path and yaml_path.exists():
            yaml_path.unlink()
        await local_client.__aexit__(None, None, None)


# -----------------------------
# Inference Payload
# -----------------------------
class InferencePayload(BaseModel):
    agent_id: str
    message: str
    user_id: str | None = None
    system_prompt_variables: dict = {}
    filter_variables: dict = {}
    features: list = []
    assets: list[str] = []


# -----------------------------
# Inference Endpoint
# -----------------------------
@app.post("/run-inference/")
async def run_inference(
    req: InferencePayload,
    user=Depends(get_current_user),
):
    rid = get_request_id()
    trace(
        f"Run inference for agent_id={req.agent_id} by {safe_user_email(user)}",
        {"request_id": rid},
    )

    api_key = extract_api_key_from_user(user) or os.getenv("LYZR_API_KEY")
    if not api_key:
        raise HTTPException(status_code=401, detail="No API key found")

    payload = {
        "user_id": req.user_id or safe_user_email(user) or safe_user_sub(user),
        "system_prompt_variables": req.system_prompt_variables or {},
        "agent_id": req.agent_id,
        "session_id": f"{req.agent_id}-{os.urandom(4).hex()}",
        "message": req.message,
        "filter_variables": req.filter_variables or {},
        "features": req.features or [],
        "assets": req.assets or [],
    }

    logger.info(f"➡️ Payload to Studio:\n{json.dumps(payload, indent=2)}")
    logger.info(f"🔑 Using API key (truncated): {api_key[:6]}...")

    try:
        resp = await client.call_agent(payload, api_key=api_key)
        if not resp["ok"]:
            raise HTTPException(status_code=502, detail=resp.get("data", "Studio error"))

        raw = resp["data"]
        out_dir = Path(f"outputs/{safe_user_sub(user)}")
        out_dir.mkdir(parents=True, exist_ok=True)

        normalized = normalize_inference_output(json.dumps(raw), out_dir)
        return {
            "status": "success",
            "agent_id": req.agent_id,
            "raw": raw,
            "normalized": normalized,
            "user": user_to_dict(user),
        }

    except TimeoutException:
        logger.error("⏱️ Studio request timed out")
        raise HTTPException(status_code=504, detail="Studio timed out")
    except RequestError as re:
        logger.error(f"❌ Studio request error: {re}")
        raise HTTPException(status_code=502, detail=f"Studio request error: {re}")
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


# -----------------------------
# Middleware (catch all exceptions → JSON + CORS)
# -----------------------------
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except HTTPException as he:
        return JSONResponse(
            status_code=he.status_code,
            content={"status": "error", "detail": he.detail},
            headers={"Access-Control-Allow-Origin": request.headers.get("origin", "*")},
        )
    except Exception as e:
        logger.exception("❌ Unhandled server error")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)},
            headers={"Access-Control-Allow-Origin": request.headers.get("origin", "*")},
        )
