import os, tempfile, json, yaml, logging, uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form, Query
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
app = FastAPI(title="Agent Orchestrator API (No-Auth Dev Mode, User Key)")

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


# -----------------------------
# Debug + health
# -----------------------------
@app.get("/me")
async def read_me():
    return {"status": "ok", "user_id": "demo-user", "claims": {"role": "tester"}}


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Agent Orchestrator API (No-Auth Dev Mode, User Key)"}

# -----------------------------
# Endpoints
# -----------------------------
@app.get("/studio-agents/")
async def list_studio_agents(api_key: str = Query(..., description="User-provided Lyzr Studio API key")):
    """
    Test connectivity to Lyzr Studio using a user-provided API key.
    Frontend can call /studio-agents?api_key=<key>.
    """
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        resp = httpx.get("https://agent-prod.studio.lyzr.ai/v3/agents/", headers=headers, timeout=30)
        resp.raise_for_status()
        return {"status": "success", "agents": resp.json()}
    except httpx.HTTPStatusError as http_err:
        logger.error(f"Studio returned {http_err.response.status_code}: {http_err.response.text}")
        raise HTTPException(
            status_code=http_err.response.status_code,
            detail=f"Studio API error: {http_err.response.text}"
        )
    except Exception as e:
        logger.exception("❌ studio connectivity failed")
        raise HTTPException(status_code=500, detail=f"Studio connectivity failed: {e}")


@app.post("/create-agents/")
async def create_agents_from_file(
    file: UploadFile = File(...),
    tz_name: str = Form("America/Los_Angeles"),
    api_key: str = Query(..., description="User-provided Lyzr Studio API key")
):
    """
    Create Manager + Role agents from a YAML file using a user-provided API key.
    tz_name is provided by user via dropdown (default: PST).
    """
    rid = get_request_id()
    trace(f"Received /create-agents request tz={tz_name}", {"request_id": rid})

    client = LyzrAPIClient(api_key=api_key)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
        tmp.write(await file.read())
        yaml_path = Path(tmp.name)

    try:
        result = create_manager_with_roles(client, yaml_path)
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
async def run_inference(
    req: InferencePayload,
    api_key: str = Query(..., description="User-provided Lyzr Studio API key")
):
    """
    Run inference against a given agent_id using a user-provided API key.
    """
    rid = get_request_id()
    trace(f"Run inference for agent_id={req.agent_id}", {"request_id": rid})

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

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
        normalized = normalize_inference_output(json.dumps(raw), Path("outputs/demo-user"))
        return {"status": "success", "agent_id": req.agent_id, "raw": raw, "normalized": normalized}
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
    print(f"📥 Incoming {request.method} {request.url} - Body: {body.decode()}")
    response = await call_next(request)
    print(f"📤 Response {response.status_code}")
    return response
