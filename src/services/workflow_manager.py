# src/services/workflow_manager.py

import yaml
from src.api.client import LyzrAPIClient


def create_workflow_from_yaml(client: LyzrAPIClient, yaml_path: str):
    """
    Create workflow from a YAML file that defines `flow_name` and `flow_data`.

    Args:
        client (LyzrAPIClient): Initialized API client
        yaml_path (str): Path to workflow YAML file

    Returns:
        dict: API response from workflow creation
    """
    with open(yaml_path, "r") as f:
        workflow_dict = yaml.safe_load(f)

    # Ensure required keys
    if "flow_name" not in workflow_dict or "flow_data" not in workflow_dict:
        raise ValueError(f"❌ Workflow YAML missing required keys: {yaml_path}")

    payload = {
        "flow_name": workflow_dict["flow_name"],
        "flow_data": workflow_dict["flow_data"],
    }

    resp = client._request("POST", "/v3/workflows/", payload)
    if not resp.get("ok"):
        print(f"❌ Workflow creation failed: {resp}")
    else:
        print(f"✅ Workflow created: {resp['data'].get('flow_id', 'unknown id')}")

    return resp
