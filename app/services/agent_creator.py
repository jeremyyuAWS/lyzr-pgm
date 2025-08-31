from pathlib import Path
import yaml
from scripts.create_agent_from_yaml import create_agent_from_yaml
from scripts.run_business_flow import load_llm_config

def yaml_to_payload(yaml_dict: dict, api_key: str) -> dict:
    """Flatten YAML dict into Studio API payload schema."""
    return {
        "api_key": api_key,
        "template_type": yaml_dict.get("template_type", "single_task"),
        "name": yaml_dict["name"],
        "description": yaml_dict.get("description", ""),
        "agent_role": yaml_dict.get("agent_role", ""),
        "agent_instructions": yaml_dict.get("agent_instructions", ""),
        "agent_goal": yaml_dict.get("agent_goal", ""),
        "features": yaml_dict.get("features", []),
        "tool": yaml_dict.get("tool", ""),
        "tool_usage_description": yaml_dict.get("tool_usage_description", ""),
        "response_format": yaml_dict.get("response_format"),
        "provider_id": yaml_dict.get("provider_id", "OpenAI"),
        "model": yaml_dict.get("model", "gpt-4o-mini"),
        "top_p": yaml_dict.get("top_p", 0.9),
        "temperature": yaml_dict.get("temperature", 0.7),
        "llm_credential_id": yaml_dict.get("llm_credential_id", "lyzr_openai"),
    }

def create_manager_with_roles(yaml_path: Path, headers, base_url: str, log_file: Path, api_key: str):
    """
    Create manager and all managed role agents from a YAML file.
    - Expands inline roles into full API payloads.
    - Attaches role IDs back to the manager before creating it.
    """
    with open(yaml_path, "r") as f:
        business_yaml = yaml.safe_load(f)

    manager_yaml = business_yaml["manager"]

    # --- 1. Create role agents first ---
    created_roles = []
    for role in manager_yaml.get("managed_agents", []):
        if "yaml" in role:
            role_yaml = yaml.safe_load(role["yaml"])
            role_payload = yaml_to_payload(role_yaml, api_key)
            role_result = create_agent_from_yaml(role_payload, headers, base_url)
            created_roles.append(role_result)

    # --- 2. Replace manager's managed_agents with role IDs ---
    if created_roles:
        manager_yaml["managed_agents"] = [
            {"id": r["agent_id"], "name": r["name"]}
            for r in created_roles
        ]

    # --- 3. Create manager with full payload ---
    manager_payload = yaml_to_payload(manager_yaml, api_key)
    manager_result = create_agent_from_yaml(manager_payload, headers, base_url)

    return {
        "manager": manager_result,
        "roles": created_roles
    }
