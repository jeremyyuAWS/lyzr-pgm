from __future__ import annotations

import os
import sys
import yaml
import logging
import asyncio
from pathlib import Path
from typing import Union, Dict, Any, List
from datetime import datetime
import pytz
import json

from src.api.client_async import LyzrAPIClient  # ✅ async client

# -----------------------------
# Logging
# -----------------------------
logger = logging.getLogger("create-manager-with-roles")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [create-manager-with-roles] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# -----------------------------
# Helpers
# -----------------------------
def _tz() -> pytz.timezone:
    tz_name = os.getenv("APP_TZ", "America/Los_Angeles")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone("America/Los_Angeles")


def _timestamp_str() -> str:
    now = datetime.now(_tz())
    return now.strftime("%d%b%Y-%I:%M%p %Z").upper()


def _suffix_from_id(agent_id: str | None) -> str:
    return (agent_id or "")[-6:] or "XXXXXX"


def _rich_manager_name(base: str, agent_id: str) -> str:
    return f"{base}_v1.0_{_suffix_from_id(agent_id)}_{_timestamp_str()}"


def _rich_role_name(base: str, agent_id: str) -> str:
    return f"(R) {base}_v1.0_{_suffix_from_id(agent_id)}_{_timestamp_str()}"


def _compose_system_prompt(agent_def: Dict[str, Any]) -> str:
    """Build system_prompt by joining role, goal, and instructions."""
    role = agent_def.get("agent_role", "").strip()
    goal = agent_def.get("agent_goal", "").strip()
    instr = agent_def.get("agent_instructions", "").strip()

    parts = []
    if role:
        parts.append(f"ROLE:\n{role}")
    if goal:
        parts.append(f"GOAL:\n{goal}")
    if instr:
        parts.append(f"INSTRUCTIONS:\n{instr}")
    return "\n\n".join(parts).strip()


def _manager_supervision_instructions(
    manager_def: Dict[str, Any], created_roles: List[Dict[str, Any]]
) -> str:
    """Append role responsibilities to manager instructions."""
    base = manager_def.get("agent_instructions", "").strip()
    lines = [base, "", "Manage these attached roles:"]
    for r in created_roles:
        goal = (r.get("agent_goal") or "").strip().replace("\n", " ")
        if goal:
            lines.append(f"- Role '{r['name']}': {goal}")
        else:
            lines.append(
                f"- Role '{r['name']}': Execute delegated sub-tasks from the manager."
            )
    return "\n".join([l for l in lines if l]).strip()


def _safe_parse_role_yaml(role: Dict[str, Any]) -> Dict[str, Any] | None:
    """Parse role['yaml'] (string or dict) safely into a dict."""
    raw = role.get("yaml")
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        # Try YAML first
        try:
            parsed = yaml.safe_load(raw)
            if isinstance(parsed, dict):
                return parsed
            logger.error(
                f"❌ Role {role.get('name')} YAML parsed into {type(parsed)}, expected dict"
            )
        except Exception:
            pass
        # Try JSON as fallback
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                logger.info(f"📦 Parsed role {role.get('name')} as JSON")
                return parsed
        except Exception as e:
            logger.error(f"❌ Failed to parse role YAML/JSON for {role.get('name')}: {e}")
            return None
    logger.error(f"❌ Role {role.get('name')} had unsupported yaml type: {type(raw)}")
    return None


