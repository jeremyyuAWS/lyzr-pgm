import os
import json
import logging
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yaml

from src.api.client import LyzrAPIClient
from src.utils.payload_normalizer import normalize_payload

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
    if manager_name in cache:
        return cache[manager_name].get("manager_id")
    return None

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
        # RUN MANAGER + USECASE YAML (with caching + saving artifacts)
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
                payload = normalize_payload(manager_obj)
                resp = client.create_agent(payload)
                if not resp.get("ok"):
                    raise HTTPException(status_code=500, detail=f"Failed to create manager: {resp}")
                manager_id = resp["data"].get("_id") if "data" in resp else None
                if not manager_id:
                    raise HTTPException(status_code=500, detail="Manager ID missing after creation")
                set_cached_manager(manager_name, manager_id)
                logger.info(f"✅ Cached new manager {manager_name} -> {manager_id}")

            # 2. Save manager + roles YAMLs
            _save_manager_and_roles(manager_name, manager_yaml_text, manager_obj)

            # 3. Run usecases
            usecase_yaml_text = _load_yaml(req.usecase_yaml)
            usecases = yaml.safe_load(usecase_yaml_text).get("use_cases", [])

            results = []
            for case in usecases:
                name = case.get("name")
                desc = case.get("description")
                logger.info(f"📥 Running use case: {name}")
                resp = client.run_inference(manager_id, desc)

                # Save inference output
                _save_usecase_output(manager_name, name, resp)

                results.append({"use_case": name, "response": resp})

            return {
                "ok": True,
                "manager_id": manager_id,
                "results": results,
            }

        # --------------------
        # List agents
        # --------------------
        elif req.action == "list_agents":
            return {"ok": True, "agents": client.list_agents()}

        # --------------------
        # Delete all
        # --------------------
        elif req.action == "delete_all_agents":
            return {"ok": True, "response": client.delete_all_agents()}

        # --------------------
        # Delete one
        # --------------------
        elif req.action == "delete_agent" and req.agent_id:
            return {"ok": True, "response": client.delete_agent(req.agent_id)}

        # --------------------
        # Run inference
        # --------------------
        elif req.action == "run_inference" and req.agent_id and req.message:
            return {"ok": True, "response": client.run_inference(req.agent_id, req.message)}

        # --------------------
        # Create agent from YAML
        # --------------------
        elif req.action == "create_agent_from_yaml" and req.yaml_input:
            yaml_text = _load_yaml(req.yaml_input)
            return {"ok": True, "response": client.create_agent_from_yaml(yaml_text, is_path=False)}

        # --------------------
        # Create manager with roles (explicit)
        # --------------------
        elif req.action == "create_manager_with_roles" and req.manager_yaml:
            yaml_text = _load_yaml(req.manager_yaml)
            yaml_obj = yaml.safe_load(yaml_text)
            payload = normalize_payload(yaml_obj)
            resp = client.create_agent(payload)
            logger.info(f"✅ create_manager_with_roles -> {resp}")
            return {"ok": True, "response": resp}

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


def _save_manager_and_roles(manager_name: str, manager_yaml_text: str, manager_obj: dict):
    """Save manager YAML + role YAMLs into output/{manager}/"""
    safe_manager = manager_name.replace(" ", "_")
    outdir = Path("output") / safe_manager
    outdir.mkdir(parents=True, exist_ok=True)

    # Save Manager YAML
    (outdir / f"{safe_manager}_manager.yaml").write_text(manager_yaml_text)
    logger.info(f"💾 Saved Manager YAML -> {outdir}/{safe_manager}_manager.yaml")

    # Save Role YAMLs if defined under managed_agents
    if "managed_agents" in manager_obj:
        for role in manager_obj["managed_agents"]:
            role_file = role.get("file")
            role_yaml = None
            if role_file and Path(role_file).exists():
                role_yaml = Path(role_file).read_text()
            elif "yaml" in role:
                role_yaml = role["yaml"]

            if role_yaml:
                role_name = Path(role_file).stem if role_file else role.get("name", "role")
                safe_role = role_name.replace(" ", "_")
                (outdir / f"{safe_role}.yaml").write_text(role_yaml)
                logger.info(f"💾 Saved Role YAML -> {outdir}/{safe_role}.yaml")


def _save_usecase_output(manager_name: str, usecase_name: str, resp: dict):
    """Save each use case result to output/{manager}/{usecase}.json"""
    safe_manager = manager_name.replace(" ", "_")
    safe_usecase = usecase_name.replace(" ", "_")

    outdir = Path("output") / safe_manager
    outdir.mkdir(parents=True, exist_ok=True)

    outfile = outdir / f"{safe_usecase}.json"
    with open(outfile, "w") as f:
        json.dump(resp, f, indent=2)

    logger.info(f"💾 Saved use case {usecase_name} -> {outfile}")
