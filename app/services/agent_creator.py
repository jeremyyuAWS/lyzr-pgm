from pathlib import Path
import yaml
from scripts.run_business_flow import create_then_rename_agent, load_llm_config
import os

def create_manager_with_roles(yaml_path, headers, base_url, log_file):
    # create manager first...
    manager_result = create_agent_from_yaml(manager_yaml, headers, base_url)

    roles = manager_yaml.get("managed_agents", [])
    created_roles = []

    for role in roles:
        if "yaml" in role:
            role_yaml = yaml.safe_load(role["yaml"])
            role_result = create_agent_from_yaml(role_yaml, headers, base_url)
            created_roles.append(role_result)

    return {"manager": manager_result, "roles": created_roles}

    with open(yaml_path, "r") as f:
        business_yaml = yaml.safe_load(f)

    config = load_llm_config()
    role_results = []
    for role in business_yaml.get("roles", []):
        r = create_then_rename_agent(role, "role", config, headers, base_url, log_file)
        if r:
            role_results.append(r)

    manager = business_yaml["manager"]
    if role_results:
        manager["managed_agents"] = [
            {"id": r["agent_id"], "name": r["name"]} for r in role_results
        ]

    mgr = create_then_rename_agent(manager, "manager", config, headers, base_url, log_file)
    return {"roles": role_results, "manager": mgr}
