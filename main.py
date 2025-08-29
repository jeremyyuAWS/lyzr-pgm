import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager  # ✅ added

# --------------------
# Setup Logging
# --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lyzr-pgm")

# --------------------
# FastAPI App
# --------------------
app = FastAPI(title="Lyzr PGM API")

# --------------------
# Enable CORS
# --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # TODO: Restrict to your frontend domain(s) in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------
# Request Model
# --------------------
class AgentActionRequest(BaseModel):
    action: str
    api_key: str | None = None
    agent_id: str | None = None
    message: str | None = None
    yaml_input: str | None = None


# --------------------
# Routes
# --------------------
@app.get("/")
def root():
    return {"ok": True, "message": "Welcome to Lyzr PGM API"}


@app.get("/health")
def health_check():
    return {"ok": True, "message": "FastAPI backend is healthy"}


@app.post("/agent-action/")
def agent_action(req: AgentActionRequest):
    if not req.api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    client = LyzrAPIClient(api_key=req.api_key)
    logger.info(f"▶️ Received action: {req.action}")

    try:
        if req.action == "list_agents":
            resp = client.list_agents()
            logger.info(f"✅ list_agents -> {resp}")
            return {"ok": True, "agents": resp}

        elif req.action == "delete_all_agents":
            resp = client.delete_all_agents()
            logger.info(f"✅ delete_all_agents -> {resp}")
            return {"ok": True, "response": resp}

        elif req.action == "delete_agent" and req.agent_id:
            resp = client.delete_agent(req.agent_id)
            logger.info(f"✅ delete_agent {req.agent_id} -> {resp}")
            return {"ok": True, "response": resp}

        elif req.action == "run_inference" and req.agent_id and req.message:
            resp = client.run_inference(req.agent_id, req.message)
            logger.info(f"✅ run_inference {req.agent_id} -> {resp}")
            return {"ok": True, "response": resp}

        elif req.action == "create_agent_from_yaml" and req.yaml_input:
            resp = client.create_agent_from_yaml(req.yaml_input, is_path=False)
            logger.info(f"✅ create_agent_from_yaml -> {resp}")
            return {"ok": True, "response": resp}

        elif req.action == "create_manager_with_roles" and req.yaml_input:
            manager = AgentManager(client)
            resp = manager.create_manager_with_roles(req.yaml_input)
            logger.info(f"✅ create_manager_with_roles -> {resp}")
            return {"ok": True, "response": resp}

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action or missing params: {req.action}")

    except Exception as e:
        logger.error(f"❌ Error handling action {req.action}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
