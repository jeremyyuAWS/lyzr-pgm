import os, tempfile, json, yaml, logging, uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from scripts.create_manager_with_roles import create_manager_with_roles
from src.utils.normalize_output import normalize_inference_output
from src.api.client import LyzrAPIClient

# -----------------------------
# Environment
# -----------------------------
load_dotenv()
print("🔍 Loaded LYZR_API_KEY (first 8 chars):", os.getenv("LYZR_API_KEY", "")[:8])

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
app = FastAPI(title="Agent Orchestrator API (No-Auth Dev Mode)")

# -----------------------------
# CORS (wide open for dev)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # allow all
    allow_credentials=False,   # must be False with "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Helpers
# -----------------------------
def get_request_id() -> str:
    return uuid.uuid4().hex[:8]

def get_api_client() -> LyzrAPIClient:
    api_key = os.getenv("LYZR_API_KEY")
    if not api_key:
        raise RuntimeError("Missing LYZR_API_KEY in environment")
    return LyzrAPIClient(api_key=api_key)

# -----------------------------
# Debug + health
# -----------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Agent Orchestrator API (No-Auth Dev Mode)"}

# -----------------------------
# Endpoints
# -----------------------------
@app.post("/create-agents/")
async def create_agents_from_file(
    file: UploadFile = File(...),
    tz_name: str = Form("America/Los_Angeles")  # 👈 user picks from dropdown on frontend
):
    """
    Create Manager + Role agents from a YAML file.
    tz_name is provided by user via dropdown (default: PST).
    """
    rid = get_request_id()
    trace(f"Received /create-agents request tz={tz_name}", {"request_id": rid})

    client = get_api_client()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
        tmp.write(await file.read())
        yaml_path = Path(tmp.name)

    try:
        result = create_manager_with_roles(client, yaml_path, tz_name=tz_name)
        return {"status": "success", "created": result}
    except Exception as e:
        logger.exception("❌ create_agents_from_file failed")
        raise HTTPException(status_code=500, detail=f"Create agents failed: {e}")

# -----------------------------
# Inference
# -----------------------------
class InferencePayload(BaseModel):
    agent_id: str
    message: str

@app.post("/run-inference/")
async def run_inference(req: InferencePayload):
    rid = get_request_id()
    trace(f"Run inference for agent_id={req.agent_id}", {"request_id": rid})

    client = get_api_client()
    headers = {"x-api-key": client.api_key, "Content-Type": "application/json"}
    payload = {
        "agent_id": req.agent_id,
        "user_id": "demo-user",
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
        normalized = normalize_inference_output(json.dumps(raw), Path("outputs/demo-user"))
        return {"status": "success", "agent_id": req.agent_id, "raw": raw, "normalized": normalized}
    except Exception as e:
        logger.exception("❌ run_inference failed")
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

# -----------------------------
# Middleware (logs)
# -----------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    body = await request.body()
    print(f"📥 Incoming {request.method} {request.url} - Body: {body.decode()}")
    response = await call_next(request)
    print(f"📤 Response {response.status_code}")
    return response
