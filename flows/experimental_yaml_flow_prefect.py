from prefect import flow, task
import os, json, yaml
from pathlib import Path
from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.response_validator import is_valid_response
from src.utils.file_io import save_output as save_file_io


@task(retries=3, retry_delay_seconds=30)
def create_manager(client: LyzrAPIClient, manager_yaml_path: str):
    manager = AgentManager(client)
    try:
        mgr_meta = manager.create_manager_with_roles(manager_yaml_path)
        return {"ok": True, "agent_id": mgr_meta["agent_id"], "raw": mgr_meta}
    except Exception as e:
        return {"ok": False, "error": str(e), "raw": {}}


@task(retries=2, retry_delay_seconds=15)
def run_inference(client: LyzrAPIClient, agent_id: str, usecase_file: str):
    with open(usecase_file, "r") as f:
        usecase_yaml = yaml.safe_load(f)
    usecase_text = usecase_yaml.get("use_case") or usecase_yaml.get("description")

    payload = {
        "user_id": os.getenv("LYZR_USER_ID", "demo-user"),
        "system_prompt_variables": {},
        "agent_id": agent_id,
        "session_id": f"{agent_id}-{os.urandom(4).hex()}",
        "message": usecase_text,
        "filter_variables": {},
        "features": [],
        "assets": []
    }

    resp = client._request("POST", "/v3/inference/chat/", payload=payload)
    return resp


@task
def parse_response(raw_data):
    ok, parsed, err = is_valid_response(raw_data)
    return {"ok": ok, "parsed": parsed, "error": err, "raw": raw_data}


@flow(name="Experimental YAML Flow v.3")
def experimental_yaml_flow(manager_yaml: str, usecase_file: str):
    client = LyzrAPIClient(debug=os.getenv("LYZR_DEBUG", "0") == "1", timeout=180)

    # Step 1: create manager
    mgr_result = create_manager(client, manager_yaml)
    save_file_io(mgr_result, Path(manager_yaml).stem, category="managers")

    if not mgr_result.get("ok"):
        print("Manager creation failed, stopping flow.")
        return

    # Step 2: run inference
    raw = run_inference(client, mgr_result["agent_id"], usecase_file)
    result = parse_response(raw)

    # Step 3: save structured workflow output
    save_file_io(result, Path(usecase_file).stem, category="workflows")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m flows.experimental_yaml_flow_prefect <manager_yaml> <usecase_file>")
        sys.exit(1)
    experimental_yaml_flow(sys.argv[1], sys.argv[2])
