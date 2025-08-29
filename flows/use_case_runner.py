import os
import json
import yaml
from pathlib import Path
from datetime import datetime

from prefect import flow, task
from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.normalize_output import normalize_inference_output


@task
def create_manager(client: LyzrAPIClient, manager_yaml_path: str):
    manager = AgentManager(client)
    result = manager.create_manager_with_roles(manager_yaml_path)
    if not result:
        raise RuntimeError("❌ Manager creation failed.")
    print(f"🤖 Created Manager {result['name']} [{result['agent_id']}]")
    return result["agent_id"]


@task(retries=2, retry_delay_seconds=10)
def run_inference(client: LyzrAPIClient, agent_id: str, use_case: dict, out_dir: Path):
    """Run inference on one use case and save raw + normalized response."""
    message = use_case["description"]
    name = use_case["name"]

    payload = {
        "user_id": os.getenv("LYZR_USER_ID", "demo-user"),
        "system_prompt_variables": {},
        "agent_id": agent_id,
        "session_id": f"{agent_id}-{os.urandom(4).hex()}",
        "message": message,
        "filter_variables": {},
        "features": [],
        "assets": []
    }

    resp = client._request("POST", "/v3/inference/chat/", payload=payload)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    case_dir = out_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)

    # Save raw
    raw_file = case_dir / f"inference_raw_{ts}.json"
    with open(raw_file, "w") as f:
        json.dump(resp, f, indent=2)
    print(f"📦 Saved raw response → {raw_file}")

    # Normalize + save
    if resp.get("ok") and "data" in resp and "response" in resp["data"]:
        norm = normalize_inference_output(resp["data"]["response"])
        norm_file = case_dir / f"inference_normalized_{ts}.json"
        with open(norm_file, "w") as f:
            json.dump(norm, f, indent=2)
        print(f"✅ Saved normalized output → {norm_file}")

        # Also extract workflow + agents if possible
        if isinstance(norm, dict):
            if "workflow_yaml" in norm:
                with open(case_dir / "workflow.yaml", "w") as f:
                    f.write(norm["workflow_yaml"])
                print("📝 Saved workflow.yaml")

            for agent in norm.get("agents", []):
                if "yaml" in agent:
                    fname = f"{agent['name']}.yaml"
                    with open(case_dir / fname, "w") as f:
                        f.write(agent["yaml"])
                    print(f"📝 Saved {fname}")
    else:
        print("⚠️ No 'response' in inference output.")

    return resp


@flow(name="HR Use Case YAML Generator")
def hr_use_case_flow(manager_yaml: str, use_cases_file: str):
    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)

    # 1. Create Manager + Roles
    mgr_id = create_manager(client, manager_yaml)

    # 2. Load use cases
    with open(use_cases_file, "r") as f:
        use_cases = yaml.safe_load(f)["use_cases"]

    # 3. Output dir
    out_dir = Path("output") / Path(use_cases_file).stem

    # 4. Run all use cases
    for uc in use_cases:
        run_inference(client, mgr_id, uc, out_dir)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m flows.use_case_runner <manager_yaml> <use_cases_file>")
        sys.exit(1)

    hr_use_case_flow(sys.argv[1], sys.argv[2])
