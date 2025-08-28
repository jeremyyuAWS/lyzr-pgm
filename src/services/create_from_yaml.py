# src/services/create_from_yaml.py

import os
import yaml
from pathlib import Path

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from scripts.create_agent import create_agent


def create_agent_from_yaml(fpath: str, debug: bool = None):
    """
    Create an agent from a YAML file.
    - If file is a Manager definition, delegate to AgentManager.create_manager_with_roles.
    - Otherwise, create a single role agent.
    """

    debug = os.getenv("LYZR_DEBUG", "0") == "1" if debug is None else debug
    client = LyzrAPIClient(debug=debug)
    manager = AgentManager(client)

    # Load YAML
    with open(fpath, "r") as f:
        content = yaml.safe_load(f)

    # Detect if this is a Manager agent
    is_manager = (
        "mgr" in Path(fpath).name.lower()
        or "manager" in Path(fpath).name.lower()
        or "managed_agents" in content
    )

    if is_manager:
        print(f"⚡ Treating {fpath} as a manager file", flush=True)
        return manager.create_manager_with_roles(fpath)
    else:
        print(f"🚀 Creating single agent from {fpath}", flush=True)
        # FIX: pass client into create_agent
        return create_agent(fpath, client)
