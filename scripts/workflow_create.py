# scripts/workflow_create.py

import os
import yaml
from pathlib import Path
from datetime import datetime
import pytz
import argparse

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.payload_normalizer import normalize_payload
from scripts.create_agent import create_agent

def create_agent_workflow(yaml_path: str, client: LyzrAPIClient, debug: bool = False):
    manager = AgentManager(client)

    yaml_path = Path(yaml_path)
    with open(yaml_path, "r") as f:
        content = yaml.safe_load(f)

    is_manager = (
        "mgr" in yaml_path.name.lower()
        or "manager" in yaml_path.name.lower()
        or "managed_agents" in content
    )

    if is_manager:
        print(f"⚡ Treating {yaml_path} as a manager file", flush=True)
        result = manager.create_manager_with_roles(str(yaml_path))
        # nothing more to do — rename is already handled
    else:
        print(f"🚀 Creating role agent from {yaml_path}", flush=True)
        create_agent(str(yaml_path), client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create agent(s) from YAML")
    parser.add_argument("yaml_file", help="Path to YAML definition")
    args = parser.parse_args()

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug)

    create_agent_workflow(args.yaml_file, client, debug=debug)
