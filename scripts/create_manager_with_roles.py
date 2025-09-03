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
    Create a manager agent and optionally link role agents.

    If roles_json is empty/None → only manager will be created.
    """
    logger.info(f"🚀 Creating manager agent: {manager_json.get('name')}")

    # Create the manager
    manager = await client.create_agent(manager_json)

    if not roles_json:
        logger.info("ℹ️ No roles_json provided, returning manager only.")
        return {"manager": manager, "roles": []}

    created_roles = []
    for role in roles_json:
        logger.info(f"➕ Creating role agent: {role.get('name')}")
        role_agent = await client.create_agent(role)

        logger.info(f"🔗 Linking role '{role_agent['name']}' to manager '{manager['name']}'")
        await client.link_agents(manager["id"], role_agent["id"], rename_manager=False)

        created_roles.append(role_agent)

    # Final rename only after all roles linked
    manager = await client.rename_manager(manager["id"])

    return {"manager": manager, "roles": created_roles}
