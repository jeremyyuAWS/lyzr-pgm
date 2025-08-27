# flows/orchestrate_agents.py
# Runs files based on actions in UPDATEME.yaml

from prefect import flow, task, get_run_logger
from prefect.runtime import task_run
import yaml
from pathlib import Path
from datetime import datetime
import pytz

# === Replace with your real implementations ===
def fake_create_manager_with_roles(file_path: str):
    # Pretend this also spawns roles and returns metadata
    return {
        "manager": Path(file_path).stem,
        "version": "v1.3",
        "id": "68af37f66c80197869654710",
        "linked_roles": [
            {"name": "YAML_COMPOSER_ROLE_v1.2", "id": "68af37f599e8c20dd8f25305"}
        ],
    }

def fake_create_agent(file_path: str):
    return {
        "role": Path(file_path).stem,
        "version": "v1.2",
        "id": "68af37f599e8c20dd8f25305",
    }

def pst_now_str():
    pst = pytz.timezone("America/Los_Angeles")
    return datetime.now(pst).strftime("%Y-%m-%d %I:%M %p %Z")


@task
def load_config(path: str = "UPDATEME.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

from prefect import task, get_run_logger
from pathlib import Path
import datetime
import pytz

@task
def create_agent_task(fpath: str):
    """
    Creates an agent from a YAML file. 
    Auto-detects manager vs role and logs clear messages.
    """
    logger = get_run_logger()
    fname = Path(fpath).name

    # Detect type
    if "manager" in fpath.lower():
        agent_type = "manager"
    else:
        agent_type = "role"

    logger.info(f"⚡ Treating {fpath} as a {agent_type} file")

    # Simulate API response (replace with real API calls)
    fake_id = "68af37f66c80197869654710"
    pst = pytz.timezone("America/Los_Angeles")
    now_str = datetime.datetime.now(pst).strftime("%Y-%m-%d %I:%M %p %Z")

    if agent_type == "role":
        msg = f"🧩 Created role agent {fname} [{fake_id} | {now_str}]"
    else:
        msg = f"🤖 Created manager agent {fname} [{fake_id} | {now_str}] with 1 linked roles"

    # This will show up in Prefect UI/logs
    logger.info(msg)

    return {
        "file": fpath,
        "agent_type": agent_type,
        "agent_id": fake_id,
        "message": msg,
        "timestamp": now_str,
    }

@task
def update_agent_task(file_path: str):
    logger = get_run_logger()
    msg = f"🔄 Updated agent from {file_path} [{pst_now_str()}]"
    logger.info(msg)
    task_run.set_task_run_name(msg)
    return {"file": file_path, "status": "updated"}


@task
def create_workflow_task(file_path: str):
    logger = get_run_logger()
    msg = f"🛠 Created workflow from {file_path} [{pst_now_str()}]"
    logger.info(msg)
    task_run.set_task_run_name(msg)
    return {"file": file_path, "status": "workflow_created"}


@task
def execute_workflow_task(file_path: str):
    logger = get_run_logger()
    msg = f"▶️ Executed workflow from {file_path} [{pst_now_str()}]"
    logger.info(msg)
    task_run.set_task_run_name(msg)
    return {"file": file_path, "status": "workflow_executed"}

@task
def dispatch_actions(cfg: dict):
    logger = get_run_logger()
    actions = cfg.get("actions", {})

    results = []
    for action, settings in actions.items():
        enabled = settings.get("enabled", False)
        files = settings.get("files", [])
        if not (enabled and files):
            logger.info(f"❌ Action '{action}' skipped")
            continue

        logger.info(f"✅ Action '{action}' enabled with {len(files)} file(s)")

        for fpath in files:
            short_name = Path(fpath).stem

            if action == "create_agents":
                results.append(
                    create_agent_task.with_options(
                        name=f"create_agent:{short_name}"
                    ).submit(fpath)
                )

            elif action == "update_agents":
                results.append(
                    update_agent_task.with_options(
                        name=f"update_agent:{short_name}"
                    ).submit(fpath)
                )

            elif action == "create_workflows":
                results.append(
                    create_workflow_task.with_options(
                        name=f"create_workflow:{short_name}"
                    ).submit(fpath)
                )

            elif action == "execute_workflows":
                results.append(
                    execute_workflow_task.with_options(
                        name=f"execute_workflow:{short_name}"
                    ).submit(fpath)
                )

            else:
                logger.warning(f"⚠️ Unknown action: {action}")

    return results


@flow(name="Agent Orchestration")
def orchestrate_agents(config_path: str = "UPDATEME.yaml"):
    cfg = load_config(config_path)
    dispatch_actions(cfg)


if __name__ == "__main__":
    orchestrate_agents()
