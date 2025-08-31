# scripts/create_manager_with_roles.py
# Used in api/main_with_auth.py

import sys
import os
import yaml
from pathlib import Path
from datetime import datetime
from typing import Union
from src.api.client import LyzrAPIClient
from scripts.create_agent_from_yaml import create_agent_from_yaml


def canonical_role_examples(role_name: str) -> str:
    """Return canonical YAML schema string for a Role agent."""
    return f"""Expected canonical YAML format for Role agents:

workflow_name: {role_name}_Flow
workflow_yaml: |
  flow_name: {role_name}_Flow
  flow_data:
    tasks:
      - name: {role_name.lower()}_task
        function: call_agent
        agent: {role_name}
agents:
  - name: {role_name}
    type: role
    yaml: |
      name: {role_name}
      description: Example Role description
      agent_role: Example Role
      agent_goal: Example goal
      agent_instructions: Example instructions
      features:
        - type: yaml_role_generation
          config: {{}}
          priority: 0
      tools: []
      response_format:
        type: json
      provider_id: OpenAI
      model: gpt-4o-mini
      temperature: 0.3
      top_p: 0.9
      llm_credential_id: lyzr_openai
"""


def canonical_manager_examples(manager_name: str, role_names: list[str]) -> str:
    """Return canonical YAML schema string for a Manager + Role setup."""
    roles_block = "\n".join(
        [f"  - name: {r}\n    type: role\n    yaml: |\n      name: {r}\n      description: Example Role description\n      agent_role: Example Role\n      agent_goal: Example goal\n      agent_instructions: Example instructions\n      features:\n        - type: yaml_role_generation\n          config: {{}}\n          priority: 0\n      tools: []\n      response_format:\n        type: json\n      provider_id: OpenAI\n      model: gpt-4o-mini\n      temperature: 0.3\n      top_p: 0.9\n      llm_credential_id: lyzr_openai"
         for r in role_names]
    )

    return f"""Expected canonical YAML format for Manager + Roles:

workflow_name: {manager_name}_Flow
workflow_yaml: |
  flow_name: {manager_name}_Flow
  flow_data:
    tasks:
      - name: {manager_name.lower()}_task
        function: call_agent
        agent: {manager_name}
agents:
  - name: {manager_name}
    type: manager
    yaml: |
      name: {manager_name}
      description: Example Composer Manager description
      agent_role: Composer Manager
      agent_goal: Example manager goal
      agent_instructions: Example instructions
      features:
        - type: proposal_generation
          config: {{}}
          priority: 1
      tools: []
      response_format:
        type: json
      provider_id: OpenAI
      model: gpt-4o-mini
      temperature: 0.3
      top_p: 0.9
      llm_credential_id: lyzr_openai
{roles_block if roles_block else ""}
"""


def create_manager_with_roles(client: LyzrAPIClient, manager_yaml: Union[Path, dict]):
    """Create role agents first, then create a manager agent referencing them."""

    # If a Path is passed, load YAML from disk
    if isinstance(manager_yaml, Path):
        if not manager_yaml.exists():
            raise FileNotFoundError(f"Manager YAML not found: {manager_yaml}")
        with open(manager_yaml, "r") as f:
            manager_yaml = yaml.safe_load(f)

    if not isinstance(manager_yaml, dict):
        raise ValueError("manager_yaml must be a dict or Path")

    manager_def = manager_yaml.get("manager")
    if not manager_def:
        raise ValueError("YAML must contain a top-level 'manager' key")

    # --- Create roles first ---
    created_roles = []
    for role in manager_def.get("managed_agents", []):
        if "yaml" not in role:
            print(f"⚠️ Skipping role {role.get('name')} (no inline YAML)")
            continue

        role_yaml = yaml.safe_load(role["yaml"])

        # ✅ Inject canonical examples
        role_yaml["examples"] = canonical_role_examples(role_yaml.get("name"))

        print(f"🎭 Creating role agent: {role_yaml.get('name')}")
        role_resp = create_agent_from_yaml(client, role_yaml)

        if role_resp.get("ok"):
            role_id = role_resp["data"].get("agent_id")
            created_roles.append({
                "id": role_id,
                "name": role_yaml.get("name"),
                "description": role_yaml.get("description", ""),
                "agent_role": role_yaml.get("agent_role", ""),
                "agent_goal": role_yaml.get("agent_goal", ""),
                "agent_instructions": role_yaml.get("agent_instructions", ""),
            })
        else:
            print(f"❌ Failed to create role {role_yaml.get('name')}")
            print(role_resp)

    # --- Attach created roles to manager ---
    if created_roles:
        manager_def["managed_agents"] = [
            {
                "id": r["id"],
                "name": r["name"],
                "usage_description": f"Manager coordinates role '{r['name']}'"
            }
            for r in created_roles
        ]

    # ✅ Inject canonical examples into manager
    role_names = [r["name"] for r in created_roles]
    manager_def["examples"] = canonical_manager_examples(manager_def.get("name"), role_names)

    # --- Create the manager last ---
    print(f"👑 Creating manager agent: {manager_def.get('name')}")
    manager_resp = create_agent_from_yaml(client, manager_def)

    if not manager_resp.get("ok"):
        print("❌ Manager creation failed")
        print(manager_resp)
        return None

    manager_id = manager_resp["data"].get("agent_id")
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p %Z")

    return {
        "agent_id": manager_id,
        "name": manager_def.get("name"),
        "roles": created_roles,
        "timestamp": timestamp,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_manager_with_roles <manager_yaml>")
        sys.exit(1)

    yaml_path = Path(sys.argv[1])

    api_key = os.getenv("LYZR_API_KEY")
    if not api_key:
        print("❌ Missing LYZR_API_KEY in environment")
        sys.exit(1)

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(api_key=api_key, debug=debug, timeout=180)

    result = create_manager_with_roles(client, yaml_path)
    if not result:
        sys.exit(1)

    print(f"\n✅ Manager + Roles created successfully!")
    print(f"   Manager ID   : {result['agent_id']}")
    print(f"   Manager Name : {result['name']}")
    print(f"   Roles        : {[r['name'] for r in result['roles']]}")
    print(f"   Timestamp    : {result['timestamp']}")


if __name__ == "__main__":
    main()
