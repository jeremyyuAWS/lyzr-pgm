# backend/main_with_auth.py

import os
import json
import yaml
import logging
import uuid
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from httpx import TimeoutException, RequestError

# You can keep this import around; we no longer call it directly,
# but leaving it here doesn't break anything you already had.
from scripts.create_manager_with_roles import create_manager_with_roles  # noqa: F401

from src.utils.normalize_output import normalize_inference_output
from src.api.client_async import LyzrAPIClient  # ✅ async client
from src.utils.auth import get_current_user     # ✅ JWT-based auth

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
    """Structured trace logging with optional extra context."""
    rid = uuid.uuid4().hex[:8]
    if extra:
        logger.info(f"[trace:{rid}] {msg} | {json.dumps(extra)}")
    else:
        logger.info(f"[trace:{rid}] {msg}")


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
    allow_credentials=("*" not in origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# -----------------------------
# Shared async client (for health checks, etc.)
# -----------------------------
@app.on_event("startup")
async def startup_event():
    # Shared client uses env key; per-request routes will build their own client
    # if a user-scoped key is provided.
    app.state.lyzr_client = await LyzrAPIClient(
        api_key=os.getenv("LYZR_API_KEY", ""),
        timeout=300,
    ).__aenter__()
    logger.info("✅ Shared LyzrAPIClient initialized")


@app.on_event("shutdown")
async def shutdown_event():
    client: LyzrAPIClient = getattr(app.state, "lyzr_client", None)
    if client:
        await client.__aexit__(None, None, None)
        logger.info("👋 Shared LyzrAPIClient closed")


# -----------------------------
# Helpers
# -----------------------------
def get_request_id() -> str:
    return uuid.uuid4().hex[:8]


def safe_user_email(user) -> str | None:
    return getattr(user, "email", None)


def safe_user_sub(user) -> str:
    return getattr(user, "sub", "") or ""


def user_to_dict(user) -> dict:
    if hasattr(user, "dict"):
        return user.dict()
    if isinstance(user, dict):
        return user
    return {"sub": safe_user_sub(user), "email": safe_user_email(user)}


def extract_api_key_from_user(user) -> str | None:
    # Pull API key from JWT claims if present; otherwise fall back to env.
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
        return env_key

    logger.error("❌ No API key available in user claims or environment")
    return None


async def build_client_for_user(user) -> LyzrAPIClient:
    """
    Build a *request-scoped* async client using the user's key if present.
    Falls back to env key. Always __aenter__/__aexit__ this client in the route.
    """
    api_key = extract_api_key_from_user(user)
    if not api_key:
        raise HTTPException(status_code=401, detail="No API key found in user profile or environment")

    return await LyzrAPIClient(api_key=api_key, timeout=300).__aenter__()


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
async def health_check(request: Request):
    """
    Pings Lyzr Studio via GET /v3/agents/ using the shared client created in startup.
    """
    client: LyzrAPIClient = getattr(app.state, "lyzr_client", None)
    if not client:
        return {"status": "error", "service": "Agent Orchestrator API", "studio_ok": False, "error": "Client not ready"}

    try:
        resp = await client.list_agents()
        ok = bool(resp.get("ok"))
        count = len(resp.get("data", [])) if ok else 0
        return {"status": "ok" if ok else "error", "service": "Agent Orchestrator API", "studio_ok": ok, "count": count}
    except Exception as e:
        logger.exception("❌ Healthcheck failed")
        return {"status": "error", "service": "Agent Orchestrator API", "studio_ok": False, "error": str(e)}


# -----------------------------
# Models
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
# Endpoints
# -----------------------------
@app.post("/create-agents")
@app.post("/create-agents/")
async def create_agents_from_file(
    file: UploadFile = File(...),
    tz_name: str = Form("America/Los_Angeles"),
    user=Depends(get_current_user),
):
    """
    Accepts a YAML file (FormData 'file') describing a Manager + Roles.
    Uses a request-scoped async client with the user's API key and calls the
    async Lyzr client helper to create roles then manager.
    """
    rid = get_request_id()
    trace("📥 Received /create-agents", {"tz": tz_name, "user": safe_user_email(user), "rid": rid})

    # Build request-scoped client with user key
    local_client = await build_client_for_user(user)

    yaml_tmp_path: Path | None = None
    try:
        raw_bytes = await file.read()
        text = raw_bytes.decode("utf-8")  # keep as TEXT to avoid dict-vs-path confusion

        # (Optional) keep a temp file purely for debugging trace / inspection
        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
            tmp.write(text.encode("utf-8"))
            yaml_tmp_path = Path(tmp.name)

        # ✅ Call async client helper with YAML TEXT (not dict), so it can parse itself
        result = await local_client.create_manager_with_roles(text, is_path=False)

        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error") or "Failed to create agents")

        return {"status": "success", "created": result, "user": user_to_dict(user)}

    except yaml.YAMLError as ye:
        logger.error(f"YAML parse failed: {ye}")
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {ye}")
    except Exception as e:
        logger.exception("❌ create_agents_from_file failed")
        raise HTTPException(status_code=500, detail=f"Create agents failed: {e}")
    finally:
        if yaml_tmp_path and yaml_tmp_path.exists():
            try:
                yaml_tmp_path.unlink()
            except Exception:
                pass
        # Close request-scoped client
        await local_client.__aexit__(None, None, None)


@app.post("/upload-yaml")
@app.post("/upload-yaml/")
async def upload_yaml(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Upload a single agent YAML and create it directly.
    """
    local_client = await build_client_for_user(user)

    try:
        contents = await file.read()
        text = contents.decode("utf-8")

        # ✅ Pass YAML TEXT to client; it will safe_load internally
        resp = await local_client.create_agent_from_yaml(text, is_path=False)
        if not resp.get("ok"):
            raise HTTPException(status_code=502, detail=resp.get("data") or "Failed to create agent")

        return {"ok": True, "agent": resp.get("data")}
    except Exception as e:
        logger.exception("❌ upload_yaml failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await local_client.__aexit__(None, None, None)


@app.post("/upload-manager-yaml")
@app.post("/upload-manager-yaml/")
async def upload_manager_yaml(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Upload a Manager YAML (with managed_agents inline) and create the full system.
    Mirrors /create-agents but keeps the route for compatibility.
    """
    local_client = await build_client_for_user(user)

    try:
        contents = await file.read()
        text = contents.decode("utf-8")

        # ✅ Again, pass TEXT
        resp = await local_client.create_manager_with_roles(text, is_path=False)
        if not resp.get("ok"):
            raise HTTPException(status_code=502, detail=resp.get("error") or "Failed to create manager")

        return {"ok": True, "manager": resp.get("data"), "roles": resp.get("roles")}
    except Exception as e:
        logger.exception("❌ upload_manager_yaml failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await local_client.__aexit__(None, None, None)


@app.post("/run-inference")
@app.post("/run-inference/")
async def run_inference(
    req: InferencePayload,
    user=Depends(get_current_user),
):
    """
    Runs Studio chat inference via POST /v3/inference/chat/ using a request-scoped client
    and the user's API key (if provided).
    """
    rid = get_request_id()
    trace("💬 Run inference", {"agent_id": req.agent_id, "user": safe_user_email(user), "rid": rid})

    local_client = await build_client_for_user(user)

    payload = {
        "user_id": req.user_id or safe_user_email(user) or safe_user_sub(user) or "anonymous",
        "system_prompt_variables": req.system_prompt_variables or {},
        "agent_id": req.agent_id,
        "session_id": f"{req.agent_id}-{uuid.uuid4().hex[:8]}",
        "message": req.message,
        "filter_variables": req.filter_variables or {},
        "features": req.features or [],
        "assets": req.assets or [],
    }

    try:
        # Use the Studio chat endpoint directly (this is what Studio expects)
        resp = await local_client.post("/v3/inference/chat/", payload)
        if not resp.get("ok"):
            raise HTTPException(status_code=502, detail=resp.get("data") or "Studio error")

        raw = resp.get("data")
        # Try to normalize if there is a 'response' in payload
        try:
            normalized = normalize_inference_output(
                raw.get("response") if isinstance(raw, dict) else raw
            )
        except Exception as ne:
            logger.warning(f"⚠️ Normalization failed: {ne}")
            normalized = None

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
    finally:
        await local_client.__aexit__(None, None, None)


# -----------------------------
# Middleware (logs)
# -----------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        body = await request.body()
        try:
            body_text = body.decode("utf-8")
        except UnicodeDecodeError:
            body_text = f"<{len(body)} bytes of binary>"
        print(f"📥 Incoming {request.method} {request.url} - Body: {body_text}")
    except Exception:
        # best effort
        print(f"📥 Incoming {request.method} {request.url} - Body: <unavailable>")

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
