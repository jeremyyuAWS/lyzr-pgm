# app/services/agent_creator.py

from pathlib import Path
import yaml
from scripts.run_business_flow import create_then_rename_agent, load_llm_config


REQUIRED_AGENT_FIELDS = [
    "name",
    "description",
    "agent_role",
    "agent_goal",
    "agent_instructions",
    "features",
    "tools",
    "response_format",
    "provider_id",
    "model",
    "temperature",
    "top_p",
    "llm_credential_id"
]


def normalize_agent_yaml(agent_yaml: dict) -> dict:
    """
    Ensure all required keys are present in the agent payload.
    Fill missing keys with safe defaults so Studio doesn't strip them.
    """
    normalized = {}

    for field in REQUIRED_AGENT_FIELDS:
        if field in agent_yaml:
            normalized[field] = agent_yaml[field]
        else:
            # Fill defaults
            if field == "features":
                normalized[field] = []
            elif field == "tools":
                normalized[field] = []
            elif field == "response_format":
                normalized[field] = {"type": "json"}
            elif field == "temperature":
                normalized[field] = 0.7
            elif field == "top_p":
                normalized[field] = 0.9
            elif field == "provider_id":
                normalized[field] = "OpenAI"
            elif field == "model":
                normalized[field] = "gpt-4o-mini"
            elif field == "llm_credential_id":
                normalized[field] = "lyzr_openai"
            else:
                normalized[field] = ""  # safe fallback

    return normalized


def create_manager_with_roles(yaml_path: Path, headers: dict, base_url: str, log_file: Path):
    """
    Create a manager agent and its associated role agents from a YAML definition.
    Expands inline managed_agents into real agents and links them back to the manager.
    """

    if not Path(yaml_path).exists():
        raise FileNotFoundError(f"YAML path not found: {yaml_path}")

    with open(yaml_path, "r") as f:
        business_yaml = yaml.safe_load(f)

    if "manager" not in business_yaml:
        raise ValueError("YAML must include a top-level 'manager' key")

    config = load_llm_config()
    manager_yaml = normalize_agent_yaml(business_yaml["manager"])

    created_roles = []
    for role_def in manager_yaml.get("managed_agents", []):
        if "yaml" not in role_def:
            continue

        role_yaml = yaml.safe_load(role_def["yaml"])
        role_payload = normalize_agent_yaml(role_yaml)

        for role in manager_yaml.get("managed_agents", []):
            if "yaml" in role:
                role_yaml = yaml.safe_load(role["yaml"])
                # ensure full schema gets passed, not truncated
                role_result = create_then_rename_agent(role_yaml, "role", config, headers, base_url, log_file)
                created_roles.append(role_result)

        # attach roles by ID
        if created_roles:
            manager_yaml["managed_agents"] = [
                {"id": r["agent_id"], "name": r["name"], "description": r.get("description", "")}
                for r in created_roles
            ]

        # now create manager with full YAML (role/goal/instructions intact)
        manager_result = create_then_rename_agent(manager_yaml, "manager", config, headers, base_url, log_file)

        role_result = create_then_rename_agent(
            role_payload,
            "role",
            config,
            headers,
            base_url,
            log_file
        )
        if role_result:
            created_roles.append(role_result)

    # Update manager with real linked role IDs
    if created_roles:
        manager_yaml["managed_agents"] = [
            {
                "id": r["agent_id"],
                "name": r["name"],
                "description": r.get("description", ""),
                "instructions": f"Delegate to role agent {r['name']} (id={r['agent_id']})"
            }
            for r in created_roles
        ]

    manager_result = create_then_rename_agent(
        manager_yaml,
        "manager",
        config,
        headers,
        base_url,
        log_file
    )

    return {
        "manager": manager_result,
        "roles": created_roles
    }
