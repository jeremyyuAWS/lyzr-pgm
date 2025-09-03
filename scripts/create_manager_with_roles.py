from __future__ import annotations

import os
import sys
import yaml
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Union
from datetime import datetime
import pytz
import json

from src.api.client_async import LyzrAPIClient

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
    return datetime.now(_tz()).strftime("%d%b%Y-%I:%M%p %Z").upper()


def _suffix_from_id(agent_id: str | None) -> str:
    return (agent_id or "")[-6:] or "XXXXXX"


def _rich_manager_name(base: str, agent_id: str) -> str:
    return f"{base}_v1.0_{_suffix_from_id(agent_id)}_{_timestamp_str()}"


def _rich_role_name(base: str, agent_id: str) -> str:
    return f"(R) {base}_v1.0_{_suffix_from_id(agent_id)}_{_timestamp_str()}"


def _compose_system_prompt(agent_def: Dict[str, Any]) -> str:
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
    base = manager_def.get("agent_instructions", "").strip()
    lines = [base, "", "Manage these attached roles:"]
    for r in created_roles:
        goal = (r.get("agent_goal") or "").strip().replace("\n", " ")
        lines.append(f"- Role '{r['name']}': {goal or 'Execute delegated sub-tasks'}")
    return "\n".join([l for l in lines if l]).strip()


def _safe_parse_role(role: Dict[str, Any]) -> Dict[str, Any] | None:
    raw = role.get("yaml")
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return yaml.safe_load(raw)
        except Exception:
            try:
                return json.loads(raw)
            except Exception:
                return None
    return None


def _load_manager(file_or_dict: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(file_or_dict, dict):
        logger.info("📦 Using provided JSON dict")
        return file_or_dict
    if isinstance(file_or_dict, (str, Path)):
        text = Path(file_or_dict).read_text() if isinstance(file_or_dict, Path) else file_or_dict
        try:
            return yaml.safe_load(text)
        except Exception:
            return json.loads(text)
    raise ValueError("Unsupported manager input type")


# -----------------------------
# Main Orchestration
# -----------------------------
async def create_manager_with_roles(
    client: LyzrAPIClient, manager_input: Union[Dict[str, Any], Path, str]
) -> Dict[str, Any]:
    manager_def = _load_manager(manager_input)

    if not isinstance(manager_def, dict) or not manager_def.get("name"):
        raise ValueError("Manager JSON must be a dict with 'name'")

    created_roles: List[Dict[str, Any]] = []

    for role in manager_def.get("managed_agents", []):
        parsed_role = _safe_parse_role(role)
        if not parsed_role:
            continue

        role_resp = await client.create_agent_from_yaml(parsed_role)
        if not role_resp.get("ok"):
            continue

        role_id = (role_resp.get("data") or {}).get("agent_id")
        if not role_id:
            continue

        role_renamed = _rich_role_name(parsed_role.get("name", "ROLE"), role_id)
        await client.update_agent(role_id, {
            "name": role_renamed,
            "system_prompt": _compose_system_prompt(parsed_role),
            "agent_role": parsed_role.get("agent_role", ""),
            "agent_goal": parsed_role.get("agent_goal", ""),
            "agent_instructions": parsed_role.get("agent_instructions", ""),
        })

        created_roles.append({
            "id": role_id,
            "name": role_renamed,
            "description": parsed_role.get("description", ""),
            "agent_role": parsed_role.get("agent_role", ""),
            "agent_goal": parsed_role.get("agent_goal", ""),
            "agent_instructions": parsed_role.get("agent_instructions", ""),
        })

    mgr_resp = await client.create_agent_from_yaml(manager_def)
    if not mgr_resp.get("ok"):
        return {}

    manager_id = (mgr_resp.get("data") or {}).get("agent_id")
    if not manager_id:
        return {}

    manager_renamed = _rich_manager_name(manager_def["name"], manager_id)
    await client.update_agent(manager_id, {
        "name": manager_renamed,
        "system_prompt": _compose_system_prompt(manager_def),
        "agent_role": manager_def.get("agent_role", ""),
        "agent_goal": manager_def.get("agent_goal", ""),
        "agent_instructions": _manager_supervision_instructions(manager_def, created_roles),
        "managed_agents": [{"id": r["id"], "name": r["name"]} for r in created_roles],
    })

    return {"agent_id": manager_id, "name": manager_renamed, "roles": created_roles}


# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_manager_with_roles.py <manager.json|yaml>")
        sys.exit(1)

    yaml_path = Path(sys.argv[1])
    async def _main():
        async with LyzrAPIClient(debug=True) as client:
            result = await create_manager_with_roles(client, yaml_path)
            print(json.dumps(result, indent=2))

    asyncio.run(_main())
