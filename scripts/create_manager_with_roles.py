# scripts/create_manager_with_roles.py
# Orchestration: create roles first → rename inline → create manager with linked role IDs

import os
import yaml
import logging
import pytz
from pathlib import Path
from typing import Union, Dict, Any, List
from datetime import datetime

from src.api.client_async import LyzrAPIClient

logger = logging.getLogger("create-manager-with-roles")

# ---------- Timezone / naming helpers ----------

def _tz() -> pytz.timezone:
    tz_name = os.getenv("APP_TZ", "America/Los_Angeles")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone("America/Los_Angeles")

def _timestamp_str() -> str:
    now = datetime.now(_tz())
    return now.strftime("%d%b%Y-%I:%M%p %Z").upper()

def _rich_manager_name(base: str) -> str:
    return f"{base}_v1.0_{_timestamp_str()}"

def _rich_role_name(base: str) -> str:
    return f"(R) {base}_v1.0_{_timestamp_str()}"

# ---------- Prompt + examples builders ----------

def _compose_system_prompt(agent_def: Dict[str, Any]) -> str:
    role = agent_def.get("agent_role", "").strip()
    goal = agent_def.get("agent_goal", "").strip()
    instr = agent_def.get("agent_instructions", "").strip()

    sections = []
    if role:
        sections.append(f"ROLE:\n{role}")
    if goal:
        sections.append(f"GOAL:\n{goal}")
    if instr:
        sections.append(f"INSTRUCTIONS:\n{instr}")
    return "\n\n".join(sections).strip()

def _manager_supervision_instructions(manager_def: Dict[str, Any], created_roles: List[Dict[str, Any]]) -> str:
    base = manager_def.get("agent_instructions", "").strip()
    lines = [base, "", "Manage these attached roles:"]
    for r in created_roles:
        bullets = (r.get("agent_goal") or "").strip().replace("\n", " ").strip()
        if bullets:
            lines.append(f"- Role '{r['name']}': {bullets}")
        else:
            lines.append(f"- Role '{r['name']}': Execute delegated sub-tasks from the manager.")
    return "\n".join([l for l in lines if l]).strip()

# ---------- Main orchestration ----------

async def create_manager_with_roles(client: LyzrAPIClient, manager_yaml: Union[Path, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Flow:
      1. Parse manager YAML/JSON
      2. Create role agents first (renamed inline)
      3. Create manager agent with rich name, linked role IDs, and updated instructions
    """
    try:
        logger.info("📥 Starting create_manager_with_roles orchestration")

        # 1. Load YAML if file path
        if isinstance(manager_yaml, Path):
            logger.info(f"📂 Loading manager YAML from {manager_yaml}")
            with open(manager_yaml, "r") as f:
                manager_yaml = yaml.safe_load(f)

        if not isinstance(manager_yaml, dict):
            raise ValueError("manager_yaml must be a dict or Path")

        manager_def = manager_yaml.get("manager")
        if not manager_def:
            raise ValueError("YAML must contain a top-level 'manager' key")

        # 2. Create roles first
        created_roles: List[Dict[str, Any]] = []
        for role_def in manager_def.get("managed_agents", []):
            role_name = role_def.get("name", "ROLE")
            role_renamed = _rich_role_name(role_name)

            role_payload = {
                **role_def,
                "name": role_renamed,
                "system_prompt": _compose_system_prompt(role_def),
            }

            logger.info(f"🎭 Creating role agent → {role_renamed}")
            role_resp = await client.create_agent(role_payload)
            if not role_resp.get("ok"):
                logger.error(f"❌ Failed to create role {role_renamed}: {role_resp}")
                continue

            role_data = role_resp["data"]
            created_roles.append({
                "id": role_data.get("agent_id") or role_data.get("_id"),
                "name": role_renamed,
                "description": role_payload.get("description", ""),
                "agent_role": role_payload.get("agent_role", ""),
                "agent_goal": role_payload.get("agent_goal", ""),
                "agent_instructions": role_payload.get("agent_instructions", ""),
            })

        # 3. Create manager
        manager_base_name = manager_def.get("name", "MANAGER")
        manager_renamed = _rich_manager_name(manager_base_name)

        manager_payload = {
            **manager_def,
            "name": manager_renamed,
            "agent_instructions": _manager_supervision_instructions(manager_def, created_roles),
            "managed_agents": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "usage_description": f"Manager delegates YAML subtasks to {r['name']}"
                }
                for r in created_roles if r.get("id")
            ],
        }

        logger.info(f"👑 Creating manager agent → {manager_renamed}")
        mgr_resp = await client.create_agent(manager_payload)
        if not mgr_resp.get("ok"):
            logger.error(f"❌ Manager creation failed: {mgr_resp}")
            return {"ok": False, "error": "Manager creation failed", "roles": created_roles}

        manager_data = mgr_resp["data"]

        logger.info("✅ Manager + roles orchestration complete")

        return {
            "ok": True,
            "manager": manager_data,
            "roles": created_roles,
            "timestamp": _timestamp_str(),
        }

    except Exception as e:
        logger.exception("💥 Exception in create_manager_with_roles")
        return {"ok": False, "error": str(e)}
