# scripts/create_from_output.py

import argparse
from pathlib import Path

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.services.workflow_manager import create_workflow_from_yaml


def process_subfolder(client: LyzrAPIClient, manager: AgentManager, folder: Path):
    """Create Manager + Roles and Workflow from a subfolder"""
    # 1. Find Manager YAML
    mgr_files = list(folder.glob("*Manager*.yaml"))
    if not mgr_files:
        print(f"⚠️ No Manager YAML found in {folder}")
        return
    manager_yaml_path = mgr_files[0]

    # 2. Create Manager + Roles
    print(f"\n🚀 Creating Manager + Roles from {manager_yaml_path}")
    mgr_result = manager.create_manager_with_roles(str(manager_yaml_path))
    if not mgr_result:
        print(f"❌ Manager creation failed for {manager_yaml_path}")
        return
    print(f"✅ Manager created: {mgr_result.get('name')} (id={mgr_result.get('agent_id')})")

    # 3. Find Workflow YAML
    wf_files = sorted(folder.glob("workflow_*.yaml"))
    if not wf_files:
        print(f"⚠️ No workflow YAML found in {folder}")
        return
    workflow_yaml_path = wf_files[-1]  # pick latest by filename sort

    # 4. Create Workflow
    print(f"🚀 Creating Workflow from {workflow_yaml_path}")
    wf_result = create_workflow_from_yaml(client, str(workflow_yaml_path))
    if not wf_result.get("ok"):
        print(f"❌ Workflow creation failed in {folder}: {wf_result}")
    else:
        data = wf_result.get("data", {})
        print(f"✅ Workflow created: {data.get('flow_name')} (id={data.get('flow_id')})")


def main():
    parser = argparse.ArgumentParser(
        description="Recursively create Managers + Roles and Workflows from output folder"
    )
    parser.add_argument(
        "root_folder",
        type=str,
        help="Root folder to scan (e.g., output/YAML_COMPOSER_MANAGER_v1)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    root_path = Path(args.root_folder)
    if not root_path.exists():
        print(f"❌ Root folder not found: {root_path}")
        return

    client = LyzrAPIClient(debug=args.debug)
    manager = AgentManager(client)

    # Iterate subfolders
    for sub in sorted(root_path.iterdir()):
        if sub.is_dir():
            print(f"\n📂 Processing subfolder: {sub}")
            process_subfolder(client, manager, sub)


if __name__ == "__main__":
    main()
