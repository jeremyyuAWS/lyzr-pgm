import os, tempfile, json, yaml, logging, uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
import httpx

# from app.services.agent_creator import create_manager_with_roles
from scripts.create_manager_with_roles import create_manager_with_roles
from src.utils.normalize_output import normalize_inference_output
from backend.auth_middleware import get_current_user
from backend.runner import run_use_cases_with_manager
from fastapi import Body
from backend.schemas.agent_action import AgentActionRequest
from fastapi import UploadFile, File, HTTPException, Depends
import yaml
from src.api.client import LyzrAPIClient

# -----------------------------
# Environment
# -----------------------------
load_dotenv()
print("🔍 Loaded SUPABASE_JWT_SECRET (first 8 chars):", os.getenv("SUPABASE_JWT_SECRET", "")[:8])

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
app = FastAPI(title="Agent Orchestrator API with Auth")

# -----------------------------
# CORS
# -----------------------------
origins = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
if not origins or origins == [""]:
    origins = ["http://localhost:5173", "https://lyzr-pgm.onrender.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 🔑 open for now, restrict later
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
# Helpers
# -----------------------------
def get_request_id() -> str:
    return uuid.uuid4().hex[:8]

def get_lyzr_api_key_for_user(user_id: str) -> str:
    """Fetch decrypted API key if available, fallback to encrypted key."""
    trace(f"Fetching API key for user {user_id}")
    try:
        resp = (
            supabase.from_("user_profiles_with_decrypted_key")
            .select("decrypted_api_key")
            .eq("id", user_id)
            .execute()
        )
        if resp.data and resp.data[0].get("decrypted_api_key"):
            return resp.data[0]["decrypted_api_key"]

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
        logger.exception("❌ Failed fetching Lyzr API key")
        raise HTTPException(status_code=400, detail=f"Failed to fetch Lyzr API key: {e}")

# -----------------------------
# Debug + health
# -----------------------------
@app.get("/debug-token")
async def debug_token(request: Request):
    return {"auth_header": request.headers.get("Authorization")}

@app.get("/me")
async def read_me(current_user: dict = Depends(get_current_user)):
    return {"status": "ok", "user_id": current_user["user_id"], "claims": current_user["claims"]}

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Agent Orchestrator API"}

# -----------------------------
# Endpoints
# -----------------------------
@app.post("/agent-action/")
async def agent_action(request: AgentActionRequest):
    """
    Legacy: Create manager + roles from a YAML path/string
    """
    rid = get_request_id()
    trace("Received /agent-action request", {"request_id": rid})
    trace(f"Payload: {request.dict()}", {"request_id": rid})

    try:
        result = create_manager_with_roles(request.file)
        return {
            "status": "success",
            "created": {"manager": result, "roles": result.get("roles", [])}
        }
    except Exception as e:
        logger.exception("❌ agent_action failed")
        raise HTTPException(status_code=500, detail=f"agent_action failed: {e}")


@app.post("/run-use-cases/")
async def run_use_cases(manager_id: str, current_user: dict = Depends(get_current_user)):
    rid = get_request_id()
    trace(f"Run use cases with manager_id={manager_id}", {"request_id": rid})

    api_key = get_lyzr_api_key_for_user(current_user["user_id"])
    try:
        results = run_use_cases_with_manager(manager_id, api_key)
        trace(f"Use cases completed. Count={len(results)}", {"request_id": rid})
        return {"status": "success", "results": results}
    except Exception as e:
        logger.exception("❌ run_use_cases failed")
        raise HTTPException(status_code=500, detail=f"Run use cases failed: {e}")

@app.post("/create-agents/")
async def create_agents_from_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Create manager + roles from uploaded YAML definition."""
    user_id = current_user["user_id"]
    api_key = get_lyzr_api_key_for_user(user_id)

    try:
        # Load YAML from uploaded file
        raw_content = await file.read()
        yaml_dict = yaml.safe_load(raw_content)

        if not yaml_dict or "manager" not in yaml_dict:
            raise HTTPException(
                status_code=400,
                detail="Uploaded YAML must contain a top-level 'manager' key"
            )

        debug = os.getenv("LYZR_DEBUG", "0") == "1"
        client = LyzrAPIClient(api_key=api_key, debug=debug, timeout=180)

        # Pass dict instead of Path
        result = create_manager_with_roles(client, yaml_dict)

        return {"status": "success", "created": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create agents failed: {e}")

# -----------------------------
# Inference
# -----------------------------
class InferencePayload(BaseModel):
    agent_id: str
    message: str

@app.post("/run-inference/")
async def run_inference(req: InferencePayload, current_user: dict = Depends(get_current_user)):
    rid = get_request_id()
    trace(f"Run inference for agent_id={req.agent_id}", {"request_id": rid})

    api_key = get_lyzr_api_key_for_user(current_user["user_id"])
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "agent_id": req.agent_id,
        "user_id": current_user["user_id"],
        "session_id": f"{req.agent_id}-{os.urandom(4).hex()}",
        "message": req.message,
        "features": [],
        "tools": [],
    }

    try:
        resp = httpx.post(
            "https://agent-prod.studio.lyzr.ai/v3/inference/chat/",
            headers=headers,
            json=payload,
            timeout=60,
        )
        trace(f"Studio response status={resp.status_code}", {"request_id": rid})
        resp.raise_for_status()

        raw = resp.json()
        normalized = normalize_inference_output(json.dumps(raw), Path(f"outputs/{current_user['user_id']}"))
        return {"status": "success", "agent_id": req.agent_id, "raw": raw, "normalized": normalized}
    except Exception as e:
        logger.exception("❌ run_inference failed")
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

# -----------------------------
# Studio agent management
# -----------------------------
@app.get("/list-agents/")
async def list_agents(current_user: dict = Depends(get_current_user)):
    rid = get_request_id()
    trace("Received /list-agents request", {"request_id": rid})
    # TODO: Replace with real lookup logic
    return {"status": "success", "agents": ["agent-1", "agent-2"]}


# (a) List agents
@app.get("/studio-agents/")
async def list_studio_agents(current_user: dict = Depends(get_current_user)):
    rid = get_request_id()
    trace("Listing Studio agents", {"request_id": rid})

    api_key = get_lyzr_api_key_for_user(current_user["user_id"])
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        resp = httpx.get("https://agent-prod.studio.lyzr.ai/v3/agents/", headers=headers, timeout=60)
        trace(f"Studio agents response {resp.status_code}", {"request_id": rid})
        resp.raise_for_status()
        return {"status": "success", "agents": resp.json()}
    except Exception as e:
        logger.exception("❌ list_studio_agents failed")
        raise HTTPException(status_code=500, detail=f"Studio list agents failed: {e}")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    body = await request.body()
    print(f"📥 Incoming {request.method} {request.url} - Body: {body.decode()}")
    response = await call_next(request)
    print(f"📤 Response {response.status_code}")
    return response
