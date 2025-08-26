import sys
import json
import yaml
import argparse
from pathlib import Path

from src.api.client import LyzrAPIClient
from src.utils.prompt_builder import build_system_prompt
from src.utils.payload_normalizer import normalize_payload


def create_agent(yaml_path: str, client: LyzrAPIClient, debug: bool = False):
    """Create a single agent from a YAML definition."""
    with open(yaml_path, "r") as f:
        agent_yaml = yaml.safe_load(f)

    # Normalize payload
    payload = normalize_payload(agent_yaml)

    # Build system_prompt if not already provided
    if "system_prompt" not in payload:
        payload["system_prompt"] = build_system_prompt(agent_yaml)

    if debug:
        print("🔍 Payload being sent:")
        print(json.dumps(payload, indent=2))

    # Call API (FIXED: use client.create_agent)
    res = client.create_agent(payload)

    agent_id = res.get("data", {}).get("agent_id") if res and res.get("ok") else None
    agent_name = agent_yaml.get("name", "unknown")

    if agent_id:
        print(f"✅ Created agent {agent_name} with ID {agent_id}")
        return agent_id
    else:
        print(f"❌ Failed to create agent {agent_name}: {res}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Create a single agent from YAML")
    parser.add_argument("yaml_file", type=str, help="Path to the agent YAML file")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    client = LyzrAPIClient(debug=args.debug)
    yaml_path = Path(args.yaml_file)

    if not yaml_path.exists():
        print(f"❌ File not found: {yaml_path}")
        sys.exit(1)

    create_agent(str(yaml_path), client, debug=args.debug)


if __name__ == "__main__":
    main()
