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

from scripts.create_manager_with_roles import create_manager_with_roles  # noqa: F401
from src.utils.normalize_output import normalize_inference_output
from src.api.client_async import LyzrAPIClient
from src.utils.auth import get_current_user

# -----------------------------
# Environment
# -----------------------------
load_dotenv()

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("agent-api")


def trace(msg: str, extra: dict | None = None):
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
# CORS
# -----------------------------
cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "")
origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
if not origins:
    logger.warning("⚠️ No CORS origins configured, falling back to * (dev mode).")
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=("*" not in origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# -----------------------------
# Startup / Shutdown
# -----------------------------
@app.on_event("startup")
async def startup_event():
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


def build_client_for_user(user) -> LyzrAPIClient:
    """Return a new async client (to be used with `async with`)."""
    api_key = extract_api_key_from_user(user)
    if not api_key:
        raise HTTPException(status_code=401, detail="No API key found in user profile or environment")
    return LyzrAPIClient(api_key=api_key, timeout=300)


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
    client: LyzrAPIClient = getattr(app.state, "lyzr_client", None)
    if not client:
        return {"status": "error", "studio_ok": False, "error": "Client not ready"}

    try:
        resp = await client.list_agents()
        ok = bool(resp.get("ok"))
        return {
            "status": "ok" if ok else "error",
            "studio_ok": ok,
            "count": len(resp.get("data", [])) if ok else 0,
        }
    except Exception as e:
        logger.exception("❌ Healthcheck failed")
        return {"status": "error", "studio_ok": False, "error": str(e)}


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
@app.post("/create-agents/")
async def create_agents_from_file(
    file: UploadFile = File(...),
    tz_name: str = Form("America/Los_Angeles"),
    user=Depends(get_current_user),
):
    rid = get_request_id()
    trace("📥 Received /create-agents", {"tz": tz_name, "user": safe_user_email(user), "rid": rid})

    yaml_tmp_path: Path | None = None
    try:
        raw_bytes = await file.read()
        text = raw_bytes.decode("utf-8")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
            tmp.write(text.encode("utf-8"))
            yaml_tmp_path = Path(tmp.name)

        async with build_client_for_user(user) as client:
            result = await client.create_manager_with_roles(text, is_path=False)

        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error") or "Failed to create agents")

        return {"status": "success", "created": result, "user": user_to_dict(user)}

    except yaml.YAMLError as ye:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {ye}")
    except Exception as e:
        logger.exception("❌ create_agents_from_file failed")
        raise HTTPException(status_code=500, detail=f"Create agents failed: {e}")
    finally:
        if yaml_tmp_path and yaml_tmp_path.exists():
            yaml_tmp_path.unlink(missing_ok=True)


@app.post("/upload-yaml/")
async def upload_yaml(file: UploadFile = File(...), user=Depends(get_current_user)):
    try:
        contents = await file.read()
        text = contents.decode("utf-8")

        async with build_client_for_user(user) as client:
            resp = await client.create_agent_from_yaml(text, is_path=False)

        if not resp.get("ok"):
            raise HTTPException(status_code=502, detail=resp.get("data") or "Failed to create agent")

        return {"ok": True, "agent": resp.get("data")}
    except Exception as e:
        logger.exception("❌ upload_yaml failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-manager-yaml/")
async def upload_manager_yaml(file: UploadFile = File(...), user=Depends(get_current_user)):
    try:
        contents = await file.read()
        text = contents.decode("utf-8")

        async with build_client_for_user(user) as client:
            resp = await client.create_manager_with_roles(text, is_path=False)

        if not resp.get("ok"):
            raise HTTPException(status_code=502, detail=resp.get("error") or "Failed to create manager")

        return {"ok": True, "manager": resp.get("data"), "roles": resp.get("roles")}
    except Exception as e:
        logger.exception("❌ upload_manager_yaml failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run-inference/")
async def run_inference(req: InferencePayload, user=Depends(get_current_user)):
    rid = get_request_id()
    trace("💬 Run inference", {"agent_id": req.agent_id, "user": safe_user_email(user), "rid": rid})

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
        async with build_client_for_user(user) as client:
            resp = await client.post("/v3/inference/chat/", payload)

        if not resp.get("ok"):
            raise HTTPException(status_code=502, detail=resp.get("data") or "Studio error")

        raw = resp.get("data")
        try:
            normalized = normalize_inference_output(
                raw.get("response") if isinstance(raw, dict) else raw
            )
        except Exception as ne:
            logger.warning(f"⚠️ Normalization failed: {ne}")
            normalized = None

        return {"status": "success", "agent_id": req.agent_id, "raw": raw, "normalized": normalized, "user": user_to_dict(user)}

    except TimeoutException:
        raise HTTPException(status_code=504, detail="Studio timed out")
    except RequestError as re:
        raise HTTPException(status_code=502, detail=f"Studio request error: {re}")
    except Exception as e:
        logger.exception("❌ run_inference failed")
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")


# -----------------------------
# Middleware
# -----------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        body = await request.body()
        try:
            body_text = body.decode("utf-8")
        except UnicodeDecodeError:
            body_text = f"<{len(body)} bytes of binary>"
        print(f"📥 {request.method} {request.url} - Body: {body_text}")
    except Exception:
        print(f"📥 {request.method} {request.url} - Body: <unavailable>")

    response = await call_next(request)
    print(f"📤 Response {response.status_code}")
    return response


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except HTTPException as he:
        return JSONResponse(status_code=he.status_code, content={"status": "error", "detail": he.detail}, headers={"Access-Control-Allow-Origin": request.headers.get("origin", "*")})
    except Exception as e:
        logger.exception("❌ Unhandled server error")
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)}, headers={"Access-Control-Allow-Origin": request.headers.get("origin", "*")})
