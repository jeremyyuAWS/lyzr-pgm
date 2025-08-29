# runme2.py
import os
import sys
import json
import yaml
import uuid
import httpx
from datetime import datetime
import pytz

# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------

def to_pst_str() -> str:
    pst = pytz.timezone("America/Los_Angeles")
    return datetime.now(pst).strftime("%Y-%m-%d %I:%M %p %Z")

def timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def load_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def save_json(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ------------------------------------------------------------------------------
# API Calls
# ------------------------------------------------------------------------------

def create_agent(manager_yaml: dict) -> dict:
    """Register manager agent with Lyzr API."""
    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    api_key = os.getenv("LYZR_API_KEY")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    url = f"{base_url}/v3/agents/"
    print(f"📤 Creating manager agent → {url}")

    r = httpx.post(url, headers=headers, json=manager_yaml, timeout=30)
    if r.status_code != 200:
        print(f"❌ Manager creation failed [{r.status_code}]: {r.text}")
        sys.exit(1)

    data = r.json().get("data", {})
    agent_id = data.get("_id") or data.get("agent_id")
    if not agent_id:
        print(f"⚠️ Manager created but no agent_id in response: {data}")
        sys.exit(1)

    print(f"🤖 Created manager agent {manager_yaml.get('name')} "
          f"[{agent_id} | {to_pst_str()}]")
    return {**manager_yaml, "agent_id": agent_id}

def run_inference(agent: dict, usecase_file: str) -> dict:
    """Send use case content to agent and return raw response."""
    with open(usecase_file, "r") as f:
        usecase_text = f.read().strip()

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    api_key = os.getenv("LYZR_API_KEY")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    agent_id = agent["agent_id"]
    session_id = f"{agent_id}-{uuid.uuid4().hex[:8]}"

    payload = {
        "user_id": os.getenv("LYZR_USER_ID", "demo-user"),
        "system_prompt_variables": {},
        "agent_id": agent_id,
        "session_id": session_id,
        "message": usecase_text,
        "filter_variables": {},
        "features": [],
        "assets": []
    }

    url = f"{base_url}/v3/inference/chat/"
    print(f"📡 Running inference with agent {agent_id}…")

    r = httpx.post(url, headers=headers, json=payload, timeout=90)
    if r.status_code != 200:
        print(f"❌ Inference failed [{r.status_code}]: {r.text}")
        sys.exit(1)

    return r.json()

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python runme2.py <manager_yaml_path> <usecase_file>")
        sys.exit(1)

    manager_yaml_path = sys.argv[1]      # e.g. output/YAML_COMPOSER_MANAGER_v1.yaml
    usecase_file = sys.argv[2]           # e.g. agents/use_cases_hr.yaml

    manager_yaml = load_yaml(manager_yaml_path)
    agent = create_agent(manager_yaml)
    resp = run_inference(agent, usecase_file)

    # Save raw response with timestamp
    out_path = f"output/raw_response_{timestamp_str()}.json"
    save_json(resp, out_path)
    print(f"💾 Saved raw response → {out_path}")
