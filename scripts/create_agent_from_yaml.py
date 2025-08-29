import sys
import os
import yaml
from pathlib import Path
from src.api.client import LyzrAPIClient

def create_agent_from_yaml(client: LyzrAPIClient, yaml_path: Path):
    """Load YAML from disk and create a Lyzr agent via API."""
    with open(yaml_path, "r") as f:
        agent_def = yaml.safe_load(f)

    # Build payload for API
    payload = {
        "template_type": agent_def.get("template_type", "single_task"),
        "name": agent_def["name"],
        "description": agent_def.get("description", ""),
        "agent_role": agent_def.get("agent_role", ""),
        "agent_goal": agent_def.get("agent_goal", ""),
        "agent_instructions": agent_def.get("agent_instructions", ""),
        "features": agent_def.get("features", []),
        "tools": agent_def.get("tools", []),
        "response_format": agent_def.get("response_format", {"type": "json"}),
        "provider_id": agent_def.get("llm_config", {}).get("provider_id", "OpenAI"),
        "model": agent_def.get("llm_config", {}).get("model", "gpt-4o-mini"),
        "temperature": agent_def.get("llm_config", {}).get("temperature", 0.7),
        "top_p": agent_def.get("llm_config", {}).get("top_p", 0.9),
        "llm_credential_id": agent_def.get("llm_config", {}).get("llm_credential_id", "lyzr-default"),
    }

    print(f"⚙️ Creating agent from {yaml_path}…")
    resp = client._request("POST", "/v3/agents/", payload=payload)

    if resp.get("ok"):
        agent_id = resp["data"].get("agent_id", "unknown")
        print(f"✅ Created agent {agent_def['name']} → {agent_id}")
    else:
        print(f"❌ Failed to create agent from {yaml_path}")
        print(resp)

    return resp


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_agent_from_yaml <agent_yaml_file>")
        sys.exit(1)

    yaml_file = Path(sys.argv[1])
    if not yaml_file.exists():
        print(f"❌ YAML file not found: {yaml_file}")
        sys.exit(1)

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)

    create_agent_from_yaml(client, yaml_file)


if __name__ == "__main__":
    main()
