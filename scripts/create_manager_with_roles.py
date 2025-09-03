import logging
from typing import Dict, Any, List
from datetime import datetime
import pytz

from src.api.client_async import LyzrAPIClient

logger = logging.getLogger("create-manager-with-roles")

# -----------------------------
# Timezone / naming helpers
# -----------------------------
def _tz() -> pytz.timezone:
    tz_name = os.getenv("APP_TZ", "America/Los_Angeles")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone("America/Los_Angeles")

def _timestamp_str() -> str:
    # Example: 03SEP2025-04:37PM PDT
    now = datetime.now(_tz())
    return now.strftime("%d%b%Y-%I:%M%p %Z").upper()

def _suffix_from_id(agent_id: str) -> str:
    return (agent_id or "")[-6:] or "XXXXXX"

def _rich_manager_name(base: str, agent_id: str) -> str:
    return f"{base}_v1.0_{_suffix_from_id(agent_id)}_{_timestamp_str()}"

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
# Main entrypoint
# -----------------------------
async def create_manager_with_roles(
    client: LyzrAPIClient,
    manager_json: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create a manager agent and its role agents using JSON only.
    Roles are linked back to the manager via PUT, then the manager is renamed with a suffix + timestamp.
    """

    logger.info("📦 Using provided JSON dict for manager + roles")

    # -----------------------------
    # Create manager first
    # -----------------------------
    _validate_manager(manager_json)
    logger.info(f"🚀 Creating manager: {manager_json['name']}")

    mgr_resp = await client.create_agent(manager_json)
    if not mgr_resp.get("ok"):
        raise RuntimeError(f"❌ Manager creation failed: {mgr_resp}")

    manager_data = mgr_resp["data"]
    manager_id = manager_data.get("_id") or manager_data.get("agent_id")
    if not manager_id:
        raise RuntimeError(f"❌ Manager response missing agent_id: {mgr_resp}")

    results: Dict[str, Any] = {
        "manager": manager_data,
        "roles": [],
        "manager_id": manager_id,
    }

    # -----------------------------
    # Create roles and attach via PUT
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

        # Link role → manager (PUT)
        link_resp = await client.link_agents(manager_id, role_id, role.get("name"))
        if link_resp.get("ok"):
            logger.info(f"🔗 Linked role {role['name']} → manager {manager_json['name']}")
        else:
            logger.warning(f"⚠️ Failed to link role {role['name']} → manager {manager_json['name']}: {link_resp}")

        results["roles"].append(role_data)

    # -----------------------------
    # Rename manager with suffix + timestamp
    # -----------------------------
    manager_base_name = manager_json.get("name", "MANAGER")
    manager_renamed = _rich_manager_name(manager_base_name, manager_id)

    upd_resp = await client.put(
        f"/v3/agents/{manager_id}",
        {"name": manager_renamed}
    )
    if upd_resp.get("ok"):
        logger.info(f"✏️ Renamed manager → {manager_renamed}")
        results["manager"]["name"] = manager_renamed
    else:
        logger.warning(f"⚠️ Failed to rename manager {manager_base_name}: {upd_resp}")

    results["timestamp"] = _timestamp_str()

    logger.info("✅ Manager + roles created, linked, and renamed successfully")
    return results
