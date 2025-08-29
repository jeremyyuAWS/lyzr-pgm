# scripts/run_list_iterate.py

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
import yaml
import argparse

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.normalize_output import normalize_inference_output, canonicalize_name
from src.services.workflow_manager import create_workflow_from_yaml


def run_inference(
    client: LyzrAPIClient,
    agent_id: str,
    usecase: dict,
    out_root: Path,
    save_outputs: bool,
    push: bool,
    manager: AgentManager,
    max_retries: int = 3,
):
    """Run inference for a single use case, retrying if response unusable."""
    raw_name = usecase.get("name", "unnamed_usecase")
    usecase_name = canonicalize_name(raw_name)   # Title_Case_Underscore
    usecase_text = usecase.get("description", "")
    if not usecase_text:
        print(f"⚠️ Skipping {usecase_name}: no description found")
        return

    # pretty name for logs
    pretty_name = usecase.get("name", "Unnamed Use Case").replace("_", " ").title()
    print(f"\n📥 Running use case: {pretty_name}")

    out_dir = out_root / usecase_name
    out_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        payload = {
            "user_id": os.getenv("LYZR_USER_ID", "demo-user"),
            "system_prompt_variables": {},
            "agent_id": agent_id,
            "session_id": f"{agent_id}-{os.urandom(4).hex()}",
            "message": usecase_text,
            "filter_variables": {},
            "features": [],
            "assets": [],
        }

        resp = client._request("POST", "/v3/inference/chat/", payload=payload)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        if save_outputs:
            raw_file = out_dir / f"inference_raw_{ts}_attempt{attempt}.json"
            with open(raw_file, "w") as f:
                json.dump(resp, f, indent=2)
            print(f"📦 Raw inference response saved to {raw_file}")

        usable = False
        if resp.get("ok") and "data" in resp and "response" in resp["data"]:
            raw_str = resp["data"]["response"]
            try:
                norm = normalize_inference_output(raw_str, out_dir)
                if save_outputs:
                    norm_file = out_dir / f"inference_normalized_{ts}_attempt{attempt}.json"
                    with open(norm_file, "w") as f:
                        json.dump(norm, f, indent=2)
                    print(f"✅ Normalized inference output saved to {norm_file}")
                usable = True

                # 🚀 Push to Lyzr Platform if requested
                if push:
                    print(f"🚀 Push flag enabled — creating agents from {out_dir}")

                    # 1. Manager + Roles
                    mgr_files = list(out_dir.glob("*Manager*.yaml"))
                    if mgr_files:
                        manager_yaml_path = mgr_files[0]
                        mgr_result = manager.create_manager_with_roles(str(manager_yaml_path))
                        if mgr_result:
                            print(f"✅ Manager created: {mgr_result.get('name')} (id={mgr_result.get('agent_id')})")
                        else:
                            print(f"❌ Failed to create Manager from {manager_yaml_path}")
                    else:
                        print(f"⚠️ No Manager YAML found in {out_dir}")

                    # 2. Workflow
                    wf_files = sorted(out_dir.glob("workflow_*.yaml"))
                    if wf_files:
                        workflow_yaml_path = wf_files[-1]
                        print(f"🚀 Creating Workflow from {workflow_yaml_path}")
                        wf_result = create_workflow_from_yaml(client, str(workflow_yaml_path))
                        if wf_result.get("ok"):
                            data = wf_result.get("data", {})
                            print(f"✅ Workflow created: {data.get('flow_name')} (id={data.get('flow_id')})")
                        else:
                            print(f"❌ Workflow creation failed in {out_dir}: {wf_result}")
                    else:
                        print(f"⚠️ No Workflow YAML found in {out_dir}")

            except Exception as e:
                print(f"⚠️ Normalization failed on attempt {attempt}: {e}")

        if usable:
            return  # success → stop retrying
        else:
            if attempt < max_retries:
                wait = 2 ** (attempt - 1)
                print(f"⚠️ No usable response for {usecase_name}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"❌ Failed to get valid response for {usecase_name} after {max_retries} attempts.")


def main():
    parser = argparse.ArgumentParser(description="Run manager agent across a list of use cases")
    parser.add_argument("manager_yaml", help="Path to manager agent YAML")
    parser.add_argument("usecases_file", help="Path to use cases YAML file")
    parser.add_argument("--save", action="store_true", help="Save raw/normalized JSON outputs")
    parser.add_argument("--push", action="store_true", help="Push created agents & workflows to Lyzr platform")
    args = parser.parse_args()

    # toggle logic: CLI flag overrides env
    save_outputs = args.save or os.getenv("SAVE_OUTPUTS", "0") == "1"

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)
    manager = AgentManager(client)

    # Create Manager + Roles
    result = manager.create_manager_with_roles(args.manager_yaml)
    if not result:
        print("❌ Manager creation failed.")
        sys.exit(1)

    mgr_id = result["agent_id"]
    print(f"\n✅ Manager agent ready: {result['name']}")

    # Load use cases
    with open(args.usecases_file, "r") as f:
        usecases = yaml.safe_load(f)

    # Run inference per use case
    out_root = Path("output") / Path(args.manager_yaml).stem
    for uc in usecases.get("use_cases", []):
        run_inference(client, mgr_id, uc, out_root, save_outputs, args.push, manager)


if __name__ == "__main__":
    main()
