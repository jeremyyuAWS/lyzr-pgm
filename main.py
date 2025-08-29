import os
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.api.client import LyzrAPIClient

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
    allow_origins=["*"],   # TODO: Restrict in production
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
            yaml_input = req.yaml_input

            # Detect if yaml_input looks like a file path
            if Path(yaml_input).exists():
                logger.info(f"📄 Loading YAML from file: {yaml_input}")
                with open(yaml_input, "r") as f:
                    yaml_text = f.read()
                resp = client.create_agent_from_yaml(yaml_text, is_path=False)
            else:
                logger.info("📄 Using provided raw YAML string")
                resp = client.create_agent_from_yaml(yaml_input, is_path=False)

            logger.info(f"✅ create_agent_from_yaml -> {resp}")
            return {"ok": True, "response": resp}

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action or missing params: {req.action}")

    except Exception as e:
        logger.error(f"❌ Error handling action {req.action}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
