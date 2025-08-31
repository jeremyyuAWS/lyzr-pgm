import sys
import os
import yaml
from pathlib import Path
from typing import Union, Dict, Any
from src.api.client import LyzrAPIClient


def build_payload(agent_def: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a YAML/dict agent definition into canonical payload for Studio API."""
    return {
        "template_type": agent_def.get("template_type", "single_task"),
        "name": agent_def.get("name"),
        "description": agent_def.get("description", ""),
        "agent_role": agent_def.get("agent_role", ""),
        "agent_goal": agent_def.get("agent_goal", ""),
        "agent_instructions": agent_def.get("agent_instructions", ""),
        "features": agent_def.get("features", []),
        "tools": agent_def.get("tools", []),
        "response_format": agent_def.get("response_format", {"type": "json"}),
        "provider_id": agent_def.get("provider_id", "OpenAI"),
        "model": agent_def.get("model", "gpt-4o-mini"),
        "temperature": agent_def.get("temperature", 0.7),
        "top_p": agent_def.get("top_p", 0.9),
        "llm_credential_id": agent_def.get("llm_credential_id", "lyzr_openai"),
    }


def create_agent_from_yaml(
    client: LyzrAPIClient, 
    yaml_input: Union[Path, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Create a Lyzr agent from a YAML file path or a pre-parsed dict.
    Returns the raw API response.
    """
    if isinstance(yaml_input, Path):
        if not yaml_input.exists():
            raise FileNotFoundError(f"YAML file not found: {yaml_input}")
        with open(yaml_input, "r") as f:
            agent_def = yaml.safe_load(f)
        src_label = str(yaml_input)
    elif isinstance(yaml_input, dict):
        agent_def = yaml_input
        src_label = "<inline-dict>"
    else:
        raise TypeError("yaml_input must be a Path or dict")

    payload = build_payload(agent_def)

    print(f"⚙️ Creating agent from {src_label}…")
    resp = client._request("POST", "/v3/agents/", payload=payload)

    if resp.get("ok"):
        data = resp.get("data", {})
        agent_id = data.get("agent_id", "unknown")
        print(f"✅ Created agent {agent_def.get('name')} → {agent_id}")
    else:
        print(f"❌ Failed to create agent from {src_label}")
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
