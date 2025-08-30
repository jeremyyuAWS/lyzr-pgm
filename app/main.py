from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from pathlib import Path
import os, tempfile, httpx, json, yaml
from datetime import datetime
from app.services.agent_creator import create_manager_with_roles
from src.utils.normalize_output import normalize_inference_output
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Agent Orchestrator API")

# -----------------------------
# 1) Create agents
# -----------------------------
@app.post("/create-agents/")
async def create_agents_from_file(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    lyzr_api_key: str = Form(...)
):
    if not lyzr_api_key:
        raise HTTPException(status_code=400, detail="Missing LYZR_API_KEY in request")

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai") + "/v3/agents/"
    headers = {"x-api-key": lyzr_api_key, "Content-Type": "application/json"}
    log_file = Path("logs/created_agents.jsonl")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
        tmp.write(await file.read())
        yaml_path = Path(tmp.name)

    result = create_manager_with_roles(yaml_path, headers, base_url, log_file)

    # Store agent refs in Supabase
    try:
        for role in result.get("roles", []):
            supabase.table("agents").insert({
                "id": role["agent_id"],
                "user_id": user_id,
                "name": role["name"],
                "type": "role",
                "created_at": datetime.utcnow().isoformat()
            }).execute()

        manager = result.get("manager")
        if manager:
            supabase.table("agents").insert({
                "id": manager["agent_id"],
                "user_id": user_id,
                "name": manager["name"],
                "type": "manager",
                "created_at": datetime.utcnow().isoformat()
            }).execute()
    except Exception as e:
        print("⚠️ Supabase insert failed:", e)

    return {"status": "success", "created": result}


# -----------------------------
# 2) Run inference
# -----------------------------
class InferencePayload(BaseModel):
    agent_id: str
    message: str
    user_id: str
    lyzr_api_key: str  # 👈 frontend must provide

@app.post("/run-inference/")
async def run_inference(req: InferencePayload, format: str = "json"):
    if not req.lyzr_api_key:
        raise HTTPException(status_code=400, detail="Missing LYZR_API_KEY in request")

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    headers = {"x-api-key": req.lyzr_api_key, "Content-Type": "application/json"}

    payload = {
        "agent_id": req.agent_id,
        "user_id": req.user_id,
        "session_id": f"session-{os.urandom(4).hex()}",
        "message": req.message,
        "features": [],
        "tools": []
    }

    try:
        resp = httpx.post(f"{base_url}/v3/inference/chat/", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data.get("response", "")

        parsed = normalize_inference_output(raw_text, Path("output") / req.agent_id)

        supabase.table("runs").insert({
            "agent_id": req.agent_id,
            "user_id": req.user_id,
            "message": req.message,
            "raw_response": raw_text,
            "normalized": parsed,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        return {
            "status": "success",
            "agent_id": req.agent_id,
            "raw": raw_text,
            "normalized": parsed if format == "json" else yaml.safe_dump(parsed, sort_keys=False)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
