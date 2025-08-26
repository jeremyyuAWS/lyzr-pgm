import argparse
import json
from src.services.agent_manager import AgentManager

def main():
    parser = argparse.ArgumentParser(description="List all agents")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    manager = AgentManager(debug=args.debug)
    agents = manager.list_agents()

    print("📋 Agents:")
    print(json.dumps(agents, indent=2))

if __name__ == "__main__":
    main()
