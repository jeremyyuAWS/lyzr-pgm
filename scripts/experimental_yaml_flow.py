import os
import sys
import json
import yaml
from pathlib import Path
from datetime import datetime

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.yaml_utils import save_yaml_file, safe_name
from src.utils.response_parser import classify_and_normalize


def create_manager_from_yaml(client: LyzrAPIClient, manager_yaml_path: str):
    manager = AgentManager(client)
    mgr_meta = manager.create_manager_with_roles(manager_yaml_path)
    return mgr_meta["agent_id"]


def run_inference(client: LyzrAPIClient, agent_id: str, usecase_file: str):
    with open(usecase_file, "r") as f:
        usecase_yaml = yaml.safe_load(f)

    usecase_text = usecase_yaml.get("use_case") or usecase_yaml.get("description")
    if not usecase_text:
        raise ValueError("Use-case YAML missing 'use_case' or 'description'")

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


def persist_raw(out_root: Path, domain: str, raw_resp) -> Path:
    raw_dir = out_root / domain / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = raw_dir / f"response_{ts}.json"
    with open(raw_path, "w") as f:
        json.dump(raw_resp, f, ensure_ascii=False, indent=2)
    return raw_path


def save_success(payload: dict, out_root: Path, domain: str):
    workflow_name = safe_name(payload.get("workflow_name", "unnamed_workflow"))
    base_dir = out_root / domain / workflow_name
    base_dir.mkdir(parents=True, exist_ok=True)

    # Write workflow YAML (pretty)
    if payload.get("workflow_yaml"):
        wf_file = base_dir / f"{workflow_name}.yaml"
        save_yaml_file(wf_file, payload["workflow_yaml"])
        print(f"📝 Saved workflow → {wf_file}")

    # Write agents (pretty)
    for agent in payload.get("agents", []):
        name = safe_name(agent.get("name", "unnamed_agent"))
        yaml_str = agent.get("yaml", "")
        agent_file = base_dir / f"{name}.yaml"
        save_yaml_file(agent_file, yaml_str)
        print(f"📝 Saved agent → {agent_file}")

    # Also persist a normalized JSON for quick inspection
    norm_json = {
        "workflow_name": payload.get("workflow_name"),
        "agents": [{"name": a.get("name"), "type": a.get("type")} for a in payload.get("agents", [])],
    }
    with open(base_dir / "normalized.json", "w") as f:
        json.dump(norm_json, f, ensure_ascii=False, indent=2)

    print(f"✅ Outputs saved under {base_dir}")


def save_error(message: str, out_root: Path, domain: str, diag: dict, raw_path: Path):
    err_dir = out_root / domain / "errors" / datetime.now().strftime("%Y%m%d_%H%M%S")
    err_dir.mkdir(parents=True, exist_ok=True)

    with open(err_dir / "error.log", "w") as f:
        f.write(message)

    # Diagnostics: how we parsed, attempts tried, pointers to raw
    with open(err_dir / "diagnostics.json", "w") as f:
        json.dump({"diagnostics": diag, "raw_pointer": str(raw_path)}, f, ensure_ascii=False, indent=2)

    print(f"❌ Classified as error. See {err_dir}/error.log and diagnostics.json (raw at {raw_path}).")


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.experimental_yaml_flow <manager_yaml> <usecase_file>")
        sys.exit(1)

    manager_yaml_path = sys.argv[1]
    usecase_file = sys.argv[2]

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)

    out_root = Path("output")
    usecase_name = Path(usecase_file).stem
    domain = usecase_name.split("_")[-1] if "_" in usecase_name else usecase_name

    # 1) Create manager
    mgr_id = create_manager_from_yaml(client, manager_yaml_path)

    # 2) Inference
    resp = run_inference(client, mgr_id, usecase_file)
    if not isinstance(resp, dict) or not resp.get("ok"):
        raw_path = persist_raw(out_root, domain, resp)
        save_error(str(resp), out_root, domain, {"steps": ["http_error_or_non_dict"]}, raw_path)
        return

    data = resp["data"]

    # 3) Persist raw API data every time (for reuse/debug)
    raw_path = persist_raw(out_root, domain, data)

    # 4) Classify + normalize
    status, payload, diag = classify_and_normalize(data)

    # 5) Save accordingly
    if status == "success":
        save_success(payload, out_root, domain)
    else:
        msg = payload.get("message", "Unknown error")
        save_error(msg, out_root, domain, diag, raw_path)


if __name__ == "__main__":
    main()
