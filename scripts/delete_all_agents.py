import argparse
from src.services.agent_manager import AgentManager
from src.api.client import LyzrAPIClient


def main(dry_run: bool):
    # Initialize client with debug=True
    client = LyzrAPIClient(debug=True)
    manager = AgentManager(client=client)

    print("📋 Fetching all agents from Lyzr...")
    resp = client.get("/v3/agents/")

    # Handle both possible response formats
    if isinstance(resp, dict) and "data" in resp:
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
        if dry_run:
            print(f"🟡 DRY RUN → Would delete {name} ({agent_id})")
        else:
            print(f"🗑️ Deleting {name} ({agent_id}) ...")
            result = client.delete(f"/v3/agents/{agent_id}")
            if isinstance(result, dict) and result.get("ok"):
                print(f"✅ Deleted {name} ({agent_id})")
            else:
                print(f"❌ Failed to delete {name} ({agent_id}) → {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete all Lyzr agents")
    parser.add_argument("--dry-run", action="store_true", help="Preview deletions without deleting")
    args = parser.parse_args()

    main(dry_run=args.dry_run)
