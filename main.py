import os
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.api.client import LyzrAPIClient
import yaml

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
        # LIST AGENTS
        # --------------------
        if req.action == "list_agents":
            resp = client.list_agents()
            logger.info(f"✅ list_agents -> {resp}")
            return {"ok": True, "agents": resp}

        # --------------------
        # DELETE ALL AGENTS
        # --------------------
        elif req.action == "delete_all_agents":
            resp = client.delete_all_agents()
            logger.info(f"✅ delete_all_agents -> {resp}")
            return {"ok": True, "response": resp}

        # --------------------
        # DELETE SINGLE AGENT
        # --------------------
        elif req.action == "delete_agent" and req.agent_id:
            resp = client.delete_agent(req.agent_id)
            logger.info(f"✅ delete_agent {req.agent_id} -> {resp}")
            return {"ok": True, "response": resp}

        # --------------------
        # RUN INFERENCE
        # --------------------
        elif req.action == "run_inference" and req.agent_id and req.message:
            resp = client.run_inference(req.agent_id, req.message)
            logger.info(f"✅ run_inference {req.agent_id} -> {resp}")
            return {"ok": True, "response": resp}

        # --------------------
        # CREATE AGENT FROM YAML
        # --------------------
        elif req.action == "create_agent_from_yaml" and req.yaml_input:
            yaml_text = _load_yaml(req.yaml_input)
            resp = client.create_agent_from_yaml(yaml_text, is_path=False)
            logger.info(f"✅ create_agent_from_yaml -> {resp}")
            return {"ok": True, "response": resp}

        # --------------------
        # CREATE MANAGER WITH ROLES FROM YAML
        # --------------------
        elif req.action == "create_manager_with_roles" and req.manager_yaml:
            yaml_text = _load_yaml(req.manager_yaml)
            resp = client.create_manager_with_roles(yaml_text, is_path=False)
            logger.info(f"✅ create_manager_with_roles -> {resp}")
            return {"ok": True, "response": resp}

        # --------------------
        # RUN MANAGER + USECASE YAML (like run_list_iterate)
        # --------------------
        elif req.action == "run_manager_with_usecases" and req.manager_yaml and req.usecase_yaml:
            # 1. Load Manager YAML
            manager_yaml_text = _load_yaml(req.manager_yaml)
            manager_resp = client.create_manager_with_roles(manager_yaml_text, is_path=False)

            if not manager_resp.get("ok"):
                raise HTTPException(status_code=500, detail=f"Failed to create manager: {manager_resp}")

            manager_id = manager_resp["data"]["_id"] if "data" in manager_resp else None
            if not manager_id:
                raise HTTPException(status_code=500, detail="Manager ID missing after creation")

            # 2. Load Usecase YAML
            usecase_yaml_text = _load_yaml(req.usecase_yaml)
            usecases = yaml.safe_load(usecase_yaml_text).get("use_cases", [])

            # 3. Run Inference for each usecase
            results = []
            for case in usecases:
                name = case.get("name")
                desc = case.get("description")
                logger.info(f"📥 Running use case: {name}")
                resp = client.run_inference(manager_id, desc)
                results.append({"use_case": name, "response": resp})

            return {
                "ok": True,
                "manager_id": manager_id,
                "results": results,
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action or missing params: {req.action}")

    except Exception as e:
        logger.error(f"❌ Error handling action {req.action}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --------------------
# Helper
# --------------------
def _load_yaml(yaml_input: str) -> str:
    """Load YAML from file path or use raw string"""
    path = Path(yaml_input)
    if path.exists():
        with open(path, "r") as f:
            return f.read()
    return yaml_input
