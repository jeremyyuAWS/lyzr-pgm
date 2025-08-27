# flows/orchestrate_hr_use_cases.py
from prefect import flow, task, get_run_logger
import os, yaml, json
from datetime import datetime
from jsonschema import validate, ValidationError

# --- Canonical schema ---
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

# --- Prefect tasks ---
@task
def load_use_cases(file_path: str) -> list:
    logger = get_run_logger()
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)
    active = [uc for uc in data["use_cases"] if uc.get("status") == "active"]
    logger.info(f"🔎 Found {len(active)} active use cases: {[uc['id'] for uc in active]}")
    return active

@task(retries=3, retry_delay_seconds=15)
def call_architect_manager(use_case: dict) -> dict:
    logger = get_run_logger()
    logger.info(f"📤 Submitting {use_case['id']} - {use_case['name']}")
    # TODO: replace with real Lyzr API call
    return {
        "workflow_name": f"{use_case['name']}_Workflow",
        "workflow_yaml": f"flow_name: {use_case['name']}_Workflow\nflow_data:\n  tasks: ...",
        "agents": [
            {
                "name": f"{use_case['name']}_Manager",
                "type": "manager",
                "yaml": f"name: {use_case['name']}_Manager\ndescription: Auto-generated manager YAML"
            },
            {
                "name": f"{use_case['name']}_ROLE_1",
                "type": "role",
                "yaml": f"name: {use_case['name']}_ROLE_1\ndescription: Auto-generated role YAML"
            }
        ]
    }

@task(retries=2, retry_delay_seconds=10)
def validate_schema(response: dict, expected_roles: int, use_case_id: str) -> dict:
    logger = get_run_logger()
    try:
        validate(instance=response, schema=ARCHITECT_SCHEMA)
        role_count = len([a for a in response["agents"] if a["type"] == "role"])
        if role_count < expected_roles:
            raise ValidationError(f"Expected at least {expected_roles} roles, got {role_count}")
        logger.info(f"✅ Validation passed for {use_case_id}")
        response["_validation"] = {"status": "passed"}
    except ValidationError as e:
        logger.error(f"❌ Validation failed for {use_case_id}: {e}")
        response["_validation"] = {"status": "failed", "error": str(e)}
        raise
    return response

@task
def save_outputs(response: dict, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "workflow.yaml"), "w") as f:
        f.write(response["workflow_yaml"])
    for agent in response["agents"]:
        with open(os.path.join(output_dir, f"{agent['name']}.yaml"), "w") as f:
            f.write(agent["yaml"])
    with open(os.path.join(output_dir, "validation.json"), "w") as f:
        json.dump(response.get("_validation", {"status": "unknown"}), f, indent=2)
    return output_dir


# --- Prefect Flow ---
@flow(name="Architect_Manager_HR_Flow")
def orchestrate_hr_use_cases(
    use_case_file="agents/use_cases_hr.yaml",
    output_root="outputs"
):
    logger = get_run_logger()
    use_cases = load_use_cases(use_case_file)

    for uc in use_cases:
        folder_name = f"{uc['id']}-{uc['name']}"
        output_dir = os.path.join(output_root, folder_name)

        raw = call_architect_manager(uc)
        validated = validate_schema(raw, uc.get("expected_roles", 1), uc["id"])
        save_outputs(validated, output_dir)

    logger.info("🎉 All active HR use cases processed successfully!")

if __name__ == "__main__":
    orchestrate_hr_use_cases()
