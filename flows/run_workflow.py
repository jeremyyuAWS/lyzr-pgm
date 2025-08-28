import os
import sys
import yaml
from src.services.create_from_yaml import create_agent_from_yaml
from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager


def run_workflow(yaml_file: str = "WORKFLOW.yaml"):
    """
    Executes workflows defined in WORKFLOW.yaml.
    For each manager, ensures role agents are created first, then the manager.
    """
    with open(yaml_file, "r") as f:
        config = yaml.safe_load(f)

    client = LyzrAPIClient(debug=os.getenv("LYZR_DEBUG", "0") == "1")
    manager_service = AgentManager(client)

    for wf in config.get("workflows", []):
        print(f"\n▶️ Running workflow: {wf['name']}")

        manager_file = wf["manager"]

        # Load manager YAML
        with open(manager_file, "r") as f:
            mgr_yaml = yaml.safe_load(f)

        # Collect managed agents
        managed_agents = mgr_yaml.get("managed_agents", [])

        role_ids = []
        for role_def in managed_agents:
            # Allow both string and dict formats
            role_path = role_def["file"] if isinstance(role_def, dict) else role_def

            print(f"🚀 Creating role agent {role_path}")
            role_res = create_agent_from_yaml(role_path)
            if role_res and "data" in role_res:
                role_ids.append(role_res["data"].get("agent_id"))


        # Create the manager after all roles
        print(f"⚡ Creating manager {manager_file} with {len(role_ids)} role(s)")
        manager_service.create_manager_with_roles(manager_file)

    print("\n✅ All workflows complete")


if __name__ == "__main__":
    yaml_file = "WORKFLOW.yaml"
    if len(sys.argv) > 1:
        yaml_file = sys.argv[1]

    try:
        run_workflow(yaml_file)
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        sys.exit(1)
