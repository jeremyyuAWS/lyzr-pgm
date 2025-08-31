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
                "description": r["description"],
                "agent_role": r["agent_role"],
                "agent_goal": r["agent_goal"],
                "agent_instructions": r["agent_instructions"],
            }
            for r in created_roles
        ]

        # ✨ Enhance manager instructions with role summaries
        role_summaries = [
            f"- Role '{r['name']}': {r['agent_goal'] or r['description']}"
            for r in created_roles
        ]
        extra_instructions = "\n\nManage these attached roles:\n" + "\n".join(role_summaries)

        manager_def["agent_instructions"] = (
            (manager_def.get("agent_instructions") or "").strip()
            + "\n\n"
            + extra_instructions
        )

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
