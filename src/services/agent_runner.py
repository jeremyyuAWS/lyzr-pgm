# src/services/agent_runner.py
import os
import json
import time
from pathlib import Path
from datetime import datetime
import yaml

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.normalize_output import normalize_inference_output, canonicalize_name


def push_results(out_dir: Path, client: LyzrAPIClient):
    ...
    # (copy logic from your script unchanged)


def run_inference(client: LyzrAPIClient, agent_id: str, usecase: dict,
                  out_root: Path, save_outputs: bool, max_retries: int = 3):
    ...
    # (copy logic from your script unchanged)


def create_and_run(manager_yaml: str, usecases_file: str,
                   save_outputs: bool = False, push: bool = False):
    """Programmatic wrapper for FastAPI or CLI."""
    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)
    manager = AgentManager(client)

    # Create Manager + Roles
    result = manager.create_manager_with_roles(manager_yaml)
    if not result:
        raise RuntimeError("Manager creation failed")

    mgr_id = result["agent_id"]

    # Load use cases
    with open(usecases_file, "r") as f:
        usecases = yaml.safe_load(f)

    out_root = Path("output") / Path(manager_yaml).stem
    all_results = []

    for uc in usecases.get("use_cases", []):
        out_dir = run_inference(client, mgr_id, uc, out_root, save_outputs)
        if push and out_dir:
            push_results(out_dir, client)
        all_results.append(str(out_dir))

    return {"manager": result, "outputs": all_results}
