import argparse
from src.services.agent_manager import AgentManager

def main(dry_run: bool):
    manager = AgentManager(debug=True)

    print("📋 Fetching all agents from Lyzr...")
    resp = manager.list_agents()

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
            result = manager.delete_agent(agent_id)

            # ✅ Handle different response formats
            if isinstance(result, dict):
                if result.get("message") == "Agent deleted successfully":
                    print(f"✅ Deleted {name} ({agent_id})")
                elif result.get("ok") and result.get("status") == 200:
                    print(f"✅ Deleted {name} ({agent_id})")
                else:
                    print(f"❌ Failed to delete {name} ({agent_id}) → {result}")
            else:
                print(f"❌ Unexpected delete response for {name} ({agent_id}): {result}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete all Lyzr agents")
    parser.add_argument("--dry-run", action="store_true", help="Preview deletions without deleting")
    args = parser.parse_args()

    main(dry_run=args.dry_run)
