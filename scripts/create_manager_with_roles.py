# scripts/create_manager_with_roles.py

import logging
from typing import Dict, Any, List

from src.api.client_async import LyzrAPIClient

logger = logging.getLogger("create-manager-with-roles")

# -----------------------------
# Validation
# -----------------------------
def _validate_manager(manager: Dict[str, Any]) -> None:
    """Validate manager definition."""
    if not isinstance(manager, dict):
        raise ValueError("Manager JSON must be a dict")

    required_fields = ["name", "agent_role", "agent_goal", "agent_instructions"]
    for field in required_fields:
        if field not in manager or not manager[field]:
            raise ValueError(f"Manager JSON must include '{field}'")


def _validate_role(role: Dict[str, Any]) -> None:
    """Validate role definition."""
    if not isinstance(role, dict):
        raise ValueError("Role JSON must be a dict")

    required_fields = ["name", "agent_role", "agent_goal", "agent_instructions"]
    for field in required_fields:
        if field not in role or not role[field]:
            raise ValueError(f"Role JSON must include '{field}'")


# -----------------------------
# Main entrypoint
# -----------------------------
async def create_manager_with_roles(
    client: LyzrAPIClient,
    manager_json: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a manager agent and its role agents using JSON only.

    manager_json must be shaped like:
    {
      "name": "...",
      "description": "...",
      "agent_role": "...",
      "agent_goal": "...",
      "agent_instructions": "...",
      "tz_name": "...",              # Optional
      "managed_agents": [ { role_json }, ... ]
    }

    Returns:
        {
          "manager": <manager_result["data"]>,
          "roles": [ <role_result["data"]>, ... ]
        }
    """

    logger.info("📦 Using provided JSON dict for manager + roles")

    # -----------------------------
    # Create manager
    # -----------------------------
    _validate_manager(manager_json)
    logger.info(f"🚀 Creating manager: {manager_json['name']}")

    mgr_payload = manager_json.copy()
    if "tz_name" in manager_json:
        logger.info(f"🌍 Attaching tz_name='{manager_json['tz_name']}'")
        mgr_payload["tz_name"] = manager_json["tz_name"]

    mgr_resp = await client.create_agent(mgr_payload)
    if not mgr_resp.get("ok"):
        raise RuntimeError(f"❌ Manager creation failed: {mgr_resp}")

    manager_data = mgr_resp["data"]
    manager_id = manager_data.get("_id") or manager_data.get("agent_id")
    if not manager_id:
        raise RuntimeError(f"❌ Manager response missing agent_id: {mgr_resp}")

    results: Dict[str, Any] = {"manager": manager_data, "roles": []}

    # -----------------------------
    # Create and link roles
    # -----------------------------
    roles: List[Dict[str, Any]] = manager_json.get("managed_agents", [])
    for role in roles:
        _validate_role(role)

        logger.info(f"👷 Creating role: {role['name']}")
        role_resp = await client.create_agent(role)
        if not role_resp.get("ok"):
            raise RuntimeError(f"❌ Role creation failed: {role_resp}")

        role_data = role_resp["data"]
        role_id = role_data.get("_id") or role_data.get("agent_id")
        if not role_id:
            raise RuntimeError(f"❌ Role response missing agent_id: {role_resp}")

        # Link role → manager
        try:
            link_resp = await client.link_agents(manager_id, role_id)
            if link_resp.get("ok"):
                logger.info(f"🔗 Linked role {role['name']} → manager {manager_json['name']}")
            else:
                logger.warning(f"⚠️ Link failed: {link_resp}")
        except Exception as e:
            logger.error(f"⚠️ Exception linking role {role['name']} to manager {manager_json['name']}: {e}")

        results["roles"].append(role_data)

    logger.info("✅ Manager + roles created successfully")
    return results
