import logging
from typing import Dict, Any, List, Optional

from src.api.client_async import LyzrAPIClient, _rich_manager_name

logger = logging.getLogger("create-manager-with-roles")


def _extract_roles(manager_json: Dict[str, Any], roles_json: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Choose role definitions from roles_json if provided,
    otherwise fall back to manager_json['managed_agents'].
    """
    if roles_json and len(roles_json) > 0:
        logger.info("📦 Using roles from roles_json")
        return roles_json
    elif manager_json.get("managed_agents"):
        logger.info("📦 Using roles from manager_json['managed_agents']")
        return manager_json["managed_agents"]
    else:
        logger.info("ℹ️ No role agents provided")
        return []


async def create_manager_with_roles(
    client: LyzrAPIClient,
    manager_json: Dict[str, Any],
    roles_json: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Create role agent(s) (from roles_json or manager_json.managed_agents),
    create the manager, link roles, then update the manager once with:
      - Rich name convention (original + v1.0 + suffix + timestamp)
      - All original fields preserved (description, instructions, examples, etc.)
      - Managed_agents explicitly set to linked role agents
    """
    created_roles: List[Dict[str, Any]] = []

    # 1) Extract role definitions
    role_defs = _extract_roles(manager_json, roles_json)

    # 2) Create role agents first
    for role in role_defs:
        logger.info(f"➕ Creating role agent: {role.get('name')}")
        role_agent = await client.create_agent(role)
        created_roles.append(role_agent)

    # 3) Create manager agent
    logger.info(f"🚀 Creating manager agent: {manager_json.get('name')}")
    manager = await client.create_agent(manager_json)

    # 4) Link roles to manager (server-side association only)
    if created_roles:
        for role_agent in created_roles:
            logger.info(
                f"🔗 Linking role '{role_agent.get('name')}' to manager '{manager.get('name', manager.get('id'))}'"
            )
            await client.link_agents(manager["id"], role_agent["id"], rename_manager=False)

    # 5) Build final enriched manager payload
    try:
        logger.info(f"✨ Updating manager '{manager.get('id')}' with rich name and all details")

        enriched_name = _rich_manager_name(manager.get("name"), manager["id"])

        # Always include original manager fields to avoid data loss
        final_payload = {
            **manager,
            "name": enriched_name,
            "managed_agents": created_roles,  # explicitly attach role agents
        }

        # 6) PUT update to Studio
        updated = await client.update_agent(manager["id"], final_payload)

        manager = updated

    except Exception as e:
        logger.error(f"❌ Failed to fully update manager {manager.get('id')}: {e}")

    return {"manager": manager, "roles": created_roles}
