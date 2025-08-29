# flows/create_and_infer.py
import os
import json
import uuid
import yaml
import httpx
from pathlib import Path
from datetime import datetime
import pytz

from prefect import flow, task

# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

BASE_URL = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
API_KEY = os.getenv("LYZR_API_KEY")
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}

def to_pst_str() -> str:
    pst = pytz.timezone("America/Los_Angeles")
    return datetime.now(pst).strftime("%Y-%m-%d %I:%M %p %Z")

def timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def save_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_yaml(path: Path) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

# ------------------------------------------------------------------------------
# Tasks
# ------------------------------------------------------------------------------

@task
def create_agent(agent_yaml: dict) -> dict:
    """Register agent with Lyzr API and return response + agent_id."""
    url = f"{BASE_URL}/v3/agents/"
    print(f"📤 Creating agent {agent_yaml.get('name')} → {url}")

    r = httpx.post(url, headers=HEADERS, json=agent_yaml, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"❌ Agent creation failed [{r.status_code}]: {r.text}")

    data = r.json().get("data", {})
    agent_id = data.get("_id") or data.get("agent_id")
    if not agent_id:
        raise RuntimeError(f"⚠️ Created agent but no agent_id in response: {data}")

    print(f"🤖 Created {agent_yaml.get('name')} [{agent_id} | {to_pst_str()}]")
    return {**agent_yaml, "agent_id": agent_id}

@task
def build_message_from_usecase(usecase_yaml: dict) -> str:
    """Flatten use case YAML into a structured message string."""
    parts = []
    if "use_case" in usecase_yaml:
        parts.append(f"Use Case:\n{usecase_yaml['use_case']}")
    if "requirements" in usecase_yaml:
        parts.append(f"\nRequirements:\n{json.dumps(usecase_yaml['requirements'], indent=2)}")
    if "constraints" in usecase_yaml:
        parts.append(f"\nConstraints:\n{json.dumps(usecase_yaml['constraints'], indent=2)}")
    if "acceptance_criteria" in usecase_yaml:
        parts.append(f"\nAcceptance Criteria:\n{json.dumps(usecase_yaml['acceptance_criteria'], indent=2)}")
    return "\n".join(parts)

@task
def run_inference(agent: dict, message: str) -> dict:
    """Call Lyzr inference API with the given agent and message."""
    agent_id = agent.get("agent_id")
    session_id = f"{agent_id}-{uuid.uuid4().hex[:8]}"

    payload = {
        "user_id": os.getenv("LYZR_USER_ID", "demo-user"),
        "system_prompt_variables": {},
        "agent_id": agent_id,
        "session_id": session_id,
        "message": message,
        "filter_variables": {},
        "features": [],
        "assets": []
    }

    url = f"{BASE_URL}/v3/inference/chat/"
    print(f"📡 Running inference with agent {agent_id}…")

    r = httpx.post(url, headers=HEADERS, json=payload, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"❌ Inference failed [{r.status_code}]: {r.text}")

    data = r.json()
    out_file = OUTPUT_DIR / f"inference_raw_{timestamp_str()}.json"
    save_json(data, out_file)
    print(f"💾 Saved raw response → {out_file}")
    return data

# ------------------------------------------------------------------------------
# Prefect Flow
# ------------------------------------------------------------------------------

@flow(name="Create Agents and Run HR Use Case")
def create_and_infer(updateme_file: str, usecase_file: str):
    # 1. Load agent base YAML (UPDATEME)
    agent_def = load_yaml(Path(updateme_file))

    # 2. Create manager agent
    manager = create_agent(agent_def)

    # 3. Load use case YAML
    usecase_yaml = load_yaml(Path(usecase_file))

    # 4. Build message from use case
    message = build_message_from_usecase(usecase_yaml)

    # 5. Run inference
    run_inference(manager, message)

# ------------------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python -m flows.create_and_infer <UPDATEME.yaml> <usecase_file>")
        sys.exit(1)

    create_and_infer(sys.argv[1], sys.argv[2])
