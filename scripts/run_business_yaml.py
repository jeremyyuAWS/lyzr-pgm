import os
import json
import yaml
import httpx
from pathlib import Path

def load_llm_config():
    """Load config/llm_config.yaml"""
    config_path = Path("config/llm_config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def build_system_prompt(agent: dict) -> str:
    """Combine role, goal, and instructions into system_prompt."""
    role = agent.get("role", "")
    goal = agent.get("goal", "")
    instructions = agent.get("instructions", "")
    return f"{role}\n\nGoal:\n{goal}\n\nInstructions:\n{instructions}"

def enrich_for_api(agent: dict, agent_type: str, config: dict) -> dict:
    """Expand business-friendly agent into API-ready payload using config"""
    base_defaults = {
        "llm_credential_id": config["default_llm_credential_id"],
        "provider_id": config["default_provider_id"],
        "model": config["default_model"],
        "top_p": config["default_top_p"],
        "response_format": {"type": "json"},
    }

    # Role vs Manager specific overrides
    specific = config.get(agent_type, {})

    enriched = {
        "name": agent["name"],
        "description": agent["description"],
        "system_prompt": build_system_prompt(agent),
    }
    enriched.update(base_defaults)
    enriched.update({
        "temperature": specific.get("temperature", config["default_temperature"]),
        "features": specific.get("features", []),
        "tools": specific.get("tools", []),
    })
    return enriched

def main():
    # --- Load Config ---
    config = load_llm_config()

    # --- Load Business YAML ---
    yaml_path = Path("agents/managers/KYC_Onboarding_Flow.yaml")
    with open(yaml_path, "r") as f:
        business_yaml = yaml.safe_load(f)

    api_key = os.getenv("LYZR_API_KEY")
    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai/v3/agents/")

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    # Manager
    manager_payload = enrich_for_api(business_yaml["manager"], "manager", config)
    print("🚀 Creating manager agent...")
    resp = httpx.post(base_url, headers=headers, json=manager_payload, timeout=60)
    print("Manager response:", resp.status_code, resp.text)

    # Roles
    for role in business_yaml.get("roles", []):
        role_payload = enrich_for_api(role, "role", config)
        print(f"🚀 Creating role agent {role['name']}...")
        resp = httpx.post(base_url, headers=headers, json=role_payload, timeout=60)
        print("Role response:", resp.status_code, resp.text)

if __name__ == "__main__":
    main()
