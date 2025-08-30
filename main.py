import os
import json
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yaml

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
    allow_origins=["*"],   # TODO: Restrict in prod
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
    manager_yaml: str | None = None
    usecase_yaml: str | None = None


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
        # --------------------
        # RUN MANAGER + USECASE YAML
        # --------------------
        if req.action == "run_manager_with_usecases" and req.manager_yaml and req.usecase_yaml:
            resp = client.run_manager_with_usecases(req.manager_yaml, req.usecase_yaml, save_outputs=True)
            return resp

        elif req.action == "list_agents":
            return {"ok": True, "agents": client.list_agents()}

        elif req.action == "delete_all_agents":
            return {"ok": True, "response": client.delete_all_agents()}

        elif req.action == "delete_agent" and req.agent_id:
            return {"ok": True, "response": client.delete_agent(req.agent_id)}

        elif req.action == "run_inference" and req.agent_id and req.message:
            return {"ok": True, "response": client.run_inference(req.agent_id, req.message)}

        elif req.action == "create_agent_from_yaml" and req.yaml_input:
            yaml_text = _load_yaml(req.yaml_input)
            return {"ok": True, "response": client.create_agent_from_yaml(yaml_text, is_path=False)}

        # --------------------
        # Create manager with roles (roles-first → manager)
        # --------------------
        elif req.action in ["create_manager_with_roles", "create_manager"]:
            yaml_source = req.manager_yaml or req.yaml_input
            if not yaml_source:
                raise HTTPException(status_code=400, detail="manager_yaml or yaml_input is required")

            # ⚡ Roles-first flow handled inside client
            resp = client.create_manager_with_roles(yaml_source, is_path=False)
            logger.info(f"✅ {req.action} -> {resp}")

            # Normalize shape for frontend
            return {
                "ok": resp.get("ok", False),
                "manager": resp.get("data"),   # manager object
                "roles": resp.get("roles", []),  # role objects
                "error": resp.get("error") if not resp.get("ok") else None
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action or missing params: {req.action}")

    except Exception as e:
        logger.error(f"❌ Error handling action {req.action}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --------------------
# Helpers
# --------------------
def _load_yaml(yaml_input: str) -> str:
    """Load YAML from file path or use raw string"""
    path = Path(yaml_input)
    if path.exists():
        with open(path, "r") as f:
            return f.read()
    return yaml_input
