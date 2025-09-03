# scripts/delete_all_agents.py

import argparse
import asyncio
import logging
import os
from dotenv import load_dotenv

from src.api.client_async import LyzrAPIClient

# Load environment variables from .env
load_dotenv()

logger = logging.getLogger("delete-all-agents")


async def main(dry_run: bool):
    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    api_key = os.getenv("LYZR_API_KEY")

    if not api_key:
        print("❌ Missing LYZR_API_KEY in environment. Add it to your .env file.")
        return

    async with LyzrAPIClient(base_url=base_url, api_key=api_key) as client:
        print(f"📋 Fetching all agents from Lyzr Studio at {base_url} ...")
        resp = await client.get("/v3/agents/")

        # Normalize response
        if isinstance(resp, dict) and "data" in resp:
            agents = resp["data"]
        elif isinstance(resp, dict) and "ok" in resp and isinstance(resp.get("data"), list):
            agents = resp["data"]
        elif isinstance(resp, list):
            agents = resp
        else:
            print(f"❌ Unexpected response format: {resp}")
            return

        if not agents:
            print("⚠️ No agents found.")
            return

        print(f"🔎 Found {len(agents)} agents")

        for agent in agents:
            agent_id = agent.get("_id") or agent.get("agent_id")
            name = agent.get("name", "unknown")

            if not agent_id:
                print(f"⚠️ Skipping {name} (no id found)")
                continue

            if dry_run:
                print(f"🟡 DRY RUN → Would delete {name} ({agent_id})")
            else:
                print(f"🗑️ Deleting {name} ({agent_id}) ...")
                result = await client._client.delete(
                    f"{client.base_url}/v3/agents/{agent_id}",  # 👈 NO trailing slash
                    headers=client._headers(),
                )
                if result.status_code in (200, 202, 204):
                    print(f"✅ Deleted {name} ({agent_id})")
                else:
                    try:
                        detail = result.json()
                    except Exception:
                        detail = result.text
                    print(f"❌ Failed to delete {name} ({agent_id}) → {detail}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete all Lyzr agents from Studio")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview deletions without actually deleting"
    )
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
