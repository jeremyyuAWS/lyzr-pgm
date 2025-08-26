# scripts/run_use_cases.py

import os
import yaml
import json
import httpx
from pathlib import Path
from dotenv import load_dotenv
from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager

# Load .env with API key
load_dotenv()

BASE_URL = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai/v3")
API_KEY = os.getenv("LYZR_API_KEY")

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
}

SESSION_PREFIX = "usecases-session"


def recreate_architect_manager():
    """Recreate the Architect Manager (and its roles) fresh each run."""
    client = LyzrAPIClient(debug=True)
    manager = AgentManager(client)
    mgr_yaml = "agents/managers/ARCHITECT_MANAGER.yaml"
    mgr_id = manager.create_manager_with_roles(mgr_yaml)
    print(f"🤖 Recreated ARCHITECT_MANAGER agent → ID {mgr_id}")
    return mgr_id

def call_agent(agent_id: str, session_id: str, message: str):
    """Call inference/chat endpoint with a use case message, stripping unsupported fields."""
    payload = {
        "user_id": "demo-user",
        "agent_id": agent_id,
        "session_id": session_id,
        "message": message,
        # Minimal valid keys only (match your working curl!)
        "system_prompt_variables": {},
        "filter_variables": {}
    }

    print("🔍 Payload being sent:\n", json.dumps(payload, indent=2))

    r = httpx.post(
        f"{BASE_URL}/v3/inference/chat/",
        headers=HEADERS,
        json=payload,
        timeout=120.0
    )

    # Instead of raising, print out the response body on error
    if r.status_code != 200:
        print(f"❌ Inference failed with {r.status_code}")
        print("🔍 Response text:\n", r.text)
        return {"error": f"Bad request {r.status_code}", "detail": r.text}

    data = r.json()

    # Try parsing JSON embedded in "response" or "agent_response"
    raw_response = data.get("response") or data.get("agent_response")
    if not raw_response:
        return {"error": "No response from agent", "raw": data}

    try:
        return json.loads(raw_response)
    except Exception:
        try:
            return yaml.safe_load(raw_response)
        except Exception:
            return {"raw_response": raw_response}


def save_workflow(use_case_name: str, content: dict):
    """Save parsed content to outputs/<use_case_name>/workflow.yaml"""
    out_dir = Path("outputs") / use_case_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "workflow.yaml"

    with open(out_file, "w") as f:
        yaml.safe_dump(content, f, sort_keys=False)

    print(f"✅ Saved workflow for {use_case_name} → {out_file}")


def main():
    # Recreate Architect Manager first
    agent_id = recreate_architect_manager()

    # Load use cases
    with open("agents/use_cases.yaml", "r") as f:
        use_cases = yaml.safe_load(f)["use_cases"]

    # Iterate through use cases
    for i, case in enumerate(use_cases, 1):
        name = case["name"]
        desc = case["description"]
        session_id = f"{agent_id}-{SESSION_PREFIX}-{i}"

        print(f"\n🚀 Running use case: {name}")
        response = call_agent(agent_id, session_id, desc)

        save_workflow(name, response)


if __name__ == "__main__":
    main()
