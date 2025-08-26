import argparse
from src.services.agent_manager import AgentManager

def main():
    parser = argparse.ArgumentParser(description="Create a Manager Agent from YAML definition")
    parser.add_argument("yaml_file", help="Path to manager agent YAML file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    manager = AgentManager(debug=args.debug)
    resp = manager.create_agent(args.yaml_file)

    print("✅ Created Manager Agent")
    print(resp)

if __name__ == "__main__":
    main()
