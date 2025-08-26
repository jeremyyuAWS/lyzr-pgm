import os
import sys
import yaml
from pathlib import Path

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from scripts.create_agent import create_agent


def main():
    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug)
    manager = AgentManager(client)

    with open("UPDATEME.yaml", "r") as f:
        config = yaml.safe_load(f)

    actions = config.get("actions", {})
    if actions.get("create_agents", {}).get("enabled"):
        for fpath in actions["create_agents"]["files"]:
            with open(fpath, "r") as f:
                content = yaml.safe_load(f)

            is_manager = (
                "mgr" in Path(fpath).name.lower()
                or "manager" in Path(fpath).name.lower()
                or "managed_agents" in content
            )

            if is_manager:
                print(f"⚡ Treating {fpath} as a manager file", flush=True)
                manager.create_manager_with_roles(fpath)
            else:
                # Avoid creating role twice if already referenced
                if any("mgr" in Path(mgr).name.lower() or "manager" in Path(mgr).name.lower()
                       for mgr in actions["create_agents"]["files"]):
                    continue
                create_agent(fpath)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        sys.exit(1)
