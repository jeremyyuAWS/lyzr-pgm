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
    mgr_meta = manager.create_manager_with_roles(manager_yaml_path)
    return mgr_meta["agent_id"]

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

    client = LyzrAPIClient(debug=os.getenv("LYZR_DEBUG", "0") == "1", timeout=180)
    resp = client._request("POST", "/v3/inference/chat/", payload=payload)

    if not resp.get("ok"):
        raise RuntimeError(f"Inference failed: {resp}")
    return resp["data"]

@task
def parse_response(raw_data):
    ok, parsed, err = is_valid_response(raw_data)
    if ok:
        return parsed
    return {"error": err or str(raw_data)}


def save_yaml_file(path: Path, yaml_str: str):
    """
    Parse a YAML string and dump it nicely formatted.
    """
    try:
        parsed = yaml.safe_load(yaml_str)
        with open(path, "w") as f:
            yaml.dump(
                parsed,
                f,
                sort_keys=False,
                default_flow_style=False,   # <- force block style
                indent=2,                   # <- nicer indentation
                width=80,                   # <- avoid long inline lines
            )
    except Exception:
        # Fallback: just write raw if parsing fails
        with open(path, "w") as f:
            f.write(yaml_str)

@task
def save_output(data, usecase_name: str, out_root="output"):
    # Pass both parsed and raw into file_io
    if "error" in data and len(data) == 1:
        print(f"❌ Manager failed: {data['error']}")
        save_file_io(None, data["error"], base=out_root, domain=usecase_name)
        return

    save_file_io(data, json.dumps(data, indent=2), base=out_root, domain=usecase_name)

@flow(name="Experimental YAML Flow v.1")
def experimental_yaml_flow(manager_yaml: str, usecase_file: str):
    client = LyzrAPIClient(debug=os.getenv("LYZR_DEBUG", "0") == "1", timeout=180)
    mgr_id = create_manager(client, manager_yaml)
    raw = run_inference(client, mgr_id, usecase_file)
    parsed = parse_response(raw)
    save_output(parsed, Path(usecase_file).stem)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m flows.experimental_yaml_flow <manager_yaml> <usecase_file>")
        sys.exit(1)
    experimental_yaml_flow(sys.argv[1], sys.argv[2])
