from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import os, tempfile, httpx, json, yaml
from supabase import create_client, Client

from app.services.agent_creator import create_manager_with_roles
from src.utils.normalize_output import normalize_inference_output
from backend.auth_middleware import get_current_user
from fastapi import Request
from jose import jwt
# In main_with_auth.py
import os
print("🔍 Loaded SUPABASE_JWT_SECRET (first 8 chars):", os.getenv("SUPABASE_JWT_SECRET", "")[:8])



# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(title="Agent Orchestrator API with Auth")

# -----------------------------
# CORS Setup
# -----------------------------
origins = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
if not origins or origins == [""]:
    origins = [
        "http://localhost:5173",      # Local dev
        "https://lyzr-pgm.onrender.com" # Backend itself
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 🔑 open for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Supabase setup
# -----------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError("Missing Supabase credentials in environment")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# -----------------------------
# Helper: Fetch decrypted Lyzr key
# -----------------------------
def get_lyzr_api_key_for_user(user_id: str) -> str:
    """Fetch decrypted API key from Supabase view for the given user_id."""
    try:
        resp = (
            supabase.from_("user_profiles_with_decrypted_key")
            .select("decrypted_api_key")
            .eq("id", user_id)
            .execute()
        )
        if not resp.data or "decrypted_api_key" not in resp.data[0]:
            raise ValueError("No decrypted API key found for user")
        return resp.data[0]["decrypted_api_key"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Lyzr API key: {e}")

# -----------------------------
# /me (test token decoding)
# -----------------------------
@app.get("/debug-token")
async def debug_token(request: Request):
    auth = request.headers.get("Authorization")
    return {"auth_header": auth}


@app.get("/me")
async def read_me(current_user: dict = Depends(get_current_user)):
    return {
        "status": "ok",
        "user_id": current_user["user_id"],
        "claims": current_user["claims"],
    }

# -----------------------------
# /health (for connection tests)
# -----------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Agent Orchestrator API"}

# -----------------------------
# 1) Create agents
# -----------------------------
@app.post("/create-agents/")
async def create_agents_from_file(
    file: UploadFile = File(...), current_user: dict = Depends(get_current_user)
):
    user_id = current_user["user_id"]
    api_key = get_lyzr_api_key_for_user(user_id)

    base_url = (
        os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai") + "/v3/agents/"
    )
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    log_file = Path("logs/created_agents.jsonl")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
        tmp.write(await file.read())
        yaml_path = Path(tmp.name)

    try:
        result = create_manager_with_roles(yaml_path, headers, base_url, log_file)
        return {"status": "success", "created": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create agents failed: {e}")

# -----------------------------
# 2) Run inference
# -----------------------------
class InferencePayload(BaseModel):
    agent_id: str
    message: str

@app.post("/run-inference/")
async def run_inference(req: InferencePayload, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    api_key = get_lyzr_api_key_for_user(user_id)

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    payload = {
        "agent_id": req.agent_id,
        "user_id": user_id,
        "session_id": f"{req.agent_id}-{os.urandom(4).hex()}",
        "message": req.message,
        "features": [],
        "tools": [],
    }

    try:
        resp = httpx.post(
            f"{base_url}/v3/inference/chat/", headers=headers, json=payload, timeout=60
        )
        resp.raise_for_status()
        raw = resp.json()
        normalized = normalize_inference_output(json.dumps(raw), Path(f"outputs/{user_id}"))
        return {
            "status": "success",
            "agent_id": req.agent_id,
            "raw": raw,
            "normalized": normalized,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

# -----------------------------
# 3) List agents
# -----------------------------
@app.get("/list-agents/")
async def list_agents(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    api_key = get_lyzr_api_key_for_user(user_id)

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        resp = httpx.get(f"{base_url}/v3/agents/", headers=headers, timeout=60)
        resp.raise_for_status()
        return {"status": "success", "agents": resp.json()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List agents failed: {e}")
# -----------------------------
# 4) Get agent details
# -----------------------------
@app.get("/agent-details/{agent_id}")
async def agent_details(agent_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    api_key = get_lyzr_api_key_for_user(user_id)

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        resp = httpx.get(f"{base_url}/v3/agents/{agent_id}/", headers=headers, timeout=60)
        resp.raise_for_status()
        return {"status": "success", "agent": resp.json()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Get agent details failed: {e}")       