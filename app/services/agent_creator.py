# app/services/agent_creator.py

from pathlib import Path
import yaml
import os
from scripts.run_business_flow import create_then_rename_agent, load_llm_config
from scripts.create_agent_from_yaml import create_agent_from_yaml


def create_manager_with_roles(yaml_path: Path, headers: dict, base_url: str, log_file: Path):
    """
    Create a manager agent and its associated role agents from a YAML definition.
    
    Expected YAML structure (Option 1: inline roles):
    
    manager:
      name: SOME_MANAGER
      ...
      managed_agents:
        - name: ROLE_NAME
          type: role
          yaml: | 
            name: ROLE_NAME
            description: ...
            agent_role: ...
            ...
    """

    # -----------------------------
    # 1. Load YAML
    # -----------------------------
    if not Path(yaml_path).exists():
        raise FileNotFoundError(f"YAML path not found: {yaml_path}")

    with open(yaml_path, "r") as f:
        business_yaml = yaml.safe_load(f)

    if "manager" not in business_yaml:
        raise ValueError("YAML must include a top-level 'manager' key")

    config = load_llm_config()
    manager_yaml = business_yaml["manager"]

    # -----------------------------
    # 2. Create role agents
    # -----------------------------
    created_roles = []
    for role_def in manager_yaml.get("managed_agents", []):
        if "yaml" not in role_def:
            continue

        # Parse inline YAML string into dict
        role_yaml = yaml.safe_load(role_def["yaml"])

        # Create the role agent
        role_result = create_then_rename_agent(
            role_yaml, 
            "role", 
            config, 
            headers, 
            base_url, 
            log_file
        )
        if role_result:
            created_roles.append(role_result)

    # -----------------------------
    # 3. Update manager YAML with role links
    # -----------------------------
    if created_roles:
        manager_yaml["managed_agents"] = [
            {
                "id": r["agent_id"],
                "name": r["name"],
                "description": r.get("description", ""),
                "instructions": f"Delegate tasks to role agent {r['name']} (id={r['agent_id']})"
            }
            for r in created_roles
        ]

    # -----------------------------
    # 4. Create manager agent
    # -----------------------------
    manager_result = create_then_rename_agent(
        manager_yaml,
        "manager",
        config,
        headers,
        base_url,
        log_file
    )

    # -----------------------------
    # 5. Return combined result
    # -----------------------------
    return {
        "manager": manager_result,
        "roles": created_roles
    }
