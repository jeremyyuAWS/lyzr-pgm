import os
import json
import logging
from pathlib import Path
from datetime import datetime
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
# Cache Helpers
# --------------------
CACHE_FILE = Path(".manager_cache.json")

def load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}

def save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

def get_cached_manager(manager_name: str) -> str | None:
    cache = load_cache()
    return cache.get(manager_name)

def set_cached_manager(manager_name: str, manager_id: str):
    cache = load_cache()
    cache[manager_name] = {
        "manager_id": manager_id,
        "cached_at": datetime.utcnow().isoformat()
    }
    save_cache(cache)


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
        # RUN MANAGER + USECASE YAML (with caching)
        # --------------------
        if req.action == "run_manager_with_usecases" and req.manager_yaml and req.usecase_yaml:
            manager_yaml_text = _load_yaml(req.manager_yaml)
            manager_obj = yaml.safe_load(manager_yaml_text)
            manager_name = manager_obj.get("name")

            # 1. Check cache
            manager_id = get_cached_manager(manager_name)
            if manager_id:
                logger.info(f"⚡ Using cached manager {manager_name} -> {manager_id}")
            else:
                # Deploy new manager
                resp = client.create_manager_with_roles(manager_yaml_text, is_path=False)
                if not resp.get("ok"):
                    raise HTTPException(status_code=500, detail=f"Failed to create manager: {resp}")
                manager_id = resp["data"]["_id"] if "data" in resp else None
                if not manager_id:
                    raise HTTPException(status_code=500, detail="Manager ID missing after creation")
                set_cached_manager(manager_name, manager_id)
                logger.info(f"✅ Cached new manager {manager_name} -> {manager_id}")

            # 2. Run usecases
            usecase_yaml_text = _load_yaml(req.usecase_yaml)
            usecases = yaml.safe_load(usecase_yaml_text).get("use_cases", [])

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

        # --------------------
        # Other existing actions...
        # --------------------
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

        elif req.action == "create_manager_with_roles" and req.manager_yaml:
            yaml_text = _load_yaml(req.manager_yaml)
            return {"ok": True, "response": client.create_manager_with_roles(yaml_text, is_path=False)}

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
