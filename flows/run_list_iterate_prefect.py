# flows/run_list_iterate_prefect.py

import os
import json
from pathlib import Path
from datetime import datetime

import yaml
from prefect import flow, task

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.normalize_output import normalize_inference_output


# -----------------------
# Helper Tasks
# -----------------------

@task
def save_workflow_yaml(yaml_text: str, out_dir: Path, uc_name: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    wf_file = out_dir / f"workflow_{ts}.yaml"
    with open(wf_file, "w") as f:
        f.write(yaml_text)
    print(f"📝 [{uc_name}] Saved workflow YAML → {wf_file}")
    return str(wf_file)


@task
def save_agent_yaml(agent: dict, out_dir: Path, roles_dir: Path, uc_name: str) -> str:
    """Save agent YAML to both use-case output folder and canonical roles dir."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    agent_name = agent.get("name") or f"unnamed_agent_{ts}"
    yaml_text = agent.get("yaml", "")
    if not yaml_text:
        return ""

    # Save into use-case folder
    agent_file = out_dir / f"{agent_name}_{ts}.yaml"
    with open(agent_file, "w") as f:
        f.write(yaml_text)
    print(f"📝 [{uc_name}] Saved agent YAML → {agent_file}")

    # If role, also save into agents/roles
    if "manager" not in agent_name.lower():
        roles_dir.mkdir(parents=True, exist_ok=True)
        role_file = roles_dir / f"{agent_name}.yaml"
        with open(role_file, "w") as f:
            f.write(yaml_text)
        print(f"📂 [{uc_name}] Copied role agent YAML → {role_file}")

    return str(agent_file)


@task
def update_manager_yaml(manager_file: str, role_agents: list[str], uc_name: str) -> str:
    """Append managed_agents section with canonical role paths."""
    with open(manager_file, "r") as f:
        mgr_yaml = yaml.safe_load(f)

    mgr_yaml["managed_agents"] = [
        {
            "file": f"agents/roles/{Path(r).name}",
            "usage_description": f"Auto-linked from {uc_name}",
        }
        for r in role_agents
    ]

    with open(manager_file, "w") as f:
        yaml.safe_dump(mgr_yaml, f, sort_keys=False)

    print(f"🔗 [{uc_name}] Updated Manager {mgr_yaml.get('name','<unknown>')} with {len(role_agents)} managed_agents")
    return manager_file


@task
def normalize_and_save(raw_str: str, out_dir: Path, uc_name: str) -> dict:
    norm = normalize_inference_output(raw_str, out_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    norm_file = out_dir / f"inference_normalized_{ts}.json"
    with open(norm_file, "w") as f:
        json.dump(norm, f, indent=2)
    print(f"✅ [{uc_name}] Normalized inference output saved to {norm_file}")
    return norm


@task
def call_inference(client: LyzrAPIClient, agent_id: str, message: str, uc_name: str) -> dict:
    payload = {
        "user_id": os.getenv("LYZR_USER_ID", "demo-user"),
        "system_prompt_variables": {},
        "agent_id": agent_id,
        "session_id": f"{agent_id}-{os.urandom(4).hex()}",
        "message": message,
        "filter_variables": {},
        "features": [],
        "assets": [],
    }
    print(f"💬 [{uc_name}] Sending inference request")
    return client._request("POST", "/v3/inference/chat/", payload=payload)


# -----------------------
# Flows
# -----------------------

@flow(name="Use Case Flow")
def run_usecase_flow(manager_yaml: str, usecase: dict, save_outputs: bool = True, push: bool = False):
    """Flow for a single use case, with detailed task-level logs."""
    uc_name = usecase.get("name", "unnamed_usecase").replace("_", " ").title()
    print(f"\n🚀 Running use case: {uc_name}")

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)
    manager = AgentManager(client)

    result = manager.create_manager_with_roles(manager_yaml)
    if not result:
        raise RuntimeError("Manager creation failed")

    mgr_id = result["agent_id"]

    out_dir = Path("output") / Path(manager_yaml).stem / uc_name.lower().replace(" ", "_")
    roles_dir = Path("agents/roles")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Call inference
    resp = call_inference.with_options(name=f"Call Inference [{uc_name}]")(client, mgr_id, usecase.get("description", ""), uc_name)
    raw_str = resp.get("data", {}).get("response", "")

    # Normalize + save
    norm = normalize_and_save.with_options(name=f"Normalize Output [{uc_name}]")(raw_str, out_dir, uc_name)

    role_files = []
    if "workflow_yaml" in norm:
        save_workflow_yaml.with_options(name=f"Save Workflow [{uc_name}]")(norm["workflow_yaml"], out_dir, uc_name)

    for agent in norm.get("agents", []):
        f = save_agent_yaml.with_options(name=f"Save Agent [{agent.get('name','unnamed')}]")(agent, out_dir, roles_dir, uc_name)
        if f and "manager" not in agent.get("name", "").lower():
            role_files.append(f)

    mgr_files = list(out_dir.glob("*Manager*.yaml"))
    if mgr_files and role_files:
        update_manager_yaml.with_options(name=f"Update Manager [{uc_name}]")(str(mgr_files[0]), role_files, uc_name)


@flow(name="Run All Use Cases")
def run_all_usecases(manager_yaml: str, usecases_file: str, save_outputs: bool = True, push: bool = False):
    """Top-level flow to run all use cases sequentially."""
    with open(usecases_file, "r") as f:
        usecases = yaml.safe_load(f).get("use_cases", [])

    for uc in usecases:
        uc_name = uc.get("name", "unnamed").replace("_", " ").title()
        run_usecase_flow.with_options(name=f"Use Case [{uc_name}]")(manager_yaml, uc, save_outputs, push)


# -----------------------
# CLI Entry Point
# -----------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m flows.run_list_iterate_prefect <manager_yaml> <usecases_file>")
        sys.exit(1)

    manager_yaml = sys.argv[1]
    usecases_file = sys.argv[2]
    run_all_usecases(manager_yaml, usecases_file)
