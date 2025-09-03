import logging
from typing import Dict, Any, List, Optional

from src.api.client_async import LyzrAPIClient

logger = logging.getLogger("create-manager-with-roles")


async def create_manager_with_roles(
    client: LyzrAPIClient,
    manager_json: Dict[str, Any],
    roles_json: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Create role agent(s), then a manager agent, link them together, and return the full result.

    Flow:
    1. Create role agent(s) first (if roles_json is provided)
    2. Create manager agent
    3. Link roles to manager (if any)
    4. Always rename manager once at the end
    """
    created_roles: List[Dict[str, Any]] = []

    # 1) Create role agents first
    if roles_json and len(roles_json) > 0:
        for role in roles_json:
            logger.info(f"➕ Creating role agent: {role.get('name')}")
            role_agent = await client.create_agent(role)
            created_roles.append(role_agent)
    elif manager_json.get("managed_agents"):
        logger.info("📎 Manager JSON already includes managed_agents, skipping role creation.")
    else:
        logger.info("ℹ️ No roles provided, will create manager only.")

    # 2) Create manager agent
    logger.info(f"🚀 Creating manager agent: {manager_json.get('name')}")
    manager = await client.create_agent(manager_json)

    # 3) Link roles to manager
    if created_roles:
        for role_agent in created_roles:
            logger.info(
                f"🔗 Linking role '{role_agent['name']}' to manager '{manager['name']}'"
            )
            await client.link_agents(manager["id"], role_agent["id"], rename_manager=False)

    # 4) Always rename manager (even if no roles were provided)
    logger.info(f"✨ Renaming manager '{manager['name']}' (final step)")
    manager = await client.rename_manager(manager["id"])

    return {"manager": manager, "roles": created_roles}
