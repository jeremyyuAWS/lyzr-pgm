from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import os, tempfile, httpx, json, yaml
from supabase import create_client, Client

from app.services.agent_creator import create_manager_with_roles
from src.utils.normalize_output import normalize_inference_output
from backend.auth_middleware import get_current_user

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
        "http://localhost:5173",       # Local dev
        "https://lyzr-pgm.onrender.com"  # Render backend
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 🔑 open for now
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
    """Fetch decrypted API key if available, fallback to encrypted key."""
    try:
        # Try the decrypted view first
        resp = (
            supabase.from_("user_profiles_with_decrypted_key")
            .select("decrypted_api_key")
            .eq("id", user_id)
            .execute()
        )
        if resp.data and resp.data[0].get("decrypted_api_key"):
            return resp.data[0]["decrypted_api_key"]

        # Fallback: get encrypted key from user_profiles
        fallback = (
            supabase.from_("user_profiles")
            .select("lyzr_api_key")
            .eq("id", user_id)
            .execute()
        )
        if fallback.data and fallback.data[0].get("lyzr_api_key"):
            return fallback.data[0]["lyzr_api_key"]

        raise ValueError(f"No decrypted or encrypted API key found for user {user_id}")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch Lyzr API key: {e}")


# -----------------------------
# Debug + health endpoints
# -----------------------------
@app.get("/debug-token")
async def debug_token(request: Request):
    auth = request.headers.get("Authorization")
    return {"auth_header": auth}

@app.get("/me")
async def read_me(current_user: dict = Depends(get_current_user)):
    return {"status": "ok", "user_id": current_user["user_id"], "claims": current_user["claims"]}

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Agent Orchestrator API"}

# -----------------------------
# 1) Create agents (from YAML upload)
# -----------------------------
@app.post("/create-agents/")
async def create_agents_from_file(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    api_key = get_lyzr_api_key_for_user(user_id)

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai") + "/v3/agents/"
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
# 2) Run inference (your own deployed agents)
# -----------------------------
class InferencePayload(BaseModel):
    agent_id: str
    message: str

@app.post("/run-inference/")
async def run_inference(req: InferencePayload, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    api_key = get_lyzr_api_key_for_user(user_id)

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
        resp = httpx.post("https://agent-prod.studio.lyzr.ai/v3/inference/chat/", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        raw = resp.json()
        normalized = normalize_inference_output(json.dumps(raw), Path(f"outputs/{user_id}"))
        return {"status": "success", "agent_id": req.agent_id, "raw": raw, "normalized": normalized}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

# -----------------------------
# 3) Manage user’s Studio agents
# -----------------------------

# (a) List all agents
@app.get("/studio-agents/")
async def list_studio_agents(current_user: dict = Depends(get_current_user)):
    api_key = get_lyzr_api_key_for_user(current_user["user_id"])
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        resp = httpx.get("https://agent-prod.studio.lyzr.ai/v3/agents/", headers=headers, timeout=60)
        resp.raise_for_status()
        return {"status": "success", "agents": resp.json()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Studio list agents failed: {e}")


# (b) Get details of one agent
@app.get("/studio-agents/{agent_id}")
async def get_studio_agent(agent_id: str, current_user: dict = Depends(get_current_user)):
    api_key = get_lyzr_api_key_for_user(current_user["user_id"])
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        # v2 endpoint for details
        resp = httpx.get(f"https://agent-prod.studio.lyzr.ai/v2/agent/{agent_id}", headers=headers, timeout=60)
        resp.raise_for_status()
        return {"status": "success", "agent": resp.json()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Studio get agent failed: {e}")


# (c) Chat with any agent
class StudioChatPayload(BaseModel):
    message: str

@app.post("/studio-agents/{agent_id}/chat")
async def chat_with_studio_agent(agent_id: str, body: StudioChatPayload, current_user: dict = Depends(get_current_user)):
    api_key = get_lyzr_api_key_for_user(current_user["user_id"])
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    payload = {
        "user_id": current_user["claims"].get("email", current_user["user_id"]),
        "system_prompt_variables": {},
        "agent_id": agent_id,
        "session_id": f"{agent_id}-{os.urandom(6).hex()}",
        "message": body.message,
        "filter_variables": {},
        "features": [],
        "assets": []
    }

    try:
        resp = httpx.post("https://agent-prod.studio.lyzr.ai/v3/inference/chat/", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Studio chat failed: {e}")
