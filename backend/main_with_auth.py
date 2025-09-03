import os
import json
import yaml
import logging
import uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.utils.normalize_output import normalize_inference_output
from src.api.client_async import LyzrAPIClient   # ✅ your new async client
from src.utils.auth import get_current_user      # ✅ JWT-based auth

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
    rid = str(uuid.uuid4())[:8]
    if extra:
        logger.info(f"{msg} | {json.dumps(extra)}")
    else:
        logger.info(msg)


# -----------------------------
# FastAPI App + Lifespan
# -----------------------------
app = FastAPI(title="Agent API with Auth")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # adjust for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    trace("🚀 Starting up FastAPI app")
    app.state.lyzr_client = await LyzrAPIClient().__aenter__()

@app.on_event("shutdown")
async def shutdown_event():
    trace("🛑 Shutting down FastAPI app")
    client: LyzrAPIClient = app.state.lyzr_client
    await client.__aexit__(None, None, None)


# -----------------------------
# Models
# -----------------------------
class InferenceRequest(BaseModel):
    agent_id: str
    message: str
    user_id: str
    system_prompt_variables: dict = {}
    filter_variables: dict = {}
    features: list = []
    assets: list = []


# -----------------------------
# Endpoints
# -----------------------------
@app.post("/run-inference/")
async def run_inference(req: InferenceRequest, request: Request, user=Depends(get_current_user)):
    client: LyzrAPIClient = request.app.state.lyzr_client

    trace("📥 Incoming POST /run-inference", req.dict())

    payload = {
        "agent_id": req.agent_id,
        "message": req.message,
        "user_id": req.user_id,
        "system_prompt_variables": req.system_prompt_variables,
        "filter_variables": req.filter_variables,
        "features": req.features,
        "assets": req.assets,
    }

    resp = await client.post("/v3/inference/chat/", payload)

    if not resp.get("ok"):
        trace("❌ Inference failed", {"error": resp.get("data")})
        raise HTTPException(status_code=500, detail=f"Inference failed: {resp.get('data')}")

    try:
        norm = normalize_inference_output(resp["data"].get("response"))
    except Exception as e:
        trace("⚠️ Normalization failed", {"error": str(e)})
        norm = None

    return {"ok": True, "raw": resp, "normalized": norm}


@app.post("/upload-yaml/")
async def upload_yaml(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    client: LyzrAPIClient = request.app.state.lyzr_client
    contents = await file.read()

    try:
        yaml_def = yaml.safe_load(contents.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    trace("📥 Uploading YAML to create agent", {"filename": file.filename, "user": user})

    resp = await client.create_agent_from_yaml(yaml_def, is_path=False)
    if not resp.get("ok"):
        raise HTTPException(status_code=500, detail=resp.get("data"))

    return {"ok": True, "agent": resp.get("data")}


@app.post("/upload-manager-yaml/")
async def upload_manager_yaml(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    client: LyzrAPIClient = request.app.state.lyzr_client
    contents = await file.read()

    try:
        yaml_def = yaml.safe_load(contents.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    trace("📥 Uploading Manager YAML", {"filename": file.filename, "user": user})

    resp = await client.create_manager_with_roles(yaml_def, is_path=False)
    if not resp.get("ok"):
        raise HTTPException(status_code=500, detail=resp.get("error"))

    return {"ok": True, "manager": resp.get("data"), "roles": resp.get("roles")}
