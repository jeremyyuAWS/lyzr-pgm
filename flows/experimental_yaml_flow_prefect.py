import os
import sys
import json
import uuid
import yaml
import httpx
from datetime import datetime
import pytz

from prefect import flow, task


# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------

def to_pst_str() -> str:
    pst = pytz.timezone("America/Los_Angeles")
    return datetime.now(pst).strftime("%Y-%m-%d %I:%M %p %Z")


def save_json(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def save_yaml(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, sort_keys=False)


# ------------------------------------------------------------------------------
# Tasks
# ------------------------------------------------------------------------------

@task
def load_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


@task
def create_manager(manager_yaml: dict) -> dict:
    """Register manager agent with Lyzr API"""
    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    api_key = os.getenv("LYZR_API_KEY")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    url = f"{base_url}/v3/agents/"
    print(f"📤 Sending manager YAML → {url}")
    print(json.dumps(manager_yaml, indent=2))  # Debug print

    try:
        r = httpx.post(url, headers=headers, json=manager_yaml, timeout=30)
        if r.status_code != 200:
            print(f"❌ Manager creation failed [{r.status_code}]: {r.text}")
            return {}

        data = r.json().get("data", {})
        agent_id = data.get("_id") or data.get("agent_id")
        if not agent_id:
            print(f"⚠️ Manager created but no agent_id in response: {data}")
            return {}

        print(f"🤖 Created manager agent {manager_yaml.get('name')} [{agent_id} | {to_pst_str()}]")
        return data
    except Exception as e:
        print(f"❌ Manager creation failed: {e}")
        return {}


@task
def run_inference(manager: dict, usecase_file: str) -> dict:
    """Call Lyzr inference/chat API with manager agent and use case text."""
    with open(usecase_file, "r") as f:
        usecase_text = f.read().strip()

    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    api_key = os.getenv("LYZR_API_KEY")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    agent_id = manager.get("_id") or manager.get("agent_id")
    if not agent_id:
        raise ValueError("Manager creation response missing agent_id")

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
    print(f"📡 Calling {url} with agent {agent_id}...")

    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=90)
        if r.status_code != 200:
            print(f"❌ Inference failed [{r.status_code}]: {r.text}")
            return {}

        resp = r.json()
        print("✅ Inference complete")
        save_json(resp, "output/raw_response.json")
        return resp.get("data", resp)
    except Exception as e:
        print(f"❌ Inference failed: {e}")
        return {"error": str(e)}


@task
def parse_response(resp: dict) -> dict:
    """Parse JSON response from manager to extract workflow + agents"""
    if not resp or "error" in resp:
        print("❌ Manager failed: Empty or error response")
        return {}

    try:
        if isinstance(resp, str):
            resp = json.loads(resp)

        workflow_name = resp.get("workflow_name")
        workflow_yaml = resp.get("workflow_yaml")
        agents = resp.get("agents", [])

        if not workflow_name or not workflow_yaml:
            raise ValueError("Response missing expected keys")

        parsed = {
            "workflow_name": workflow_name,
            "workflow_yaml": yaml.safe_load(workflow_yaml),
            "agents": []
        }

        for a in agents:
            parsed["agents"].append({
                "name": a.get("name"),
                "type": a.get("type"),
                "yaml": yaml.safe_load(a.get("yaml")) if a.get("yaml") else {}
            })

        return parsed
    except Exception as e:
        print(f"❌ Manager failed while parsing: {e}")
        return {}


@task
def export_results(parsed: dict):
    """Save workflow + agent YAMLs to /output folder"""
    if not parsed:
        return

    os.makedirs("output", exist_ok=True)

    wf_file = f"output/{parsed['workflow_name']}.yaml"
    save_yaml(parsed["workflow_yaml"], wf_file)
    print(f"💾 Saved workflow YAML → {wf_file}")

    for agent in parsed["agents"]:
        name = agent["name"]
        yaml_file = f"output/{name}.yaml"
        save_yaml(agent["yaml"], yaml_file)
        print(f"💾 Saved agent YAML → {yaml_file}")


# ------------------------------------------------------------------------------
# Prefect Flow
# ------------------------------------------------------------------------------

@flow(name="Experimental YAML Flow v.4")
def experimental_yaml_flow(manager_yaml_path: str, usecase_file: str):
    manager_yaml = load_yaml(manager_yaml_path)
    manager = create_manager(manager_yaml)
    if not manager:
        raise ValueError("❌ Manager creation failed — stopping flow")

    resp = run_inference(manager, usecase_file)
    parsed = parse_response(resp)
    export_results(parsed)


# ------------------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m flows.experimental_yaml_flow_prefect <manager_yaml> <usecase_file>")
        sys.exit(1)

    manager_yaml_path = sys.argv[1]
    usecase_file = sys.argv[2]

    experimental_yaml_flow(manager_yaml_path, usecase_file)