def _load_yaml_or_json(file_or_dict: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """Accept dict, YAML file, JSON file, or string containing YAML/JSON."""
    if isinstance(file_or_dict, dict):
        return file_or_dict
    if isinstance(file_or_dict, Path):
        text = file_or_dict.read_text()
    elif isinstance(file_or_dict, str):
        text = file_or_dict
    else:
        raise ValueError("Unsupported type for manager_yaml")

    # Try YAML first
    try:
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            logger.info("📦 Parsed manager as YAML")
            return parsed
    except Exception:
        logger.warning("⚠️ YAML parse failed, trying JSON")

    # Try JSON as fallback
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            logger.info("📦 Parsed manager as JSON")
            return parsed
    except Exception as e:
        raise ValueError(f"Failed to parse as YAML or JSON: {e}")

    raise ValueError("Input is not a dict after parsing")


# -----------------------------
# Canonical Examples
# -----------------------------
def canonical_role_examples(role_name: str) -> str:
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
      features: []
      tools: []
      response_format:
        type: json
      provider_id: OpenAI
      model: gpt-4o-mini
      temperature: 0.3
      top_p: 0.9
      llm_credential_id: lyzr_openai
"""


def canonical_manager_examples(manager_name: str, role_names: List[str]) -> str:
    roles_block = "\n".join(
        [
            f"""  - name: {r}
    type: role
    yaml: |
      name: {r}
      description: Example Role description
      agent_role: Example Role
      agent_goal: Example goal
      agent_instructions: Example instructions
      features: []
      tools: []
      response_format:
        type: json
      provider_id: OpenAI
      model: gpt-4o-mini
      temperature: 0.3
      top_p: 0.9
      llm_credential_id: lyzr_openai"""
            for r in role_names
        ]
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
      features: []
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

# -----------------------------
# Main Orchestration
# -----------------------------
async def create_manager_with_roles(
    client: LyzrAPIClient, manager_yaml: Union[Path, Dict[str, Any], str]
) -> Dict[str, Any]:
    """
    Flow:
      Accepts:
        - Dict with top-level manager fields (id, name, etc.)  ✅ JSON path
        - Dict with "manager" key wrapping managed_agents       ✅ Old path
        - YAML/JSON file path or raw string
      Steps:
        1. Create role agents (PUT update + rich names).
        2. Create manager agent.
        3. PUT update manager with supervision instructions, examples, and role links.
    """
    manager_yaml = _load_yaml_or_json(manager_yaml)

    # --- New: handle raw JSON manager payload directly ---
    if "manager" in manager_yaml:
        manager_def = manager_yaml.get("manager")
    elif "id" in manager_yaml and "name" in manager_yaml:
        manager_def = manager_yaml
    else:
        raise ValueError(
            "Input must contain either a top-level 'manager' key "
            "or direct agent fields (id, name, etc.)"
        )

    created_roles: List[Dict[str, Any]] = []

    # ----- 1. Create roles -----
    for role in manager_def.get("managed_agents", []):
        parsed_role = _safe_parse_role_yaml(role)
        if not parsed_role:
            logger.warning(f"⚠️ Skipping role {role.get('name')} (invalid yaml/json)")
            continue

        role_name = parsed_role.get("name", "ROLE")
        parsed_role["examples"] = canonical_role_examples(role_name)

        role_resp = await client.create_agent_from_yaml(parsed_role)
        if not role_resp.get("ok"):
            print(f"❌ Failed to create role {role_name}")
            continue

        role_id = (role_resp.get("data") or {}).get("agent_id")
        if not role_id:
            print(f"❌ Role {role_name} created but missing agent_id")
            continue

        # Rename + PUT update
        role_renamed = _rich_role_name(role_name, role_id)
        role_updates = {
            "name": role_renamed,
            "system_prompt": _compose_system_prompt(parsed_role),
            "examples": parsed_role["examples"],
            "agent_role": parsed_role.get("agent_role", ""),
            "agent_goal": parsed_role.get("agent_goal", ""),
            "agent_instructions": parsed_role.get("agent_instructions", ""),
        }
        await client.update_agent(role_id, role_updates)

        print(f"🧩 Created role agent {role_renamed} [{role_id} | {_timestamp_str()}]")

        created_roles.append(
            {
                "id": role_id,
                "name": role_renamed,
                "base_name": role_name,
                "description": parsed_role.get("description", ""),
                "agent_role": parsed_role.get("agent_role", ""),
                "agent_goal": parsed_role.get("agent_goal", ""),
                "agent_instructions": parsed_role.get("agent_instructions", ""),
            }
        )

    # ----- 2. Create manager -----
    manager_base_name = manager_def.get("name", "MANAGER")
    mgr_instr_with_supervision = _manager_supervision_instructions(
        manager_def, created_roles
    )
    mgr_examples = canonical_manager_examples(
        manager_base_name, [r["base_name"] for r in created_roles]
    )
    manager_def["examples"] = mgr_examples

    mgr_resp = await client.create_agent_from_yaml(manager_def)
    if not mgr_resp.get("ok"):
        print("❌ Manager creation failed")
        return {}

    manager_id = (mgr_resp.get("data") or {}).get("agent_id")
    if not manager_id:
        print("❌ Manager created but missing agent_id")
        return {}

    # ----- 3. PUT update manager -----
    manager_renamed = _rich_manager_name(manager_base_name, manager_id)
    managed_agents_payload = [
        {
            "id": r["id"],
            "name": r["name"],
            "usage_description": f"Manager delegates YAML-subtasks to '{r['name']}'.",
        }
        for r in created_roles
    ]
    manager_updates = {
        "name": manager_renamed,
        "system_prompt": _compose_system_prompt(
            {
                "agent_role": manager_def.get("agent_role", ""),
                "agent_goal": manager_def.get("agent_goal", ""),
                "agent_instructions": mgr_instr_with_supervision,
            }
        ),
        "examples": mgr_examples,
        "agent_role": manager_def.get("agent_role", ""),
        "agent_goal": manager_def.get("agent_goal", ""),
        "agent_instructions": mgr_instr_with_supervision,
        "managed_agents": managed_agents_payload,
        "description": manager_def.get("description", ""),
        "features": manager_def.get("features", []),
        "tools": manager_def.get("tools", []),
        "llm_credential_id": manager_def.get("llm_credential_id", "lyzr_openai"),
        "provider_id": manager_def.get("provider_id", "OpenAI"),
        "model": manager_def.get("model", "gpt-4o-mini"),
        "top_p": manager_def.get("top_p", 0.9),
        "temperature": manager_def.get("temperature", 0.3),
        "response_format": manager_def.get("response_format", {"type": "json"}),
    }
    await client.update_agent(manager_id, manager_updates)

    print(
        f"🤖 Created manager agent {manager_renamed} [{manager_id} | {_timestamp_str()}] with {len(created_roles)} linked roles"
    )

    return {
        "agent_id": manager_id,
        "name": manager_renamed,
        "roles": created_roles,
        "timestamp": _timestamp_str(),
    }


# -----------------------------
# __main__ runner
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("⚠️ Usage: python scripts/create_manager_with_roles.py <manager_yaml_path>")
        sys.exit(1)

    yaml_path = Path(sys.argv[1])
    if not yaml_path.exists():
        print(f"❌ File not found: {yaml_path}")
        sys.exit(1)

    async def _main():
        async with LyzrAPIClient(debug=True) as client:
            result = await create_manager_with_roles(client, yaml_path)
            print("\n✅ Done. Result:")
            print(result)

    asyncio.run(_main())
