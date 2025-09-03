# scripts/create_manager_with_roles.py

import logging
from typing import Dict, Any, List
from datetime import datetime
import pytz

from src.api.client_async import LyzrAPIClient

logger = logging.getLogger("create-manager-with-roles")


# -----------------------------
# Validation
# -----------------------------
def _validate_manager(manager: Dict[str, Any]) -> None:
    if not isinstance(manager, dict):
        raise ValueError("Manager JSON must be a dict")

    required_fields = ["name", "agent_role", "agent_goal", "agent_instructions"]
    for field in required_fields:
        if field not in manager or not manager[field]:
            raise ValueError(f"Manager JSON must include '{field}'")


def _validate_role(role: Dict[str, Any]) -> None:
    if not isinstance(role, dict):
        raise ValueError("Role JSON must be a dict")

    required_fields = ["name", "agent_role", "agent_goal", "agent_instructions"]
    for field in required_fields:
        if field not in role or not role[field]:
            raise ValueError(f"Role JSON must include '{field}'")


# -----------------------------
# Create Manager with Roles
# -----------------------------
async def create_manager_with_roles(
    client: LyzrAPIClient,
    manager_json: Dict[str, Any],
    roles_json: List[Dict[str, Any]],
    tz_name: str = "UTC"
) -> Dict[str, Any]:
    """
    Create a manager agent, link roles, and perform final rename with preserved instructions.
    """

    _validate_manager(manager_json)
    for role in roles_json:
        _validate_role(role)

    logger.info(f"🚀 Creating manager: {manager_json['name']}")
    manager = await client.create_agent(manager_json)
    manager_id = manager["id"]

    # Cache original manager JSON so we can re-use later
    cached_manager_json = manager_json.copy()

    # Create and link each role
    for role_json in roles_json:
        logger.info(f"👷 Creating role: {role_json['name']}")
        role = await client.create_agent(role_json)
        role_id = role["id"]

        await client.link_agents(manager_id, role_id)
        logger.info(f"🔗 Linked role {role_json['name']} → manager {manager_json['name']}")

    # Final rename step: re-pass full JSON payload
    short_id = manager_id[-6:]
    now = datetime.now(pytz.timezone(tz_name))
    timestamp = now.strftime("%d%b%Y-%I:%M%p %Z")

    final_name = f"{cached_manager_json['name']}_v1.0_{short_id}_{timestamp}"

    final_payload = {
        **cached_manager_json,   # keep original instructions, examples, etc.
        "name": final_name       # override only the name
    }

    logger.info(f"✏️ Final manager rename → {final_name}")
    await client.update_agent(manager_id, final_payload)

    logger.info("✅ Manager + roles created, linked, and renamed successfully")

    return {
        "manager": final_payload,
        "roles": roles_json,
        "manager_id": manager_id,
        "agent_id": manager_id  # alias for frontend
    }
