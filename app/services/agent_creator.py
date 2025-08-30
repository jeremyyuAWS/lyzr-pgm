from pathlib import Path
import yaml
from scripts.run_business_flow import create_then_rename_agent, load_llm_config
import os

def create_manager_with_roles(yaml_path: Path, headers, base_url: str, log_file):
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
