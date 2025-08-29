# flows/create_yaml_agents.py
import os
from pathlib import Path
import yaml
from prefect import flow, task

ROOT_DIR = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT_DIR / "agents"
UPDATEME_FILE = ROOT_DIR / "UPDATEME.yaml"

AGENT_DIR.mkdir(exist_ok=True)

# Read UPDATEME.yaml and create two agent YAMLs: Manager and Role
@task
def read_updateme_yaml():
    """Read the base UPDATEME.yaml in root and return parsed dict."""
    if not UPDATEME_FILE.exists():
        raise FileNotFoundError(f"❌ Missing {UPDATEME_FILE}")
    with open(UPDATEME_FILE, "r") as f:
        data = yaml.safe_load(f)
    return data

# Uses values from UPDATEME.yaml to build Manager and Role YAMLs    
@task
def build_manager_yaml(base_yaml: dict):
    """Derive Manager YAML from UPDATEME.yaml."""
    manager_yaml = {
        "name": "YAML_COMPOSER_MANAGER_v1",
        "template_type": "manager",
        "agent_role": base_yaml.get("agent_role", "Manager Agent"),
        "agent_goal": base_yaml.get("agent_goal", "Orchestrate role agents."),
        "agent_instructions": base_yaml.get("agent_instructions", "Manage YAML schema composition."),
        "source": "UPDATEME.yaml"
    }
    return manager_yaml

# For Role agent, use fixed instructions and goals
@task
def build_role_yaml(base_yaml: dict):
    """Derive Role YAML from UPDATEME.yaml."""
    role_yaml = {
        "name": "YAML_COMPOSER_ROLE_v1",
        "template_type": "role",
        "agent_role": base_yaml.get("agent_role", "Role Agent"),
        "agent_goal": "Generate schema-complete YAML fragments.",
        "agent_instructions": "Produce and validate YAML blocks for workflows.",
        "source": "UPDATEME.yaml"
    }
    return role_yaml

# Stores YAML files under agents/ directory
@task
def save_yaml(agent_dict, filename: str):
    """Write YAML file under agents/."""
    path = AGENT_DIR / filename
    with open(path, "w") as f:
        yaml.dump(agent_dict, f, sort_keys=False)
    print(f"✅ Saved {filename} → {path}")
    return str(path)

@flow(name="Create YAML Agents from UPDATEME.yaml")
def create_yaml_agents():
    base = read_updateme_yaml()
    manager = build_manager_yaml(base)
    role = build_role_yaml(base)
    
    save_yaml(manager, "YAML_COMPOSER_MANAGER_v1.yaml")
    save_yaml(role, "YAML_COMPOSER_ROLE_v1.yaml")

if __name__ == "__main__":
    create_yaml_agents()
