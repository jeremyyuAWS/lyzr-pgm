# flows/orchestrate_agents.py
# Runs files based on actions in UPDATEME.yaml

from prefect import flow, task, get_run_logger
from prefect.runtime import task_run
import yaml
from pathlib import Path
from datetime import datetime
import pytz

# Import your real Lyzr client
from src.api.client import LyzrAPIClient

client = LyzrAPIClient()


def pst_now_str() -> str:
    """Return current time in PST for consistent logging."""
    pst = pytz.timezone("America/Los_Angeles")
    return datetime.now(pst).strftime("%Y-%m-%d %I:%M %p %Z")


# ---------------------------
# Tasks
# ---------------------------

@task
def load_config(path: str = "UPDATEME.yaml") -> dict:
    """Load orchestration config from YAML file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


@task
def create_agent_task(fpath: str) -> dict:
    """Create an agent on Lyzr from a YAML file."""
    logger = get_run_logger()
    fname = Path(fpath).name
    yaml_text = Path(fpath).read_text()

    logger.info(f"⚡ Creating agent from {fname}")

    # Call Lyzr API
    agent_info = client.create_agent_from_yaml(yaml_text, is_path=False)


    now_str = pst_now_str()
    msg = f"✅ Created agent {agent_info.get('name')} [{agent_info.get('_id')}] at {now_str}"
    logger.info(msg)

    return {
        "file": fpath,
        "agent_info": agent_info,
        "timestamp": now_str,
    }


@task
def update_agent_task(file_path: str) -> dict:
    """Update an existing agent on Lyzr from a YAML file."""
    logger = get_run_logger()
    yaml_text = Path(file_path).read_text()

    logger.info(f"🔄 Updating agent from {file_path}")
    agent_info = client.update_agent_from_yaml(yaml_text)

    msg = f"✅ Updated agent {agent_info.get('name')} [{agent_info.get('_id')}] at {pst_now_str()}"
    logger.info(msg)

    task_run.set_task_run_name(msg)
    return {"file": file_path, "agent_info": agent_info}


@task
def create_workflow_task(file_path: str) -> dict:
    """Create a workflow on Lyzr from a YAML file."""
    logger = get_run_logger()
    yaml_text = Path(file_path).read_text()

    logger.info(f"🛠 Creating workflow from {file_path}")
    wf_info = client.create_workflow_from_yaml(yaml_text)

    msg = f"✅ Created workflow {wf_info.get('flow_name')} [{wf_info.get('flow_id')}] at {pst_now_str()}"
    logger.info(msg)

    task_run.set_task_run_name(msg)
    return {"file": file_path, "workflow_info": wf_info}


@task
def execute_workflow_task(file_path: str) -> dict:
    """Execute a workflow on Lyzr from a YAML file."""
    logger = get_run_logger()
    yaml_text = Path(file_path).read_text()

    logger.info(f"▶️ Executing workflow from {file_path}")
    run_info = client.execute_workflow_from_yaml(yaml_text)

    msg = f"✅ Executed workflow run {run_info.get('flow_name')} [{run_info.get('flow_id')}] at {pst_now_str()}"
    logger.info(msg)

    task_run.set_task_run_name(msg)
    return {"file": file_path, "run_info": run_info}


@task
def dispatch_actions(cfg: dict) -> list:
    """Dispatch actions defined in config YAML."""
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


# ---------------------------
# Flow
# ---------------------------

@flow(name="Agent Orchestration")
def orchestrate_agents(config_path: str = "UPDATEME.yaml"):
    """Main orchestration flow."""
    cfg = load_config(config_path)
    dispatch_actions(cfg)


if __name__ == "__main__":
    orchestrate_agents()
