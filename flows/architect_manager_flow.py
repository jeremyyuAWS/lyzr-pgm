from prefect import flow, task, get_run_logger
import json, yaml, os
from jsonschema import validate, ValidationError
from datetime import datetime

ARCHITECT_SCHEMA = {
    "type": "object",
    "properties": {
        "workflow_name": {"type": "string"},
        "workflow_yaml": {"type": "string"},
        "agents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"enum": ["manager", "role"]},
                    "yaml": {"type": "string"}
                },
                "required": ["name", "type", "yaml"]
            }
        }
    },
    "required": ["workflow_name", "workflow_yaml", "agents"]
}

@task
def load_use_case(file_path: str) -> str:
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)
    return data["use_case"]

@task
def call_architect_manager(use_case: str) -> dict:
    # stubbed – integrate with your Lyzr API client
    response = call_lyzr_agent(agent_id="ARCHITECT_MANAGER_v1.3", message=use_case)
    return response["data"]

@task
def validate_schema(response: dict) -> dict:
    validate(instance=response, schema=ARCHITECT_SCHEMA)
    return response

@task
def save_outputs(response: dict):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = f"outputs/{ts}"
    os.makedirs(f"{base}/workflows", exist_ok=True)
    os.makedirs(f"{base}/agents", exist_ok=True)

    with open(f"{base}/workflows/{response['workflow_name']}.yaml", "w") as f:
        f.write(response["workflow_yaml"])

    for agent in response["agents"]:
        with open(f"{base}/agents/{agent['name']}.yaml", "w") as f:
            f.write(agent["yaml"])

    return base

@flow
def architect_manager_flow(use_case_file: str):
    use_case = load_use_case(use_case_file)
    raw_response = call_architect_manager(use_case)
    valid = validate_schema(raw_response)
    folder = save_outputs(valid)
    return folder

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-case", required=True, help="Path to YAML file with use_case")
    args = parser.parse_args()

    result_folder = architect_manager_flow(args.use_case)
    print(f"✅ Outputs written to {result_folder}")
