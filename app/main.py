# app/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from pathlib import Path
import os, tempfile, httpx, json, yaml

from app.services.agent_creator import create_manager_with_roles
from src.utils.normalize_output import normalize_inference_output

app = FastAPI(title="Agent Orchestrator API")

# -----------------------------
# Supabase Helper
# -----------------------------
async def fetch_user_api_key(user_id: str) -> str:
    """
    Fetch decrypted LYZR API key for a given user_id from Supabase.
    Requires SUPABASE_URL + SUPABASE_SERVICE_KEY env vars.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_service_key:
        raise HTTPException(status_code=500, detail="Missing Supabase configuration")

    headers = {
        "apikey": supabase_service_key,
        "Authorization": f"Bearer {supabase_service_key}",
        "Content-Type": "application/json",
    }

    query = {
        "user_id": f"eq.{user_id}"
    }

    resp = httpx.get(
        f"{supabase_url}/rest/v1/user_profiles_with_decrypted_key",
        headers=headers,
        params=query,
        timeout=30
    )

    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Supabase fetch failed: {resp.text}")

    data = resp.json()
    if not data or "decrypted_api_key" not in data[0]:
        raise HTTPException(status_code=404, detail="No API key found for user")

    return data[0]["decrypted_api_key"]

# -----------------------------
# 1) Create agents
# -----------------------------
@app.post("/create-agents/")
async def create_agents_from_file(user_id: str, file: UploadFile = File(...)):
    api_key = await fetch_user_api_key(user_id)
    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai") + "/v3/agents/"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    log_file = Path("logs/created_agents.jsonl")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp:
        tmp.write(await file.read())
        yaml_path = Path(tmp.name)

    result = create_manager_with_roles(yaml_path, headers, base_url, log_file)
    return {"status": "success", "created": result}

# -----------------------------
# 2) Run inference
# -----------------------------
class InferencePayload(BaseModel):
    user_id: str
    agent_id: str
    message: str

@app.post("/run-inference/")
async def run_inference(req: InferencePayload):
    api_key = await fetch_user_api_key(req.user_id)
    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    payload = {
        "agent_id": req.agent_id,
        "user_id": req.user_id,
        "session_id": f"session-{os.urandom(4).hex()}",
        "message": req.message,
        "features": [],  # keep empty
        "tools": []      # keep empty
    }

    try:
        resp = httpx.post(f"{base_url}/v3/inference/chat/", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()

        raw = resp.json()
        # Normalize output if possible
        normalized = normalize_inference_output(json.dumps(raw), Path("output") / req.agent_id)

        return {
            "status": "success",
            "agent_id": req.agent_id,
            "raw": raw,
            "normalized": normalized
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
