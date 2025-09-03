# scripts/create_manager_with_roles.py

import argparse
import asyncio
import logging
import json
from pathlib import Path

from src.api.client_async import LyzrAPIClient
from src.utils.payload_normalizer import normalize_payload

logger = logging.getLogger("create-manager-with-roles")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)

# -----------------------------
# Helpers
# -----------------------------
def load_json_file(path: Path) -> dict:
    """Load and parse a JSON file safely."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"❌ Failed to load JSON from {path}: {e}")
        raise


# -----------------------------
# Core Orchestration
# -----------------------------
async def create_manager_with_roles(manager_path: Path, tz_name: str = "America/Los_Angeles"):
    """
    Create manager + role agents from JSON file and update manager with roles.
    Ensures full payload PUT updates to prevent data loss.
    """
    manager_def = load_json_file(manager_path)

    async with LyzrAPIClient() as client:
        # 1. Create role agents first
        created_roles = []
        for entry in manager_def.get("managed_agents", []):
            try:
                role_payload = normalize_payload(entry)
                logger.info(f"📥 Creating Role Agent: {role_payload.get('name')}")
                role_resp = await client.create_agent(role_payload)
                if role_resp.get("ok"):
                    created_roles.append(role_resp["data"])
                    logger.info(f"✅ Created Role: {role_payload.get('name')} ({role_resp['data'].get('id')})")
                else:
                    logger.error(f"❌ Failed to create role: {role_resp}")
            except Exception as e:
                logger.error(f"❌ Exception creating role: {e}")

        # 2. Create manager agent
        logger.info(f"📥 Creating Manager Agent: {manager_def.get('name')}")
        manager_payload = normalize_payload(manager_def)
        mgr_resp = await client.create_agent(manager_payload)

        if not mgr_resp.get("ok"):
            logger.error(f"❌ Manager creation failed: {mgr_resp}")
            return {"ok": False, "error": mgr_resp.get("error"), "roles": created_roles}

        manager = mgr_resp["data"]
        logger.info(f"✅ Created Manager: {manager.get('name')} ({manager.get('id')})")

        # 3. Re-fetch and update manager with roles
        if created_roles:
            mgr_fetched = await client.get(f"/v3/agents/{manager['id']}")
            if not mgr_fetched.get("ok"):
                return {"ok": False, "error": f"Failed to fetch manager: {mgr_fetched}"}

            manager_data = mgr_fetched["data"]
            manager_data["managed_agents"] = (manager_data.get("managed_agents") or []) + created_roles

            # Always rename manager on final update
            from src.api.client_async import _rich_manager_name, _timestamp_str
            manager_data["name"] = _rich_manager_name(manager_data["name"], manager["id"])

            logger.info(f"🔄 Final Manager Update: {manager_data['name']} with {len(created_roles)} roles")
            upd_resp = await client.update_agent(manager["id"], manager_data)
            if upd_resp.get("ok"):
                manager = upd_resp["data"]
                logger.info(f"✅ Manager Updated: {manager['name']} ({manager['id']})")

        return {"ok": True, "manager": manager, "roles": created_roles, "timestamp": _timestamp_str()}


# -----------------------------
# CLI Entry
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Create Manager + Role agents from JSON")
    parser.add_argument("json_file", type=str, help="Path to JSON file defining manager and roles")
    parser.add_argument("--tz", type=str, default="America/Los_Angeles", help="Timezone for renaming")
    args = parser.parse_args()

    manager_path = Path(args.json_file)
    result = asyncio.run(create_manager_with_roles(manager_path, tz_name=args.tz))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
